// src/firewall/rules.rs
//
// Firewall rule operations.
//
// Two mechanisms, each used where it's the right tool:
//
// IP blocking — netsh advfirewall
//   Reason: wfp 0.0.3 IpAddrConditionBuilder existence unconfirmed in public docs.
//   netsh writes to the same BFE (Base Filtering Engine) as WFP. Rules persist
//   after AEGIS exits, which is the right behaviour for blocked attacker IPs
//   (you want them to stay blocked even if HELENA restarts). Rules are tagged
//   with "HELENA_BLOCK_" prefix for easy identification and cleanup.
//
// Port blocking — wfp crate via Transaction
//   PortConditionBuilder is confirmed in the wfp 0.0.3 docs example.
//   Uses a dynamic WFP session so port blocks are temporary — they're removed
//   automatically when AEGIS stops. Port blocks are defensive responses to
//   active scanning; they don't need to persist.
//
// Both approaches use HELENA's WFP sublayer for WFP filters, and the
// HELENA_BLOCK_ naming convention for netsh rules.

use std::collections::HashMap;
use std::net::Ipv4Addr;
use std::process::Command;
use std::str::FromStr;
use std::sync::Mutex;

use anyhow::{Context, Result};
use tracing::{info, warn};

use wfp::{FilterBuilder, ActionType, Layer, PortConditionBuilder};

use super::engine::FirewallEngine;

// ── Rule registry ─────────────────────────────────────────────────────────────

pub struct RuleSet {
    /// IPs blocked via netsh — key is IP string
    blocked_ips:   Mutex<HashMap<String, String>>,   // ip → rule_name
    /// Ports blocked via WFP — key is port, value is WFP filter ID
    blocked_ports: Mutex<HashMap<u16, ()>>,
}

impl RuleSet {
    pub fn new() -> Self {
        Self {
            blocked_ips:   Mutex::new(HashMap::new()),
            blocked_ports: Mutex::new(HashMap::new()),
        }
    }

    pub fn is_ip_blocked(&self, ip: &str) -> bool {
        self.blocked_ips.lock().unwrap().contains_key(ip)
    }

    pub fn blocked_ip_count(&self) -> usize {
        self.blocked_ips.lock().unwrap().len()
    }

    pub fn blocked_port_count(&self) -> usize {
        self.blocked_ports.lock().unwrap().len()
    }

    pub fn list_blocked_ips(&self) -> Vec<String> {
        self.blocked_ips.lock().unwrap().keys().cloned().collect()
    }
}

// ── IP blocking (netsh) ───────────────────────────────────────────────────────

/// Block all inbound and outbound traffic to/from an IPv4 address.
/// Persists after AEGIS exits. Use unblock_ip to remove.
pub fn block_ip(
    rule_set: &RuleSet,
    ip_str:   &str,
    reason:   &str,
) -> Result<()> {
    // Don't double-block
    if rule_set.is_ip_blocked(ip_str) {
        return Ok(());
    }

    // Validate it's a real IPv4 address
    Ipv4Addr::from_str(ip_str)
        .context(format!("Invalid IPv4 address: {}", ip_str))?;

    let rule_name = format!("HELENA_BLOCK_{}", ip_str.replace('.', "_"));

    // Block inbound
    let out = Command::new("netsh")
        .args([
            "advfirewall", "firewall", "add", "rule",
            &format!("name={}", rule_name),
            "dir=in",
            "action=block",
            &format!("remoteip={}", ip_str),
            "enable=yes",
            "profile=any",
            &format!("description=HELENA blocked: {}", &reason[..reason.len().min(60)]),
        ])
        .output()
        .context("Failed to run netsh")?;

    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr);
        return Err(anyhow::anyhow!("netsh inbound block failed: {}", stderr));
    }

    // Block outbound
    let out = Command::new("netsh")
        .args([
            "advfirewall", "firewall", "add", "rule",
            &format!("name={}_OUT", rule_name),
            "dir=out",
            "action=block",
            &format!("remoteip={}", ip_str),
            "enable=yes",
            "profile=any",
        ])
        .output()
        .context("Failed to run netsh")?;

    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr);
        warn!("netsh outbound block failed for {}: {}", ip_str, stderr);
        // Don't fail — inbound block is the critical one
    }

    rule_set.blocked_ips.lock().unwrap()
        .insert(ip_str.to_string(), rule_name.clone());

    info!("Firewall: Blocked {} via netsh ({})", ip_str, reason);
    Ok(())
}

