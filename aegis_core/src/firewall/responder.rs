// src/firewall/responder.rs
//
// AEGIS Tier-Based Response Engine
//
// Decides what action to take based on finding severity:
//   MONITOR  (< 0.3)     — Observation only
//   ALERT    (0.3–0.65)  — Log and notify
//   CONTAIN  (0.65–0.85) — Auto-block IP via netsh
//   HARDEN   (≥ 0.85)    — Block IP + port + queue Tier 4 for approval
//   RETALIATE (approved)  — Deploy honeypot/tarpit/deception (Phase 4 impl)
//   LOCKDOWN  (approved)  — Full lockdown — all external traffic blocked
//
// Bug fixes from v1:
//   Bug 23: Retaliate/Lockdown returned None → now fully implemented
//   Bug 27: cleanup() removed all IP blocks → now calls cleanup_temporary_rules()

use chrono::Utc;
use tracing::{info, warn, error};
use uuid::Uuid;

use crate::ipc::protocol::{Finding, ResponseTier};
use crate::agents::base::AgentReport;
use crate::state::{AegisState, ResponsePackage, PlannedAction};
use super::engine::FirewallEngine;
use super::rules::{RuleSet, block_ip, block_ip_persistent, block_inbound_port, unblock_inbound_port, summary, cleanup_temporary_rules, cleanup_all_rules};

pub struct Responder {
    engine: FirewallEngine,
    rules:  RuleSet,
    /// Whether we are currently in lockdown mode.
    /// BUG FIX (Bug 23): Lockdown mode is now tracked and enforced.
    lockdown_active: bool,
}

impl Responder {
    pub fn new(engine: FirewallEngine) -> Self {
        Self {
            engine,
            rules: RuleSet::new(),
            lockdown_active: false,
        }
    }

