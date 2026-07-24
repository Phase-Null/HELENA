---
tags: [aegis, security]
date: 2026-03-05
status: active
component: aegis_core/src/main.rs
---

# AEGIS Overview — Adaptive Evolving Guardian and Intelligence System

AEGIS is HELENA's security nervous system. A Rust-based security core that provides kernel-level visibility, ETW monitoring, WFP firewall, and 16 autonomous agents. It runs as a separate process alongside HELENA, connected via IPC on port 47201.

> [!quote] Why Rust?
> Python has three core problems for security:
> 1. **Performance** — GIL means agents block each other; milliseconds matter
> 2. **Memory safety** — Python's memory model lacks guarantees for security-critical code
> 3. **Kernel blindness** — Python can't interface with Windows ETW at the kernel level

---

## Three-Layer Language Model

```
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Python (HELENA, ChatEngine, Desktop)          │
│  — High-level logic, personality, conversation          │
│  — Performance-insensitive, flexibility-critical        │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Rust (AEGIS)                                  │
│  — Performance-critical agents, ETW consumers            │
│  — WFP firewall, IPC server, state management            │
│  — Memory-safe, concurrent, kernel-aware                 │
├─────────────────────────────────────────────────────────┤
│  Layer 1: Kernel (ETW, WFP, Windows APIs)               │
│  — Ring 0 visibility, driver-level defense               │
│  — Event tracing, network filtering, process monitoring  │
└─────────────────────────────────────────────────────────┤
```

---

## AEGIS Phase 3a — Current Status

```
main.rs entry point:
  ├── IPC server (IpcServer on 127.0.0.1:47201)
  ├── Firewall thread (WFP engine + Responder)
  │     └── Port 47201 self-protection (loopback only)
  ├── 16 Phase 1 agents (4 variants each):
  │     ├── NetworkMonitor v1-v4
  │     ├── FileIntegrityMonitor v1-v4
  │     ├── ProcessWatchdog v1-v4
  │     └── IntrusionDetection v1-v4
  ├── ETW consumers (3 providers)
  │     ├── Microsoft-Windows-Kernel-Process
  │     ├── Microsoft-Windows-DNS-Client
  │     └── Microsoft-Windows-Security-Auditing
  ├── ETW heartbeat monitor (60s silence = alert)
  ├── Approved response poller (5s interval)
  ├── Dispatch loop (rate-limited agent reports → HELENA alerts)
  └── Heartbeat to HELENA (30s interval)
```

---

## Key Components

| Component | Rust File | Python Bridge | Purpose |
|-----------|-----------|--------------|---------|
| IPC Server | `src/ipc/server.rs` | `aegis_python/aegis_bridge.py` | HELENA ↔ AEGIS communication |
| ETW Consumers | `src/etw/consumer.rs` | — | Kernel-level event tracing |
| ETW Providers | `src/etw/providers.rs` | — | Provider GUIDs, event IDs, suspicious patterns |
| Network Agents | `src/agents/network.rs` | — | Socket enumeration, process validation |
| File Integrity | `src/agents/integrity.rs` | — | File hash monitoring |
| Process Watchdog | `src/agents/process.rs` | — | Process lifecycle monitoring |
| Intrusion Detection | `src/agents/intrusion.rs` | — | Attack pattern recognition |
| Firewall Engine | `src/firewall/engine.rs` | — | WFP-based network blocking |
| Firewall Rules | `src/firewall/rules.rs` | — | IP/port block management |
| Firewall Responder | `src/firewall/responder.rs` | — | Automated threat response |
| State Management | `src/state.rs` | — | Central threat state + response packages |
| Integration Bridge | — | `aegis_python/helena_integration.py` | Python-side HELENA wiring |

---

## IPC Protocol

| Message Kind | Source | Direction | Content |
|-------------|--------|-----------|---------|
| `Alert` | AEGIS → HELENA | Push | Agent findings, threat details |
| `StatusReport` | AEGIS → HELENA | 30s heartbeat | Threat level, agent count, uptime |
| `Command` | HELENA → AEGIS | Request | Security commands, approvals |

---

## Threat Tiers

| Tier | Level | Automated Response |
|------|-------|-------------------|
| Monitor | Low | Log only |
| Alert | Medium | Notify HELENA, escalate |
| Contain | High | Block suspicious IPs/ports |
| Harden | High+ | Additional security measures |
| Retaliate | Critical | Active countermeasures (Bug #23 — now implemented) |
| Lockdown | Maximum | Full system isolation (Bug #23 — now implemented) |

---

## Rate Limiting

| Agent | Cooldown |
|-------|----------|
| process_watchdog | 30 seconds |
| network_monitor | 15 seconds |
| Others | No cooldown (immediate) |

---

## Related Notes

- [[ETW System]] — provider GUIDs, event callbacks, suspicious patterns
- [[Network Agent]] — NetworkMonitor v1-v4, path-validated safe processes
- [[State Management]] — AegisState, ResponsePackage, threat escalation
- [[Integration Bridge]] — Python-side AEGIS ↔ HELENA wiring
- [[Threat Model]] — three-layer architecture, defense philosophy
- [[Bug Fixes]] — AEGIS-specific bug fixes
