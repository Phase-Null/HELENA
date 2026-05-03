// src/main.rs
//
// AEGIS Phase 3a — Security hardening additions.
//
// Adds to Phase 3:
//   - Port 47201 self-protection: WFP rule blocking external access to
//     AEGIS's IPC port at startup. Loopback (127.0.0.1) remains open.
//     Prevents external processes from connecting and sending commands.
//   - ETW heartbeat monitoring: checks every 60 seconds that each ETW
//     session is still delivering events. Silence for >60s = alert.
//     Catches ETW tampering (T1562) and session crashes.

mod ipc;
mod state;
mod agents;
mod etw;
mod firewall;

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
use firewall::{FirewallEngine, Responder};

const AEGIS_IPC_PORT: u16 = 47201;

// ── Rate limit config ─────────────────────────────────────────────────────────

fn cooldown_for_agent(agent_id: &str) -> u64 {
    if agent_id.starts_with("process_watchdog") { return 30; }
    if agent_id.starts_with("network_monitor")  { return 15; }
    0
}

// ── Firewall command channel ──────────────────────────────────────────────────

enum FirewallCmd {
    Respond(AgentReport),
    ExecuteApproved,
    Shutdown,
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
    info!("  AEGIS Security Core — Phase 3a       ");
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

    // ── Firewall thread ────────────────────────────────────────────────────────

    let (fw_tx, fw_rx) = std::sync::mpsc::channel::<FirewallCmd>();
    let state_for_fw   = Arc::clone(&state);
    let fw_rt_handle   = tokio::runtime::Handle::current();

    std::thread::Builder::new()
        .name("aegis_firewall".to_string())
        .spawn(move || {
            match FirewallEngine::open() {
                Ok(engine) => {
                    info!("WFP: Firewall engine active");
                    let mut responder = Responder::new(engine);

                    // ── Port 47201 self-protection ─────────────────────────────
                    // Block all inbound connections to AEGIS's IPC port from
                    // non-loopback addresses. Only 127.0.0.1 should ever connect.
                    // This prevents external processes from sending fake commands.
                    if let Err(e) = protect_ipc_port(&mut responder) {
                        tracing::warn!("WFP: Could not protect IPC port: {}", e);
                    } else {
                        info!("WFP: IPC port {} protected (loopback only)", AEGIS_IPC_PORT);
                    }

                    run_firewall_thread(fw_rx, responder, state_for_fw, fw_rt_handle);
                }
                Err(e) => {
                    tracing::warn!(
                        "WFP: Firewall unavailable: {}. Detection continues without blocking.",
                        e
                    );
                }
            }
        })?;

    let fw_tx = Arc::new(std::sync::Mutex::new(fw_tx));

    // ── Report channel ─────────────────────────────────────────────────────────

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

    // ── Phase 2: ETW ───────────────────────────────────────────────────────────

    let etw_handles = start_etw_consumers(Arc::clone(&state), report_tx.clone());

    // ── ETW heartbeat monitor ──────────────────────────────────────────────────
    // Checks every 60 seconds that ETW sessions are still alive.
    // If a session goes silent, it may have been tampered with (T1562)
    // or crashed. Either way, we alert.
    // etw_handles.last_event_times is a shared map of provider → last event Instant.

    let report_tx_heartbeat = report_tx.clone();
    let heartbeat_times = etw_handles.last_event_times.clone();

    tokio::spawn(async move {
        let mut interval = tokio::time::interval(
            tokio::time::Duration::from_secs(60)
        );
        interval.tick().await; // skip immediate first tick — give ETW time to start

        loop {
            interval.tick().await;

            let times = heartbeat_times.lock().unwrap();
            for (provider, last_event) in times.iter() {
                let silence = last_event.elapsed().as_secs();
                if silence > 60 {
                    tracing::warn!(
                        "ETW HEARTBEAT: {} has been silent for {}s — possible tampering or crash",
                        provider, silence
                    );
                    // Push as a finding so it surfaces in HELENA
                    let _ = report_tx_heartbeat.send(AgentReport {
                        agent_id:     format!("etw_heartbeat_{}", provider),
                        threat_level: crate::ipc::protocol::ThreatLevel::Active,
                        findings:     vec![crate::ipc::protocol::Finding {
                            finding_type: "etw_session_silent".to_string(),
                            severity:     0.8,
                            detail: format!(
                                "ETW provider {} has been silent for {}s. \
                                 Possible ETW tampering (T1562) or session crash.",
                                provider, silence
                            ),
                            data: serde_json::json!({
                                "provider":   provider,
                                "silence_secs": silence,
                            }),
                        }],
                    });
                }
            }
        }
    });

