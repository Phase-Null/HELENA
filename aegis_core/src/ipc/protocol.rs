// src/ipc/protocol.rs
//
// The IPC protocol between AEGIS (Rust) and HELENA (Python).
//
// Everything that crosses the bridge is serialised as newline-delimited JSON.
// One JSON object per line. This is the simplest format that is:
//   - Human readable (you can read the socket stream in a terminal)
//   - Language agnostic (Python's json module handles it trivially)
//   - Streamable (no need to frame messages with length prefixes)
//   - Debuggable (if something goes wrong you can see exactly what was sent)
//
// Transport: TCP socket on 127.0.0.1:47201
// Port 47201 is unregistered with IANA and unlikely to conflict with anything.
// Loopback only — AEGIS is never reachable from the network.
//
// Message flow:
//   HELENA → AEGIS: Commands (query status, approve response, set threat level)
//   AEGIS  → HELENA: Events (alerts, status updates, telemetry summaries)
//
// Both sides speak the same format. Direction is indicated by the `direction`
// field, which is informational only — the socket itself tells you who sent it.

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
    Monitor   = 0,  // log only, automatic
    Alert     = 1,  // notify HELENA, automatic
    Contain   = 2,  // block IP / isolate, AEGIS decides
    Harden    = 3,  // firewall changes, AEGIS decides + logs
    Retaliate = 4,  // deception layer — REQUIRES operator approval
    Lockdown  = 5,  // full isolation — REQUIRES approval + 30s delay
}

// ── Message envelope ──────────────────────────────────────────────────────────
//
// Every message has this wrapper. The `payload` field contains the actual
// command or event data, specific to each message type.

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    /// Unique ID for this message. Used to correlate responses to requests.
    pub id: String,

    /// Wall clock time the message was created.
    pub timestamp: DateTime<Utc>,

    /// Who sent this. Informational.
    pub source: MessageSource,

    /// What kind of message this is.
    pub kind: MessageKind,

    /// The actual payload. Varies by `kind`.
    pub payload: serde_json::Value,
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

    /// Serialise to a single line of JSON (no newlines within).
    pub fn to_line(&self) -> anyhow::Result<String> {
        Ok(serde_json::to_string(self)?)
    }

    /// Parse from a single line of JSON.
    pub fn from_line(line: &str) -> anyhow::Result<Self> {
        Ok(serde_json::from_str(line)?)
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
    Ping,               // health check
    QueryStatus,        // ask for current state
    QueryPending,       // ask for pending approval requests
    ApproveResponse,    // approve a Tier 4/5 response
    RejectResponse,     // reject a pending response
    SetThreatLevel,     // manually set threat level

    // AEGIS → HELENA
    Pong,               // reply to ping
    StatusReport,       // reply to QueryStatus
    PendingReport,      // reply to QueryPending
    Alert,              // unsolicited — threat detected
    ThreatLevelChange,  // threat level escalated/de-escalated
    ResponseExecuted,   // a response package was executed
    Error,              // something went wrong on the AEGIS side
}

// ── Typed payload structs ─────────────────────────────────────────────────────
//
// These are the actual data inside `payload` for each message kind.
// Rust serialises/deserialises them via serde_json::Value.
// Python just reads the JSON dict directly.

/// AEGIS → HELENA: current system state
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StatusPayload {
    pub threat_level:      ThreatLevel,
    pub active_agents:     u32,
    pub pending_responses: u32,
    pub uptime_seconds:    u64,
    pub events_processed:  u64,
    pub last_event_at:     Option<DateTime<Utc>>,
}

/// AEGIS → HELENA: a detected threat
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlertPayload {
    pub agent_id:     String,
    pub threat_level: ThreatLevel,
    pub summary:      String,       // plain English for HELENA to surface
    pub findings:     Vec<Finding>,
    pub response_tier: ResponseTier,
    pub package_id:   Option<String>, // set if Tier 4/5 pending approval
}

/// One finding from one agent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Finding {
    pub finding_type: String,
    pub severity:     f32,          // 0.0 - 1.0
    pub detail:       String,
    pub data:         serde_json::Value,
}

/// HELENA → AEGIS: approve a pending response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovePayload {
    pub package_id:  String,
    pub reason_code: String,
    pub approved_by: String,
}

/// HELENA → AEGIS: reject a pending response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RejectPayload {
    pub package_id: String,
    pub reason:     String,
}

/// HELENA → AEGIS: override threat level
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SetThreatPayload {
    pub level:  ThreatLevel,
    pub reason: String,
}

/// AEGIS → HELENA: error notification
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorPayload {
    pub code:    String,
    pub message: String,
    pub context: Option<String>,
}
