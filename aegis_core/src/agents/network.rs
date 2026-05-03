// src/agents/network.rs
//
// Type A — Network Monitor
//
// Phase 3a changes:
//   - known_safe_processes() replaced with is_known_safe(name, exe)
//     validating both name AND executable path. Closes T1036 masquerading
//     gap for network-facing processes.

use std::collections::HashSet;
use netstat2::{get_sockets_info, AddressFamilyFlags, ProtocolFlags, ProtocolSocketInfo};
use sysinfo::{System, ProcessesToUpdate, ProcessRefreshKind};

use crate::agents::base::{Agent, AgentConfig};
use crate::ipc::protocol::SharedContext;
use crate::ipc::protocol::Finding;

// ── Known suspicious ports ────────────────────────────────────────────────────

fn suspicious_ports() -> HashSet<u16> {
    [
        4444, 4445, 4446,
        5555, 5556,
        6666, 6667, 6668,
        7777, 8888,
        31337, 1337,
        9001, 9030, 9050, 9051,
        1080,
        3389,
        4899,
        5900, 5901,
    ].into()
}

// ── Path-validated safe process check ────────────────────────────────────────
//
// Validates both the process name AND the executable path.
// Prevents T1036 masquerading — a spoofed chrome.exe from AppData
// fails the path check even though the name matches.

