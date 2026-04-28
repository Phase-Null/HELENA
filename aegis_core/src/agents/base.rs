// src/agents/base.rs
//
// Agent trait, AgentConfig, AgentReport, and spawn_agent().
//
// SharedContext is defined in ipc::protocol (not here) to avoid a
// circular dependency: state.rs needs SharedContext, agents::base needs
// AegisState — if SharedContext lived here that would be a cycle.
// Centralising in ipc::protocol means both state and base import from
// one place with no cycle.

use std::sync::Arc;
use tokio::sync::{Mutex, mpsc};
use tokio::time::{interval, Duration};
use tracing::{debug, warn};

use crate::state::AegisState;
use crate::ipc::protocol::{Finding, SharedContext, ThreatLevel};

// ── Agent configuration ───────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct AgentConfig {
    pub id:            String,
    pub interval_secs: u64,
    pub threshold:     f32,
}

impl AgentConfig {
    pub fn new(agent_type: &str, variant: u8, interval_secs: u64, threshold: f32) -> Self {
        Self {
            id: format!("{}_v{}", agent_type, variant),
            interval_secs,
            threshold,
        }
    }
}

// ── Agent trait ───────────────────────────────────────────────────────────────

/// All AEGIS agents implement this trait.
///
/// scan() performs monitoring and returns findings.
/// It runs in spawn_blocking so synchronous I/O is allowed.
/// Agents must be Send + Sync to be shared across threads.
pub trait Agent: Send + Sync + 'static {
    fn config(&self) -> &AgentConfig;
    fn scan(&self, context: &SharedContext) -> Vec<Finding>;
}

// ── Agent report ──────────────────────────────────────────────────────────────

#[derive(Debug)]
pub struct AgentReport {
    pub agent_id:     String,
    pub threat_level: ThreatLevel,
    pub findings:     Vec<Finding>,
}

// ── Spawn helper ──────────────────────────────────────────────────────────────

/// Spawn a single agent as a long-running Tokio task.
///
/// Loop:
///   1. Wait for configured interval
///   2. Snapshot shared context (brief lock)
///   3. Run scan() in spawn_blocking (blocking thread — safe for sync I/O)
///   4. Filter findings below threshold
///   5. Write findings back to state
///   6. Send report if anything found
pub fn spawn_agent(
    agent:     Arc<dyn Agent>,
    state:     Arc<Mutex<AegisState>>,
    report_tx: mpsc::UnboundedSender<AgentReport>,
) {
    tokio::spawn(async move {
        let cfg = agent.config().clone();
        let mut ticker = interval(Duration::from_secs(cfg.interval_secs));
        ticker.tick().await; // skip immediate first tick

        loop {
            ticker.tick().await;

            // 1. Snapshot context — hold lock as briefly as possible
            let context = {
                let s = state.lock().await;
                s.snapshot_context()
            };

            // 2. Run scan in blocking thread
            let agent_clone = Arc::clone(&agent);
            let findings = tokio::task::spawn_blocking(move || {
                agent_clone.scan(&context)
            }).await;

            let findings = match findings {
                Ok(f)  => f,
                Err(e) => {
                    warn!("Agent {} panicked: {}", cfg.id, e);
                    continue;
                }
            };

            // 3. Filter below threshold
            let findings: Vec<Finding> = findings.into_iter()
                .filter(|f| f.severity >= cfg.threshold)
                .collect();

            if findings.is_empty() {
                debug!("Agent {} — nothing to report", cfg.id);
                continue;
            }

            // 4. Write to shared state for correlation
            {
                let mut s = state.lock().await;
                for finding in &findings {
                    s.write_finding(&cfg.id, finding.clone());
                }
            }

            // 5. Assess threat level and send report
            let max_sev     = findings.iter().map(|f| f.severity).fold(0.0_f32, f32::max);
            let threat_level = severity_to_threat(max_sev);

            let report = AgentReport {
                agent_id: cfg.id.clone(),
                threat_level,
                findings,
            };

            if let Err(e) = report_tx.send(report) {
                warn!("Agent {} could not send report: {}", cfg.id, e);
            }
        }
    });
}

// ── Helper ────────────────────────────────────────────────────────────────────

pub fn severity_to_threat(severity: f32) -> ThreatLevel {
    if severity >= 0.9      { ThreatLevel::Critical }
    else if severity >= 0.6 { ThreatLevel::Active   }
    else if severity >= 0.3 { ThreatLevel::Elevated }
    else                    { ThreatLevel::Idle      }
}
