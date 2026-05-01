# HELENA Security Threat Model & Countermeasures
## Comprehensive Attack Surface Analysis
### Phase-Null / H.O.P.E. Project — April 2026

---

## HOW TO USE THIS DOCUMENT

Each attack category follows the same structure:
  - What it is (plain English)
  - How it works technically
  - What HELENA currently does about it
  - What we need to add
  - Priority (CRITICAL / HIGH / MEDIUM / LOW)

Attacks are ordered by real-world prevalence in 2025-2026 based on
MITRE ATT&CK v19 data and Picus Labs analysis of 1M+ malware samples.

---

## CATEGORY 1 — PROCESS MASQUERADING (T1036)
Priority: CRITICAL

### What it is
An attacker names their malicious process chrome.exe, svchost.exe,
or any other trusted name so it passes name-based whitelists.

### How it works
Windows allows any process to be named anything. There is no enforcement
of naming conventions at the OS level. CreateProcess() accepts any
executable path regardless of its name. A malicious binary at:
  C:\Users\franc\AppData\Temp\svchost.exe
is completely indistinguishable from the real one at:
  C:\Windows\System32\svchost.exe
if you only check the name.

Sub-techniques:
  T1036.001 - Invalid code signature (copy metadata from legitimate binary)
  T1036.005 - Match legitimate name (simple rename)
  T1036.009 - Break process trees (spoof parent PID to hide lineage)

### Current HELENA coverage
Partial. We check name AND exe path for suspicious_path_fragments.
But our whitelist is name-only, not name+path. So a spoofed
chrome.exe from AppData would pass if chrome.exe is whitelisted.

### What we add

1. Path-validated whitelist (replace name-only):

```rust
// In process.rs — replace is_known_safe check
fn is_known_safe(name: &str, exe: &str) -> bool {
    let exe_lower = exe.to_lowercase();
    match name {
        "chrome.exe"    => exe_lower.contains("\\google\\chrome\\application\\"),
        "msedge.exe"    => exe_lower.contains("\\microsoft\\edge\\application\\"),
        "firefox.exe"   => exe_lower.contains("\\mozilla firefox\\"),
        "opera.exe"     => exe_lower.contains("\\opera gx\\") || exe_lower.contains("\\opera\\"),
        "code.exe"      => exe_lower.contains("\\microsoft vs code\\"),
        "svchost.exe"   => exe_lower.starts_with("c:\\windows\\system32\\")
                        || exe_lower.starts_with("c:\\windows\\syswow64\\"),
        "lsass.exe"     => exe_lower.starts_with("c:\\windows\\system32\\"),
        "explorer.exe"  => exe_lower.starts_with("c:\\windows\\"),
        "spotify.exe"   => exe_lower.contains("\\spotify\\"),
        "discord.exe"   => exe_lower.contains("\\discord\\"),
        "steam.exe"     => exe_lower.contains("\\steam\\"),
        "ollama.exe"    => exe_lower.contains("\\ollama\\") || exe_lower.contains("program files"),
        "python.exe"    => exe_lower.contains("\\python") || exe_lower.contains("\\miniconda"),
        "protonvpn.wireguardservice.exe" => exe_lower.contains("\\protonvpn\\"),
        "nitrosense.exe" => exe_lower.contains("\\acer\\") || exe_lower.contains("windowsapps"),
        _ => false, // anything not explicitly listed is unknown
    }
}
```

2. Parent-child relationship validation (ETW Kernel-Process gives us this):

```rust
// Expected parent processes for common system binaries
// If actual parent doesn't match, flag regardless of path
fn expected_parents(process_name: &str) -> Option<&'static [&'static str]> {
    match process_name {
        "svchost.exe"   => Some(&["services.exe"]),
        "lsass.exe"     => Some(&["wininit.exe"]),
        "explorer.exe"  => Some(&["userinit.exe", "winlogon.exe"]),
        "taskhost.exe"  => Some(&["services.exe"]),
        "conhost.exe"   => Some(&["csrss.exe"]),
        _               => None,
    }
}
// Mismatch = severity 0.9 finding regardless of name/path
```

