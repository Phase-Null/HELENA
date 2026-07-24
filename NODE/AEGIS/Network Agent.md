---
tags: [aegis, network]
date: 2026-03-05
status: active
component: aegis_core/src/agents/network.rs
bugs: [22]
---

# Network Agent — NetworkMonitor

Type A agent that enumerates network sockets, identifies suspicious connections, and validates process identities against their executable paths.

> [!tip] Four Variants
> NetworkMonitor has v1-v4 variants with different scan intervals and thresholds:
> | Variant | Interval | Threshold |
> |---------|----------|-----------|
> | v1 | 5s | 0.3 |
> | v2 | 10s | 0.5 |
> | v3 | 20s | 0.7 |
> | v4 | 3s | 0.4 |

---

## Suspicious Ports

```rust
fn suspicious_ports() -> HashSet<u16> {
    [4444, 4445, 4446,       // Metasploit defaults
     5555, 5556,             // Reverse shell common
     6666, 6667, 6668,       // IRC C2
     7777, 8888,             // Generic suspicious
     31337, 1337,            // Elite/hacker ports
     9001, 9030, 9050, 9051, // Tor
     1080,                   // SOCKS proxy
     3389,                   // RDP
     4899,                   // RemoteAnywhere
     5900, 5901,             // VNC
    ].into()
}
```

---

## Path-Validated Safe Process Check (`is_known_safe()`)

> [!info] T1036 Masquerading Defense
> `is_known_safe(name, exe)` validates **both** the process name AND the executable path. A spoofed `chrome.exe` from `AppData` fails the path check even though the name matches. This closes the T1036 masquerading gap for network-facing processes.

Categories of safe processes:
| Category | Examples | Path Validation |
|----------|---------|----------------|
| Steam games | Any exe | Must contain `\steamapps\` |
| Browsers | chrome.exe, msedge.exe, firefox.exe, opera.exe, brave.exe | Must be in official install path |
| Development | code.exe, python.exe, git.exe, node.exe, cargo.exe | Must be in dev tool paths |
| HELENA stack | ollama.exe, aegis.exe | Must be in HELENA/AEGIS paths |
| Windows system | svchost.exe, lsass.exe, explorer.exe | Must start with `c:\windows\system32\` |
| VPN | protonvpn.exe, wireguard.exe | Must be in VPN paths |
| Gaming/comms | steam.exe, discord.exe, spotify.exe | Must be in app paths |
| Acer OEM | nitrosense.exe, ubtservice.exe | Must contain `\acer\` |
| Utilities | onedrive.exe, ssh.exe, curl.exe | Must be in proper paths |

---

## Scan Logic

```
1. Create System instance once (Bug #22 fix)
2. Refresh all processes with specifics (exe + cmd)
3. Enumerate sockets via netstat2 (IPv4 + IPv6, TCP only)
4. For each socket with remote connection:
   a. Skip loopback (127.x or ::1)
   b. Get process name and exe path from PID
   c. Check 1: suspicious port → finding (severity: 0.7 + IP_history * 0.2, max 1.0)
   d. Check 2: unknown process + external connection → finding (severity: 0.35 + PID_history * 0.3, max 0.9)
5. Return all findings
```

> [!warning] Bug #22 — New `System` Object Created Per PID
> `System::new()` is extremely expensive. Was called once per PID in `get_process_info()`. Fixed: single System instance created in `scan()`, passed by reference. See [[Bug Fixes]].

---

## Finding Types

| Type | Severity Range | Trigger |
|------|---------------|---------|
| `suspicious_port` | 0.7–1.0 | Connection on known suspicious port |
| `unknown_external_connection` | 0.35–0.9 | Unrecognized process with external connection |

Severity is escalated based on prior threat history:
- `context.ip_severity(remote_addr)` — previously flagged IP gets higher severity
- `context.pid_severity(pid)` — previously flagged PID gets higher severity

---

## Related Notes

- [[Overview]] — NetworkMonitor variants spawned in main.rs
- [[ETW System]] — complementary kernel-level process monitoring
- [[State Management]] — SharedContext provides IP/PID severity history
- [[Bug Fixes]] — Bug #22 (System per PID)
