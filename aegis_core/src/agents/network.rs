// src/agents/network.rs
//
// Type A — Network Monitor
//
// Watches active TCP connections for suspicious activity:
//   - Connections to known bad ports (reverse shells, RATs, etc.)
//   - Established connections from processes AEGIS doesn't recognise
//   - Unusual connection counts from a single process
//
// Uses the `netstat2` crate which calls GetExtendedTcpTable on Windows.
// This gives us remote IP, remote port, local port, and the PID that
// owns the connection — all in one call, no admin rights needed.
//
// Four variants with different scan intervals and thresholds:
//   V1 — sensitive, fast  (5s, threshold 0.3)
//   V2 — balanced         (10s, threshold 0.5)
//   V3 — conservative     (20s, threshold 0.7)
//   V4 — rapid sweep      (3s, threshold 0.4)

use std::collections::HashSet;
use netstat2::{get_sockets_info, AddressFamilyFlags, ProtocolFlags, ProtocolSocketInfo};

use crate::agents::base::{Agent, AgentConfig};
use crate::ipc::protocol::SharedContext;
use crate::ipc::protocol::Finding;

// ── Known suspicious ports ────────────────────────────────────────────────────

/// Ports commonly used by reverse shells, RATs, and C2 frameworks.
/// Not exhaustive — flagged as elevated, not critical, on their own.
fn suspicious_ports() -> HashSet<u16> {
    [
        4444, 4445, 4446,       // Metasploit default reverse shell
        5555, 5556,             // Android ADB, also common RAT port
        6666, 6667, 6668,       // IRC (used by botnets), also common RAT
        7777, 8888,             // Generic RAT ports
        31337,                  // "Elite" — classic backdoor port
        1337,                   // Common in CTF-style tools
        9001, 9030, 9050, 9051, // Tor
        1080,                   // SOCKS proxy — tunnelling indicator
        3389,                   // RDP — external RDP is suspicious
        4899,                   // Radmin remote admin
        5900, 5901,             // VNC
    ].into()
}

/// Processes we expect to make network connections.
/// Unknown processes making external connections get flagged.
fn known_safe_processes() -> HashSet<&'static str> {
    [
        "chrome.exe", "firefox.exe", "msedge.exe", "brave.exe",
        "python.exe", "pythonw.exe",
        "ollama.exe", "ollama_llama_server.exe",
        "aegis.exe",
        "svchost.exe", "lsass.exe", "services.exe",
        "system", "idle",
        "discord.exe", "slack.exe",
        "git.exe", "ssh.exe",
        "curl.exe", "wget.exe",
        "opera.exe", "opera_gx.exe",
        "steam.exe", "steamwebhelper.exe",
        "discord.exe",
        "onedrive.exe",
        "explorer.exe",
        "searchhost.exe", "searchindexer.exe",
    ].into()
}

// ── Agent struct ──────────────────────────────────────────────────────────────

pub struct NetworkMonitor {
    config:           AgentConfig,
    suspicious_ports: HashSet<u16>,
    safe_processes:   HashSet<&'static str>,
}

impl NetworkMonitor {
    pub fn new(variant: u8, interval_secs: u64, threshold: f32) -> Self {
        Self {
            config:           AgentConfig::new("network_monitor", variant, interval_secs, threshold),
            suspicious_ports: suspicious_ports(),
            safe_processes:   known_safe_processes(),
        }
    }

    /// Shorthand constructors for the four variants.
    pub fn v1() -> Self { Self::new(1, 5,  0.3) }
    pub fn v2() -> Self { Self::new(2, 10, 0.5) }
    pub fn v3() -> Self { Self::new(3, 20, 0.7) }
    pub fn v4() -> Self { Self::new(4, 3,  0.4) }
}

impl Agent for NetworkMonitor {
    fn config(&self) -> &AgentConfig { &self.config }

