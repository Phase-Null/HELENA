// src/agents/process.rs
//
// Type F — Process Watchdog
//
// Phase 3a changes:
//   - known_safe_processes() replaced with is_known_safe(name, exe)
//     which validates BOTH the process name AND the executable path.
//     A spoofed svchost.exe running from AppData will fail the path check
//     even if the name matches. This closes the T1036 masquerading gap.
//   - expected_parents() added — flags system processes spawned by
//     unexpected parents (catches T1036.009 parent PID spoofing)
//   - safe field removed from struct — replaced by is_known_safe() call

use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use sysinfo::{System, ProcessesToUpdate, ProcessRefreshKind, RefreshKind};

use crate::agents::base::{Agent, AgentConfig};
use crate::ipc::protocol::SharedContext;
use crate::ipc::protocol::Finding;

// ── Suspicious process names ──────────────────────────────────────────────────

fn suspicious_names() -> HashSet<&'static str> {
    [
        "mimikatz", "mimikatz.exe", "wce", "wce.exe", "pwdump",
        "msfconsole", "metasploit", "empire", "covenant",
        "nc", "nc.exe", "ncat", "ncat.exe",
        "nmap", "nmap.exe",
        "wireshark", "wireshark.exe", "tshark", "tshark.exe", "tcpdump",
        "psexec", "psexec.exe", "wmiexec",
        "keylogger", "revealer",
    ].into()
}

/// Paths that are suspicious for executable processes.
fn suspicious_path_fragments() -> Vec<&'static str> {
    vec![
        "\\temp\\", "/tmp/",
        "\\appdata\\local\\temp\\",
        "\\windows\\temp\\",
        "\\downloads\\",
    ]
}

// ── Path-validated safe process check ────────────────────────────────────────
//
// Replaces the name-only HashSet approach.
// Both name AND exe path must match for a process to be considered safe.
// This prevents T1036 masquerading — a process named svchost.exe running
// from AppData fails the path check regardless of its name.

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

        // Development tools
        "code.exe"          => exe_lower.contains("\\microsoft vs code\\")
                            || exe_lower.contains("\\vscode\\"),
        "git.exe"           => exe_lower.contains("\\git\\"),
        "python.exe"        => exe_lower.contains("\\python") || exe_lower.contains("\\miniconda")
                            || exe_lower.contains("\\anaconda"),
        "pythonw.exe"       => exe_lower.contains("\\python") || exe_lower.contains("\\miniconda"),
        "cargo.exe"         => exe_lower.contains("\\.cargo\\"),
        "rustc.exe"         => exe_lower.contains("\\.rustup\\") || exe_lower.contains("\\rustup\\"),
        "node.exe"          => exe_lower.contains("\\nodejs\\") || exe_lower.contains("\\node\\"),

        // HELENA stack
        "ollama.exe"        => exe_lower.contains("\\ollama\\")
                            || exe_lower.contains("program files"),
        "ollama_llama_server.exe" => exe_lower.contains("\\ollama\\")
                            || exe_lower.contains("program files"),
        "aegis.exe"         => exe_lower.contains("\\helena\\") || exe_lower.contains("\\aegis"),

        // Windows system processes — strict path requirements
        "svchost.exe"       => exe_lower.starts_with("c:\\windows\\system32\\")
                            || exe_lower.starts_with("c:\\windows\\syswow64\\"),
        "lsass.exe"         => exe_lower.starts_with("c:\\windows\\system32\\"),
        "services.exe"      => exe_lower.starts_with("c:\\windows\\system32\\"),
        "explorer.exe"      => exe_lower.starts_with("c:\\windows\\"),
        "dwm.exe"           => exe_lower.starts_with("c:\\windows\\system32\\"),
        "winlogon.exe"      => exe_lower.starts_with("c:\\windows\\system32\\"),
        "csrss.exe"         => exe_lower.starts_with("c:\\windows\\system32\\"),
        "wininit.exe"       => exe_lower.starts_with("c:\\windows\\system32\\"),
        "taskhostw.exe"     => exe_lower.starts_with("c:\\windows\\system32\\"),
        "runtimebroker.exe" => exe_lower.starts_with("c:\\windows\\system32\\"),
        "sihost.exe"        => exe_lower.starts_with("c:\\windows\\system32\\"),
        "searchhost.exe"    => exe_lower.starts_with("c:\\windows\\system32\\")
                            || exe_lower.contains("\\windows\\"),
        "searchindexer.exe" => exe_lower.starts_with("c:\\windows\\system32\\"),

        // VPN
        "protonvpn.exe"     => exe_lower.contains("\\protonvpn\\"),
        "protonvpn.wireguardservice.exe" => exe_lower.contains("\\protonvpn\\"),
        "wireguard.exe"     => exe_lower.contains("\\wireguard\\"),

        // Gaming/comms
        "steam.exe"         => exe_lower.contains("\\steam\\"),
        "steamwebhelper.exe"=> exe_lower.contains("\\steam\\"),
        "discord.exe"       => exe_lower.contains("\\discord\\"),
        "spotify.exe"       => exe_lower.contains("\\spotify\\"),

        // Acer/OEM software
        "nitrosense.exe"    => exe_lower.contains("\\acer\\") || exe_lower.contains("windowsapps"),
        "ubtservice.exe"    => exe_lower.contains("\\acer\\"),

        // Utilities
        "onedrive.exe"      => exe_lower.contains("\\onedrive\\"),
        "ssh.exe"           => exe_lower.contains("\\openssh\\")
                            || exe_lower.starts_with("c:\\windows\\system32\\"),
        "curl.exe"          => exe_lower.starts_with("c:\\windows\\system32\\")
                            || exe_lower.contains("\\curl\\"),

        // These names have no fixed path — allow by name only
        "system"            => true,
        "idle"              => true,
        "registry"          => true,
        "memory compression"=> true,

        // Anything else is unknown
        _                   => false,
    }
}

