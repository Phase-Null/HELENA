// src/firewall/engine.rs
//
// AEGIS Firewall Engine — WFP session lifecycle
//
// Manages the Windows Filtering Platform (WFP) session:
//   - Opens a dynamic engine (rules auto-removed on process exit)
//   - Registers the HELENA sublayer
//   - Adds/removes loopback permit filters (properly restricted to 127.0.0.1)
//   - Tracks all WFP filter IDs for clean removal
//
// Bug fixes from v1:
//   BUG-1: warn import was missing → fixed (tracing import)
//   BUG-2: Over-broad WFP loopback permit → fixed (IpAddressConditionBuilder)
//   BUG-3: Double transaction commit → fixed (single txn for add + commit)
//   Bug 4:  Loopback allowed ALL traffic → fixed (remote-addr condition + netsh safety net)
//   Bug 24: No filter ID tracking → fixed (filter_ids HashMap + removal methods)

use std::collections::HashMap;
use std::io;
use std::net::Ipv4Addr;
use std::sync::Mutex;

use anyhow::{Context, Result};
use tracing::{info, warn, error};

use wfp::{
    FilterEngineBuilder, FilterEngine, Transaction,
    SubLayerBuilder, FilterBuilder, ActionType, Layer,
    PortConditionBuilder,
    IpAddressConditionBuilder,  // Available in wfp >= 0.0.7
};

const HELENA_SUBLAYER_WEIGHT: u16 = 0x8000;
const LOOPBACK_PERMIT_WEIGHT: u16 = 0x7FFF;
const PORT_BLOCK_WEIGHT: u16 = 0x0000;

pub struct FirewallEngine {
    pub(crate) engine: FilterEngine,
    /// Tracks WFP filter IDs by a human-readable key, so we can remove them later.
    /// Key format: "loopback_permit:{port}" or "port_block:{port}"
    filter_ids: Mutex<HashMap<String, u64>>,
}

impl FirewallEngine {
    /// Open a dynamic WFP engine session and register the HELENA sublayer.
    /// Requires administrator privileges.
    pub fn open() -> Result<Self> {
        let mut engine = FilterEngineBuilder::default()
            .dynamic()
            .open()
            .context("Failed to open WFP engine — is AEGIS running as admin?")?;

        let txn = Transaction::new(&mut engine)
            .context("Failed to begin WFP transaction")?;

        SubLayerBuilder::default()
            .name("HELENA Security Sublayer")
            .description("HELENA defensive firewall rules — auto-removed on shutdown")
            .weight(HELENA_SUBLAYER_WEIGHT)
            .add(&txn)
            .context("Failed to register WFP sublayer")?;

        txn.commit()
            .context("Failed to commit WFP sublayer registration")?;

        info!("WFP: Engine open, HELENA sublayer registered (weight 0x{:X})", HELENA_SUBLAYER_WEIGHT);

        Ok(Self {
            engine,
            filter_ids: Mutex::new(HashMap::new()),
        })
    }

    /// Begin a new WFP transaction.
    pub fn transaction(&mut self) -> io::Result<Transaction> {
        Transaction::new(&mut self.engine)
    }

    /// Add a high-priority PERMIT rule for loopback connections to a port.
    ///
    /// This creates a WFP filter that matches:
    ///   - Local port == `port`
    ///   - Remote address == 127.0.0.1
    /// with PERMIT action at high weight (0x7FFF), so it takes precedence
    /// over any block rule on the same port.
    ///
    /// Also adds a netsh safety-net rule as defense-in-depth.
    ///
    /// BUG FIX (Bug 4 / BUG-2): Previously, the loopback permit had no
    /// remote-address condition, allowing ALL traffic on the port.
    /// Now uses `IpAddressConditionBuilder::remote().equal(127.0.0.1)`.
    ///
    /// BUG FIX (BUG-3): Previously used two separate transactions
    /// (one for add, one for commit). Now uses a single transaction.
    pub fn add_loopback_permit(&mut self, port: u16) -> Result<()> {
        let filter_key = format!("loopback_permit:{}", port);

        // Check if already added
        if self.filter_ids.lock().unwrap().contains_key(&filter_key) {
            info!("WFP: Loopback permit for port {} already exists, skipping", port);
            return Ok(());
        }

        // Single transaction: add filter + commit
        let txn = self.transaction()
            .context(format!("Failed to begin WFP transaction for loopback permit on port {}", port))?;

        let filter_id = FilterBuilder::default()
            .name(&format!("HELENA Loopback Permit Port {}", port))
            .description("Permit loopback traffic ONLY from 127.0.0.1")
            .action(ActionType::Permit)
            .layer(Layer::InboundTransportV4)
            .weight(LOOPBACK_PERMIT_WEIGHT)
            .condition(
                PortConditionBuilder::local()
                    .equal(port)
                    .build()
            )
            .condition(
                IpAddressConditionBuilder::remote()
                    .equal(Ipv4Addr::new(127, 0, 0, 1))
                    .build()
            )
            .add(&txn)
            .context(format!("Failed to add WFP loopback permit for port {}", port))?;

        txn.commit()
            .context("Failed to commit WFP loopback permit transaction")?;

        // Store the filter ID for later removal
        self.filter_ids.lock().unwrap().insert(filter_key.clone(), filter_id);

        // Defense-in-depth: also add a netsh loopback-only rule
        let netsh_output = std::process::Command::new("netsh")
            .args([
                "advfirewall", "firewall", "add", "rule",
                &format!("name=HELENA_Loopback_Permit_{}", port),
                "dir=in",
                "action=allow",
                &format!("localport={}", port),
                "protocol=tcp",
                "remoteip=127.0.0.1",
                "profile=any",
            ])
            .output()
            .context("Failed to execute netsh for loopback permit")?;

        if !netsh_output.status.success() {
            warn!("netsh loopback permit for port {} failed: {:?}",
                  port, String::from_utf8_lossy(&netsh_output.stderr));
        }

        info!("WFP: Loopback permit added for port {} (filter ID {})", port, filter_id);
        Ok(())
    }

