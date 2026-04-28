// src/agents/integrity.rs
//
// Type E — File Integrity Monitor
//
// Watches HELENA's own source files for unexpected modifications.
// Computes SHA-256 hashes on first scan (baseline), then compares
// on every subsequent scan. Any change is a finding.
//
// Protected files (kill_switch.py, core.py, start_helena.py) trigger
// severity 1.0 on ANY change — these must never be silently modified.
//
// Non-protected files trigger severity 0.3 on change — expected
// because HELENA writes her own code through CodeEditor. The file
// integrity agent is not there to block self-modification, it's there
// to detect unexpected modification (i.e., not through HELENA).
//
// Four variants:
//   V1 — 15s interval (general monitoring)
//   V2 — 30s interval (balanced)
//   V3 — 60s interval (low-overhead)
//   V4 — 10s interval (fast — focused on protected files only)

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use sha2::{Sha256, Digest};

use crate::agents::base::{Agent, AgentConfig};
use crate::ipc::protocol::SharedContext;
use crate::ipc::protocol::Finding;

// ── Watched directories and protected files ───────────────────────────────────
// These are relative to HELENA's root directory.
// We resolve them at construction time.

fn watched_dirs() -> Vec<&'static str> {
    vec![
        "helena_core",
        "helena_ml",
        "helena_desktop",
        "helena_training",
        "helena_security",
        "aegis_core/src",
        "aegis_python",
    ]
}

fn protected_filenames() -> HashSet<&'static str> {
    [
        "kill_switch.py",
        "core.py",
        "start_helena.py",
        "aegis.exe",
    ].into()
}

// ── Agent struct ──────────────────────────────────────────────────────────────

pub struct FileIntegrityMonitor {
    config:     AgentConfig,
    /// SHA-256 baseline: path → hex hash
    /// Wrapped in Mutex so scan() can update non-protected baselines
    /// (we treat changes to non-protected files as expected after first detection)
    baseline:   Mutex<HashMap<String, String>>,
    protected:  HashSet<&'static str>,
    /// For V4 — only watch protected files, skip everything else
    protected_only: bool,
}

impl FileIntegrityMonitor {
    pub fn new(variant: u8, interval_secs: u64, threshold: f32, protected_only: bool) -> Self {
        let mut agent = Self {
            config:         AgentConfig::new("file_integrity", variant, interval_secs, threshold),
            baseline:       Mutex::new(HashMap::new()),
            protected:      protected_filenames(),
            protected_only,
        };
        agent.build_baseline();
        agent
    }

    pub fn v1() -> Self { Self::new(1, 15, 0.3, false) }
    pub fn v2() -> Self { Self::new(2, 30, 0.3, false) }
    pub fn v3() -> Self { Self::new(3, 60, 0.3, false) }
    /// V4 only watches protected files, very fast
    pub fn v4() -> Self { Self::new(4, 10, 0.0, true)  }

    fn build_baseline(&mut self) {
        let mut baseline = self.baseline.lock().unwrap();
        for path in self.collect_files() {
            if let Ok(hash) = hash_file(&path) {
                baseline.insert(path.to_string_lossy().to_string(), hash);
            }
        }
        tracing::info!(
            "FileIntegrity {}: baseline built — {} files",
            self.config.id, baseline.len()
        );
    }

    fn collect_files(&self) -> Vec<PathBuf> {
        let mut files = Vec::new();

        // Try to find HELENA root — walk up from current dir
        let root = find_helena_root().unwrap_or_else(|| PathBuf::from("."));

        for dir_name in watched_dirs() {
            let dir = root.join(dir_name);
            if !dir.exists() { continue; }

            collect_py_files(&dir, &mut files);
        }

        if self.protected_only {
            // Filter to only files whose name is in the protected set
            files.retain(|p| {
                p.file_name()
                    .and_then(|n| n.to_str())
                    .map(|n| self.protected.contains(n))
                    .unwrap_or(false)
            });
        }

        files
    }

    fn is_protected(&self, path: &Path) -> bool {
        path.file_name()
            .and_then(|n| n.to_str())
            .map(|n| self.protected.contains(n))
            .unwrap_or(false)
    }
}

impl Agent for FileIntegrityMonitor {
    fn config(&self) -> &AgentConfig { &self.config }

    fn scan(&self, _context: &SharedContext) -> Vec<Finding> {
        let mut findings = Vec::new();
        let mut baseline = self.baseline.lock().unwrap();

        // Check all baselined files for changes or deletion
        let paths: Vec<String> = baseline.keys().cloned().collect();
        for path_str in &paths {
            let path = Path::new(path_str);
            let is_protected = self.is_protected(path);

            if !path.exists() {
                findings.push(Finding {
                    finding_type: "file_deleted".to_string(),
                    severity: if is_protected { 1.0 } else { 0.6 },
                    detail: format!("File deleted: {}", path_str),
                    data: serde_json::json!({
                        "path":      path_str,
                        "protected": is_protected,
                    }),
                });
                // Remove from baseline — don't keep firing on the same deletion
                baseline.remove(path_str);
                continue;
            }

            match hash_file(path) {
                Ok(current_hash) => {
                    let known = &baseline[path_str];
                    if &current_hash != known {
                        findings.push(Finding {
                            finding_type: "file_modified".to_string(),
                            severity: if is_protected { 1.0 } else { 0.3 },
                            detail: format!("File modified: {}", path_str),
                            data: serde_json::json!({
                                "path":      path_str,
                                "protected": is_protected,
                                "old_hash":  &known[..12],
                                "new_hash":  &current_hash[..12],
                            }),
                        });

                        // Update baseline for non-protected files so we don't
                        // keep reporting the same change on every scan
                        if !is_protected {
                            baseline.insert(path_str.clone(), current_hash);
                        }
                        // Protected files: keep old hash — keep firing until
                        // operator explicitly acknowledges and resets baseline
                    }
                }
                Err(_) => {
                    // Can't read file — flag it
                    findings.push(Finding {
                        finding_type: "file_unreadable".to_string(),
                        severity: if is_protected { 0.8 } else { 0.2 },
                        detail: format!("Cannot read file: {}", path_str),
                        data: serde_json::json!({ "path": path_str }),
                    });
                }
            }
        }

        // Check for new files not in baseline
        if !self.protected_only {
            for path in self.collect_files() {
                let key = path.to_string_lossy().to_string();
                if !baseline.contains_key(&key) {
                    if let Ok(hash) = hash_file(&path) {
                        findings.push(Finding {
                            finding_type: "new_file".to_string(),
                            severity: 0.4,
                            detail: format!("New file appeared: {}", key),
                            data: serde_json::json!({ "path": key }),
                        });
                        baseline.insert(key, hash);
                    }
                }
            }
        }

        findings
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

fn hash_file(path: &Path) -> anyhow::Result<String> {
    let bytes = std::fs::read(path)?;
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    Ok(hex::encode(hasher.finalize()))
}

fn collect_py_files(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = std::fs::read_dir(dir) else { return };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_py_files(&path, out);
        } else if path.extension().and_then(|e| e.to_str()) == Some("py")
               || path.extension().and_then(|e| e.to_str()) == Some("rs") {
            out.push(path);
        }
    }
}

/// Walk upward from the current directory looking for HELENA's marker files.
fn find_helena_root() -> Option<PathBuf> {
    let mut dir = std::env::current_dir().ok()?;
    for _ in 0..6 {
        if dir.join("start_helena.py").exists()
            || dir.join("helena_core").exists() {
            return Some(dir);
        }
        dir = dir.parent()?.to_path_buf();
    }
    None
}