3. Code signature verification:
Windows Authenticode signatures can be checked via the
WinVerifyTrust API. A process claiming to be chrome.exe
without Google's signature is immediately flagged. Implement
in process.rs using windows-rs WinTrust bindings.

---

## CATEGORY 2 — PROCESS INJECTION (T1055)
Priority: CRITICAL

### What it is
Attacker runs malicious code inside a legitimate process's memory space.
The malicious code appears to come from that legitimate process.
Extremely common — #1 technique in MITRE ATT&CK 2025 analysis.

### How it works

Sub-technique breakdown:

T1055.001 — DLL Injection
  Write path to malicious DLL into target process memory.
  Call CreateRemoteThread to make target load the DLL.
  The DLL runs inside the legitimate process.

T1055.002 — Portable Executable Injection
  Write raw PE/shellcode directly into target process memory.
  Execute via CreateRemoteThread or APC queue.
  Never touches disk — fileless.

T1055.012 — Process Hollowing
  Create legitimate process in SUSPENDED state (CREATE_SUSPENDED).
  Unmap its memory (ZwUnmapViewOfSection).
  Write malicious code into the now-empty address space.
  Resume the thread — legitimate process name, malicious code.
  
T1055.013 — Process Doppelgänging
  Use NTFS transactions to write malicious code to a temp file.
  Create process from the transactional file.
  Roll back the transaction — file disappears from disk.
  Process continues running with malicious code from "nothing".

T1055.004 — Asynchronous Procedure Call (APC) Injection
  Queue malicious code to a thread's APC queue.
  Code executes when thread enters alertable wait state.
  No new threads created — harder to detect.

### Current HELENA coverage
None currently. ETW:TI (the kernel provider that fires on cross-process
memory writes) requires PPL. Our Phase 1-3 agents don't detect injection.

### What we add

Short term (no PPL required):
  - Monitor for VirtualAllocEx calls from unexpected processes using ETW
    Kernel-Process with the memory allocation keyword
  - Flag processes with executable memory regions that have no corresponding
    file on disk (PAGE_EXECUTE_READWRITE regions = classic injection indicator)
  - Detect CreateRemoteThread calls via ETW thread events
  - Detect suspended process creation + immediate thread manipulation

Medium term (with ELAM certificate):
  - ETW:TI provider gives us WriteProcessMemory callbacks directly
  - This is the definitive detection — fires the moment injection begins

Implementation note: Add to etw/consumer.rs — subscribe to the
Microsoft-Windows-Kernel-Process thread creation events and flag
when a thread is created in a REMOTE process (parent != creator).

---

## CATEGORY 3 — DEFENSE EVASION — ETW PATCHING (T1562/T1685)
Priority: CRITICAL

### What it is
Attacker patches Windows ETW in memory to blind our Phase 2 monitoring.
MITRE ATT&CK v19 (April 2026) restructured this as T1685.

### How it works
Two main approaches:

1. Patch NtTraceEvent in NTDLL
   NtTraceEvent is the userspace function that writes ETW events.
   Overwrite the first few bytes with a RET instruction.
   All ETW events from that process are silently dropped.
   
2. Patch EtwEventWrite in NTDLL
   Same principle, different function.
   Some malware patches both.

3. Provider unregistration
   Call EtwUnregisterProvider for specific security providers.
   Events stop being generated without any memory patches.

### Current HELENA coverage
The ETW anti-tamper design in the Phase 2 plan was deferred pending PPL.
Currently: none.

### What we add

1. Periodic hash check of NTDLL in memory vs on disk.
   If NtTraceEvent or EtwEventWrite bytes differ from the on-disk version,
   ETW has been patched. CRITICAL alert regardless of other state.

2. Canary events. Periodically write a known ETW event from a known process.
   If that event doesn't arrive at our consumer, ETW is silent — flag it.

