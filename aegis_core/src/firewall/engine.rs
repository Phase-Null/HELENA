// src/firewall/engine.rs
//
// WFP engine wrapper — HELENA's firewall session.
//
// The wfp crate API (verified from docs.rs/wfp/0.0.3):
//   - FilterEngineBuilder::default().dynamic().open() -> io::Result<FilterEngine>
//   - Transaction::new(&mut engine) -> io::Result<Transaction>
//   - SubLayerBuilder::default().name().weight().add(&transaction) -> io::Result<()>
//   - FilterBuilder::default().name().action().layer().condition().add(&transaction) -> io::Result<u64>
//   - transaction.commit() -> io::Result<()>
//   - "dynamic" mode: all filters added through this session are removed on drop
//
// Design: FirewallEngine wraps the FilterEngine. All rule additions
// open a short-lived Transaction, add the filter, commit, and return the
// filter ID. This is the correct pattern per the wfp docs example.
//
// Thread safety note: FilterEngine is Send but not Sync. The Responder
// that owns FirewallEngine lives on a single dedicated thread in main.rs
// and receives commands via an std::sync::mpsc channel. No concurrent
// access to the engine handle.
//
// IP blocking uses netsh rather than WFP IP conditions. Reason: the
// wfp 0.0.3 API examples only confirm PortConditionBuilder. IpAddrConditionBuilder
// may exist but is not confirmed in the public docs for this version. netsh
// writes to the same Base Filtering Engine as WFP, is reliable, and the
// commands are extremely well documented. Port blocking uses WFP directly
// since PortConditionBuilder is confirmed.

use std::io;
use anyhow::{Context, Result};
use tracing::info;

use wfp::{FilterEngineBuilder, FilterEngine, Transaction, SubLayerBuilder};

/// Sublayer weight — above Windows Firewall defaults (0x2710),
/// below system-critical rules (0xFFFF).
const HELENA_SUBLAYER_WEIGHT: u16 = 0x8000;

pub struct FirewallEngine {
    pub(crate) engine: FilterEngine,
}

impl FirewallEngine {
    /// Open a dynamic WFP session and register HELENA's sublayer.
    /// Requires admin. Fails gracefully if unavailable.
    pub fn open() -> Result<Self> {
        let mut engine = FilterEngineBuilder::default()
            .dynamic()
            .open()
            .context("Failed to open WFP engine — is AEGIS running as admin?")?;

        // Register HELENA's sublayer in a transaction
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

        Ok(Self { engine })
    }

    /// Begin a new transaction for adding/modifying filters.
    /// The caller must call txn.commit() or the changes are rolled back.
    pub fn transaction(&mut self) -> io::Result<Transaction> {
        Transaction::new(&mut self.engine)
    }
}

// On drop: dynamic session closes, all WFP filters added through it
// are automatically removed by Windows — no explicit cleanup needed.
impl Drop for FirewallEngine {
    fn drop(&mut self) {
        info!("WFP: Engine closing — HELENA firewall rules removed");
    }
}