// ── Parent-child relationship validation ──────────────────────────────────────
//
// Maps known system processes to their expected parent process names.
// If svchost.exe is spawned by anything other than services.exe, that's
// T1036.009 parent PID spoofing or process hollowing.

fn expected_parent(process_name: &str) -> Option<&'static [&'static str]> {
    match process_name {
        "svchost.exe"    => Some(&["services.exe"]),
        "lsass.exe"      => Some(&["wininit.exe"]),
        "explorer.exe"   => Some(&["userinit.exe", "winlogon.exe"]),
        "taskhost.exe"   => Some(&["services.exe"]),
        "conhost.exe"    => Some(&["csrss.exe"]),
        "taskhostw.exe"  => Some(&["services.exe"]),
        _                => None,
    }
}

// ── CPU history ───────────────────────────────────────────────────────────────

struct CpuHistory {
    samples: HashMap<u32, Vec<f32>>,
    window:  usize,
}

impl CpuHistory {
    fn new(window: usize) -> Self {
        Self { samples: HashMap::new(), window }
    }

    fn push(&mut self, pid: u32, cpu: f32) {
        let s = self.samples.entry(pid).or_default();
        s.push(cpu);
        if s.len() > self.window { s.remove(0); }
    }

    fn sustained_high(&self, pid: u32, threshold: f32) -> bool {
        if let Some(s) = self.samples.get(&pid) {
            s.len() >= self.window && s.iter().all(|&c| c > threshold)
        } else { false }
    }

    fn prune(&mut self, active_pids: &HashSet<u32>) {
        self.samples.retain(|pid, _| active_pids.contains(pid));
    }
}

// ── Agent struct ──────────────────────────────────────────────────────────────

pub struct ProcessWatchdog {
    config:      AgentConfig,
    suspicious:  HashSet<&'static str>,
    bad_paths:   Vec<&'static str>,
    sys:         Mutex<System>,
    known_pids:  Mutex<HashSet<u32>>,
    cpu_history: Mutex<CpuHistory>,
}

impl ProcessWatchdog {
    pub fn new(variant: u8, interval_secs: u64, threshold: f32) -> Self {
        let mut sys = System::new_with_specifics(
            RefreshKind::nothing().with_processes(ProcessRefreshKind::everything()),
        );
        sys.refresh_all();

        let known_pids: HashSet<u32> = sys.processes()
            .keys()
            .map(|p| p.as_u32())
            .collect();

        Self {
            config:      AgentConfig::new("process_watchdog", variant, interval_secs, threshold),
            suspicious:  suspicious_names(),
            bad_paths:   suspicious_path_fragments(),
            sys:         Mutex::new(sys),
            known_pids:  Mutex::new(known_pids),
            cpu_history: Mutex::new(CpuHistory::new(3)),
        }
    }

    pub fn v1() -> Self { Self::new(1, 5,  0.3) }
    pub fn v2() -> Self { Self::new(2, 10, 0.5) }
    pub fn v3() -> Self { Self::new(3, 20, 0.7) }
    pub fn v4() -> Self { Self::new(4, 7,  0.4) }
}

impl Agent for ProcessWatchdog {
    fn config(&self) -> &AgentConfig { &self.config }

