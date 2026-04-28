// src/agents/process.rs
//
// Type F — Process Watchdog
//
// Monitors running processes for:
//   - Suspicious names (mimikatz, metasploit, common RATs)
//   - New processes that appeared since last scan
//   - Sustained high CPU (>85% for 3+ consecutive scans)
//   - Processes running from unusual paths (temp dirs, etc.)
//
// Uses the `sysinfo` crate — the only cross-platform option that
// actually works on Windows. rust-psutil is Linux/macOS only.
//
// sysinfo requires keeping a System instance alive between scans
// for CPU measurements to be accurate (they need a delta).
// We store it in a Mutex on the struct.
//
// Four variants:
//   V1 — 5s,  threshold 0.3 (catches most, more noise)
//   V2 — 10s, threshold 0.5 (balanced)
//   V3 — 20s, threshold 0.7 (conservative)
//   V4 — 7s,  threshold 0.4 (mid-speed)

use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use sysinfo::{System, ProcessesToUpdate, ProcessRefreshKind, RefreshKind};

use crate::agents::base::{Agent, AgentConfig};
use crate::ipc::protocol::SharedContext;
use crate::ipc::protocol::Finding;

// ── Suspicious process names ──────────────────────────────────────────────────

fn suspicious_names() -> HashSet<&'static str> {
    [
        // Credential theft
        "mimikatz", "mimikatz.exe", "wce", "wce.exe", "pwdump",
        // Remote access / exploitation
        "msfconsole", "metasploit", "empire", "covenant",
        // Network tools (legitimate but suspicious in this context)
        "nc", "nc.exe", "ncat", "ncat.exe",
        "nmap", "nmap.exe",
        // Packet capture
        "wireshark", "wireshark.exe", "tshark", "tshark.exe", "tcpdump",
        // Lateral movement
        "psexec", "psexec.exe", "wmiexec",
        // Keyloggers
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

fn known_safe_processes() -> HashSet<&'static str> {
    [
        "nitrosense.exe", "opera.exe",
        "steam.exe", "steamwebhelper.exe",
        "onedrive.exe", "explorer.exe",
        "searchhost.exe", "searchindexer.exe",
        "svchost.exe", "lsass.exe", "services.exe",
        "system", "idle", "registry",
        "runtimebroker.exe", "sihost.exe",
        "taskhostw.exe", "dwm.exe",
    ].into()
}

// ── CPU history ───────────────────────────────────────────────────────────────

/// Tracks CPU usage samples per PID to detect sustained high usage.
struct CpuHistory {
    /// Ring buffer of last N samples per PID
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
        if s.len() > self.window {
            s.remove(0);
        }
    }

    /// True if the last `window` samples are all above threshold.
    fn sustained_high(&self, pid: u32, threshold: f32) -> bool {
        if let Some(s) = self.samples.get(&pid) {
            s.len() >= self.window && s.iter().all(|&c| c > threshold)
        } else {
            false
        }
    }

    /// Clean up PIDs that no longer exist.
    fn prune(&mut self, active_pids: &HashSet<u32>) {
        self.samples.retain(|pid, _| active_pids.contains(pid));
    }
}

// ── Agent struct ──────────────────────────────────────────────────────────────

pub struct ProcessWatchdog {
    config:          AgentConfig,
    suspicious:      HashSet<&'static str>,
    bad_paths:       Vec<&'static str>,
    safe:            HashSet<&'static str>,
    /// sysinfo System — must be kept alive between scans for CPU delta to work
    sys:             Mutex<System>,
    /// PIDs seen on previous scan — used to detect new processes
    known_pids:      Mutex<HashSet<u32>>,
    cpu_history:     Mutex<CpuHistory>,
}

impl ProcessWatchdog {
    pub fn new(variant: u8, interval_secs: u64, threshold: f32) -> Self {
        // Create and seed the sysinfo System instance
        let mut sys = System::new_with_specifics(
            RefreshKind::nothing().with_processes(ProcessRefreshKind::everything()),
        );
        sys.refresh_all();

        // Seed known PIDs so we don't report every running process as "new"
        let known_pids: HashSet<u32> = sys.processes()
            .keys()
            .map(|p| p.as_u32())
            .collect();

        Self {
            config:      AgentConfig::new("process_watchdog", variant, interval_secs, threshold),
            suspicious:  suspicious_names(),
            bad_paths:   suspicious_path_fragments(),
            safe:        known_safe_processes(), 
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

        // Refresh process list — sysinfo needs explicit refresh calls
        let mut sys = self.sys.lock().unwrap();
        sys.refresh_processes_specifics(
            ProcessesToUpdate::All,
            true,
            ProcessRefreshKind::everything(),
        );

        let mut known = self.known_pids.lock().unwrap();
        let mut cpu_hist = self.cpu_history.lock().unwrap();

        let mut current_pids: HashSet<u32> = HashSet::new();

        for (pid_obj, process) in sys.processes() {
            let pid = pid_obj.as_u32();
            current_pids.insert(pid);

            let name = process.name().to_string_lossy().to_lowercase();
            let exe  = process.exe()
                .map(|p| p.to_string_lossy().to_lowercase())
                .unwrap_or_default();

            // ── Check 1: suspicious process name ─────────────────────────────
            for sus in &self.suspicious {
                if name.contains(sus) || exe.contains(sus) {
                    // Correlate: already flagged by another agent?
                    let existing = context.pid_severity(pid);
                    let severity = (0.95_f32 + existing * 0.05).min(1.0);

                    findings.push(Finding {
                        finding_type: "suspicious_process".to_string(),
                        severity,
                        detail: format!(
                            "Suspicious process: {} (PID {}) at {}",
                            name, pid, exe
                        ),
                        data: serde_json::json!({
                            "pid":  pid,
                            "name": name,
                            "exe":  exe,
                        }),
                    });
                    break; // one finding per process per scan
                }
            }

            // ── Check 2: process running from suspicious path ─────────────────
            for bad in &self.bad_paths {
                if exe.contains(bad) {
                    findings.push(Finding {
                        finding_type: "suspicious_path".to_string(),
                        severity: 0.7,
                        detail: format!(
                            "Process running from suspicious path: {} (PID {})",
                            exe, pid
                        ),
                        data: serde_json::json!({
                            "pid":  pid,
                            "name": name,
                            "exe":  exe,
                        }),
                    });
                    break;
                }
            }

            // ── Check 3: new process since last scan ──────────────────────────
            if !known.contains(&pid) && pid > 4 && !self.safe.contains(name.as_str()) {
                findings.push(Finding {
                    finding_type: "new_process".to_string(),
                    severity: 0.2,
                    detail: format!("New process: {} (PID {})", name, pid),
                    data: serde_json::json!({
                        "pid":  pid,
                        "name": name,
                        "exe":  exe,
                    }),
                });
            }

            // ── Check 4: sustained high CPU ───────────────────────────────────
            let cpu = process.cpu_usage();
            cpu_hist.push(pid, cpu);

            if cpu_hist.sustained_high(pid, 85.0) {
                findings.push(Finding {
                    finding_type: "sustained_high_cpu".to_string(),
                    severity: 0.5,
                    detail: format!(
                        "Process {} (PID {}) has sustained >85% CPU usage",
                        name, pid
                    ),
                    data: serde_json::json!({
                        "pid":         pid,
                        "name":        name,
                        "cpu_percent": cpu,
                    }),
                });
            }
        }

        // Update known PIDs and prune CPU history
        *known = current_pids.clone();
        cpu_hist.prune(&current_pids);

        findings
    }
}
