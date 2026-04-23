// src/main.rs
//
// AEGIS — Adaptive Evolving Guardian and Intelligence System
// Phase 0 — IPC Bridge (proof of concept)
//
// This binary does three things in Phase 0:
//   1. Initialises shared state
//   2. Starts the IPC server so HELENA can connect
//   3. Runs a heartbeat loop that sends status to HELENA every 30 seconds
//
// Agents are stubbed in Phase 0. The point of this phase is to prove
// the bridge works end-to-end. Phase 1 adds real agents.
//
// Run with:
//   cargo run --release
//
// Or build and run:
//   cargo build --release
//   ./target/release/aegis

mod ipc;
mod state;

use std::sync::Arc;
use tokio::sync::Mutex;
use tracing::info;
use tracing_subscriber::EnvFilter;

use ipc::{
    protocol::{Message, MessageKind, MessageSource, StatusPayload, ThreatLevel},
    server::IpcServer,
};
use state::AegisState;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialise logging
    // Set RUST_LOG=debug for verbose output, RUST_LOG=info for normal
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info"))
        )
        .with_target(false)
        .with_thread_ids(false)
        .init();

    info!("═══════════════════════════════════════");
    info!("  AEGIS Security Core — Phase 0        ");
    info!("  H.O.P.E. Project / HELENA Initiative ");
    info!("═══════════════════════════════════════");

    // Initialise shared state
    let state = Arc::new(Mutex::new(AegisState::new()));

    // Build IPC server
    let (server, helena_tx) = IpcServer::new(Arc::clone(&state));

    // Spawn the IPC server on its own task
    tokio::spawn(async move {
        if let Err(e) = server.run().await {
            tracing::error!("IPC server crashed: {}", e);
        }
    });

    // Heartbeat loop — sends a status report to HELENA every 30 seconds
    // This is also how HELENA knows AEGIS is alive without polling
    let state_for_heartbeat = Arc::clone(&state);
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(
            tokio::time::Duration::from_secs(30)
        );

        loop {
            interval.tick().await;

            let payload = {
                let s = state_for_heartbeat.lock().await;
                StatusPayload {
                    threat_level:      s.threat_level,
                    active_agents:     s.active_agent_count,
                    pending_responses: s.pending_responses.len() as u32,
                    uptime_seconds:    s.uptime_seconds(),
                    events_processed:  s.events_processed,
                    last_event_at:     s.last_event_at,
                }
            };

            let heartbeat = Message::new(
                MessageSource::Aegis,
                MessageKind::StatusReport,
                serde_json::to_value(&payload).unwrap_or_default(),
            );

            // Push to HELENA if connected
            let tx_lock = helena_tx.lock().await;
            if let Some(tx) = tx_lock.as_ref() {
                let _ = tx.send(heartbeat);
            }
        }
    });

    info!("AEGIS ready. Waiting for HELENA on 127.0.0.1:47201");

    // Main thread — handle OS signals for clean shutdown
    // On Windows this catches Ctrl+C
    tokio::signal::ctrl_c().await?;
    info!("Shutdown signal received. AEGIS stopping.");

    Ok(())
}