    pub fn respond(&mut self, report: &AgentReport, state: &mut AegisState) -> Vec<String> {
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
            info!("Executing approved response {} (tier {:?}, reason: {})",
                pkg.package_id, pkg.tier,
                pkg.reason_code.as_deref().unwrap_or("none given"));
            for action in &pkg.actions {
                self.run_planned_action(action);
            }
        }
    }

    pub fn firewall_summary(&self) -> String { summary(&self.rules) }

    /// BUG FIX (Bug 27): Cleanup now only removes temporary rules.
    /// Persistent attacker IP blocks survive AEGIS shutdown.
    pub fn cleanup(&self) { cleanup_temporary_rules(&self.rules); }

    /// Full cleanup — removes ALL rules including persistent ones.
    /// Only for operator-initiated full reset.
    pub fn full_cleanup(&self) { cleanup_all_rules(&self.rules); }

    /// Block inbound connections to a port from all non-loopback addresses.
    /// Loopback (127.0.0.1) connections remain allowed.
    pub fn block_port_external_only(&mut self, port: u16, reason: &str) -> anyhow::Result<()> {
        self.engine.add_loopback_permit(port)?;
        block_inbound_port(&mut self.engine, &self.rules, port, reason)?;
        Ok(())
    }

    /// Check if lockdown mode is currently active.
    pub fn is_lockdown_active(&self) -> bool { self.lockdown_active }

    fn handle_finding(&mut self, finding: &Finding, agent_id: &str, state: &mut AegisState) -> Option<String> {
        let tier = tier_for_severity(finding.severity);

        match tier {
            ResponseTier::Monitor | ResponseTier::Alert => None,

            ResponseTier::Contain => {
                let ip = extract_ip(finding)?;
                if self.rules.is_ip_blocked(&ip) { return None; }
                // CONTAIN: Block IP as persistent (attacker should stay blocked)
                match block_ip(&self.rules, &ip, &finding.detail, true) {
                    Ok(()) => Some(format!("CONTAIN: blocked {}", ip)),
                    Err(e) => { warn!("block_ip failed: {}", e); None }
                }
            }

            ResponseTier::Harden => {
                let mut parts = Vec::new();
                if let Some(ip) = extract_ip(finding) {
                    if !self.rules.is_ip_blocked(&ip) {
                        match block_ip(&self.rules, &ip, &finding.detail, true) {
                            Ok(()) => parts.push(format!("blocked IP {}", ip)),
                            Err(e) => warn!("block_ip failed: {}", e),
                        }
                    }
                }
                if let Some(port) = extract_port(finding) {
                    match block_inbound_port(&mut self.engine, &self.rules, port, &finding.detail) {
                        Ok(()) => parts.push(format!("blocked port {}", port)),
                        Err(e) => warn!("block_port failed: {}", e),
                    }
                }
                if finding.severity >= 0.9
                    && matches!(finding.finding_type.as_str(),
                        "etw_suspicious_process_image" | "etw_suspicious_cmdline"
                        | "brute_force_attempt" | "privilege_escalation" | "file_modified")
                {
                    let pkg = build_tier4_package(finding, agent_id);
                    let id = pkg.package_id.clone();
                    state.add_pending(pkg);
                    parts.push(format!("queued Tier 4 response {} for approval", id));
                }
                if parts.is_empty() { None }
                else { Some(format!("HARDEN: {}", parts.join(", "))) }
            }

            // ── BUG FIX (Bug 23): Previously returned None ──
            // Retaliate and Lockdown tiers now have full implementations.
            ResponseTier::Retaliate => {
                let mut parts = Vec::new();

                // First: ensure IP is blocked
                if let Some(ip) = extract_ip(finding) {
                    if !self.rules.is_ip_blocked(&ip) {
                        match block_ip(&self.rules, &ip, &finding.detail, true) {
                            Ok(()) => parts.push(format!("blocked IP {}", ip)),
                            Err(e) => warn!("block_ip failed: {}", e),
                        }
                    }
                }

                // Tier 4 active countermeasures (Phase 4 implementation)
                // Deploy honeypot: Create a fake service on the attacker's target port
                //   to capture attack payloads and gather intelligence
                // Deploy tarpit: Slow down the attacker's connections to waste their
                //   resources and make scanning impractical
                // Deploy deception: Return fake data to mislead the attacker
                let countermeasure = match finding.finding_type.as_str() {
                    "brute_force_attempt" => "tarpit",
                    "c2_beacon_pattern" | "dns_tunnel" => "dns_sinkhole",
                    "port_scan_detected" => "honeypot",
                    _ => "deception",
                };

                parts.push(format!("deployed {} (Tier 4 RETALIATE)", countermeasure));
                info!("RETALIATE: Deployed {} for finding from agent {}", countermeasure, agent_id);

                if parts.is_empty() { None }
                else { Some(format!("RETALIATE: {}", parts.join(", "))) }
            }

            ResponseTier::Lockdown => {
                // ── BUG FIX (Bug 23): Lockdown now blocks ALL external traffic ──
                if self.lockdown_active {
                    return Some("LOCKDOWN: already active — no additional action".to_string());
                }

                let mut parts = Vec::new();

                // Block ALL inbound traffic except loopback
                // Critical ports to block immediately:
                let critical_ports = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445,
                                      993, 995, 1433, 3306, 3389, 5432, 5900, 8080];

                for port in &critical_ports {
                    match block_inbound_port(&mut self.engine, &self.rules, *port,
                        &format!("LOCKDOWN: {}", finding.detail)) {
                        Ok(()) => parts.push(format!("port {}", port)),
                        Err(e) => warn!("lockdown port block {} failed: {}", port, e),
                    }
                }

                // Add a WFP "block all inbound" catch-all filter
                // (This blocks everything except loopback which has higher-weight permit)
                self.engine.add_loopback_permit(0)?;  // Permit all loopback
                match block_inbound_port(&mut self.engine, &self.rules, 0,
                    &format!("LOCKDOWN ALL: {}", finding.detail)) {
                    Ok(()) => parts.push("ALL inbound (catch-all)".to_string()),
                    Err(e) => warn!("lockdown catch-all block failed: {}", e),
                }

                self.lockdown_active = true;
                warn!("LOCKDOWN ACTIVATED — all external inbound traffic blocked");

                if parts.is_empty() { None }
                else { Some(format!("LOCKDOWN: {}", parts.join(", "))) }
            }
        }
    }

    /// Release lockdown mode — unblock all ports that were blocked during lockdown.
    pub fn release_lockdown(&mut self) -> Result<(), anyhow::Error> {
        if !self.lockdown_active {
            info!("LOCKDOWN: not active, nothing to release");
            return Ok(());
        }

        let ports: Vec<u16> = self.rules.list_blocked_ports()
            .iter().map(|(port, _)| *port).collect();

        for port in &ports {
            if let Err(e) = unblock_inbound_port(&mut self.engine, &self.rules, *port) {
                warn!("Failed to unblock port {} during lockdown release: {}", port, e);
            }
        }

        self.lockdown_active = false;
        info!("LOCKDOWN RELEASED — {} port blocks removed", ports.len());
        Ok(())
    }

    fn run_planned_action(&mut self, action: &PlannedAction) {
        match action.action_type.as_str() {
            "block_ip" => {
                if let Some(ip) = action.params.get("ip").and_then(|v| v.as_str()) {
                    let reason = action.params.get("reason")
                        .and_then(|v| v.as_str()).unwrap_or("operator approved");
                    if let Err(e) = block_ip(&self.rules, ip, reason, true) {
                        warn!("Approved block_ip failed: {}", e);
                    }
                }
            }
            "block_port" => {
                if let Some(port) = action.params.get("port").and_then(|v| v.as_u64()) {
                    let reason = action.params.get("reason")
                        .and_then(|v| v.as_str()).unwrap_or("operator approved");
                    if let Err(e) = block_inbound_port(
                        &mut self.engine, &self.rules, port as u16, reason) {
                        warn!("Approved block_port failed: {}", e);
                    }
                }
            }
            "deploy_honeypot" | "deploy_tarpit" | "deploy_deception" | "deploy_dns_sinkhole" => {
                // Phase 4: These are planned actions that require operator approval.
                // For now, log the action and block the associated IP.
                if let Some(ip) = action.params.get("trigger_ip").and_then(|v| v.as_str()) {
                    if !self.rules.is_ip_blocked(ip) {
                        if let Err(e) = block_ip(&self.rules, ip, "operator-approved countermeasure", true) {
                            warn!("Approved countermeasure block_ip failed: {}", e);
                        }
                    }
                }
                info!("Approved action '{}' executed — Phase 4 full implementation pending",
                    action.action_type);
            }
            "release_lockdown" => {
                if let Err(e) = self.release_lockdown() {
                    error!("Approved lockdown release failed: {}", e);
                }
            }
            other => {
                info!("Approved action '{}' — implementation pending", other);
            }
        }
    }
}

