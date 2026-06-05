// src/firewall/rules.rs
//
// AEGIS Firewall Rule Management
//
// Two mechanisms, each used where it's the right tool:
//
// IP blocking — netsh advfirewall
//   netsh writes to the same BFE (Base Filtering Engine) as WFP. Rules can
//   persist after AEGIS exits (persistent=true), which is the right behaviour
//   for blocked attacker IPs. Tagged with "HELENA_BLOCK_" prefix.
//
// Port blocking — wfp crate via FirewallEngine
//   Uses a dynamic WFP session so port blocks are temporary — removed
//   automatically when AEGIS stops. Port blocks are defensive responses
//   to active scanning; they don't need to persist.
//
// Bug fixes from v1:
//   Bug 24: blocked_ports stored () instead of WFP filter ID → now stores u64
//   Bug 27: cleanup_netsh_rules removed ALL IP blocks → split into
//           cleanup_temporary() and respect persistent flag per IP

use std::collections::HashMap;
use std::net::Ipv4Addr;
use std::process::Command;
use std::str::FromStr;
use std::sync::Mutex;

use anyhow::{Context, Result};
use tracing::{info, warn};

use super::engine::FirewallEngine;

/// Metadata for a blocked IP rule.
#[derive(Debug, Clone)]
pub struct IPRuleMeta {
    /// The netsh rule name (e.g., "HELENA_BLOCK_185_220_101_34")
    pub rule_name: String,
    /// Whether this rule should persist after AEGIS exits.
    /// BUG FIX (Bug 27): Previously all IP blocks were removed on shutdown.
    /// Now only non-persistent blocks are cleaned up.
    pub persistent: bool,
    /// Reason for the block (for audit trail)
    pub reason: String,
}

pub struct RuleSet {
    /// Blocked IPs with metadata. Key = IP string, Value = rule metadata.
    blocked_ips: Mutex<HashMap<String, IPRuleMeta>>,

    /// Blocked ports with WFP filter IDs.
    /// BUG FIX (Bug 24): Was HashMap<u16, ()>, now HashMap<u16, u64>
    /// so individual ports can be unblocked by filter ID.
    blocked_ports: Mutex<HashMap<u16, u64>>,
}

