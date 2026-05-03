// src/etw/consumer.rs
//
// Phase 3a change:
//   EtwHandles gains a last_event_times field — a shared map of
//   provider name → Instant of last event received. main.rs reads
//   this every 60 seconds. If any provider has been silent for >60s
//   while the system is active, the heartbeat monitor fires an alert.
//   This catches ETW tampering (T1562) and session crashes.
//
// All other logic unchanged from Phase 3.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::Instant;
use tokio::sync::mpsc;
use tracing::{info, warn};

use ferrisetw::EventRecord;
use ferrisetw::schema_locator::SchemaLocator;
use ferrisetw::parser::Parser;
use ferrisetw::provider::Provider;
use ferrisetw::trace::UserTrace;

use crate::state::AegisState;
use crate::ipc::protocol::Finding;
use crate::agents::base::{AgentReport, severity_to_threat};

use super::providers::{
    KERNEL_PROCESS_GUID, DNS_CLIENT_GUID, SECURITY_AUDITING_GUID,
    kernel_process, dns_client, security_auditing,
    SUSPICIOUS_IMAGE_PATHS, SUSPICIOUS_CMDLINE_FRAGMENTS, SUSPICIOUS_DNS_PATTERNS,
};

// Shared last-event timestamp map type
pub type EventTimesMap = Arc<Mutex<HashMap<String, Instant>>>;

// ── Trace handle store ────────────────────────────────────────────────────────

pub struct EtwHandles {
    _kernel_process:    Option<UserTrace>,
    _dns_client:        Option<UserTrace>,
    _security_auditing: Option<UserTrace>,
    /// Shared map of provider → last event time.
    /// main.rs reads this for heartbeat monitoring.
    pub last_event_times: EventTimesMap,
}

// ── Entry point ───────────────────────────────────────────────────────────────

pub fn start_etw_consumers(
    _state:    Arc<tokio::sync::Mutex<AegisState>>,
    report_tx: mpsc::UnboundedSender<AgentReport>,
) -> EtwHandles {
    // Shared timestamp map — seeded with current time so providers that
    // fail to start don't immediately trigger a false heartbeat alert.
    let times: EventTimesMap = Arc::new(Mutex::new({
        let mut m = HashMap::new();
        m.insert("kernel_process".to_string(),    Instant::now());
        m.insert("dns_client".to_string(),        Instant::now());
        m.insert("security_auditing".to_string(), Instant::now());
        m
    }));

    let kernel_handle = {
        let tx   = report_tx.clone();
        let ts   = Arc::clone(&times);
        match build_kernel_process_trace(tx, ts) {
            Ok(t)  => { info!("ETW: Microsoft-Windows-Kernel-Process active"); Some(t) }
            Err(e) => { warn!("ETW: Kernel-Process failed (need admin?): {}", e); None }
        }
    };

    let dns_handle = {
        let tx   = report_tx.clone();
        let ts   = Arc::clone(&times);
        match build_dns_trace(tx, ts) {
            Ok(t)  => { info!("ETW: Microsoft-Windows-DNS-Client active"); Some(t) }
            Err(e) => { warn!("ETW: DNS-Client failed: {}", e); None }
        }
    };

    let security_handle = {
        let tx   = report_tx.clone();
        let ts   = Arc::clone(&times);
        match build_security_auditing_trace(tx, ts) {
            Ok(t)  => { info!("ETW: Microsoft-Windows-Security-Auditing active"); Some(t) }
            Err(e) => { warn!("ETW: Security-Auditing failed: {}", e); None }
        }
    };

    EtwHandles {
        _kernel_process:    kernel_handle,
        _dns_client:        dns_handle,
        _security_auditing: security_handle,
        last_event_times:   times,
    }
}

// ── Kernel-Process ────────────────────────────────────────────────────────────

fn build_kernel_process_trace(
    tx: mpsc::UnboundedSender<AgentReport>,
    times: EventTimesMap,
) -> anyhow::Result<UserTrace> {

    let provider = Provider::by_guid(KERNEL_PROCESS_GUID)
        .add_callback(move |record: &EventRecord, schema_locator: &SchemaLocator| {
            // Update heartbeat timestamp on every event received
            if let Ok(mut t) = times.lock() {
                t.insert("kernel_process".to_string(), Instant::now());
            }

            let event_id = record.event_id();

            if event_id != kernel_process::EVENT_PROCESS_START
                && event_id != kernel_process::EVENT_IMAGE_LOAD {
                return;
            }

            let Ok(schema) = schema_locator.event_schema(record) else { return };
            let parser = Parser::create(record, &schema);

            if event_id == kernel_process::EVENT_PROCESS_START {
                let pid:        u32    = parser.try_parse("ProcessID").unwrap_or(0);
                let parent_pid: u32    = parser.try_parse("ParentProcessID").unwrap_or(0);
                let image:      String = parser.try_parse("ImageFileName").unwrap_or_default();
                let cmdline:    String = parser.try_parse("CommandLine").unwrap_or_default();
                let img_low             = image.to_lowercase();
                let cmd_low             = cmdline.to_lowercase();

                let mut findings = Vec::new();

                for &sus in SUSPICIOUS_IMAGE_PATHS {
                    if img_low.contains(sus) {
                        findings.push(Finding {
                            finding_type: "etw_suspicious_process_image".to_string(),
                            severity:     0.8,
                            detail: format!(
                                "ETW: Suspicious process: {} (PID {} ← PID {})",
                                image, pid, parent_pid
                            ),
                            data: serde_json::json!({
                                "pid": pid, "parent_pid": parent_pid,
                                "image": image, "cmdline": cmdline, "matched": sus,
                            }),
                        });
                        break;
                    }
                }

                for &frag in SUSPICIOUS_CMDLINE_FRAGMENTS {
                    if cmd_low.contains(frag) {
                        findings.push(Finding {
                            finding_type: "etw_suspicious_cmdline".to_string(),
                            severity:     0.85,
                            detail: format!(
                                "ETW: Suspicious cmdline PID {}: {}",
                                pid, &cmdline[..cmdline.len().min(150)]
                            ),
                            data: serde_json::json!({
                                "pid": pid, "cmdline": cmdline, "matched": frag,
                            }),
                        });
                        break;
                    }
                }

                if !findings.is_empty() {
                    push_findings(&tx, "etw_kernel_process", findings);
                }
            }

            if event_id == kernel_process::EVENT_IMAGE_LOAD {
                let pid:   u32    = parser.try_parse("ProcessID").unwrap_or(0);
                let image: String = parser.try_parse("ImageName").unwrap_or_default();
                let lower         = image.to_lowercase();

                let suspicious = lower.contains("\\temp\\")
                    || lower.contains("\\downloads\\")
                    || lower.contains("\\appdata\\local\\temp\\");

                if suspicious {
                    push_findings(&tx, "etw_kernel_process", vec![Finding {
                        finding_type: "etw_suspicious_dll_load".to_string(),
                        severity:     0.7,
                        detail: format!("ETW: DLL from suspicious path PID {}: {}", pid, image),
                        data: serde_json::json!({ "pid": pid, "image": image }),
                    }]);
                }
            }
        })
        .build();

    Ok(UserTrace::new()
        .named(String::from("aegis_kernel_process"))
        .enable(provider)
        .start_and_process()
        .map_err(|e| anyhow::anyhow!("ETW trace failed: {:?}", e))?)
}

