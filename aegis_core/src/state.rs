// src/state.rs
//
// Phase 3a change:
//   - add_pending() now enforces a 50-item cap on pending_responses.
//     If the queue is full, the oldest non-approved entry is dropped
//     before the new one is added. This prevents queue flooding attacks
//     where a compromised process generates thousands of fake findings
//     to exhaust memory and hide real threats.

use chrono::{DateTime, Utc};
use std::collections::HashMap;
use serde::{Deserialize, Serialize};

use crate::ipc::protocol::{Finding, ResponseTier, ThreatLevel, SharedContext};

const MAX_PENDING_RESPONSES: usize = 50;

// ── Pending response package ───────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResponsePackage {
    pub package_id:  String,
    pub tier:        ResponseTier,
    pub trigger:     String,
    pub description: String,
    pub actions:     Vec<PlannedAction>,
    pub created_at:  DateTime<Utc>,
    pub approved:    bool,
    pub approved_by: Option<String>,
    pub approved_at: Option<DateTime<Utc>>,
    pub reason_code: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlannedAction {
    pub action_type: String,
    pub params:      serde_json::Value,
}

// ── Shared threat context entry ────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThreatContextEntry {
    pub agent_id:   String,
    pub finding:    Finding,
    pub written_at: DateTime<Utc>,
    pub read_count: u32,
}

// ── Central state ──────────────────────────────────────────────────────────────

pub struct AegisState {
    pub threat_level:       ThreatLevel,
    pub active_agent_count: u32,
    pub pending_responses:  HashMap<String, ResponsePackage>,
    pub response_history:   Vec<ResponsePackage>,
    pub threat_context:     HashMap<String, ThreatContextEntry>,
    pub events_processed:   u64,
    pub started_at:         DateTime<Utc>,
    pub last_event_at:      Option<DateTime<Utc>>,
}

impl AegisState {
    pub fn new() -> Self {
        Self {
            threat_level:       ThreatLevel::Idle,
            active_agent_count: 0,
            pending_responses:  HashMap::new(),
            response_history:   Vec::new(),
            threat_context:     HashMap::new(),
            events_processed:   0,
            started_at:         Utc::now(),
            last_event_at:      None,
        }
    }

    pub fn uptime_seconds(&self) -> u64 {
        (Utc::now() - self.started_at).num_seconds().max(0) as u64
    }

    // ── Snapshot ──────────────────────────────────────────────────────────────

    pub fn snapshot_context(&self) -> SharedContext {
        let mut flagged_ips:   Vec<(String, f32)> = Vec::new();
        let mut flagged_pids:  Vec<(u32,    f32)> = Vec::new();
        let mut flagged_paths: Vec<(String, f32)> = Vec::new();

        for entry in self.threat_context.values() {
            let sev  = entry.finding.severity;
            let data = &entry.finding.data;

            if let Some(ip) = data.get("remote_ip").and_then(|v| v.as_str()) {
                if let Some(e) = flagged_ips.iter_mut().find(|(i, _)| i == ip) {
                    e.1 = e.1.max(sev);
                } else {
                    flagged_ips.push((ip.to_string(), sev));
                }
            }
            if let Some(pid) = data.get("pid").and_then(|v| v.as_u64()) {
                let pid = pid as u32;
                if let Some(e) = flagged_pids.iter_mut().find(|(p, _)| *p == pid) {
                    e.1 = e.1.max(sev);
                } else {
                    flagged_pids.push((pid, sev));
                }
            }
            if let Some(path) = data.get("path").and_then(|v| v.as_str()) {
                if let Some(e) = flagged_paths.iter_mut().find(|(p, _)| p == path) {
                    e.1 = e.1.max(sev);
                } else {
                    flagged_paths.push((path.to_string(), sev));
                }
            }
        }

        SharedContext { flagged_ips, flagged_pids, flagged_paths, threat_level: self.threat_level }
    }

    // ── Threat context ────────────────────────────────────────────────────────

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

        let cutoff = Utc::now() - chrono::Duration::hours(1);
        self.threat_context.retain(|_, v| v.written_at > cutoff);
    }

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

    pub fn highest_severity_for_ip(&self, ip: &str) -> f32 {
        self.threat_context.values()
            .filter(|e| e.finding.data.get("remote_ip")
                .and_then(|v| v.as_str()).map(|v| v == ip).unwrap_or(false))
            .map(|e| e.finding.severity)
            .fold(0.0_f32, f32::max)
    }

    // ── Threat level ──────────────────────────────────────────────────────────

    pub fn set_threat_level(&mut self, level: ThreatLevel) {
        if level != self.threat_level {
            tracing::info!("Threat level: {} → {}", self.threat_level, level);
            self.threat_level = level;
        }
    }

    pub fn escalate_if_higher(&mut self, level: ThreatLevel) {
        if level > self.threat_level {
            self.set_threat_level(level);
        }
    }

    // ── Response packages ─────────────────────────────────────────────────────

    /// Add a pending response package.
    /// Enforces a cap of MAX_PENDING_RESPONSES (50).
    /// If full, drops the oldest unapproved entry to make room.
    /// This prevents queue flooding attacks.
    pub fn add_pending(&mut self, pkg: ResponsePackage) {
        if self.pending_responses.len() >= MAX_PENDING_RESPONSES {
            // Find oldest unapproved entry to drop
            let oldest_key = self.pending_responses.iter()
                .filter(|(_, p)| !p.approved)
                .min_by_key(|(_, p)| p.created_at)
                .map(|(k, _)| k.clone());

            if let Some(key) = oldest_key {
                let dropped = self.pending_responses.remove(&key);
                if let Some(pkg) = dropped {
                    tracing::warn!(
                        "Pending queue full ({}) — dropped oldest: {}",
                        MAX_PENDING_RESPONSES, pkg.package_id
                    );
                    self.archive_response(pkg);
                }
            } else {
                // All entries are approved and waiting execution — don't drop any
                tracing::warn!(
                    "Pending queue full ({}) — all approved, skipping new entry {}",
                    MAX_PENDING_RESPONSES, pkg.package_id
                );
                return;
            }
        }
        self.pending_responses.insert(pkg.package_id.clone(), pkg);
    }

    pub fn approve_response(&mut self, package_id: &str, reason: &str, by: &str) -> bool {
        if let Some(pkg) = self.pending_responses.get_mut(package_id) {
            pkg.approved    = true;
            pkg.approved_by = Some(by.to_string());
            pkg.approved_at = Some(Utc::now());
            pkg.reason_code = Some(reason.to_string());
            true
        } else { false }
    }

    pub fn reject_response(&mut self, package_id: &str) -> bool {
        if let Some(pkg) = self.pending_responses.remove(package_id) {
            self.archive_response(pkg);
            true
        } else { false }
    }

    pub fn take_approved(&mut self) -> Vec<ResponsePackage> {
        let approved: Vec<String> = self.pending_responses.iter()
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
