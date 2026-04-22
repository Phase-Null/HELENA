# AEGIS — Adaptive Evolving Guardian and Intelligence System
## Master Architecture Plan for HELENA Integration
### Phase-Null / April 2026

---

## PREAMBLE — WHY THIS DOCUMENT EXISTS

The previous security implementation was a good start but had fundamental
limitations: Python is the wrong language for the performance-critical
components, the agents were isolated rather than correlated, and the
system had no kernel-level visibility — meaning a sophisticated attacker
operating at ring 0 would be invisible to it.

This plan addresses all of that. We build in stages, validate each stage
before moving to the next, and the result is something genuinely
professional-grade rather than a script collection dressed up as a
security system.

---

## SECTION 1 — LANGUAGE ARCHITECTURE

The previous Python-only approach has three core problems:

**Problem 1 — Performance.** Python's GIL means agents running in threads
are not truly concurrent. On a CPU-bound security scan, they block each
other. On a modern attacker's timeline, milliseconds matter.

**Problem 2 — Memory safety.** Python's memory model doesn't give us
the guarantees we need for security-critical code. A memory corruption
bug in a security agent is a catastrophic vulnerability.

**Problem 3 — Kernel blindness.** Python cannot interface with Windows
ETW (Event Tracing for Windows) at the kernel level without wrapping
a C extension, and it cannot write kernel drivers at all. An attacker
operating at ring 0 — with a rootkit — is simply invisible to
a Python-only security system.

### The Three-Layer Language Model

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 1 — KERNEL / OS INTERFACE                        │
│  Language: Rust                                         │
│  What: ETW consumer (Windows), kernel callbacks,        │
│         WFP packet inspection, process telemetry        │
│  Why Rust: Memory safe at ring 0 adjacent code,         │
│            zero GC pauses, direct Windows API access,   │
│            Microsoft themselves are rewriting Windows    │
│            components in Rust (confirmed 2025)          │
├─────────────────────────────────────────────────────────┤
│  LAYER 2 — AGENT NETWORK / CORRELATION ENGINE           │
│  Language: Rust (with Tokio async runtime)              │
│  What: 32+ agents, shared threat context, correlation,  │
│         honeypots, deception layer, firewall control    │
│  Why Rust: True concurrency without GIL, async I/O      │
│            at near-C speed, sends findings to Layer 3   │
├─────────────────────────────────────────────────────────┤
│  LAYER 3 — HELENA INTEGRATION / INTELLIGENCE LAYER      │
│  Language: Python (existing HELENA codebase)            │
│  What: HELENA receives telemetry from Rust via IPC,     │
│         makes decisions, presents to Phase-Null,        │
│         gates approvals for Tier 4-5 responses          │
│  Why Python: HELENA is Python. We don't rewrite her.    │
│              The Rust core talks to Python over a       │
│              named pipe or local socket.                │
└─────────────────────────────────────────────────────────┘
```

The Rust core and Python HELENA communicate via a local Unix socket
(or named pipe on Windows). HELENA sends commands to Rust. Rust sends
telemetry and alerts to HELENA. Neither depends on the other to be
running — AEGIS operates independently and reports in.

---

## SECTION 2 — THREAT MODEL

Before building defenses, we map what we're defending against.
Based on MITRE ATT&CK v17.1 (April 2025), the threat categories
most relevant to HELENA's operational profile:

### Relevant Tactic Categories (MITRE ATT&CK)

```
TA0001 — Initial Access
    T1566  Phishing (not HELENA's primary risk but HELENA monitors email
            via honeytokens)
    T1190  Exploit Public-Facing Application
    T1133  External Remote Services

TA0002 — Execution  
    T1059  Command and Scripting Interpreter
           T1059.001 PowerShell
           T1059.003 Windows Command Shell
    T1106  Native API (direct syscalls to avoid ETW)
    T1053  Scheduled Task/Job

TA0003 — Persistence
    T1547  Boot/Logon Autostart Execution
    T1543  Create/Modify System Process (services)
    T1136  Create Account

TA0004 — Privilege Escalation
    T1068  Exploitation for Privilege Escalation
    T1055  Process Injection (DLL injection, process hollowing)
    T1134  Access Token Manipulation