    // ── Approved response poller ───────────────────────────────────────────────

    let fw_tx_poller = Arc::clone(&fw_tx);
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(
            tokio::time::Duration::from_secs(5)
        );
        loop {
            interval.tick().await;
            let lock = fw_tx_poller.lock().unwrap();
            let _ = lock.send(FirewallCmd::ExecuteApproved);
        }
    });

    // ── Dispatch loop ──────────────────────────────────────────────────────────

    let state_for_dispatch = Arc::clone(&state);
    let helena_tx_dispatch  = Arc::clone(&helena_tx);
    let fw_tx_dispatch      = Arc::clone(&fw_tx);

    tokio::spawn(async move {
        let mut last_sent: HashMap<String, Instant> = HashMap::new();

        while let Some(report) = report_rx.recv().await {
            let cooldown = cooldown_for_agent(&report.agent_id);

            if cooldown > 0 {
                if let Some(last) = last_sent.get(&report.agent_id) {
                    if last.elapsed().as_secs() < cooldown {
                        let mut s = state_for_dispatch.lock().await;
                        for f in &report.findings {
                            s.write_finding(&report.agent_id, f.clone());
                        }
                        s.escalate_if_higher(report.threat_level);
                        continue;
                    }
                }
            }

            if cooldown > 0 {
                last_sent.insert(report.agent_id.clone(), Instant::now());
            }

            tracing::warn!(
                "REPORT [{}] threat={} findings={}",
                report.agent_id, report.threat_level, report.findings.len()
            );

            {
                let mut s = state_for_dispatch.lock().await;
                for f in &report.findings {
                    s.write_finding(&report.agent_id, f.clone());
                }
                s.escalate_if_higher(report.threat_level);
            }

            {
                let lock = fw_tx_dispatch.lock().unwrap();
                let _ = lock.send(FirewallCmd::Respond(report.clone()));
            }

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

    // ── Heartbeat to HELENA ────────────────────────────────────────────────────

    let state_hb     = Arc::clone(&state);
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

    info!("AEGIS Phase 3a ready — {} agents, ETW, WFP firewall, self-protection active", agent_count);
    info!("Waiting for HELENA on 127.0.0.1:{}", AEGIS_IPC_PORT);

    // Keep ETW handles alive for process lifetime
    let _etw = etw_handles;

    tokio::signal::ctrl_c().await?;
    info!("Shutdown signal received. AEGIS stopping.");

    {
        let lock = fw_tx.lock().unwrap();
        let _ = lock.send(FirewallCmd::Shutdown);
    }

    Ok(())
}

// ── Port self-protection ───────────────────────────────────────────────────────

/// Add a WFP rule blocking all inbound connections to port 47201
/// from non-loopback addresses. Called once at startup.
fn protect_ipc_port(responder: &mut Responder) -> anyhow::Result<()> {
    responder.block_port_external_only(AEGIS_IPC_PORT, "AEGIS IPC self-protection")
}

// ── Firewall thread loop ───────────────────────────────────────────────────────

fn run_firewall_thread(
    rx:            std::sync::mpsc::Receiver<FirewallCmd>,
    mut responder: Responder,
    state:         Arc<Mutex<AegisState>>,
    rt:            tokio::runtime::Handle,
) {
    loop {
        match rx.recv() {
            Ok(FirewallCmd::Respond(report)) => {
                let mut s = rt.block_on(state.lock());
                let actions = responder.respond(&report, &mut s);
                for action in actions {
                    info!("Firewall action: {}", action);
                }
            }
            Ok(FirewallCmd::ExecuteApproved) => {
                let mut s = rt.block_on(state.lock());
                responder.execute_approved(&mut s);
            }
            Ok(FirewallCmd::Shutdown) | Err(_) => {
                info!("Firewall thread shutting down");
                responder.cleanup();
                break;
            }
        }
    }
}
