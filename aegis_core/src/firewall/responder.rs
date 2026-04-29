// src/firewall/responder.rs
//
// Response decision engine — maps agent findings to firewall actions.
//
// Tier logic:
//   severity < 0.3:   MONITOR — already handled by dispatch loop, no action here
//   severity 0.3-0.5: ALERT   — HELENA notified, no firewall action
//   severity 0.5-0.7: CONTAIN — auto-block source IP (requires IP in finding data)
//   severity 0.7-0.9: HARDEN  — block IP + block the port being probed
//   severity >= 0.9:  HARDEN  — block IP + port + queue Tier 4 package for operator
//
// IP blocking is automatic for CONTAIN and above.
// Port blocking is automatic for HARDEN and above.
// Tier 4 packages require Phase-Null's explicit approval — the gate already
// exists in state.rs (add_pending/approve_response) and IPC server.rs handles
// the ApproveResponse message from HELENA. Phase 4 will implement the actual
// Tier 4 actions (honeypot, tarpit, deception layer).
//
// Note on &mut engine: port blocking needs a mutable engine reference for
// Transaction::new(). The Responder owns a FirewallEngine and all calls
// go through a single dedicated channel — no concurrent mutable access.

use chrono::Utc;
use tracing::{info, warn};
use uuid::Uuid;

use crate::ipc::protocol::{Finding, ResponseTier};
use crate::agents::base::AgentReport;
use crate::state::{AegisState, ResponsePackage, PlannedAction};

use super::engine::FirewallEngine;
use super::rules::{RuleSet, block_ip, block_inbound_port, summary, cleanup_netsh_rules};

// ── Responder ─────────────────────────────────────────────────────────────────

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

    /// Process an agent report and take appropriate firewall action.
    /// Returns descriptions of actions taken (for logging).
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

    /// Execute operator-approved Tier 4-5 responses from AegisState.
    /// Call periodically from main.rs dispatch loop.
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

    /// Firewall status for HELENA's security briefing
    pub fn firewall_summary(&self) -> String {
        summary(&self.rules)
    }

    /// Clean up netsh rules on shutdown
    pub fn cleanup(&self) {
        cleanup_netsh_rules(&self.rules);
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

                // Block IP
                if let Some(ip) = extract_ip(finding) {
                    if !self.rules.is_ip_blocked(&ip) {
                        match block_ip(&self.rules, &ip, &finding.detail) {
                            Ok(())  => parts.push(format!("blocked IP {}", ip)),
                            Err(e)  => warn!("block_ip failed: {}", e),
                        }
                    }
                }

                // Block port
                if let Some(port) = extract_port(finding) {
                    match block_inbound_port(
                        &mut self.engine, &self.rules, port, &finding.detail
                    ) {
                        Ok(())  => parts.push(format!("blocked port {}", port)),
                        Err(e)  => warn!("block_port failed: {}", e),
                    }
                }

                // Queue Tier 4 package for critical findings
                if finding.severity >= 0.9 {
                    let pkg = build_tier4_package(finding, agent_id);
                    let id  = pkg.package_id.clone();
                    state.add_pending(pkg);
                    parts.push(format!("queued Tier 4 response {} for approval", id));
                }

                if parts.is_empty() { None }
                else { Some(format!("HARDEN: {}", parts.join(", "))) }
            }

            // Tier 4-5 only run after operator approval via execute_approved()
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
            // Tier 4 deception actions — Phase 4
            other => {
                info!("Approved action '{}' — Phase 4 implementation pending", other);
            }
        }
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

fn tier_for_severity(sev: f32) -> ResponseTier {
    if sev >= 0.9      { ResponseTier::Harden   }
    else if sev >= 0.7 { ResponseTier::Harden   }
    else if sev >= 0.5 { ResponseTier::Contain  }
    else if sev >= 0.3 { ResponseTier::Alert    }
    else               { ResponseTier::Monitor  }
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