TA0005 — Defense Evasion (HIGHEST PRIORITY — this is what bypasses us)
    T1562  Impair Defenses
           T1562.001 Disable/Modify Tools
           T1562.006 ETW Patching ← SPECIFICALLY TARGETS US
    T1055  Process Injection (masquerade as legitimate process)
    T1036  Masquerading
    T1070  Indicator Removal (log tampering)

TA0006 — Credential Access
    T1003  OS Credential Dumping (mimikatz-class tools)
    T1110  Brute Force

TA0007 — Discovery
    T1082  System Information Discovery
    T1083  File and Directory Discovery
    T1057  Process Discovery

TA0008 — Lateral Movement (low risk for single-machine HELENA)
    T1021  Remote Services

TA0009 — Collection
    T1005  Data from Local System (targeting HELENA's memory and logs)
    T1056  Input Capture (keylogging)

TA0011 — Command and Control
    T1071  Application Layer Protocol (HTTPS C2)
    T1572  Protocol Tunneling

TA0040 — Impact
    T1486  Data Encrypted for Impact (ransomware)
    T1490  Inhibit System Recovery
```

### Priority Defense Order

Based on this: the highest-value defenses are:
1. ETW integrity monitoring (stops T1562.006 — the thing that blinds us)
2. Process injection detection (stops T1055 — masquerading as us)
3. Credential dump detection (stops T1003 — mimikatz etc.)
4. File integrity for HELENA's own code (stops persistent modification)
5. Network anomaly detection (stops C2 communication)

---

## SECTION 3 — AGENT ARCHITECTURE (REVISED)

### On Agent Communication

You asked whether agents should talk to each other. The answer is:
**yes, but indirectly, through a shared correlation engine.**

Direct agent-to-agent communication creates trust vulnerabilities.
If Agent A is compromised, it can poison Agent B's data.

Instead, all agents write to and read from a **Shared Threat Context**
— a Rust data structure protected by a read-write lock. No agent trusts
another's conclusions directly. Each agent sees the raw data other agents
have written and can factor that into its own analysis.

```
Agent A observes: suspicious IP 192.168.1.100 connecting on port 4444
→ writes to SharedThreatContext: {ip: "192.168.1.100", severity: 0.7}

Agent B (intrusion detection) independently sees: 15 failed logins
from 192.168.1.100 in 60 seconds
→ reads SharedThreatContext, sees IP already flagged
→ elevates own finding severity from 0.5 to 0.9
→ writes correlated finding

HELENA receives: correlated multi-agent finding at 0.9 severity
instead of two separate 0.5/0.7 findings
```

This is *more* powerful than direct agent communication, because
HELENA sees the correlation rather than raw noise, and compromised
agents can't lie to each other — they can only write their own data.

### Agent Types (Expanded to 8 Types)

```
Type A — Network Monitor        × 4 variants
Type B — Intrusion Detection    × 4 variants  
Type C — Vulnerability Scanner  × 4 variants  (passive, local only)
Type D — Traffic Analyzer       × 4 variants
Type E — File Integrity         × 4 variants
Type F — Process Watchdog       × 4 variants
Type G — Firewall Controller    × 4 variants
Type H — Incident Responder     × 4 variants
──────────────────────────────────────────
          32 agents total

+ Type I — Deception Layer      × 4 variants  (NEW — Tier 4+ only)
```

Type I — the Deception Layer — is your "retaliatory" class. It doesn't
attack back. Instead, when activated (requires admin approval), it:
- Deploys honeypots on ports the attacker is probing
- Feeds the attacker false data (fake file trees, fake credentials)
- Tarpits connections (slows responses to waste attacker time)
- Runs a passive fingerprinting sweep on observable traffic
- Generates canary tokens and logs when they're accessed

This is legally clean in every jurisdiction. It's your machine,
your network, your data. You're allowed to put fake files on your
own hard drive. You're allowed to answer connections to your own
ports with garbage data. You're not probing their machine.

---

## SECTION 4 — KERNEL-LEVEL MONITORING

### Windows ETW (Event Tracing for Windows)

ETW is Windows' built-in kernel telemetry system. Running at ring 0
adjacent, it provides data that userspace monitoring simply cannot see:
- Process creation/termination (with full command line)
- DLL loads into processes
- Remote memory allocation (T1055 — process injection)
- APC queue manipulation (another injection vector)
- Handle creation (who's touching what)
- Network socket operations at the syscall level

AEGIS's Rust ETW consumer subscribes to:

```
Microsoft-Windows-Kernel-Process     — process/thread/image events
Microsoft-Windows-Kernel-Network     — network at syscall level  
Microsoft-Windows-Threat-Intelligence — remote allocation, APC, injection
Microsoft-Windows-Security-Auditing  — login events, privilege changes
Microsoft-Windows-Windows-Defender   — if Windows Defender is running
```

The Threat Intelligence provider is particularly important:
it fires when a process allocates memory in *another* process's
address space — which is the core operation of process injection.
Standard userspace monitoring cannot see this. ETW:TI can.

### ETW Anti-Tamper

A sophisticated attacker will attempt to disable ETW before operating
(T1562.006 — ETW patching). AEGIS monitors for this specifically:

- The Rust ETW consumer runs as a Protected Process Light (PPL)
  service, which cannot be killed by standard process termination
- It monitors the ETW dispatch table in memory for patches
- If NtTraceEvent in NTDLL is patched (the classic evasion), it detects
  the memory modification and escalates to CRITICAL

This is what the Sanctum EDR project demonstrated — ETW tampering
at userspace can be caught by a kernel-mode observer that the
tampering tool cannot itself reach.

---

## SECTION 5 — FIREWALL ARCHITECTURE

"Can we build better firewalls" — yes, substantially.

### Current State (netsh/iptables calls)

Simple IP blocking. Static rules. No stateful inspection. No
understanding of traffic patterns or protocol semantics.

### AEGIS Firewall (WFP-based)

Windows Filtering Platform (WFP) is what modern commercial firewalls
(including Windows Defender Firewall itself) sit on. It operates in
the kernel network stack, allowing packet inspection at multiple points:

```
Network Card
    ↓
[WFP Layer: FWPM_LAYER_INBOUND_IPPACKET_V4]    ← raw IP, pre-reassembly
    ↓
[WFP Layer: FWPM_LAYER_INBOUND_TRANSPORT_V4]   ← transport layer (TCP/UDP)
    ↓
[WFP Layer: FWPM_LAYER_ALE_AUTH_RECV_ACCEPT_V4] ← application layer, post-accept
    ↓
Application
```

AEGIS registers WFP callouts at multiple layers. This allows:

**Stateful connection tracking** — track the full state of every TCP
connection. A SYN without a proper handshake is immediately suspicious.
A connection to a suspicious port from an unknown process is flagged.

**Protocol anomaly detection** — HTTP traffic on port 443? DNS traffic
to unusual resolvers? HTTPS to an IP that doesn't resolve? All flagged.

**Dynamic rule injection** — when an agent identifies a threat,
AEGIS adds a WFP filter rule in milliseconds. No netsh round-trip.
No reboot. The rule is live immediately.

**Geofencing at the kernel level** — MaxMind GeoLite2 database loaded
into memory. IP ranges by country/ASN evaluated in the kernel path.
If HELENA never needs to talk to servers in certain regions, block them.

**Port knocking** — AEGIS implements port knocking in WFP. External
connections to HELENA's management ports are blocked unless the
correct knock sequence (connection attempts to specific ports in order)
is observed first. No scanner ever sees the real ports.

### DNS Security

AEGIS intercepts DNS resolution via WFP and maintains:
- A local blocklist of known malicious domains (updated from threat feeds)
- Rate limiting on DNS queries (sudden burst = domain generation algorithm)
- Logging of all domain lookups for correlation with network connections

---

## SECTION 6 — ENCRYPTION AND DATA PROTECTION (REVISED)

The multidimensional encoding from the previous implementation stays,
but we add:

### At-Rest Encryption

HELENA's sensitive data (conversations, facts, memory, API keys)
should be encrypted at rest using AES-256-GCM with:
- Key derived from a hardware-bound secret (Windows DPAPI or TPM if available)
- Key rotation every 90 days, previous keys retained for 180 days
- Encrypted fields individually rather than whole-file encryption —
  so HELENA can read individual facts without decrypting everything

### In-Memory Protection

Python doesn't give us great tools here, but:
- API keys and credentials stored as `bytearray` objects which can be
  explicitly zeroed after use (unlike `bytes` which is immutable)
- Sensitive strings kept in memory only for the minimum time needed
- The Rust layer never passes plaintext credentials over the IPC bridge

### Cryptographic Audit Log

Every security event is logged with a cryptographic chain:
```
entry_n = {
    timestamp: ...,
    event: ...,
    prev_hash: hash(entry_n-1)
    hmac: HMAC(entry_n, log_key)
}
```

Any deletion or modification of a log entry breaks the chain.
AEGIS detects this on every startup and alerts.

### The Encoding Stack (Kept from Previous Design)

Huffman → AES-256-GCM → ChaCha20-Poly1305 → LSB steganography

This stays. But we add a sixth layer for highly sensitive data:

**Layer 0 (applied before Huffman):** Data scattering.
Split the plaintext into N chunks. Encrypt each chunk with a different
derived key. Store chunks in different locations. Reconstruction
requires all N keys and knowledge of the chunking scheme.
An attacker who finds one piece has an encrypted fragment with
no context about what it belongs to or how many pieces exist.

---

## SECTION 7 — DECEPTION LAYER (TYPE I AGENTS)

This is what you meant by "retaliatory" — making life as difficult
as possible for an attacker while remaining entirely on your own
turf.

### What Type I Agents Do (all require Tier 4 approval)

**I-V1 — Honeypot Deployer**
Spins up low-interaction honeypots on ports the attacker is probing.
Mimics SSH/FTP/HTTP. Logs every command. Feeds plausible but useless
responses. Attacker wastes time, HELENA learns their tools and method.

**I-V2 — Tarpit**
For connections from flagged IPs: artificially slow responses to
maximum. A port scan that normally takes 2 seconds now takes 45 minutes.
A brute force tool that tries 1000 passwords per second now manages 1.
No data is given. Time is wasted. Attacker's tools may time out.

**I-V3 — False Data Injector**
Creates a realistic-looking fake directory structure with fake credentials,
fake source code, fake API keys (all honeytokens). If the attacker
gets past the perimeter, they find what looks like a goldmine.
Every "credential" they try triggers an alert. Every file they open
has been accessed. Every key they use is a canary.

**I-V4 — Passive Fingerprinter**
Analyses all observable traffic from the attacking source:
TTL values, TCP window sizes, timing patterns, command sequences.
Determines: automated or manual? What tools? What OS? Skill level?
This data informs response and, if needed, incident reporting.

### What AEGIS Does NOT Do (legal boundary, kept clear)

- Does not probe or scan the attacking system
- Does not send unsolicited packets to the attacker's IP
- Does not attempt to execute code on the attacker's machine
- Does not disrupt the attacker's internet connection or other services

Everything above is on your machine, your network, your data.
Clean legal line.

---

## SECTION 8 — AGENT HARDENING

You asked: are the agents themselves vulnerable?

Yes. Here is the specific attack surface and the mitigations:

### Attack 1 — Kill the agent processes

A sufficiently privileged attacker can kill Python processes.
Mitigation: The Rust core runs as a Windows Service with PPL
(Protected Process Light) level. Standard process termination APIs
cannot kill PPL services. The service watchdog restarts any component
that dies within 5 seconds.

### Attack 2 — Flood the report queue (DoS the security layer)

Sending thousands of fake events to exhaust HELENA's attention.
Mitigation: The Shared Threat Context rate-limits per-source reporting.
Any source generating more than 100 events/second is automatically
suspected as a noisy agent and its data is quarantined pending review.

### Attack 3 — Modify the agents' own code before baseline

An attacker who can write to disk before AEGIS starts can poison
the baseline so file modifications are not detected.
Mitigation: AEGIS stores signed hashes of all critical files on first
install in a location that requires admin access to modify. The signing
key is hardware-bound via DPAPI. Hashes are verified against the
signed set, not the runtime baseline.

### Attack 4 — Disable ETW (T1562.006)

An attacker patches NtTraceEvent in NTDLL to blind our ETW consumer.
Mitigation: The ETW:TI provider operates from the kernel. User-space
patching cannot reach it. If the userspace ETW stops reporting,
the kernel-side consumer still fires. A sudden silence from userspace
ETW is itself a detection signal.

### Attack 5 — Corrupt the audit log

Mitigation: Cryptographic hash chain. Any modification breaks
the chain. AEGIS verifies chain integrity on startup and periodically.

### Attack 6 — Inject code into AEGIS processes

Process injection (T1055) against the security agents themselves.
Mitigation: The Rust core registers itself with the Windows
kernel's process protection callbacks. Any attempt to open a handle
to AEGIS's process with PROCESS_VM_WRITE is logged via ETW:TI.
This is observable even if the injection succeeds.

---

## SECTION 9 — HELENA INTEGRATION DESIGN

AEGIS is designed to feel like a natural extension of HELENA, not
a bolt-on. From HELENA's perspective, security information arrives
as context she can reference and act on, just like memory or emotion.

### Natural Language Interface

HELENA should be able to:
- "What's the current threat level?" → reads from AEGIS state
- "Someone tried to access HELENA from outside" → she already knows
- "Show me recent security events" → formatted report from AEGIS log
- "Is anything suspicious happening?" → AEGIS assessment summary
- "Approve response ABC123, reason: known attacker IP from earlier scan"
  → routes to SecurityContext.approve_response()

This means AEGIS findings are injected into HELENA's context at session
start (like FactStore entries), and HELENA's tool detection routes
security-related commands to AEGIS command handlers.

### Emotion Integration

Security events should affect HELENA's emotional state:
- Active threat: CONCERN spikes, DETERMINATION follows
- All clear after threat resolved: SATISFACTION
- Repeated probe attempts: FRUSTRATION
- Novel attack pattern: CURIOSITY

This makes security feel genuinely integrated into HELENA's identity
rather than a separate subsystem she's just reporting on.

---

## SECTION 10 — BUILD PLAN (PHASE BY PHASE)

### Phase 0 — Environment and Toolchain (1 session)
Set up Rust toolchain. Create `aegis/` directory alongside HELENA.
Define the IPC protocol between Rust and Python. Write protocol spec.
Write a minimal "hello world" that proves the bridge works.
**Test:** Python sends command → Rust responds → HELENA receives.

### Phase 1 — Shared Threat Context + Base Agents (1-2 sessions)
Implement SharedThreatContext in Rust (read-write locked hash map).
Port and rewrite the four existing agent types in Rust:
Type A (Network), Type E (File Integrity), Type F (Process), Type B (IDS).
Implement variant system. Wire to SharedThreatContext.
**Test:** Simulate a suspicious process. Verify all four agent types
detect it and SharedThreatContext reflects correlated severity.

### Phase 2 — ETW Consumer (1 session)
Implement Rust ETW consumer subscribing to the four key providers.
Especially ETW:TI for injection detection.
Implement ETW anti-tamper detection.
**Test:** Simulate NtTraceEvent patch. Verify AEGIS detects it
before and after the patch.

### Phase 3 — WFP Firewall (1-2 sessions)
Implement WFP callout driver (or WFP usermode filter — start with
usermode, which doesn't need a kernel driver signing certificate).
Implement stateful connection tracking.
Implement dynamic rule injection from agent findings.
**Test:** Block an IP dynamically. Verify connection is dropped
at kernel level. Verify rule survives a HELENA restart.

### Phase 4 — Security Context + Permission Gates (1 session)
Port SecurityContext from Python to Rust.
Implement the approval API that Python/HELENA calls over IPC.
Implement the Tier 4-5 gate with the 30-second lockdown delay.
**Test:** Trigger a Tier 4 response. Verify it does not execute
without approval. Approve it. Verify it executes exactly once.

### Phase 5 — Deception Layer (1 session)
Implement Type I agents (honeypot, tarpit, false data, fingerprinter).
Wire to Tier 4 approval gate.
**Test:** Simulate attacker connecting to honeypot. Verify logs
capture commands. Verify tarpit actually slows connection rate.

### Phase 6 — Encryption Layer (1 session)
Implement the full encoding stack in Rust (Huffman + AES + ChaCha + stego).
Add the data scattering Layer 0.
Implement at-rest encryption for HELENA's sensitive data.
**Test:** Encrypt a conversation. Restart. Verify recovery. Corrupt one
chunk. Verify detection.

### Phase 7 — Agent Hardening (1 session)
Implement signed hash baseline with DPAPI-bound key.
Implement PPL service registration for the Rust core.
Implement process protection callbacks.
Implement cryptographic audit log chain.
**Test:** Attempt to kill AEGIS process. Verify watchdog restarts it.
Modify a log entry. Verify chain break detected on next run.

### Phase 8 — HELENA Integration (1 session)
Wire all AEGIS telemetry into HELENA's context system.
Implement natural language security command routing.
Wire security events to emotion engine.
Implement "security briefing" at session start.
**Test:** Full standard test suite. Run HELENA through all eight
standard test prompts. Verify security commands work naturally.

### Phase 9 — Simulation and Validation (1 session)
Full attack simulation against the complete system.
Test each MITRE ATT&CK tactic in the threat model.
Measure detection rate, false positive rate, response latency.
Document gaps and close them.
**Test:** See Section 11.

---

## SECTION 11 — SIMULATION PLAN

Each phase has its own simulation test. The full Phase 9 simulation
covers the entire attack chain:

### Simulated Attack Sequence

```
Stage 1 — Reconnaissance
    Simulate: Port scan from external IP
    Expected: Type A agent detects, IP flagged in SharedThreatContext

Stage 2 — Initial access attempt  
    Simulate: Brute force against open service
    Expected: Type B agent detects failed logins, escalates,
              IP blocked via WFP after threshold

Stage 3 — Defense evasion attempt
    Simulate: ETW patching attempt (user mode)
    Expected: ETW anti-tamper detects patch, CRITICAL alert

Stage 4 — Process injection attempt
    Simulate: Cross-process memory allocation (WriteProcessMemory to 
              another process)
    Expected: ETW:TI fires, Type F agent correlates, alert generated

Stage 5 — Persistence attempt
    Simulate: New service creation, registry modification
    Expected: File integrity + ETW process events detect it

Stage 6 — Data access
    Simulate: Access to honeytoken file
    Expected: Honeytoken alert fires immediately, attacker fingerprinted

Stage 7 — Operator response
    Simulate: Phase-Null reviewing HELENA's security briefing,
              approving Tier 4 honeypot deployment
    Expected: Honeypot deploys, attacker's further actions are logged
              and wasted on fake data

Stage 8 — Incident closure
    Simulate: Attacker disconnects
    Expected: Full session log available, fingerprint report ready,
              threat level de-escalates, audit log intact and verifiable
```

---

## SECTION 12 — WHAT WE ARE NOT BUILDING

To keep scope realistic and legal:

- No kernel driver (for now) — WFP usermode filter first. 
  Kernel driver requires code signing certificate ($$$) and is complex.
  Usermode WFP provides most of the benefit.

- No offensive probing — AEGIS never initiates connections to 
  systems it doesn't own.

- No autonomous "retaliatory" actions against attacker infrastructure.

- No breaking encryption — AEGIS does not perform SSL inspection
  (man-in-the-middle) on HELENA's own traffic.

---

## SECTION 13 — DEPENDENCIES

Rust crates:
- `tokio` — async runtime
- `windows-rs` — Windows API bindings (ETW, WFP, DPAPI)
- `tracing-etw` — ETW consumer in Rust (confirmed Rust crate)
- `aes-gcm` — AES-256-GCM
- `chacha20poly1305` — ChaCha20
- `hkdf`, `sha2` — key derivation
- `serde`, `serde_json` — IPC serialization
- `parking_lot` — fast read-write locks for SharedThreatContext
- `maxminddb` — GeoLite2 database for geofencing
- `ring` — alternative crypto primitives (AWS-maintained, FIPS-validated)

Python additions:
- Nothing new required — HELENA talks to Rust over IPC
- `pyzmq` if we use ZMQ for IPC (robust, battle-tested)

---

## READY TO BUILD

This document is the plan. We build Phase 0 first — the toolchain
and IPC bridge — and do not move to Phase 1 until Phase 0 is working.

When you're ready, say "Phase 0" and we start.