3. ETW session heartbeat. If any of our three ETW sessions stops delivering
   events for more than 60 seconds while the system is active, that's either
   a crash or tampering. Alert either way.

```rust
// In etw/consumer.rs — add heartbeat tracking
struct EtwHeartbeat {
    last_event: Mutex<Instant>,
    provider:   String,
}

impl EtwHeartbeat {
    fn check(&self) -> bool {
        self.last_event.lock().unwrap().elapsed().as_secs() < 60
    }
}
```

---

## CATEGORY 4 — CREDENTIAL THEFT (T1003)
Priority: CRITICAL

### What it is
Attacker extracts passwords, hashes, or tokens from Windows memory or disk.
Used to escalate privileges or move laterally.

### How it works

T1003.001 — LSASS Memory Dump
  LSASS (Local Security Authority Subsystem) holds credential material.
  Dump its memory via MiniDumpWriteDump or direct handle + ReadProcessMemory.
  Parse dump offline with mimikatz or similar.
  
T1003.002 — Security Account Manager (SAM)
  SAM database contains local account hashes.
  Normally locked by SYSTEM — attackers use Volume Shadow Copy or reg save.
  
T1003.004 — LSA Secrets
  Registry keys under HKLM\SECURITY\Policy\Secrets.
  Contains service account passwords, cached domain credentials.
  Readable only as SYSTEM.

T1003.006 — DCSync
  Pretend to be a domain controller.
  Request credential replication from real DC.
  Not applicable to single-machine HELENA but worth knowing.

### Current HELENA coverage
Process watchdog flags mimikatz by name. But:
- Renamed mimikatz passes
- In-memory mimikatz (reflective load) passes
- procdump.exe (legitimate, often abused) not specifically watched

### What we add

1. LSASS access monitoring via ETW Kernel-Process.
   Any process opening a handle to LSASS with read permissions is suspicious.
   Legitimate reasons to read LSASS memory: almost none outside debuggers.
   
2. Procdump detection — flag by both name AND by behaviour:
   Process that calls MiniDumpWriteDump on another process's handle.

3. SAM/SECURITY registry access monitoring via ETW.
   Flag any process accessing HKLM\SECURITY or HKLM\SAM outside of
   known system processes.

4. Volume Shadow Copy access — flag vssadmin.exe or wmic shadowcopy
   being called from unexpected parent processes.

---

## CATEGORY 5 — PERSISTENCE (T1547, T1053, T1543)
Priority: HIGH

### What it is
Attacker ensures their code runs again after reboot without needing
re-exploitation. HELENA herself could be targeted for persistent backdoor
if an attacker modifies her startup chain.

### How it works

T1547.001 — Registry Run Keys
  Add to HKCU\Software\Microsoft\Windows\CurrentVersion\Run
  Code runs at every user login.

T1053.005 — Scheduled Tasks
  Create a task via schtasks.exe or COM Task Scheduler API.
  Runs at intervals or triggers.

T1543.003 — Windows Services
  Create a new Windows service.
  Runs as SYSTEM by default.
  Survives reboot.

T1574.002 — DLL Search Order Hijacking
  Place malicious DLL in a directory searched before the real DLL location.
  Legitimate process loads malicious DLL instead.

### Current HELENA coverage
ETW 4688 (process creation) catches schtasks.exe and sc.exe being called.
File integrity monitors HELENA's own files.

### What we add

1. Registry change monitoring for Run keys.
   ETW Microsoft-Windows-Registry provider fires on registry writes.
   Flag any write to Run/RunOnce keys from non-whitelisted processes.

2. Scheduled task creation monitoring.
   ETW 4698 (task created) in Security-Auditing provider — we already
   subscribe to this provider. Add event 4698 handler.

3. Service creation monitoring.
   ETW 7045 in System event log.
   Flag new service installations from unexpected paths.

4. DLL search order monitoring.
   Flag DLLs loaded from the current directory or user-writable paths
   when the same DLL name exists in System32. ETW image load events.

---