impl RuleSet {
    pub fn new() -> Self {
        Self {
            blocked_ips: Mutex::new(HashMap::new()),
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

    /// List all blocked ports with their WFP filter IDs.
    /// NEW: Needed for diagnostics and clean removal.
    pub fn list_blocked_ports(&self) -> Vec<(u16, u64)> {
        self.blocked_ports.lock().unwrap().iter()
            .map(|(&port, &filter_id)| (port, filter_id))
            .collect()
    }
}

/// Block all inbound and outbound traffic to/from an IPv4 address.
///
/// # Arguments
/// * `rule_set` — The shared rule set
/// * `ip_str` — IPv4 address to block (e.g., "185.220.101.34")
/// * `reason` — Human-readable reason for the block
/// * `persistent` — Whether this rule should survive AEGIS shutdown.
///   BUG FIX (Bug 27): Attack-source IP blocks should be persistent=true.
///
/// Persists after AEGIS exits if `persistent` is true. Use `unblock_ip` to remove.
pub fn block_ip(rule_set: &RuleSet, ip_str: &str, reason: &str, persistent: bool) -> Result<()> {
    if rule_set.is_ip_blocked(ip_str) { return Ok(()); }
    Ipv4Addr::from_str(ip_str)
        .context(format!("Invalid IPv4 address: {}", ip_str))?;

    let rule_name = format!("HELENA_BLOCK_{}", ip_str.replace('.', "_"));

    // Block inbound
    let out = Command::new("netsh")
        .args(["advfirewall", "firewall", "add", "rule",
            &format!("name={}", rule_name), "dir=in", "action=block",
            &format!("remoteip={}", ip_str), "enable=yes", "profile=any",
            &format!("description=HELENA blocked: {}",
                &reason[..reason.len().min(60)])])
        .output().context("Failed to run netsh")?;

    if !out.status.success() {
        return Err(anyhow::anyhow!("netsh inbound block failed: {}",
            String::from_utf8_lossy(&out.stderr)));
    }

    // Block outbound
    let out = Command::new("netsh")
        .args(["advfirewall", "firewall", "add", "rule",
            &format!("name={}_OUT", rule_name), "dir=out", "action=block",
            &format!("remoteip={}", ip_str), "enable=yes", "profile=any"])
        .output().context("Failed to run netsh")?;

    if !out.status.success() {
        warn!("netsh outbound block failed for {}: {}", ip_str,
            String::from_utf8_lossy(&out.stderr));
    }

    rule_set.blocked_ips.lock().unwrap()
        .insert(ip_str.to_string(), IPRuleMeta {
            rule_name: rule_name.clone(),
            persistent,
            reason: reason.to_string(),
        });

    info!("Firewall: Blocked {} via netsh ({}, persistent={})", ip_str, reason, persistent);
    Ok(())
}

/// Backward-compatible wrapper — blocks IP as persistent by default.
/// Existing callers that don't specify persistence get persistent blocks
/// (which is the correct default for attacker IPs).
pub fn block_ip_persistent(rule_set: &RuleSet, ip_str: &str, reason: &str) -> Result<()> {
    block_ip(rule_set, ip_str, reason, true)
}

/// Remove a netsh IP block.
pub fn unblock_ip(rule_set: &RuleSet, ip_str: &str) -> Result<()> {
    let meta = rule_set.blocked_ips.lock().unwrap().remove(ip_str);
    let Some(meta) = meta else {
        warn!("Firewall: tried to unblock {} but no rule found", ip_str);
        return Ok(());
    };

    let _ = Command::new("netsh")
        .args(["advfirewall", "firewall", "delete", "rule",
               &format!("name={}", meta.rule_name)])
        .output();
    let _ = Command::new("netsh")
        .args(["advfirewall", "firewall", "delete", "rule",
               &format!("name={}_OUT", meta.rule_name)])
        .output();

    info!("Firewall: Unblocked {} (was: {})", ip_str, meta.reason);
    Ok(())
}

/// Block all inbound connections on a specific local port.
/// Temporary — removed automatically when AEGIS stops.
///
/// BUG FIX (Bug 24): Now stores the WFP filter ID (u64) instead of (),
/// and delegates to FirewallEngine::add_port_block() which returns the ID.
pub fn block_inbound_port(
    engine: &mut FirewallEngine,
    rule_set: &RuleSet,
    port: u16,
    reason: &str,
) -> Result<()> {
    if rule_set.blocked_ports.lock().unwrap().contains_key(&port) {
        return Ok(());
    }

    let filter_id = engine.add_port_block(port, reason)?;

    rule_set.blocked_ports.lock().unwrap().insert(port, filter_id);
    info!("Firewall: Blocked inbound port {} via WFP (filter {})", port, filter_id);
    Ok(())
}

/// Remove a WFP port block.
///
/// NEW: Did not exist in v1. Required by Bug 24 fix — without storing
/// filter IDs, individual port blocks could not be removed.
pub fn unblock_inbound_port(
    engine: &mut FirewallEngine,
    rule_set: &RuleSet,
    port: u16,
) -> Result<()> {
    let filter_id = rule_set.blocked_ports.lock().unwrap().remove(&port);
    let Some(_filter_id) = filter_id else {
        warn!("Firewall: tried to unblock port {} but no rule found", port);
        return Ok(());
    };

    engine.remove_port_block(port)?;

    info!("Firewall: Unblocked inbound port {} via WFP", port);
    Ok(())
}

/// Generate a summary string of current firewall rules.
/// NEW: Replaces the missing `summary()` function that responder.rs imported.
pub fn summary(rule_set: &RuleSet) -> String {
    let ips = rule_set.blocked_ip_count();
    let ports = rule_set.blocked_port_count();
    let ip_list = rule_set.list_blocked_ips();
    let port_list = rule_set.list_blocked_ports();

    let mut s = format!("Firewall Rules: {} IPs blocked, {} ports blocked\n", ips, ports);
    if !ip_list.is_empty() {
        s.push_str("  Blocked IPs:\n");
        for ip in &ip_list {
            s.push_str(&format!("    - {}\n", ip));
        }
    }
    if !port_list.is_empty() {
        s.push_str("  Blocked Ports:\n");
        for (port, fid) in &port_list {
            s.push_str(&format!("    - Port {} (WFP filter {})\n", port, fid));
        }
    }
    s
}

/// Remove only NON-persistent (temporary) HELENA netsh IP rules.
/// Called on AEGIS shutdown.
///
/// BUG FIX (Bug 27): The old `cleanup_netsh_rules` removed ALL IP blocks
/// on shutdown, including persistent attacker blocks. This version only
/// removes temporary (non-persistent) rules, keeping attacker blocks alive.
pub fn cleanup_temporary_rules(rule_set: &RuleSet) {
    let ips: Vec<(String, IPRuleMeta)> = rule_set.blocked_ips.lock().unwrap()
        .iter()
        .filter(|(_, meta)| !meta.persistent)
        .map(|(ip, meta)| (ip.clone(), meta.clone()))
        .collect();

    for (ip, meta) in &ips {
        let _ = Command::new("netsh")
            .args(["advfirewall", "firewall", "delete", "rule",
                   &format!("name={}", meta.rule_name)])
            .output();
        let _ = Command::new("netsh")
            .args(["advfirewall", "firewall", "delete", "rule",
                   &format!("name={}_OUT", meta.rule_name)])
            .output();
        rule_set.blocked_ips.lock().unwrap().remove(ip);
        info!("Firewall: Cleaned up temporary block for {}", ip);
    }

    if !ips.is_empty() {
        info!("Firewall: Cleaned up {} temporary IP blocks on shutdown", ips.len());
    }
}

/// Remove ALL HELENA netsh IP rules (including persistent ones).
/// Only called when the operator explicitly requests a full cleanup.
pub fn cleanup_all_rules(rule_set: &RuleSet) {
    let ips: Vec<String> = rule_set.blocked_ips.lock().unwrap()
        .keys().cloned().collect();
    for ip in ips { let _ = unblock_ip(rule_set, &ip); }
}
