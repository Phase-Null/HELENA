// src/ipc/protocol.rs
//
// All shared types used across the AEGIS codebase.
// Lives in ipc/ because the IPC bridge is the reason these types exist,
// but SharedContext and Finding are also used by agents and state.
// Centralising here breaks any circular dependency risk.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ── Threat levels ─────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ThreatLevel {
    Idle     = 0,
    Elevated = 1,
    Active   = 2,
    Critical = 3,
}

impl ThreatLevel {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Idle     => "IDLE",
            Self::Elevated => "ELEVATED",
            Self::Active   => "ACTIVE",
            Self::Critical => "CRITICAL",
        }
    }
}

impl std::fmt::Display for ThreatLevel {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

// ── Response tiers ────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ResponseTier {
    Monitor   = 0,
    Alert     = 1,
    Contain   = 2,
    Harden    = 3,
    Retaliate = 4,  // requires operator approval
    Lockdown  = 5,  // requires approval + 30s delay
}

// ── Finding — one observation from one agent ──────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Finding {
    pub finding_type: String,
    pub severity:     f32,       // 0.0 - 1.0
    pub detail:       String,    // human-readable, surfaces in HELENA chat
    pub data:         serde_json::Value,  // agent-specific structured data
}

// ── SharedContext — lightweight correlation snapshot ──────────────────────────
//
// Built from AegisState before each agent scan.
// Passed into Agent::scan() so agents can correlate with other agents'
// findings WITHOUT holding the async Mutex during blocking I/O.
//
// Lives here (not in agents::base or state) to break the circular
// dependency that would result from state importing agents and vice versa.

#[derive(Debug, Clone)]
pub struct SharedContext {
    /// IPs flagged by any agent, with highest known severity
    pub flagged_ips:   Vec<(String, f32)>,
    /// PIDs flagged by any agent
    pub flagged_pids:  Vec<(u32, f32)>,
    /// Paths flagged by any agent
    pub flagged_paths: Vec<(String, f32)>,
    /// Current system-wide threat level
    pub threat_level:  ThreatLevel,
}

impl SharedContext {
    pub fn empty() -> Self {
        Self {
            flagged_ips:   Vec::new(),
            flagged_pids:  Vec::new(),
            flagged_paths: Vec::new(),
            threat_level:  ThreatLevel::Idle,
        }
    }

    /// Highest severity seen for this IP across all agents. 0.0 if not flagged.
    pub fn ip_severity(&self, ip: &str) -> f32 {
        self.flagged_ips.iter()
            .find(|(i, _)| i == ip)
            .map(|(_, s)| *s)
            .unwrap_or(0.0)
    }

    /// Highest severity seen for this PID. 0.0 if not flagged.
    pub fn pid_severity(&self, pid: u32) -> f32 {
        self.flagged_pids.iter()
            .find(|(p, _)| *p == pid)
            .map(|(_, s)| *s)
            .unwrap_or(0.0)
    }
}

// ── Message envelope ──────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub id:        String,
    pub timestamp: DateTime<Utc>,
    pub source:    MessageSource,
    pub kind:      MessageKind,
    pub payload:   serde_json::Value,
}

impl Message {
    pub fn new(source: MessageSource, kind: MessageKind, payload: serde_json::Value) -> Self {
        Self {
            id:        Uuid::new_v4().to_string(),
            timestamp: Utc::now(),
            source,
            kind,
            payload,
        }
    }

    pub fn to_line(&self) -> anyhow::Result<String> {
        Ok(serde_json::to_string(self)?)
    }

    pub fn from_line(line: &str) -> anyhow::Result<Self> {
        Ok(serde_json::from_str::<Self>(line)?)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MessageSource {
    Aegis,
    Helena,
}

// ── Message kinds ─────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MessageKind {
    // HELENA → AEGIS
    Ping,
    QueryStatus,
    QueryPending,
    ApproveResponse,
    RejectResponse,
    SetThreatLevel,
    // AEGIS → HELENA
    Pong,
    StatusReport,
    PendingReport,
    Alert,
    ThreatLevelChange,
    ResponseExecuted,
    Error,
}

// ── Typed payloads ────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StatusPayload {
    pub threat_level:      ThreatLevel,
    pub active_agents:     u32,
    pub pending_responses: u32,
    pub uptime_seconds:    u64,
    pub events_processed:  u64,
    pub last_event_at:     Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlertPayload {
    pub agent_id:      String,
    pub threat_level:  ThreatLevel,
    pub summary:       String,
    pub findings:      Vec<Finding>,
    pub response_tier: ResponseTier,
    pub package_id:    Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovePayload {
    pub package_id:  String,
    pub reason_code: String,
    pub approved_by: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RejectPayload {
    pub package_id: String,
    pub reason:     String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SetThreatPayload {
    pub level:  ThreatLevel,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorPayload {
    pub code:    String,
    pub message: String,
    pub context: Option<String>,
}
