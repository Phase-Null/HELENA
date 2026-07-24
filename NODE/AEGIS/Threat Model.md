---
tags: [aegis, threat]
date: 2026-03-05
status: active
source: AEGIS_virtual_defence.md
---

# Threat Model — AEGIS Virtual Defense Architecture

This note organizes the content from `AEGIS_virtual_defence.md` as an Obsidian knowledge note. It covers AEGIS's three-layer language model, threat tiers, defense philosophy, and phased development plan.

> [!quote] Why This Document Exists
> The previous security implementation was a good start but had fundamental limitations: Python is the wrong language for performance-critical components, agents were isolated rather than correlated, and the system had no kernel-level visibility — a sophisticated attacker at ring 0 would be invisible.

---

## The Three-Layer Language Model

```
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Python (HELENA, ChatEngine, Desktop)          │
│  — High-level logic, personality, conversation          │
│  — Performance-insensitive, flexibility-critical        │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Rust (AEGIS Security Core)                    │
│  — Performance-critical agents, ETW consumers            │
│  — WFP firewall, IPC server, state management            │
│  — Memory-safe, concurrent, kernel-aware                 │
├─────────────────────────────────────────────────────────┤
│  Layer 1: Kernel (ETW, WFP, Windows APIs)               │
│  — Ring 0 visibility, driver-level defense               │
│  — Event tracing, network filtering, process monitoring  │
└─────────────────────────────────────────────────────────┘
```

**Why Rust for Layer 2:**
- **Problem 1 — Performance**: Python's GIL means agents block each other. Milliseconds matter.
- **Problem 2 — Memory safety**: Python's memory model lacks guarantees for security-critical code.
- **Problem 3 — Kernel blindness**: Python can't interface with Windows ETW without C wrappers; can't write kernel drivers at all.

---

## Threat Tiers and Response Actions

| Tier | Level | Automated Response | Example |
|------|-------|-------------------|---------|
| **Monitor** | Low | Log only, no action | New process from temp directory |
| **Alert** | Medium | Notify HELENA, escalate | Suspicious DNS query (ngrok.io) |
| **Contain** | High | Block IP/port via WFP | Known malicious IP on port 4444 |
| **Harden** | High+ | Additional security measures | Multiple agents flagging same IP |
| **Retaliate** | Critical | Active countermeasures | Persistent attacker — block + monitor | ✅ (Bug #23 fix) |
| **Lockdown** | Maximum | Full system isolation | Critical infrastructure compromise | ✅ (Bug #23 fix) |

---

## Phased Development

### Phase 0 — Foundation ✅
- IPC framework (Rust ↔ Python via TCP)
- Core protocol definitions (Message, Finding, AgentReport)
- Python bridge (`aegis_python/aegis_bridge.py`)

### Phase 1 — Autonomous Agents ✅
- 16 agents (4 variants each of Network, Integrity, Process, Intrusion)
- Agent trait system (config, scan, interval, threshold)
- Cross-agent correlation via SharedContext

### Phase 2 — ETW Integration ✅
- 3 ETW provider consumers (Kernel-Process, DNS-Client, Security-Auditing)
- Suspicious pattern detection (process images, command lines, DNS queries)
- Heartbeat monitoring (60s silence = alert)

### Phase 3 — WFP Firewall ✅
- Windows Filtering Platform engine
- IP blocking, port blocking, loopback-only protection
- Response tiers with automated actions
- Port 47201 self-protection (Bug #4 fix)

### Phase 3a — Security Hardening ✅ (Current)
- Per-step SSM memory optimization
- ETW heartbeat monitoring
- Port 47201 self-protection
- VecDeque for response history (Bug #33 fix)
- UTF-8-safe string truncation (Bug #34 fix)
- Thread-safe lock initialization (Bug #39 re-audit fix)

---

## Defense Philosophy

> [!tip] Key Principles
> 1. **Detect at ring 0** — ETW provides kernel-level visibility that Python can't access
> 2. **Respond at ring 3** — WFP firewall blocks at the network layer, not application layer
> 3. **Correlate across agents** — SharedContext lets agents share findings and escalate severity
> 4. **Rate-limit alerts** — Prevent flood attacks from overwhelming HELENA
> 5. **Require approval for critical actions** — Retaliate/Lockdown tiers need operator confirmation
> 6. **Persist blocks** — IP blocks survive AEGIS restarts (Bug #27 fix)

---

## Related Notes

- [[Overview]] — AEGIS entry point, agent spawning, dispatch loop
- [[ETW System]] — provider GUIDs, event callbacks
- [[Network Agent]] — socket enumeration, process validation
- [[State Management]] — response packages, threat escalation
- [[Bug Fixes]] — all AEGIS-specific bug fixes