/// Remove a netsh IP block.
pub fn unblock_ip(rule_set: &RuleSet, ip_str: &str) -> Result<()> {
    let rule_name = rule_set.blocked_ips.lock().unwrap()
        .remove(ip_str);

    let Some(rule_name) = rule_name else {
        warn!("Firewall: tried to unblock {} but no rule found", ip_str);
        return Ok(());
    };

    // Delete inbound rule
    let _ = Command::new("netsh")
        .args(["advfirewall", "firewall", "delete", "rule",
               &format!("name={}", rule_name)])
        .output();

    // Delete outbound rule
    let _ = Command::new("netsh")
        .args(["advfirewall", "firewall", "delete", "rule",
               &format!("name={}_OUT", rule_name)])
        .output();

    info!("Firewall: Unblocked {}", ip_str);
    Ok(())
}

// ── Port blocking (WFP via Transaction) ───────────────────────────────────────

/// Block all inbound connections on a specific local port.
/// Temporary — removed automatically when AEGIS stops.
pub fn block_inbound_port(
    engine:   &mut FirewallEngine,
    rule_set: &RuleSet,
    port:     u16,
    reason:   &str,
) -> Result<()> {
    if rule_set.blocked_ports.lock().unwrap().contains_key(&port) {
        return Ok(());
    }

    let txn = engine.transaction()
        .context("Failed to begin WFP transaction for port block")?;

    FilterBuilder::default()
        .name(&format!("HELENA Block Port {}", port))
        .description(&format!("HELENA blocked: {}", &reason[..reason.len().min(60)]))
        .action(ActionType::Block)
        .layer(Layer::InboundTransportV4)
        .condition(
            PortConditionBuilder::local()
                .equal(port)
                .build()
        )
        .add(&txn)
        .context(format!("Failed to add WFP filter for port {}", port))?;

    txn.commit()
        .context("Failed to commit WFP port block transaction")?;

    rule_set.blocked_ports.lock().unwrap()
        .insert(port, ());

    info!("Firewall: Blocked inbound port {} via WFP ", port);
    Ok(())
}

// ── Summary ───────────────────────────────────────────────────────────────────

pub fn summary(rule_set: &RuleSet) -> String {
    let ips   = rule_set.blocked_ip_count();
    let ports = rule_set.blocked_port_count();

    if ips == 0 && ports == 0 {
        return "No active firewall blocks.".to_string();
    }

    let mut parts = Vec::new();
    if ips > 0 {
        let ip_list = rule_set.list_blocked_ips().join(", ");
        parts.push(format!("{} IP{} blocked: {}", ips,
            if ips == 1 { "" } else { "s" }, ip_list));
    }
    if ports > 0 {
        parts.push(format!("{} port{} blocked (WFP)",
            ports, if ports == 1 { "" } else { "s" }));
    }
    parts.join(" | ")
}

// ── Cleanup on shutdown ───────────────────────────────────────────────────────

/// Remove all HELENA netsh IP rules. Called on AEGIS shutdown so rules
/// don't pile up across restarts during development.
/// In production you may want to leave them — blocked attackers stay blocked.
pub fn cleanup_netsh_rules(rule_set: &RuleSet) {
    let ips: Vec<String> = rule_set.blocked_ips.lock().unwrap()
        .keys().cloned().collect();

    for ip in ips {
        let _ = unblock_ip(rule_set, &ip);
    }
}