fn is_known_safe(name: &str, exe: &str) -> bool {
    let exe_lower = exe.to_lowercase();
    match name {
        // Catch all Steam games — any exe from the Steam apps folder
        _ if exe_lower.contains("\\steamapps\\") => true,

        // Browsers
        "chrome.exe"        => exe_lower.contains("\\google\\chrome\\application\\"),
        "msedge.exe"        => exe_lower.contains("\\microsoft\\edge\\application\\"),
        "firefox.exe"       => exe_lower.contains("\\mozilla firefox\\"),
        "opera.exe"         => exe_lower.contains("\\opera gx\\") || exe_lower.contains("\\opera\\"),
        "opera_gx.exe"      => exe_lower.contains("\\opera gx\\"),
        "brave.exe"         => exe_lower.contains("\\brave software\\"),

        // Development
        "code.exe"          => exe_lower.contains("\\microsoft vs code\\")
                            || exe_lower.contains("\\vscode\\"),
        "python.exe"        => exe_lower.contains("\\python") || exe_lower.contains("\\miniconda"),
        "pythonw.exe"       => exe_lower.contains("\\python") || exe_lower.contains("\\miniconda"),
        "git.exe"           => exe_lower.contains("\\git\\"),
        "node.exe"          => exe_lower.contains("\\nodejs\\") || exe_lower.contains("\\node\\"),
        "cargo.exe"         => exe_lower.contains("\\.cargo\\"),

        // HELENA stack
        "ollama.exe"        => exe_lower.contains("\\ollama\\")
                            || exe_lower.contains("program files"),
        "ollama_llama_server.exe" => exe_lower.contains("\\ollama\\")
                            || exe_lower.contains("program files"),
        "aegis.exe"         => exe_lower.contains("\\helena\\") || exe_lower.contains("\\aegis"),

        // Windows system — strict paths
        "svchost.exe"       => exe_lower.starts_with("c:\\windows\\system32\\")
                            || exe_lower.starts_with("c:\\windows\\syswow64\\"),
        "lsass.exe"         => exe_lower.starts_with("c:\\windows\\system32\\"),
        "services.exe"      => exe_lower.starts_with("c:\\windows\\system32\\"),
        "explorer.exe"      => exe_lower.starts_with("c:\\windows\\"),

        // VPN
        "protonvpn.exe"     => exe_lower.contains("\\protonvpn\\"),
        "protonvpn.wireguardservice.exe" => exe_lower.contains("\\protonvpn\\"),
        "wireguard.exe"     => exe_lower.contains("\\wireguard\\"),

        // Gaming/comms
        "steam.exe"         => exe_lower.contains("\\steam\\"),
        "steamwebhelper.exe"=> exe_lower.contains("\\steam\\"),
        "discord.exe"       => exe_lower.contains("\\discord\\"),
        "spotify.exe"       => exe_lower.contains("\\spotify\\"),

        // OEM
        "nitrosense.exe"    => exe_lower.contains("\\acer\\") || exe_lower.contains("windowsapps"),
        "ubtservice.exe"    => exe_lower.contains("\\acer\\"),

        // Utilities
        "onedrive.exe"      => exe_lower.contains("\\onedrive\\"),
        "ssh.exe"           => exe_lower.contains("\\openssh\\")
                            || exe_lower.starts_with("c:\\windows\\system32\\"),
        "curl.exe"          => exe_lower.starts_with("c:\\windows\\system32\\")
                            || exe_lower.contains("\\curl\\"),

        // Safe regardless of path
        "system"            => true,
        "idle"              => true,
        
        // Acer services
        "aceragentservice.exe"      => exe_lower.contains("\\acer\\"),
        "acerccagent.exe"           => exe_lower.contains("\\acer\\"),
        "acerdiagent.exe"           => exe_lower.contains("\\acer\\"),
        "acergaicameraw.exe"        => exe_lower.contains("\\acer\\"),
        "acerpixyservice.exe"       => exe_lower.contains("\\acer\\"),
        "acerqaagent.exe"           => exe_lower.contains("\\acer\\"),
        "acersysmonitorservice.exe" => exe_lower.contains("\\acer\\"),
        "adesv2svc.exe"             => exe_lower.contains("\\acer\\"),
        "aqauserps.exe"             => exe_lower.contains("\\acer\\"),
        "quickpanelosd.exe"         => exe_lower.contains("\\acer\\"),
        "ubtservice.exe"            => exe_lower.contains("\\acer\\"),

        // ProtonVPN additional
        "protonvpn.client.exe"      => exe_lower.contains("\\protonvpn\\"),
        "protonvpnservice.exe"      => exe_lower.contains("\\protonvpn\\"),

        // Ollama (name has a space)
        "ollama app.exe"            => exe_lower.contains("\\ollama\\")
                                    || exe_lower.contains("program files"),

        // Microsoft services
        "msedgewebview2.exe"        => exe_lower.contains("\\microsoft\\")
                                    || exe_lower.contains("\\edge\\"),
        "onedrive.sync.service.exe" => exe_lower.contains("\\onedrive\\")
                                    || exe_lower.contains("\\microsoft\\"),
        "wudfhost.exe"              => exe_lower.starts_with("c:\\windows\\"),
        "ipfsvc.exe"                => exe_lower.starts_with("c:\\windows\\"),
        "edgegameassist.exe"        => exe_lower.contains("\\microsoft\\"),

        // MC processes (Intel/McAfee network components)
        "mc-fw-host.exe"            => exe_lower.contains("\\intel\\")
                                    || exe_lower.contains("\\mcafee\\"),
        "mc-extn-browserhost.exe"   => exe_lower.contains("\\intel\\")
                                    || exe_lower.contains("\\mcafee\\"),
        "mc-vpn.exe"                => exe_lower.contains("\\intel\\")
                                    || exe_lower.contains("\\mcafee\\"),

        // Chromium Embedded Framework (used by NitroSense and others)
        "cefsharp.browsersubprocess.exe" => true, // path varies too much
        "browserhost.exe"           => true,

        // Windows Gaming
        "gamingservices.exe"        => exe_lower.contains("\\windowsapps\\")
                                    || exe_lower.contains("\\xbox\\"),
        "gamingservicesnet.exe"     => exe_lower.contains("\\windowsapps\\")
                                    || exe_lower.contains("\\xbox\\"),
        "xboxpcappft.exe"           => exe_lower.contains("\\windowsapps\\")
                                    || exe_lower.contains("\\xbox\\"),

        // Additional Windows system
        "hostappserviceupdater.exe" => exe_lower.contains("\\windows\\")
                                    || exe_lower.contains("\\microsoft\\"),
        "powershell.exe"            => exe_lower.starts_with("c:\\windows\\"),
        "pwsh.exe"                  => exe_lower.contains("\\powershell\\"),
        "cmd.exe"                   => exe_lower.starts_with("c:\\windows\\"),
        "conhost.exe"               => exe_lower.starts_with("c:\\windows\\"),
        "dllhost.exe"               => exe_lower.starts_with("c:\\windows\\"),
        "audiodg.exe"               => exe_lower.starts_with("c:\\windows\\"),
        "spoolsv.exe"               => exe_lower.starts_with("c:\\windows\\"),
        "wmiprvse.exe"              => exe_lower.starts_with("c:\\windows\\"),
        "lsaiso.exe"                => exe_lower.starts_with("c:\\windows\\"),
        "smartscreen.exe"           => exe_lower.starts_with("c:\\windows\\"),
        "msmpeng.exe"               => exe_lower.starts_with("c:\\windows\\")
                                    || exe_lower.contains("\\defender\\"),
        "nissrv.exe"                => exe_lower.starts_with("c:\\windows\\")
                                    || exe_lower.contains("\\defender\\"),

        _                   => false,
    }
}

