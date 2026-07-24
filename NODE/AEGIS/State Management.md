---
tags: [aegis, state]
date: 2026-03-05
status: active
component: aegis_core/src/state.rs
bugs: [33]
---

# State Management — AegisState and ResponsePackages

AegisState is AEGIS's central threat tracking and response management system. It maintains threat level, agent findings, response packages, and shared context for inter-agent communication.

---

## ResponsePackage (struct)

| Field | Type | Purpose |
|-------|------|---------|
| `package_id` | `String` | Unique identifier |
| `tier` | `ResponseTier` | Monitor/Alert/Contain/Harden/Retaliate/Lockdown |
| `trigger` | `String` | What triggered this response |
| `description` | `String` | Human-readable description |
| `actions` | `Vec<PlannedAction>` | Planned actions to execute |
| `created_at` | `DateTime<Utc>` | Creation timestamp |
| `approved` | `bool` | Whether operator approved execution |
| `approved_by` | `Option<String>` | Who approved it |
| `approved_at` | `Option<DateTime<Utc>>` | When approved |
| `reason_code` | `Option<String>` | Approval reason |

---

## ThreatContextEntry (struct)

| Field | Type | Purpose |
|-------|------|---------|
| `agent_id` | `String` | Which agent wrote this |
| `finding` | `Finding` | The finding itself |
| `written_at` | `DateTime<Utc>` | When written |
| `read_count` | `u32` | How many agents read it |

---

## AegisState (struct)

| Field | Type | Purpose |
|-------|------|---------|
| `threat_level` | `ThreatLevel` | Current overall threat level |
| `active_agent_count` | `u32` | Running agents |
| `pending_responses` | `HashMap<String, ResponsePackage>` | Pending response packages (max 50) |
| `response_history` | `VecDeque<ResponsePackage>` | Archived responses (max 200) |
| `threat_context` | `HashMap<String, ThreatContextEntry>` | Cross-agent shared findings |
| `events_processed` | `u64` | Total events processed |
| `started_at` | `DateTime<Utc>` | Process start time |
| `last_event_at` | `Option<DateTime<Utc>>` | Last event timestamp |

> [!info] Bug #33 — O(n) `remove(0)` → VecDeque
> `response_history` was a `Vec` with `remove(0)` which is O(n). Changed to `VecDeque` with `pop_front()` which is O(1). See [[Bug Fixes]].

---

## Key Methods

### Threat Level

| Method | Purpose |
|--------|---------|
| `set_threat_level(level)` | Set threat level, log changes |
| `escalate_if_higher(level)` | Escalate if new level > current |

### Findings

| Method | Purpose |
|--------|---------|
| `write_finding(agent_id, finding)` | Store finding in threat_context with composite key `"agent_id:finding_type:ip_or_path"` |
| `read_context_for(agent_id)` | Return all findings NOT from this agent (inter-agent sharing) |
| `highest_severity_for_ip(ip)` | Maximum severity for a specific IP address |

### Context Snapshot

```rust
fn snapshot_context(&self) -> SharedContext {
    // Aggregates flagged IPs, PIDs, and paths with their max severities
    SharedContext { flagged_ips, flagged_pids, flagged_paths, threat_level }
}
```

Used by [[Network Agent]] for severity escalation based on prior threat history.

### Response Packages

| Method | Purpose |
|--------|---------|
| `add_pending(pkg)` | Add package, enforce **50-item cap**. Drops oldest unapproved if full |
| `approve_response(package_id, reason, by)` | Mark as approved |
| `reject_response(package_id)` | Remove and archive |
| `take_approved()` | Return all approved packages for execution |

> [!warning] Pending Queue Flood Protection
> `add_pending()` enforces a 50-item cap on `pending_responses`. If the queue is full, the oldest unapproved entry is dropped and archived. If all entries are approved and waiting execution, the new entry is skipped (logged but not added). This prevents queue flooding attacks where a compromised process generates fake findings to exhaust memory.

### Archive

```rust
fn archive_response(&mut self, pkg: ResponsePackage) {
    self.response_history.push_back(pkg);
    if self.response_history.len() > 200 {
        self.response_history.pop_front();  // O(1) with VecDeque (Bug #33 fix)
    }
}
```

---

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `MAX_PENDING_RESPONSES` | 50 | Maximum pending response packages |
| Response history max | 200 | Maximum archived responses |
| Threat context retention | 1 hour | Findings older than 1 hour are purged |

---

## Related Notes

- [[Overview]] — AegisState shared between all agents via Arc<Mutex>
- [[Network Agent]] — uses snapshot_context() for IP/PID severity
- [[Integration Bridge]] — alerts pushed to HELENA from dispatch loop
- [[Bug Fixes]] — Bug #33 (Vec→VecDeque)
