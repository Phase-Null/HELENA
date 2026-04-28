// src/main.rs
//
// AEGIS — Phase 1
//
// Adds to Phase 0:
//   - Agent pool spawned at startup (4 types × 4 variants = 16 agents at CRITICAL)
//   - Report dispatch loop: reads agent reports, escalates threat level,
//     forwards alerts to HELENA over the IPC bridge
//   - Active agent count reported in status responses

mod ipc;
mod state;
mod agents;

use std::sync::Arc;
use tokio::sync::{Mutex, mpsc};
use tracing::info;
use tracing_subscriber::EnvFilter;

use ipc::{
    protocol::{Message, MessageKind, MessageSource, StatusPayload},
    server::IpcServer,
};
use state::AegisState;
use agents::{
    AgentReport,
    spawn_agent,
    network::NetworkMonitor,
    integrity::FileIntegrityMonitor,
    process::ProcessWatchdog,
    intrusion::IntrusionDetection,
};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info"))
        )
        .with_target(false)
        .init();

    info!("═══════════════════════════════════════");
    info!("  AEGIS Security Core — Phase 1        ");
    info!("  H.O.P.E. Project / HELENA Initiative ");
    info!("═══════════════════════════════════════");

    let state = Arc::new(Mutex::new(AegisState::new()));

    // ── IPC server ────────────────────────────────────────────────────────────

    let (server, helena_tx) = IpcServer::new(Arc::clone(&state));
    tokio::spawn(async move {
        if let Err(e) = server.run().await {
            tracing::error!("IPC server crashed: {}", e);
        }
    });

    // ── Agent report channel ──────────────────────────────────────────────────
    // All agents send their findings here. The dispatch loop below reads it.

    let (report_tx, mut report_rx) = mpsc::unbounded_channel::<AgentReport>();

    // ── Spawn agents ──────────────────────────────────────────────────────────
    // Phase 1 starts at IDLE threat level: 1 variant per agent type (4 agents).
    // As threat level rises, additional variants are activated.
    // For now we spawn all 16 — they run at their own intervals regardless.
    // The threshold on each variant controls what gets reported.

    let agents: Vec<Arc<dyn agents::Agent>> = vec![
        // Type A — Network Monitor
        Arc::new(NetworkMonitor::v1()),
        Arc::new(NetworkMonitor::v2()),
        Arc::new(NetworkMonitor::v3()),
        Arc::new(NetworkMonitor::v4()),
        // Type E — File Integrity
        Arc::new(FileIntegrityMonitor::v1()),
        Arc::new(FileIntegrityMonitor::v2()),
        Arc::new(FileIntegrityMonitor::v3()),
        Arc::new(FileIntegrityMonitor::v4()),
        // Type F — Process Watchdog
        Arc::new(ProcessWatchdog::v1()),
        Arc::new(ProcessWatchdog::v2()),
        Arc::new(ProcessWatchdog::v3()),
        Arc::new(ProcessWatchdog::v4()),
        // Type B — Intrusion Detection
        Arc::new(IntrusionDetection::v1()),
        Arc::new(IntrusionDetection::v2()),
        Arc::new(IntrusionDetection::v3()),
        Arc::new(IntrusionDetection::v4()),
    ];

    let agent_count = agents.len() as u32;

    for agent in agents {
        spawn_agent(agent, Arc::clone(&state), report_tx.clone());
    }

    // Update active agent count in state
    {
        let mut s = state.lock().await;
        s.active_agent_count = agent_count;
    }

    info!("Spawned {} agents", agent_count);

    // ── Report dispatch loop ──────────────────────────────────────────────────
    // Reads agent reports and:
    //   1. Escalates global threat level if needed
    //   2. Sends an alert to HELENA over IPC

    let state_for_dispatch = Arc::clone(&state);
    let helena_tx_for_dispatch = Arc::clone(&helena_tx);

    tokio::spawn(async move {
        while let Some(report) = report_rx.recv().await {
            tracing::warn!(
                "AGENT REPORT [{}] threat={} findings={}",
                report.agent_id,
                report.threat_level,
                report.findings.len()
            );

            // Escalate threat level
            {
                let mut s = state_for_dispatch.lock().await;
                s.escalate_if_higher(report.threat_level);
            }

            // Build summary for HELENA
            let summary = if report.findings.is_empty() {
                format!("Agent {} reported a threat", report.agent_id)
            } else {
                report.findings[0].detail.clone()
            };

            let alert = Message::new(
                MessageSource::Aegis,
                MessageKind::Alert,
                serde_json::json!({
                    "agent_id":     report.agent_id,
                    "threat_level": report.threat_level,
                    "summary":      summary,
                    "findings":     report.findings,
                    "package_id":   null,
                }),
            );

            let tx_lock = helena_tx_for_dispatch.lock().await;
            if let Some(tx) = tx_lock.as_ref() {
                let _ = tx.send(alert);
            }
        }
    });

    // ── Heartbeat ─────────────────────────────────────────────────────────────

    let state_for_heartbeat = Arc::clone(&state);
    let helena_tx_for_heartbeat = Arc::clone(&helena_tx);

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
            let tx_lock = helena_tx_for_heartbeat.lock().await;
            if let Some(tx) = tx_lock.as_ref() {
                let _ = tx.send(heartbeat);
            }
        }
    });

    info!("AEGIS Phase 1 ready — {} agents active", agent_count);
    info!("Waiting for HELENA on 127.0.0.1:47201");

    tokio::signal::ctrl_c().await?;
    info!("Shutdown signal received. AEGIS stopping.");
    Ok(())
}