// ── Agent struct ──────────────────────────────────────────────────────────────

pub struct NetworkMonitor {
    config:           AgentConfig,
    suspicious_ports: HashSet<u16>,
}

impl NetworkMonitor {
    pub fn new(variant: u8, interval_secs: u64, threshold: f32) -> Self {
        Self {
            config:           AgentConfig::new("network_monitor", variant, interval_secs, threshold),
            suspicious_ports: suspicious_ports(),
        }
    }

    pub fn v1() -> Self { Self::new(1, 5,  0.3) }
    pub fn v2() -> Self { Self::new(2, 10, 0.5) }
    pub fn v3() -> Self { Self::new(3, 20, 0.7) }
    pub fn v4() -> Self { Self::new(4, 3,  0.4) }
}

impl Agent for NetworkMonitor {
    fn config(&self) -> &AgentConfig { &self.config }

    fn scan(&self, context: &SharedContext) -> Vec<Finding> {
        let mut findings = Vec::new();

        let sockets = match get_sockets_info(
            AddressFamilyFlags::IPV4 | AddressFamilyFlags::IPV6,
            ProtocolFlags::TCP,
        ) {
            Ok(s)  => s,
            Err(e) => {
                tracing::debug!("NetworkMonitor: socket enumeration failed: {}", e);
                return findings;
            }
        };

        for sock in &sockets {
            let (local_port, remote_addr, remote_port, pid) = match &sock.protocol_socket_info {
                ProtocolSocketInfo::Tcp(tcp) => {
                    if tcp.remote_port == 0 { continue; }
                    (tcp.local_port, tcp.remote_addr.to_string(),
                     tcp.remote_port, sock.associated_pids.first().copied())
                }
                _ => continue,
            };

            if remote_addr.starts_with("127.") || remote_addr == "::1" { continue; }

            let pid = pid.unwrap_or(0);
            let (process_name, exe_path) = get_process_info(pid);

            // ── Check 1: suspicious port ──────────────────────────────────────
            if self.suspicious_ports.contains(&remote_port)
                || self.suspicious_ports.contains(&local_port) {

                let existing = context.ip_severity(&remote_addr);
                let severity = (0.7_f32 + existing * 0.2).min(1.0);

                findings.push(Finding {
                    finding_type: "suspicious_port".to_string(),
                    severity,
                    detail: format!(
                        "Connection on suspicious port {} ← {} (PID {} / {})",
                        remote_port, remote_addr, pid, process_name
                    ),
                    data: serde_json::json!({
                        "remote_ip":   remote_addr,
                        "remote_port": remote_port,
                        "local_port":  local_port,
                        "pid":         pid,
                        "process":     process_name,
                    }),
                });
            }

            // ── Check 2: unknown process with external connection ─────────────
            // Uses path-validated check — spoofed names fail here
            if !is_known_safe(&process_name, &exe_path) && pid > 4 {
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
                        "exe":         exe_path,
                    }),
                });
            }
        }

        findings
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

fn get_process_info(pid: u32) -> (String, String) {
    if pid == 0 { return ("unknown".to_string(), String::new()); }

    let mut sys = System::new();
    sys.refresh_processes_specifics(
        ProcessesToUpdate::Some(&[sysinfo::Pid::from_u32(pid)]),
        true,
        ProcessRefreshKind::everything(),
    );

    if let Some(proc) = sys.process(sysinfo::Pid::from_u32(pid)) {
        let name = proc.name().to_string_lossy().to_lowercase();
        let exe  = proc.exe()
            .map(|p| p.to_string_lossy().to_lowercase())
            .unwrap_or_default();
        (name, exe)
    } else {
        ("unknown".to_string(), String::new())
    }
}
