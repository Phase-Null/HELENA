// src/firewall/responder.rs
//
// Phase 3a addition:
//   block_port_external_only() — blocks inbound access to a specific port
//   from all addresses EXCEPT loopback (127.0.0.1). Used by main.rs to
//   protect the AEGIS IPC port (47201) at startup. Only HELENA running
//   locally can connect. External processes are blocked at the WFP layer.
//
// Also: tier_for_severity thresholds raised slightly:
//   CONTAIN now requires >= 0.65 (was 0.5) — reduces false positive blocks
//   HARDEN  now requires >= 0.85 (was 0.7)
// This prevents the correlation boost on unknown processes from
// automatically triggering IP blocks on legitimate software.
//
// All other logic unchanged from Phase 3.

use chrono::Utc;
use tracing::{info, warn};
use uuid::Uuid;

use crate::ipc::protocol::{Finding, ResponseTier};
use crate::agents::base::AgentReport;
use crate::state::{AegisState, ResponsePackage, PlannedAction};

use super::engine::FirewallEngine;
use super::rules::{RuleSet, block_ip, block_inbound_port, summary, cleanup_netsh_rules};

pub struct Responder {
    engine: FirewallEngine,
    rules:  RuleSet,
}

impl Responder {
    pub fn new(engine: FirewallEngine) -> Self {
        Self {
            engine,
            rules: RuleSet::new(),
        }
    }

    pub fn respond(
        &mut self,
        report: &AgentReport,
        state:  &mut AegisState,
    ) -> Vec<String> {
        let mut log = Vec::new();
        for finding in &report.findings {
            if let Some(action) = self.handle_finding(finding, &report.agent_id, state) {
                log.push(action);
            }
        }
        log
    }

    pub fn execute_approved(&mut self, state: &mut AegisState) {
        for pkg in state.take_approved() {
            info!(
                "Executing approved response {} (reason: {})",
                pkg.package_id,
                pkg.reason_code.as_deref().unwrap_or("none given")
            );
            for action in &pkg.actions {
                self.run_planned_action(action);
            }
        }
    }

    pub fn firewall_summary(&self) -> String {
        summary(&self.rules)
    }

    pub fn cleanup(&self) {
        cleanup_netsh_rules(&self.rules);
    }

    /// Block inbound connections to a port from all non-loopback addresses.
    /// Used at startup to protect the AEGIS IPC port (47201).
    /// Loopback (127.0.0.1) connections remain allowed — only HELENA
    /// running locally should ever connect to this port.
    pub fn block_port_external_only(
        &mut self,
        port:   u16,
        reason: &str,
    ) -> anyhow::Result<()> {
        // WFP filters are evaluated in order within a sublayer.
        // We add a PERMIT rule for loopback first (higher weight),
        // then a BLOCK rule for everything else (lower weight).
        // The permit wins for loopback, block wins for everything else.
        self.engine.add_loopback_permit(port)?;
        block_inbound_port(&mut self.engine, &self.rules, port, reason)?;
        Ok(())
    }

    // ── Internal ──────────────────────────────────────────────────────────────

