---
tags: [aegis, etw]
date: 2026-03-05
status: active
component: aegis_core/src/etw/
bugs: [15, 34]
---

# ETW System — Event Tracing for Windows

AEGIS subscribes to three Windows ETW providers for kernel-level security visibility. Each provider has its own trace session and callback that parses events and pushes findings to the agent report channel.

> [!tip] ETW Heartbeat Monitoring
> Phase 3a addition: checks every 60 seconds that each ETW session is still delivering events. Silence > 60s = possible ETW tampering (T1562) or session crash. Alerts pushed to HELENA as `etw_heartbeat_{provider}` findings with severity 0.8.

---

## Provider Registry

### Microsoft-Windows-Kernel-Process

| Field | Value |
|-------|-------|
| GUID | `22fb2cd6-0e7b-422b-a0c7-2fad1fd0e716` |
| Keywords | `KEYWORD_PROCESS: 0x10`, `KEYWORD_THREAD: 0x20`, `KEYWORD_IMAGE: 0x40`, `KEYWORD_CPU_PRIORITY: 0x80` |
| Event IDs | `1 (PROCESS_START)`, `2 (PROCESS_STOP)`, `5 (IMAGE_LOAD)` |
| Trace Name | `aegis_kernel_process` |

**PROCESS_START fields**: ProcessID (u32), ParentProcessID (u32), ImageFileName (String), CommandLine (String), SessionID (u32)

**IMAGE_LOAD fields**: ProcessID (u32), ImageBase (u64), ImageSize (u32), ImageChecksum (u32), ImageName (String)

### Microsoft-Windows-DNS-Client

| Field | Value |
|-------|-------|
| GUID | `1c95126e-7eea-49a9-a3fe-a378b03ddb4d` |
| Keywords | `KEYWORD_ALL: 0xFFFFFFFFFFFFFFFF` |
| Event IDs | `3006 (DNS_QUERY)` |
| Trace Name | `aegis_dns_client` |

**DNS_QUERY fields**: QueryName (String), QueryType (u32), QueryStatus (u32), QueryResults (String — semicolon-separated IPs)

### Microsoft-Windows-Security-Auditing

| Field | Value |
|-------|-------|
| GUID | `54849625-5478-4994-a5ba-3e3b0328c30d` |
| Keywords | `KEYWORD_ALL: 0xFFFFFFFFFFFFFFFF` |
| Event IDs | `4625 (LOGON_FAILURE)`, `4672 (SPECIAL_LOGON)`, `4688 (PROCESS_CREATED)`, `4740 (ACCOUNT_LOCKED)` |
| Trace Name | `aegis_security_auditing` |
| Note | **Restricted** — admin rights required |

---

## Suspicious Indicators

### SUSPICIOUS_IMAGE_PATHS (checked with `contains()` on lowercase image path)

```
mimikatz, msfconsole, metasploit, psexec, wce.exe, pwdump,
procdump, \temp\, \appdata\local\temp\, \windows\temp\, \downloads\
```

### SUSPICIOUS_CMDLINE_FRAGMENTS (checked with `contains()` on lowercase command line)

```
-enc , -encodedcommand, invoke-mimikatz, invoke-expression,
downloadstring, net user /add, net localgroup administrators,
reg add, schtasks /create, bitsadmin /transfer
```

> [!warning] Bug #15 — Regex Pattern Used with contains()
> `"reg add.*run"` was a regex pattern but is checked with `.contains()`, which treats `.*` as literal text. Registry Run key persistence was NOT being detected. Fixed: split into separate `"reg add"` and `"run"` checks. See [[Bug Fixes]].

### SUSPICIOUS_DNS_PATTERNS (checked as substrings of lowercase query name)

```
.onion., ngrok.io, .ngrok., serveo.net, localhost.run,
.dyn.dns., no-ip., dyndns.
```

---

## Consumer Callback Logic

### Kernel-Process Callback

```
Event PROCESS_START:
  1. Parse PID, ParentPID, ImageFileName, CommandLine
  2. Check image against SUSPICIOUS_IMAGE_PATHS → finding type: etw_suspicious_process_image (severity 0.8)
  3. Check cmdline against SUSPICIOUS_CMDLINE_FRAGMENTS → finding type: etw_suspicious_cmdline (severity 0.85)
  4. Push findings to report channel

Event IMAGE_LOAD:
  1. Parse PID, ImageName
  2. Check if image from suspicious path (\temp\, \downloads\, \appdata\local\temp\)
  3. → finding type: etw_suspicious_dll_load (severity 0.7)
```

### DNS-Client Callback

```
Event DNS_QUERY (3006):
  1. Parse QueryName, QueryStatus, QueryResults
  2. Check query against SUSPICIOUS_DNS_PATTERNS
  3. → finding type: etw_suspicious_dns_query (severity 0.75)
```

> [!warning] Bug #34 — String Slice Can Panic
> Byte-based truncation `&cmdline[..cmdline.len().min(150)]` can panic on multi-byte UTF-8 characters. Fixed with `truncate_str()` function that respects char boundaries. See [[Bug Fixes]].

### Security-Auditing Callback

| Event ID | Finding Type | Severity | Detail |
|----------|-------------|----------|--------|
| 4625 | `etw_logon_failure` | 0.5 | Authentication failure |
| 4672 | `etw_special_logon` | 0.6 | Special privileges assigned to logon |
| 4740 | `etw_account_locked` | 0.75 | Account lockout — possible brute force |

---

## EtwHandles Structure

```rust
pub struct EtwHandles {
    _kernel_process:    Option<UserTrace>,
    _dns_client:        Option<UserTrace>,
    _security_auditing: Option<UserTrace>,
    pub last_event_times: EventTimesMap,  // Arc<Mutex<HashMap<String, Instant>>>
}
```

Each provider's trace session is kept alive for the process lifetime. The `last_event_times` map is shared with the heartbeat monitor in `main.rs`.

---

## Helper: `truncate_str()`

```rust
fn truncate_str(s: &str, max_bytes: usize) -> &str {
    if s.len() <= max_bytes { return s; }
    let mut boundary = max_bytes;
    while boundary > 0 && !s.is_char_boundary(boundary) { boundary -= 1; }
    &s[..boundary]
}
```

---

## Related Notes

- [[Overview]] — AEGIS entry point, ETW consumers spawned in main.rs
- [[Network Agent]] — complementary network-level monitoring
- [[Bug Fixes]] — Bug #15 (regex→contains), Bug #34 (string slice panic)
