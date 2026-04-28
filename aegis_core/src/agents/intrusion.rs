// src/agents/intrusion.rs
//
// Type B — Intrusion Detection
//
// Detects signs of active intrusion by monitoring:
//   - Windows Security Event Log (Event IDs 4625, 4672, 4688)
//   - Brute force patterns (5+ failed logins in 5 minutes from same source)
//   - Privilege escalation events
//   - Process creation from suspicious locations
//
// Uses PowerShell to read the Security event log — avoids needing
// the full windows-rs event log API, works without admin rights in
// most configurations.
//
// Four variants:
//   V1 — 8s,  threshold 0.3
//   V2 — 15s, threshold 0.5
//   V3 — 20s, threshold 0.7
//   V4 — 5s,  threshold 0.4

use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

use crate::agents::base::{Agent, AgentConfig};
use crate::ipc::protocol::SharedContext;
use crate::ipc::protocol::Finding;

// ── Brute force tracker ───────────────────────────────────────────────────────

struct FailTracker {
    failures:    HashMap<String, Vec<u64>>,
    window_secs: u64,
    threshold:   usize,
}

impl FailTracker {
    fn new(window_secs: u64, threshold: usize) -> Self {
        Self { failures: HashMap::new(), window_secs, threshold }
    }

    fn record(&mut self, source: &str) -> bool {
        let now    = unix_now();
        let cutoff = now.saturating_sub(self.window_secs);
        let list   = self.failures.entry(source.to_string()).or_default();
        list.retain(|&t| t > cutoff);
        list.push(now);
        list.len() >= self.threshold
    }

    fn count(&self, source: &str) -> usize {
        self.failures.get(source).map(|l| l.len()).unwrap_or(0)
    }
}

fn unix_now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

// ── Agent struct ──────────────────────────────────────────────────────────────

pub struct IntrusionDetection {
    config:       AgentConfig,
    fail_tracker: Mutex<FailTracker>,
    seen_records: Mutex<HashSet<u64>>,
}

impl IntrusionDetection {
    pub fn new(variant: u8, interval_secs: u64, threshold: f32) -> Self {
        Self {
            config:       AgentConfig::new("intrusion_detection", variant, interval_secs, threshold),
            fail_tracker: Mutex::new(FailTracker::new(300, 5)),
            seen_records: Mutex::new(HashSet::new()),
        }
    }

    pub fn v1() -> Self { Self::new(1, 8,  0.3) }
    pub fn v2() -> Self { Self::new(2, 15, 0.5) }
    pub fn v3() -> Self { Self::new(3, 20, 0.7) }
    pub fn v4() -> Self { Self::new(4, 5,  0.4) }
}

impl Agent for IntrusionDetection {
    fn config(&self) -> &AgentConfig { &self.config }

    fn scan(&self, context: &SharedContext) -> Vec<Finding> {
        let mut findings = Vec::new();
        let mut tracker  = self.fail_tracker.lock().unwrap();

        // Read Security event log via PowerShell — works without admin on most configs
        let output = std::process::Command::new("powershell")
            .args([
                "-NoProfile", "-NonInteractive", "-Command",
                r#"Get-WinEvent -LogName Security -MaxEvents 200 2>$null | Where-Object { $_.Id -in @(4625,4672,4688) } | Select-Object Id,Message,RecordId | ConvertTo-Json -Compress 2>$null"#
            ])
            .output();

        let output = match output {
            Ok(o)  => o,
            Err(e) => {
                tracing::debug!("IntrusionDetection: PowerShell unavailable: {}", e);
                return findings;
            }
        };

        let raw = String::from_utf8_lossy(&output.stdout);
        if raw.trim().is_empty() { return findings; }

        // PowerShell returns object or array — normalise to array
        let json_str = if raw.trim_start().starts_with('[') {
            raw.to_string()
        } else {
            format!("[{}]", raw)
        };

        let events: Vec<serde_json::Value> = match serde_json::from_str(&json_str) {
            Ok(v)  => v,
            Err(_) => return findings,
        };

        let mut seen = self.seen_records.lock().unwrap();

        for event in &events {
            let record_id = event["RecordId"].as_u64().unwrap_or(0);
            if seen.contains(&record_id) { continue; }
            seen.insert(record_id);
            if seen.len() > 10_000 { seen.clear(); }

            let event_id = event["Id"].as_u64().unwrap_or(0);
            let message  = event["Message"].as_str().unwrap_or("");

            match event_id {
                // 4625 — Failed login
                4625 => {
                    let source = extract_field(message, "Source Network Address")
                        .unwrap_or_else(|| "unknown".to_string());

                    let is_brute = tracker.record(&source);
                    let count    = tracker.count(&source);
                    let existing = context.ip_severity(&source);
                    let base_sev = if is_brute { 0.8 } else { 0.4 };
                    let severity = (base_sev + existing * 0.15_f32).min(1.0_f32);

                    findings.push(Finding {
                        finding_type: if is_brute {
                            "brute_force_attempt".to_string()
                        } else {
                            "failed_login".to_string()
                        },
                        severity,
                        detail: format!(
                            "{} failed login{} from {} in 5 minutes",
                            count, if count == 1 { "" } else { "s" }, source
                        ),
                        data: serde_json::json!({
                            "source":      source,
                            "count":       count,
                            "brute_force": is_brute,
                            "remote_ip":   source,
                        }),
                    });
                }

                // 4672 — Special privileges assigned (skip SYSTEM/service accounts)
                4672 => {
                    let account = extract_field(message, "Account Name")
                        .unwrap_or_default();
                    let upper = account.to_uppercase();
                    if upper.contains("SYSTEM")
                        || upper.contains("LOCAL SERVICE")
                        || upper.contains("NETWORK SERVICE") { continue; }

                    findings.push(Finding {
                        finding_type: "privilege_escalation".to_string(),
                        severity: 0.7,
                        detail: format!("Special privileges assigned to: {}", account),
                        data: serde_json::json!({ "account": account }),
                    });
                }

                // 4688 — New process created (requires audit policy enabled)
                4688 => {
                    let process = extract_field(message, "New Process Name")
                        .unwrap_or_default()
                        .to_lowercase();

                    let suspicious = process.contains("\\temp\\")
                        || process.contains("\\downloads\\")
                        || process.contains("\\appdata\\local\\temp\\");

                    if suspicious {
                        findings.push(Finding {
                            finding_type: "suspicious_process_creation".to_string(),
                            severity: 0.6,
                            detail: format!("Process from suspicious path: {}", process),
                            data: serde_json::json!({ "process": process }),
                        });
                    }
                }

                _ => {}
            }
        }

        findings
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

fn extract_field(message: &str, field: &str) -> Option<String> {
    let needle = format!("{}:", field);
    let line   = message.lines().find(|l| l.contains(&needle))?;
    let value  = line.split(':').nth(1)?.trim().to_string();
    if value.is_empty() || value == "-" { None } else { Some(value) }
}