    fn handle_finding(
        &mut self,
        finding:  &Finding,
        agent_id: &str,
        state:    &mut AegisState,
    ) -> Option<String> {
        let tier = tier_for_severity(finding.severity);

        match tier {
            ResponseTier::Monitor | ResponseTier::Alert => None,

            ResponseTier::Contain => {
                let ip = extract_ip(finding)?;
                if self.rules.is_ip_blocked(&ip) { return None; }

                match block_ip(&self.rules, &ip, &finding.detail) {
                    Ok(())  => Some(format!("CONTAIN: blocked {}", ip)),
                    Err(e)  => { warn!("block_ip failed: {}", e); None }
                }
            }

            ResponseTier::Harden => {
                let mut parts = Vec::new();

                if let Some(ip) = extract_ip(finding) {
                    if !self.rules.is_ip_blocked(&ip) {
                        match block_ip(&self.rules, &ip, &finding.detail) {
                            Ok(())  => parts.push(format!("blocked IP {}", ip)),
                            Err(e)  => warn!("block_ip failed: {}", e),
                        }
                    }
                }

                if let Some(port) = extract_port(finding) {
                    match block_inbound_port(
                        &mut self.engine, &self.rules, port, &finding.detail
                    ) {
                        Ok(())  => parts.push(format!("blocked port {}", port)),
                        Err(e)  => warn!("block_port failed: {}", e),
                    }
                }

                if finding.severity >= 0.9
                    && matches!(
                        finding.finding_type.as_str(),
                        "etw_suspicious_process_image"
                        | "etw_suspicious_cmdline"
                        | "brute_force_attempt"
                        | "privilege_escalation"
                        | "file_modified"
                        | "process_masquerading"
                        | "parent_child_mismatch"
                    )
                {
                    let pkg = build_tier4_package(finding, agent_id);
                    let id  = pkg.package_id.clone();
                    state.add_pending(pkg);
                    parts.push(format!("queued Tier 4 response {} for approval", id));
                }

                if parts.is_empty() { None }
                else { Some(format!("HARDEN: {}", parts.join(", "))) }
            }

            ResponseTier::Retaliate | ResponseTier::Lockdown => None,
        }
    }

    fn run_planned_action(&mut self, action: &PlannedAction) {
        match action.action_type.as_str() {
            "block_ip" => {
                if let Some(ip) = action.params.get("ip").and_then(|v| v.as_str()) {
                    let reason = action.params.get("reason")
                        .and_then(|v| v.as_str())
                        .unwrap_or("operator approved");
                    if let Err(e) = block_ip(&self.rules, ip, reason) {
                        warn!("Approved block_ip failed: {}", e);
                    }
                }
            }
            "block_port" => {
                if let Some(port) = action.params.get("port").and_then(|v| v.as_u64()) {
                    let reason = action.params.get("reason")
                        .and_then(|v| v.as_str())
                        .unwrap_or("operator approved");
                    if let Err(e) = block_inbound_port(
                        &mut self.engine, &self.rules, port as u16, reason
                    ) {
                        warn!("Approved block_port failed: {}", e);
                    }
                }
            }
            other => {
                info!("Approved action '{}' — Phase 4 implementation pending", other);
            }
        }
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/// Raised thresholds from Phase 3 to reduce false positive blocking.
fn tier_for_severity(sev: f32) -> ResponseTier {
    if sev >= 0.85      { ResponseTier::Harden  }
    else if sev >= 0.65 { ResponseTier::Contain }
    else if sev >= 0.3  { ResponseTier::Alert   }
    else                { ResponseTier::Monitor }
}

fn extract_ip(finding: &Finding) -> Option<String> {
    finding.data.get("remote_ip")
        .or_else(|| finding.data.get("source"))
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty() && *s != "unknown" && *s != "-"
            && s.parse::<std::net::Ipv4Addr>().is_ok())
        .map(|s| s.to_string())
}

fn extract_port(finding: &Finding) -> Option<u16> {
    finding.data.get("remote_port")
        .or_else(|| finding.data.get("port"))
        .and_then(|v| v.as_u64())
        .filter(|&p| p > 0 && p <= 65535)
        .map(|p| p as u16)
}

fn build_tier4_package(finding: &Finding, agent_id: &str) -> ResponsePackage {
    let id = Uuid::new_v4().to_string()[..12].to_string();
    ResponsePackage {
        package_id:  id,
        tier:        ResponseTier::Retaliate,
        trigger:     agent_id.to_string(),
        description: format!(
            "Critical finding from {}: {}. \
             Tier 4 options: honeypot, tarpit, deception layer (Phase 4).",
            agent_id,
            &finding.detail[..finding.detail.len().min(100)]
        ),
        actions: vec![PlannedAction {
            action_type: "deploy_honeypot".to_string(),
            params: serde_json::json!({
                "trigger_ip": extract_ip(finding).unwrap_or_default(),
                "detail":     finding.detail,
            }),
        }],
        created_at:  Utc::now(),
        approved:    false,
        approved_by: None,
        approved_at: None,
        reason_code: None,
    }
}