## CATEGORY 6 — PRIVILEGE ESCALATION (T1068, T1134)
Priority: HIGH

### What it is
Attacker with standard user access gains admin or SYSTEM privileges.

### How it works

T1068 — Kernel Vulnerability Exploitation
  Exploit unpatched driver or kernel vulnerability.
  Gain ring 0 access.
  Nothing userspace can fully stop this — requires kernel-level defense.

T1134 — Access Token Manipulation
  T1134.001: Token Impersonation — steal another process's token
  T1134.002: Create Process with Token — spawn process as different user
  T1134.004: Parent PID Spoofing — inherit parent's elevated token

T1055.004 — APC Injection into privileged thread
  Queue code to a SYSTEM thread.
  Code inherits SYSTEM privileges.

### Current HELENA coverage
ETW Security-Auditing 4672 (special privileges assigned) is monitored.

### What we add

1. Token manipulation detection via ETW.
   Microsoft-Windows-Security-Auditing 4624 (logon) with unusual
   logon type + impersonation level = flag.

2. Sensitive privilege assignment tracking.
   4672 handler should parse WHICH privileges were assigned.
   SeDebugPrivilege (ability to debug any process) is a red flag.
   SeImpersonatePrivilege is another.

3. Unexpected SYSTEM process spawning.
   Flag when a non-SYSTEM process spawns a child with SYSTEM token.
   ETW Kernel-Process gives us both parent PID and user SID.

---

## CATEGORY 7 — COMMAND & CONTROL (T1071, T1572, T1573)
Priority: HIGH

### What it is
Attacker's malware phones home for instructions and data exfiltration.
The communication is designed to look like normal traffic.

### How it works

T1071.001 — HTTP/HTTPS C2
  Most common. C2 traffic over port 443 looks like normal web traffic.
  Beacon interval with jitter (random delay) mimics human browsing.

T1572 — Protocol Tunneling
  DNS tunneling: encode C2 commands in DNS TXT records.
  ICMP tunneling: data in ping packet payloads.
  HTTP tunneling: C2 inside HTTP headers.

T1573 — Encrypted Channel
  Custom encryption over arbitrary port.
  Looks like garbage to inspectors.

T1568 — Dynamic Resolution (DGA)
  Malware generates domain names algorithmically.
  Attacker registers one when needed.
  Blocklists never catch up.

### Current HELENA coverage
DNS monitoring via ETW DNS-Client catches suspicious domain patterns.
Network monitor flags suspicious ports.

### What we add

1. DNS query rate analysis.
   DGA malware generates many unique queries rapidly.
   Flag processes making >10 unique DNS queries per minute to unknown domains.

2. Beacon detection.
   Periodic connections at regular intervals = C2 beaconing.
   Track connection timing per process — flag regularity.
   Normal browsing is irregular. C2 beacons are clockwork.

3. DNS response analysis.
   Short TTL (< 60 seconds) on unknown domains = suspicious.
   Many different IPs for one domain = fast flux = suspicious.

4. Certificate transparency monitoring.
   Check TLS certificates on new connections against known-good CAs.
   Self-signed cert to an IP address = flag.

5. Data volume monitoring.
   Sudden large outbound transfer from a process that doesn't normally
   transfer data = potential exfiltration.

---

## CATEGORY 8 — LIVING OFF THE LAND (T1059, T1218)
Priority: HIGH

### What it is
Attacker uses legitimate Windows tools to do malicious things.
No malware dropped — everything is "signed Microsoft software."

### How it works

T1059.001 — PowerShell abuse
  -EncodedCommand flag hides payload in base64.
  -WindowStyle Hidden hides the window.
  Invoke-Expression downloads and executes from web.
  DownloadString fetches payload without touching disk.

T1218 — Signed Binary Proxy Execution
  T1218.005 — mshta.exe executes HTA files / VBScript
  T1218.010 — regsvr32.exe /s /u /i: executes DLL or remote SCT
  T1218.011 — rundll32.exe executes arbitrary DLL exports
  T1218.007 — msiexec.exe can execute remote MSI packages