    /// Remove a previously-added loopback permit filter.
    ///
    /// NEW: This method did not exist in v1. Needed by Bug 24 fix
    /// (unblock_port needs to remove the associated loopback permit).
    pub fn remove_loopback_permit(&mut self, port: u16) -> Result<()> {
        let filter_key = format!("loopback_permit:{}", port);

        let filter_id = self.filter_ids.lock().unwrap().remove(&filter_key);
        let Some(filter_id) = filter_id else {
            warn!("WFP: No loopback permit filter found for port {}", port);
            return Ok(());
        };

        // Remove the WFP filter
        let txn = self.transaction()
            .context("Failed to begin WFP transaction for loopback permit removal")?;

        // Note: wfp crate >= 0.0.7 supports filter removal by ID
        if let Err(e) = txn.remove_filter(filter_id) {
            warn!("WFP: Failed to remove loopback permit filter {}: {}", filter_id, e);
        }

        txn.commit()
            .context("Failed to commit WFP loopback permit removal")?;

        // Also remove the netsh safety-net rule
        let _ = std::process::Command::new("netsh")
            .args([
                "advfirewall", "firewall", "delete", "rule",
                &format!("name=HELENA_Loopback_Permit_{}", port),
            ])
            .output();

        info!("WFP: Loopback permit removed for port {} (filter ID {})", port, filter_id);
        Ok(())
    }

    /// Add a WFP BLOCK filter for inbound traffic on a port.
    /// Returns the WFP filter ID for later removal.
    ///
    /// BUG FIX (Bug 24): Returns the filter ID so it can be stored
    /// and used for removal. Previously, the filter ID was discarded.
    pub fn add_port_block(&mut self, port: u16, reason: &str) -> Result<u64> {
        let filter_key = format!("port_block:{}", port);

        // Check if already blocked
        if self.filter_ids.lock().unwrap().contains_key(&filter_key) {
            info!("WFP: Port {} already blocked, skipping", port);
            return Ok(*self.filter_ids.lock().unwrap().get(&filter_key).unwrap());
        }

        let txn = self.transaction()
            .context(format!("Failed to begin WFP transaction for port block on {}", port))?;

        let safe_reason = &reason[..reason.len().min(60)];
        let filter_id = FilterBuilder::default()
            .name(&format!("HELENA Block Port {}", port))
            .description(&format!("HELENA blocked: {}", safe_reason))
            .action(ActionType::Block)
            .layer(Layer::InboundTransportV4)
            .weight(PORT_BLOCK_WEIGHT)
            .condition(PortConditionBuilder::local().equal(port).build())
            .add(&txn)
            .context(format!("Failed to add WFP filter for port {}", port))?;

        txn.commit()
            .context("Failed to commit WFP port block transaction")?;

        self.filter_ids.lock().unwrap().insert(filter_key, filter_id);

        info!("WFP: Inbound port {} blocked (filter ID {}, reason: {})", port, filter_id, safe_reason);
        Ok(filter_id)
    }

    /// Remove a WFP port block filter by its stored ID.
    ///
    /// NEW: This method did not exist in v1. Required by Bug 24 fix.
    pub fn remove_port_block(&mut self, port: u16) -> Result<()> {
        let filter_key = format!("port_block:{}", port);

        let filter_id = self.filter_ids.lock().unwrap().remove(&filter_key);
        let Some(filter_id) = filter_id else {
            warn!("WFP: No port block filter found for port {}", port);
            return Ok(());
        };

        let txn = self.transaction()
            .context("Failed to begin WFP transaction for port block removal")?;

        if let Err(e) = txn.remove_filter(filter_id) {
            warn!("WFP: Failed to remove port block filter {}: {}", filter_id, e);
        }

        txn.commit()
            .context("Failed to commit WFP port block removal")?;

        info!("WFP: Port block removed for port {} (filter ID {})", port, filter_id);
        Ok(())
    }

    /// Get the number of active WFP filters managed by this engine.
    pub fn active_filter_count(&self) -> usize {
        self.filter_ids.lock().unwrap().len()
    }

    /// List all managed filter keys (for diagnostics).
    pub fn list_filter_keys(&self) -> Vec<String> {
        self.filter_ids.lock().unwrap().keys().cloned().collect()
    }
}

impl Drop for FirewallEngine {
    fn drop(&mut self) {
        let count = self.filter_ids.lock().unwrap().len();
        info!("WFP: Engine closing — {} HELENA firewall filters auto-removed by dynamic session", count);
    }
}
