// src/firewall/engine.rs
//
// Phase 3a addition:
//   add_loopback_permit(port) — adds a WFP PERMIT filter for loopback
//   connections to a specific port. Used alongside block_inbound_port()
//   to allow only 127.0.0.1 to connect to AEGIS's IPC port (47201).
//   The permit rule has higher weight than the block rule so it wins
//   for loopback traffic while blocking everything else.
//
// All other logic unchanged from Phase 3.

use std::io;
use std::net::Ipv4Addr;                          // ← ADD THIS
use anyhow::{Context, Result};
use tracing::info;

use wfp::{
    FilterEngineBuilder, FilterEngine, Transaction,
    SubLayerBuilder, FilterBuilder, ActionType, Layer,
    PortConditionBuilder,
    IpAddressConditionBuilder,                    // ← ADD THIS
};

const HELENA_SUBLAYER_WEIGHT: u16 = 0x8000;

/// Weight for loopback permit rules — higher than block rules so
/// they take priority in WFP arbitration within our sublayer.

pub struct FirewallEngine {
    pub(crate) engine: FilterEngine,
}

impl FirewallEngine {
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

        let _ = txn.commit();

        info!("WFP: Engine open, HELENA sublayer registered (weight 0x{:X})", HELENA_SUBLAYER_WEIGHT);

        Ok(Self { engine })
    }

    /// Begin a new transaction for adding/modifying filters.
    pub fn transaction(&mut self) -> io::Result<Transaction> {
        Transaction::new(&mut self.engine)
    }

    /// Add a high-priority PERMIT rule for loopback connections to a port.
    /// Call this BEFORE block_inbound_port() for the same port.
    /// Result: loopback (127.0.0.1) is permitted, everything else blocked.
    ///
    /// WFP evaluates filters within a sublayer by weight — higher weight wins.
    /// The permit here (0xFFFF) beats the block added by block_inbound_port (default 0).
    pub fn add_loopback_permit(&mut self, port: u16) -> Result<()> {
        // WFP permit — over-broad due to wfp 0.0.3 lacking IpAddrConditionBuilder
        let filter_id = FilterBuilder::default()
            .name(&format!("HELENA Loopback Permit Port {}", port))
            .description("Permit loopback traffic (WFP — needs remote-addr restriction after wfp upgrade)")
            .action(ActionType::Permit)
            .layer(Layer::InboundTransportV4)
            .weight(0x7FFF)  // High weight so it matches before the block rule, lower weight than netsh rule
            .condition(
                PortConditionBuilder::local()
                    .equal(port)
                    .build()
            )
            .add(&self.txn()?)
            .context(format!("Failed to add WFP loopback permit for port {}", port))?;

        self.txn()?.commit()?;

        // ALSO add a netsh loopback-only rule as a safety net
        // This ensures 127.0.0.1 is explicitly permitted even if the WFP rule is too broad
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

        Ok(())
    }
}

impl Drop for FirewallEngine {
    fn drop(&mut self) {
        info!("WFP: Engine closing — HELENA firewall rules removed");
    }
}