T1059.003 — cmd.exe abuse
  Standard batch commands chained to do damage.
  whoami /priv, net user, schtasks, reg add.

### Current HELENA coverage
ETW cmdline monitoring catches some PowerShell patterns.
We watch for -enc and -encodedcommand flags.

### What we add

1. Expand PowerShell detection to full set of LOLBins:
   mshta.exe with any argument
   regsvr32.exe with /u /i or /s flags
   rundll32.exe calling non-System32 DLLs
   msiexec.exe with /q (quiet) flag + remote URL
   certutil.exe with -decode or -urlcache (classic downloader)
   bitsadmin.exe with /transfer
   wscript.exe / cscript.exe from user directories

2. Command line content analysis.
   Flag base64 strings > 100 chars in any command line.
   Flag URLs in command lines for non-browser processes.
   Flag whoami.exe, net.exe, ipconfig.exe called from unexpected parents.

3. Script execution policy bypass detection.
   powershell -ExecutionPolicy Bypass is a reliable flag.

---

## CATEGORY 9 — RANSOMWARE INDICATORS (T1486, T1490)
Priority: HIGH

### What it is
Mass file encryption + destruction of recovery options.
Detected late = everything is already gone.

### How it works

1. Discovery phase first — attacker maps drives, shares, backups.
2. Kill shadow copies: vssadmin delete shadows /all /quiet
3. Disable backup tools: bcdedit /set {default} recoveryenabled No
4. Mass file rename/encrypt: usually uses CryptGenRandom + AES.
5. Drop ransom note.

### Current HELENA coverage
None specifically. File integrity watches HELENA's own files but not
the rest of the filesystem.

### What we add

1. Shadow copy deletion detection (CRITICAL priority).
   vssadmin.exe delete or wmic shadowcopy delete = immediate CRITICAL.
   This is one of the most reliable ransomware early indicators.

2. File entropy monitoring (sampling approach).
   Periodically sample file entropy in key directories.
   Sudden spike in entropy = mass encryption likely in progress.
   Can't watch every file but can watch Documents, Desktop, HELENA dirs.

3. Mass rename detection.
   Flag any process that renames > 20 files per second.
   Normal applications don't do this. Ransomware does.

4. Backup tool interference.
   bcdedit, vssadmin, wbadmin called from non-admin processes = flag.

---

## CATEGORY 10 — SUPPLY CHAIN / DEPENDENCY ATTACKS
Priority: MEDIUM

### What it is
Attacker compromises a library or tool that HELENA depends on,
rather than attacking HELENA directly.

### How it works
- Malicious PyPI package with similar name to legitimate one
- Compromised npm/cargo package with legitimate name
- Typosquatting (requests vs reqeusts)
- Legitimate package account takeover

Real examples relevant to HELENA's stack:
  - Ollama dependency chain
  - Python packages (psutil, chromadb, etc.)
  - Rust crates (any of our dependencies)

### What we add

1. Dependency hash pinning.
   Cargo.lock already pins Rust crate versions.
   requirements.txt should pin exact versions + hashes.
   Never use wildcard versions in production.

2. Verify package integrity on install.
   pip install with --require-hashes flag.
   cargo verify-project before builds.

3. Minimal dependency principle.
   Every new dependency is attack surface.
   Question whether each one is necessary.

---

## CATEGORY 11 — AEGIS/HELENA SELF-ATTACK SURFACE
Priority: CRITICAL

### What it is
An attacker who knows about HELENA specifically targets the security
system itself rather than going around it.

### Attack vectors against HELENA directly

1. Kill the aegis.exe process.
   Mitigation: PPL service (Phase 7), watchdog restart.

2. Flood the report queue to exhaust processing.
   Mitigation: Rate limiting per source already implemented.
   Add: cap pending_responses at 50 — if queue is full, reject new ones.