    fn scan(&self, context: &SharedContext) -> Vec<Finding> {
        let mut findings = Vec::new();

        // GetExtendedTcpTable / equivalent via netstat2
        let sockets = match get_sockets_info(
            AddressFamilyFlags::IPV4 | AddressFamilyFlags::IPV6,
            ProtocolFlags::TCP,
        ) {
            Ok(s)  => s,
            Err(e) => {
                // Permission error or API failure — not a finding, just skip
                tracing::debug!("NetworkMonitor: socket enumeration failed: {}", e);
                return findings;
            }
        };

        for sock in &sockets {
            let (local_port, remote_addr, remote_port, pid) = match &sock.protocol_socket_info {
                ProtocolSocketInfo::Tcp(tcp) => {
                    // Only care about ESTABLISHED connections
                    // netstat2 includes LISTEN sockets too, skip those
                    if tcp.remote_port == 0 { continue; }
                    (
                        tcp.local_port,
                        tcp.remote_addr.to_string(),
                        tcp.remote_port,
                        sock.associated_pids.first().copied(),
                    )
                }
                _ => continue,
            };

            // Skip loopback — internal comms are expected
            if remote_addr.starts_with("127.") || remote_addr == "::1" {
                continue;
            }

            let pid = pid.unwrap_or(0);

            // Get process name for this PID (best effort)
            let process_name = get_process_name(pid)
                .unwrap_or_else(|| "unknown".to_string())
                .to_lowercase();

            // ── Check 1: suspicious remote port ──────────────────────────────
            if self.suspicious_ports.contains(&remote_port)
                || self.suspicious_ports.contains(&local_port) {

                // Correlate: is this IP already flagged by another agent?
                let existing = context.ip_severity(&remote_addr);

                // Base severity 0.7, boosted if already flagged elsewhere
                let severity = (0.7_f32 + existing * 0.2).min(1.0);

                findings.push(Finding {
                    finding_type: "suspicious_port".to_string(),
                    severity,
                    detail: format!(
                        "Connection on suspicious port {} ← {} (PID {} / {})",
                        remote_port, remote_addr, pid, process_name
                    ),
                    data: serde_json::json!({
                        "remote_ip":    remote_addr,
                        "remote_port":  remote_port,
                        "local_port":   local_port,
                        "pid":          pid,
                        "process":      process_name,
                    }),
                });
            }

            // ── Check 2: unknown process making external connection ────────────
            let base_name = process_name.split(['/', '\\']).last()
                .unwrap_or(&process_name)
                .to_string();

            if !self.safe_processes.contains(base_name.as_str()) && pid > 4 {
                // Correlate: is this PID already flagged?
                let existing_pid = context.pid_severity(pid);
                let severity = (0.35_f32 + existing_pid * 0.3).min(0.9);

                findings.push(Finding {
                    finding_type: "unknown_external_connection".to_string(),
                    severity,
                    detail: format!(
                        "Unrecognised process {} (PID {}) → {}:{}",
                        process_name, pid, remote_addr, remote_port
                    ),
                    data: serde_json::json!({
                        "remote_ip":   remote_addr,
                        "remote_port": remote_port,
                        "pid":         pid,
                        "process":     process_name,
                    }),
                });
            }
        }

        findings
    }
}

// ── Process name lookup ───────────────────────────────────────────────────────
// sysinfo is the right tool for this on Windows.
// We do a targeted single-process refresh rather than refreshing all processes
// (much faster when we only need one name).

fn get_process_name(pid: u32) -> Option<String> {
    use sysinfo::{System, ProcessesToUpdate, ProcessRefreshKind};

    if pid == 0 { return None; }

    let mut sys = System::new();
    sys.refresh_processes_specifics(
        ProcessesToUpdate::Some(&[sysinfo::Pid::from_u32(pid)]),
        true,
        ProcessRefreshKind::nothing(),
    );

    sys.process(sysinfo::Pid::from_u32(pid))
        .map(|p| p.name().to_string_lossy().to_string())
}
