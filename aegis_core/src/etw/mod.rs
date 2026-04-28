// src/etw/mod.rs
//
// Phase 2 — ETW (Event Tracing for Windows) consumer.
//
// ETW is Windows' kernel-level event telemetry system. It operates below
// userspace — events from kernel providers are written directly by the kernel
// itself, not by any userspace process. This makes ETW data fundamentally
// more reliable than polling (like Phase 1 agents do) and significantly
// harder to tamper with.
//
// What we subscribe to (no PPL required, admin sufficient):
//
//   Microsoft-Windows-Kernel-Process
//   GUID: 22fb2cd6-0e7b-422b-a0c7-2fad1fd0e716
//   Events: process start (ID 1), process stop (ID 2), image load (ID 5)
//   Keyword: 0x10 (PROCESS) | 0x40 (IMAGE)
//   Value: catches process creation the moment it happens, with full
//          command line and parent PID — more reliable than Event ID 4688
//          which goes through lsass and can be tampered in userspace.
//
//   Microsoft-Windows-DNS-Client
//   GUID: 1c95126e-7eea-49a9-a3fe-a378b03ddb4d
//   Events: DNS query (ID 3006)
//   Value: every domain name resolved by any process. C2 beaconing,
//          domain generation algorithms, exfiltration channels all
//          require DNS — this catches them at the moment of lookup.
//
//   Microsoft-Windows-Security-Auditing
//   GUID: 54849625-5478-4994-a5ba-3e3b0328c30d
//   Events: 4625 (failed login), 4672 (privilege escalation), 4688 (new process)
//   Value: real-time feed of the Security log without the polling overhead
//          of Phase 1's PowerShell approach. Same data, arrives faster.
//
// What we deliberately DO NOT subscribe to:
//
//   Microsoft-Windows-Threat-Intelligence
//   GUID: f4e1897c-bb5d-5668-f1d8-040f4d8dd344
//   Reason: requires Protected Process Light (PPL) at Antimalware-Light level.
//           This is enforced in EtwpCheckNotificationAccess in the kernel.
//           Without a Microsoft co-signed ELAM driver, access is denied.
//           The exploit-based workarounds (PPLDump) are patched on Windows
//           10 21H2+. The AutoLogger technique (January 2026) requires a
//           registry key, reboot, and complex session management.
//           FUTURE: if we obtain a code signing certificate and ELAM driver,
//           ETW:TI gives us remote memory allocation, APC injection, and
//           SetThreadContext detection — the core process injection signals.
//
// Architecture:
//   ETW consumers BLOCK the thread they run on — ferrisetw's trace.process()
//   call does not return until the trace is stopped. We run each provider
//   in its own OS thread (std::thread, not tokio). Findings are sent into
//   the same mpsc channel as Phase 1 agents.
//
// Admin requirement:
//   Microsoft-Windows-Kernel-Process requires admin. AEGIS already recommends
//   running as admin. If not admin, the ETW session start fails gracefully
//   and AEGIS logs a warning — Phase 1 agents continue running normally.

pub mod consumer;
pub mod providers;

pub use consumer::start_etw_consumers;