3. Modify HELENA's source files to insert a backdoor.
   Mitigation: File integrity monitoring already watching.
   Add: path-validated signatures.

4. Inject code into aegis.exe itself.
   Mitigation: Phase 7 agent hardening.
   ETW Kernel-Process thread creation events flag remote thread injection.

5. Replay attack on IPC bridge.
   Someone connects to port 47201 and sends fake approval messages.
   Mitigation: Add a challenge-response handshake to the IPC bridge.
   HELENA sends a nonce. AEGIS verifies response before accepting commands.

6. Exploit the netsh firewall rules themselves.
   HELENA_BLOCK_ rules could be deleted by any admin process.
   Mitigation: Monitor firewall rule deletion via ETW or registry watch.
   Alert when HELENA rules are removed outside of planned shutdown.

7. Time-of-check to time-of-use (TOCTOU) on file integrity.
   Attacker modifies a file between our hash check and when it's used.
   Mitigation: Hash check frequency < modification window.
   V4 integrity agent runs every 10 seconds — acceptable.

8. Port 47201 enumeration.
   Anyone can see AEGIS is listening on that port via netstat.
   Mitigation: Bind to 127.0.0.1 (already done — loopback only).
   Add: WFP rule blocking external access to 47201 at startup.

---

## CATEGORY 12 — PHYSICAL/SIDE CHANNEL
Priority: LOW (for now)

### What it is
Attacks that don't go through software at all.

### How it works
- Cold boot attack: freeze RAM, extract keys
- DMA attack: malicious USB/Thunderbolt device reads memory directly
- Shoulder surfing / screen capture

### What we add
- HELENA's sensitive data (API keys, conversation content) should be
  in bytearray objects that are explicitly zeroed after use.
- Disk encryption (BitLocker) for helena_memory/ and config files.
- Screen lock integration — HELENA enters lockdown mode when screen locks.

---

## IMPLEMENTATION PRIORITY ORDER

Phase 3a (NOW — before moving to Phase 4):
  1. Path-validated whitelist (replaces name-only)
  2. Parent-child process relationship validation
  3. Pending_responses queue cap (prevent queue flooding)
  4. WFP rule self-protection (block external access to port 47201)
  5. ETW heartbeat monitoring

Phase 4 (as planned):
  6. Deception layer agents
  7. Expanded LOLBin detection (PowerShell, mshta, certutil, etc.)
  8. Shadow copy deletion detection (ransomware early warning)
  9. Mass rename detection

Phase 5 (agent hardening):
  10. Code signature verification via WinVerifyTrust
  11. IPC bridge challenge-response handshake
  12. Firewall rule self-monitoring
  13. LSASS access detection

Phase 6 (encryption):
  14. At-rest encryption for sensitive HELENA data
  15. Memory zeroing for credentials

Phase 7 (full hardening):
  16. NTDLL hash check (ETW anti-tamper detection)
  17. ETW canary events
  18. DGA / beacon detection
  19. File entropy sampling (ransomware detection)

---

## SUMMARY TABLE

Attack                      | Current coverage | Gap                          | Phase
----------------------------|-----------------|------------------------------|-------
Process masquerading        | Partial         | Name-only whitelist          | 3a
Process injection           | None            | Need ETW thread monitoring   | 4-5
ETW tampering               | None            | NTDLL hash check             | 7
Credential theft (LSASS)    | Partial (name)  | Behaviour-based detection    | 5
Persistence (Run keys/tasks)| Partial (4688)  | Registry + task monitoring   | 4
Privilege escalation        | Partial (4672)  | Token manipulation detail    | 4
C2 / DNS tunneling          | Partial         | Beacon + DGA detection       | 4
Living off the land         | Partial (PS)    | Full LOLBin coverage         | 4
Ransomware                  | None            | Shadow copy + entropy        | 4
Supply chain                | None            | Hash pinning                 | 3a
AEGIS self-attack           | Partial         | Queue cap + IPC handshake    | 3a
Physical/side channel       | None            | Memory zeroing + BitLocker   | 6