// ── DNS-Client ────────────────────────────────────────────────────────────────

fn build_dns_trace(
    tx:    mpsc::UnboundedSender<AgentReport>,
    times: EventTimesMap,
) -> anyhow::Result<UserTrace> {

    let provider = Provider::by_guid(DNS_CLIENT_GUID)
        .add_callback(move |record: &EventRecord, schema_locator: &SchemaLocator| {
            if let Ok(mut t) = times.lock() {
                t.insert("dns_client".to_string(), Instant::now());
            }

            if record.event_id() != dns_client::EVENT_DNS_QUERY { return }

            let Ok(schema) = schema_locator.event_schema(record) else { return };
            let parser = Parser::create(record, &schema);

            let name:    String = parser.try_parse("QueryName").unwrap_or_default();
            let status:  u32    = parser.try_parse("QueryStatus").unwrap_or(0);
            let results: String = parser.try_parse("QueryResults").unwrap_or_default();
            let lower           = name.to_lowercase();

            for &pattern in SUSPICIOUS_DNS_PATTERNS {
                if lower.contains(pattern) {
                    push_findings(&tx, "etw_dns_client", vec![Finding {
                        finding_type: "etw_suspicious_dns_query".to_string(),
                        severity:     0.75,
                        detail: format!(
                            "ETW: Suspicious DNS: {} → {} (status {})",
                            name, &results[..results.len().min(80)], status
                        ),
                        data: serde_json::json!({
                            "query_name": name, "query_status": status,
                            "query_results": results, "matched": pattern,
                        }),
                    }]);
                    break;
                }
            }
        })
        .build();

    Ok(UserTrace::new()
        .named(String::from("aegis_dns_client"))
        .enable(provider)
        .start_and_process()
        .map_err(|e| anyhow::anyhow!("ETW trace failed: {:?}", e))?)
}

// ── Security-Auditing ─────────────────────────────────────────────────────────

fn build_security_auditing_trace(
    tx:    mpsc::UnboundedSender<AgentReport>,
    times: EventTimesMap,
) -> anyhow::Result<UserTrace> {

    let provider = Provider::by_guid(SECURITY_AUDITING_GUID)
        .add_callback(move |record: &EventRecord, _: &SchemaLocator| {
            if let Ok(mut t) = times.lock() {
                t.insert("security_auditing".to_string(), Instant::now());
            }

            let event_id = record.event_id();
            let (ftype, sev, detail) = match event_id {
                e if e == security_auditing::EVENT_LOGON_FAILURE =>
                    ("etw_logon_failure",  0.5_f32,  "ETW: Authentication failure".to_string()),
                e if e == security_auditing::EVENT_SPECIAL_LOGON =>
                    ("etw_special_logon",  0.6_f32,  "ETW: Special privileges assigned to logon".to_string()),
                e if e == security_auditing::EVENT_ACCOUNT_LOCKED =>
                    ("etw_account_locked", 0.75_f32, "ETW: Account lockout — possible brute force".to_string()),
                _ => return,
            };
            push_findings(&tx, "etw_security_auditing", vec![Finding {
                finding_type: ftype.to_string(),
                severity:     sev,
                detail,
                data: serde_json::json!({ "event_id": event_id }),
            }]);
        })
        .build();

    Ok(UserTrace::new()
        .named(String::from("aegis_security_auditing"))
        .enable(provider)
        .start_and_process()
        .map_err(|e| anyhow::anyhow!("ETW trace failed: {:?}", e))?)
}

// ── Helper ────────────────────────────────────────────────────────────────────

fn push_findings(
    tx:       &mpsc::UnboundedSender<AgentReport>,
    agent_id: &str,
    findings: Vec<Finding>,
) {
    if findings.is_empty() { return; }
    let max_sev = findings.iter().map(|f| f.severity).fold(0.0_f32, f32::max);
    let _ = tx.send(AgentReport {
        agent_id:     agent_id.to_string(),
        threat_level: severity_to_threat(max_sev),
        findings,
    });
}