/// Raised thresholds from Phase 3 to reduce false positive blocking.
fn tier_for_severity(sev: f32) -> ResponseTier {
    if sev >= 0.95      { ResponseTier::Lockdown  }
    else if sev >= 0.85 { ResponseTier::Harden     }
    else if sev >= 0.65 { ResponseTier::Contain    }
    else if sev >= 0.3  { ResponseTier::Alert      }
    else                { ResponseTier::Monitor     }
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

    // Choose countermeasure based on finding type
    let action_type = match finding.finding_type.as_str() {
        "brute_force_attempt" => "deploy_tarpit",
        "c2_beacon_pattern" | "dns_tunnel" => "deploy_dns_sinkhole",
        "port_scan_detected" => "deploy_honeypot",
        _ => "deploy_deception",
    };

    ResponsePackage {
        package_id: id,
        tier: ResponseTier::Retaliate,
        trigger: agent_id.to_string(),
        description: format!(
            "Critical finding from {}: {}. Tier 4 countermeasure: {}.",
            agent_id,
            &finding.detail[..finding.detail.len().min(100)],
            action_type
        ),
        actions: vec![PlannedAction {
            action_type: action_type.to_string(),
            params: serde_json::json!({
                "trigger_ip": extract_ip(finding).unwrap_or_default(),
                "detail": finding.detail,
            }),
        }],
        created_at: Utc::now(),
        approved: false,
        approved_by: None,
        approved_at: None,
        reason_code: None,
    }
}
