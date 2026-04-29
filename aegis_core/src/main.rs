// src/main.rs
//
// AEGIS Phase 2 — ETW consumers + deduplication tuning.
//
// Adds to Phase 1:
//   - ETW consumer for 3 providers (Kernel-Process, DNS-Client, Security-Auditing)
//   - EtwHandles stored for process lifetime (drop = session stops)
//   - Rate limiter in dispatch loop to suppress repeated polling noise
//
// Deduplication design:
//   ETW findings are event-driven — they fire exactly once per real event.
//   They are NEVER rate-limited.
//
//   Phase 1 agent findings are polling — same agent fires every N seconds
//   even if nothing changed. Rate limits per agent type:
//     file_integrity:      0s  — never suppress. File changes are critical.
//     intrusion_detection: 0s  — never suppress. Security events must reach HELENA.
//     etw_*:               0s  — event-driven, no suppression needed.
//     network_monitor:     15s — polling, suppress repeat reports.
//     process_watchdog:    30s — noisiest poller, highest suppression.
//
//   This directly addresses the "78 findings every 5 seconds" problem from Phase 1.

mod ipc;
mod state;
mod agents;
mod etw;

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::{Mutex, mpsc};
use tracing::info;
use tracing_subscriber::EnvFilter;

use ipc::{
    protocol::{Message, MessageKind, MessageSource, StatusPayload},
    server::IpcServer,
};
use state::AegisState;
use agents::{
    AgentReport, spawn_agent,
    network::NetworkMonitor,
    integrity::FileIntegrityMonitor,
    process::ProcessWatchdog,
    intrusion::IntrusionDetection,
};
use etw::start_etw_consumers;

// ── Rate limit config (seconds) ───────────────────────────────────────────────

fn cooldown_for_agent(agent_id: &str) -> u64 {
    if agent_id.starts_with("process_watchdog")    { return 30; }
    if agent_id.starts_with("network_monitor")     { return 15; }
    // file_integrity, intrusion_detection, etw_* — no cooldown
    0
}

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
    info!("  AEGIS Security Core — Phase 2        ");
    info!("  H.O.P.E. Project / HELENA Initiative ");
    info!("═══════════════════════════════════════");

    let state = Arc::new(Mutex::new(AegisState::new()));

    // ── IPC server ─────────────────────────────────────────────────────────────

    let (server, helena_tx) = IpcServer::new(Arc::clone(&state));
    tokio::spawn(async move {
        if let Err(e) = server.run().await {
            tracing::error!("IPC server crashed: {}", e);
        }
    });

    // ── Shared report channel ──────────────────────────────────────────────────

    let (report_tx, mut report_rx) = mpsc::unbounded_channel::<AgentReport>();

    // ── Phase 1 agents ─────────────────────────────────────────────────────────

    let agents: Vec<Arc<dyn agents::Agent>> = vec![
        Arc::new(NetworkMonitor::v1()),
        Arc::new(NetworkMonitor::v2()),
        Arc::new(NetworkMonitor::v3()),
        Arc::new(NetworkMonitor::v4()),
        Arc::new(FileIntegrityMonitor::v1()),
        Arc::new(FileIntegrityMonitor::v2()),
        Arc::new(FileIntegrityMonitor::v3()),
        Arc::new(FileIntegrityMonitor::v4()),
        Arc::new(ProcessWatchdog::v1()),
        Arc::new(ProcessWatchdog::v2()),
        Arc::new(ProcessWatchdog::v3()),
        Arc::new(ProcessWatchdog::v4()),
        Arc::new(IntrusionDetection::v1()),
        Arc::new(IntrusionDetection::v2()),
        Arc::new(IntrusionDetection::v3()),
        Arc::new(IntrusionDetection::v4()),
    ];

    let agent_count = agents.len() as u32;
    for agent in agents {
        spawn_agent(agent, Arc::clone(&state), report_tx.clone());
    }

    {
        let mut s = state.lock().await;
        s.active_agent_count = agent_count;
    }

    info!("Spawned {} Phase 1 agents", agent_count);

    // ── Phase 2: ETW consumers ─────────────────────────────────────────────────
    // EtwHandles MUST be stored — dropping it stops all ETW sessions.

    let _etw_handles = start_etw_consumers(
        Arc::clone(&state),
        report_tx.clone(),
    );

    // ── Dispatch loop with rate limiting ───────────────────────────────────────

    let state_for_dispatch = Arc::clone(&state);
    let helena_tx_dispatch  = Arc::clone(&helena_tx);

    tokio::spawn(async move {
        // last_sent: agent_id → Instant of last report forwarded to HELENA
        let mut last_sent: HashMap<String, Instant> = HashMap::new();

        while let Some(report) = report_rx.recv().await {
            let cooldown = cooldown_for_agent(&report.agent_id);

            // Rate limit check
            if cooldown > 0 {
                if let Some(last) = last_sent.get(&report.agent_id) {
                    if last.elapsed().as_secs() < cooldown {
                        // Still within cooldown — write findings to state for
                        // correlation but don't forward to HELENA
                        let mut s = state_for_dispatch.lock().await;
                        for f in &report.findings {
                            s.write_finding(&report.agent_id, f.clone());
                        }
                        s.escalate_if_higher(report.threat_level);
                        continue;
                    }
                }
            }

            // Update cooldown timestamp
            if cooldown > 0 {
                last_sent.insert(report.agent_id.clone(), Instant::now());
            }

            tracing::warn!(
                "REPORT [{}] threat={} findings={}",
                report.agent_id, report.threat_level, report.findings.len()
            );

            // Write to shared state
            {
                let mut s = state_for_dispatch.lock().await;
                for f in &report.findings {
                    s.write_finding(&report.agent_id, f.clone());
                }
                s.escalate_if_higher(report.threat_level);
            }

            // Forward to HELENA
            let summary = report.findings.first()
                .map(|f| f.detail.clone())
                .unwrap_or_else(|| format!("Threat from {}", report.agent_id));

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

            let tx_lock = helena_tx_dispatch.lock().await;
            if let Some(tx) = tx_lock.as_ref() {
                let _ = tx.send(alert);
            }
        }
    });

    // ── Heartbeat ──────────────────────────────────────────────────────────────

    let state_hb = Arc::clone(&state);
    let helena_tx_hb = Arc::clone(&helena_tx);

    tokio::spawn(async move {
        let mut interval = tokio::time::interval(
            tokio::time::Duration::from_secs(30)
        );
        loop {
            interval.tick().await;
            let payload = {
                let s = state_hb.lock().await;
                StatusPayload {
                    threat_level:      s.threat_level,
                    active_agents:     s.active_agent_count,
                    pending_responses: s.pending_responses.len() as u32,
                    uptime_seconds:    s.uptime_seconds(),
                    events_processed:  s.events_processed,
                    last_event_at:     s.last_event_at,
                }
            };
            let msg = Message::new(
                MessageSource::Aegis,
                MessageKind::StatusReport,
                serde_json::to_value(&payload).unwrap_or_default(),
            );
            let tx_lock = helena_tx_hb.lock().await;
            if let Some(tx) = tx_lock.as_ref() {
                let _ = tx.send(msg);
            }
        }
    });

    info!("AEGIS Phase 2 ready — {} agents + ETW consumers active", agent_count);
    info!("Waiting for HELENA on 127.0.0.1:47201");

    tokio::signal::ctrl_c().await?;
    info!("Shutdown signal received. AEGIS stopping.");

    // _etw_handles dropped here — cleanly stops all ETW sessions
    Ok(())
}