    fn scan(&self, context: &SharedContext) -> Vec<Finding> {
        let mut findings = Vec::new();

        let mut sys = self.sys.lock().unwrap();
        sys.refresh_processes_specifics(
            ProcessesToUpdate::All,
            true,
            ProcessRefreshKind::everything(),
        );

        let mut known     = self.known_pids.lock().unwrap();
        let mut cpu_hist  = self.cpu_history.lock().unwrap();
        let mut current_pids: HashSet<u32> = HashSet::new();

        // Build a pid→name lookup for parent validation
        let pid_to_name: HashMap<u32, String> = sys.processes()
            .iter()
            .map(|(pid, proc)| {
                (pid.as_u32(), proc.name().to_string_lossy().to_lowercase())
            })
            .collect::<HashMap<_, _>>();

        for (pid_obj, process) in sys.processes() {
            let pid  = pid_obj.as_u32();
            current_pids.insert(pid);

            let name = process.name().to_string_lossy().to_lowercase();
            let exe  = process.exe()
                .map(|p| p.to_string_lossy().to_lowercase())
                .unwrap_or_default();

            // ── Check 1: suspicious process name ─────────────────────────────
            for sus in &self.suspicious {
                if name.contains(sus) || exe.contains(sus) {
                    let existing = context.pid_severity(pid);
                    let severity = (0.95_f32 + existing * 0.05).min(1.0);
                    findings.push(Finding {
                        finding_type: "suspicious_process".to_string(),
                        severity,
                        detail: format!("Suspicious process: {} (PID {}) at {}", name, pid, exe),
                        data: serde_json::json!({ "pid": pid, "name": name, "exe": exe }),
                    });
                    break;
                }
            }

            // ── Check 2: running from suspicious path ─────────────────────────
            for bad in &self.bad_paths {
                if exe.contains(bad) {
                    findings.push(Finding {
                        finding_type: "suspicious_path".to_string(),
                        severity: 0.7,
                        detail: format!("Process from suspicious path: {} (PID {})", exe, pid),
                        data: serde_json::json!({ "pid": pid, "name": name, "exe": exe }),
                    });
                    break;
                }
            }

            // ── Check 3: masquerading — name known but path wrong ─────────────
            // Known process name but failing path validation = likely spoof
            if !is_known_safe(&name, &exe) && !exe.is_empty() {
                // Check if this name is a known system process running from wrong place
                let is_system_name = matches!(name.as_str(),
                    "svchost.exe" | "lsass.exe" | "services.exe" |
                    "explorer.exe" | "dwm.exe" | "winlogon.exe" |
                    "csrss.exe" | "wininit.exe" | "taskhostw.exe"
                );
                if is_system_name {
                    findings.push(Finding {
                        finding_type: "process_masquerading".to_string(),
                        severity: 0.95,
                        detail: format!(
                            "System process name from unexpected path: {} at {} (PID {})",
                            name, exe, pid
                        ),
                        data: serde_json::json!({
                            "pid": pid, "name": name, "exe": exe,
                            "expected": "c:\\windows\\system32\\"
                        }),
                    });
                }
            }

            // ── Check 4: parent-child relationship validation ──────────────────
            if let Some(expected) = expected_parent(&name) {
                if let Some(parent_pid) = process.parent().map(|p| p.as_u32()) {
                    let parent_name = pid_to_name.get(&parent_pid)
                        .map(|s| s.as_str())
                        .unwrap_or("unknown");
                    if !expected.contains(&parent_name) {
                        findings.push(Finding {
                            finding_type: "parent_child_mismatch".to_string(),
                            severity: 0.9,
                            detail: format!(
                                "Parent PID spoofing: {} (PID {}) spawned by {} instead of {:?}",
                                name, pid, parent_name, expected
                            ),
                            data: serde_json::json!({
                                "pid":         pid,
                                "name":        name,
                                "exe":         exe,
                                "parent_pid":  parent_pid,
                                "parent_name": parent_name,
                                "expected":    expected,
                            }),
                        });
                    }
                }
            }

            // ── Check 5: new process (unknown and not safe) ───────────────────
            if !known.contains(&pid) && pid > 4 && !is_known_safe(&name, &exe) {
                findings.push(Finding {
                    finding_type: "new_process".to_string(),
                    severity: 0.2,
                    detail: format!("New process: {} (PID {})", name, pid),
                    data: serde_json::json!({ "pid": pid, "name": name, "exe": exe }),
                });
            }

            // ── Check 6: sustained high CPU ───────────────────────────────────
            let cpu = process.cpu_usage();
            cpu_hist.push(pid, cpu);
            if cpu_hist.sustained_high(pid, 85.0) {
                findings.push(Finding {
                    finding_type: "sustained_high_cpu".to_string(),
                    severity: 0.5,
                    detail: format!("Process {} (PID {}) sustained >85% CPU", name, pid),
                    data: serde_json::json!({ "pid": pid, "name": name, "cpu_percent": cpu }),
                });
            }
        }

        *known = current_pids.clone();
        cpu_hist.prune(&current_pids);
        findings
    }
}
