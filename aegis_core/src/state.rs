// src/state.rs
//
// The central shared state of AEGIS.
// Every agent reads from and writes to this.
// Protected by a tokio Mutex — only one writer at a time,
// but reads are fast because we clone what we need.
//
// This is also where pending response packages live,
// and where the approval gate is enforced.

use chrono::{DateTime, Utc};
use std::collections::HashMap;
use serde::{Deserialize, Serialize};

use crate::ipc::protocol::{Finding, ResponseTier, ThreatLevel};

// ── Pending response package ───────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResponsePackage {
    pub package_id:   String,
    pub tier:         ResponseTier,
    pub trigger:      String,
    pub description:  String,
    pub actions:      Vec<PlannedAction>,
    pub created_at:   DateTime<Utc>,
    pub approved:     bool,
    pub approved_by:  Option<String>,
    pub approved_at:  Option<DateTime<Utc>>,
    pub reason_code:  Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlannedAction {
    pub action_type: String,
    pub params:      serde_json::Value,
}

// ── Shared threat context entry ────────────────────────────────────────────────
//
// When an agent writes a finding, it goes here.
// Other agents read this to correlate their own findings.
// HELENA reads summarised form via the IPC status report.

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThreatContextEntry {
    pub agent_id:    String,
    pub finding:     Finding,
    pub written_at:  DateTime<Utc>,
    pub read_count:  u32,  // how many other agents have read this
}

// ── Central state ──────────────────────────────────────────────────────────────

pub struct AegisState {
    // Current assessed threat level
    pub threat_level: ThreatLevel,

    // How many agents are currently running
    pub active_agent_count: u32,

    // Pending Tier 4/5 response packages waiting for operator approval
    pub pending_responses: HashMap<String, ResponsePackage>,

    // Executed response history (last 100)
    pub response_history: Vec<ResponsePackage>,

    // Shared threat context — agents write here, others read for correlation
    // Key is a composite of agent_type + finding_type + target
    // so multiple agents can write about the same IP without colliding
    pub threat_context: HashMap<String, ThreatContextEntry>,

    // Counters
    pub events_processed: u64,
    pub started_at:       DateTime<Utc>,
    pub last_event_at:    Option<DateTime<Utc>>,
}

impl AegisState {
    pub fn new() -> Self {
        Self {
            threat_level:        ThreatLevel::Idle,
            active_agent_count:  0,
            pending_responses:   HashMap::new(),
            response_history:    Vec::new(),
            threat_context:      HashMap::new(),
            events_processed:    0,
            started_at:          Utc::now(),
            last_event_at:       None,
        }
    }

    pub fn uptime_seconds(&self) -> u64 {
        (Utc::now() - self.started_at).num_seconds().max(0) as u64
    }

    // ── Threat context ───────────────────────────────────────────────────────

    /// Agent writes a finding to the shared context.
    pub fn write_finding(&mut self, agent_id: &str, finding: Finding) {
        let key = format!("{}:{}:{}", agent_id, finding.finding_type,
            finding.data.get("remote_ip")
                .or_else(|| finding.data.get("path"))
                .or_else(|| finding.data.get("pid"))
                .unwrap_or(&serde_json::Value::Null));

        self.threat_context.insert(key, ThreatContextEntry {
            agent_id:   agent_id.to_string(),
            finding,
            written_at: Utc::now(),
            read_count: 0,
        });

        self.events_processed += 1;
        self.last_event_at = Some(Utc::now());

        // Prune old entries (older than 1 hour) to prevent unbounded growth
        let cutoff = Utc::now() - chrono::Duration::hours(1);
        self.threat_context.retain(|_, v| v.written_at > cutoff);
    }

    /// Agent reads the threat context to correlate with its own findings.
    /// Returns all entries from other agents (not itself).
    /// Also increments read_count so we can see what's being used.
    pub fn read_context_for(&mut self, agent_id: &str) -> Vec<ThreatContextEntry> {
        let mut result = Vec::new();
        for entry in self.threat_context.values_mut() {
            if entry.agent_id != agent_id {
                entry.read_count += 1;
                result.push(entry.clone());
            }
        }
        result
    }

    /// Find the highest severity finding in the context involving a given IP.
    /// Used by agents to boost their own severity if the IP is already flagged.
    pub fn highest_severity_for_ip(&self, ip: &str) -> f32 {
        self.threat_context
            .values()
            .filter(|e| {
                e.finding.data.get("remote_ip")
                    .and_then(|v| v.as_str())
                    .map(|v| v == ip)
                    .unwrap_or(false)
            })
            .map(|e| e.finding.severity)
            .fold(0.0_f32, f32::max)
    }

    // ── Threat level ─────────────────────────────────────────────────────────

    pub fn set_threat_level(&mut self, level: ThreatLevel) {
        if level != self.threat_level {
            tracing::info!(
                "Threat level: {} → {}",
                self.threat_level,
                level
            );
            self.threat_level = level;
        }
    }

    /// Escalate threat level — only goes up, never down automatically.
    /// De-escalation requires explicit operator action or a clear-all.
    pub fn escalate_if_higher(&mut self, level: ThreatLevel) {
        if level > self.threat_level {
            self.set_threat_level(level);
        }
    }

    // ── Response packages ─────────────────────────────────────────────────────

    pub fn add_pending(&mut self, pkg: ResponsePackage) {
        self.pending_responses.insert(pkg.package_id.clone(), pkg);
    }

    /// Approve a pending response. Returns true if found and approved.
    /// Does NOT execute — execution is handled by the response engine.
    pub fn approve_response(&mut self, package_id: &str, reason: &str, by: &str) -> bool {
        if let Some(pkg) = self.pending_responses.get_mut(package_id) {
            pkg.approved    = true;
            pkg.approved_by = Some(by.to_string());
            pkg.approved_at = Some(Utc::now());
            pkg.reason_code = Some(reason.to_string());
            true
        } else {
            false
        }
    }

    pub fn reject_response(&mut self, package_id: &str) -> bool {
        if let Some(pkg) = self.pending_responses.remove(package_id) {
            // Move to history as unapproved
            self.archive_response(pkg);
            true
        } else {
            false
        }
    }

    pub fn take_approved(&mut self) -> Vec<ResponsePackage> {
        let approved: Vec<String> = self.pending_responses
            .iter()
            .filter(|(_, p)| p.approved)
            .map(|(k, _)| k.clone())
            .collect();

        approved.into_iter()
            .filter_map(|id| self.pending_responses.remove(&id))
            .collect()
    }

    fn archive_response(&mut self, pkg: ResponsePackage) {
        self.response_history.push(pkg);
        if self.response_history.len() > 200 {
            self.response_history.remove(0);
        }
    }
}
