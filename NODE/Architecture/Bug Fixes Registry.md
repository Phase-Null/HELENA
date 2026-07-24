---
tags: [bugfix, registry]
date: 2026-03-05
status: active
total_bugs: 39
already_fixed: 4
needs_fix: 25
phantom: 1
no_action: 1
re_audit: 3
---

# Bug Fixes Registry — All 39 Bugs

Comprehensive list of all bugs identified in the HELENA project, with severity, affected file, description, and wikilinks to relevant Architecture/AEGIS notes.

> [!info] Summary
> - **39 total bugs**
> - 4 CRITICAL (P0) — all **already fixed**
> - 10 HIGH (P1) — 2 fixed, 8 need fix
> - 9 MEDIUM (P2) — 4 fixed, 5 need fix
> - 9 LOW (P3) — 1 no_action, 8 need fix
> - 3 **re-audit fixes** (bugs in original fixes)
> - 1 phantom file (doesn't exist)

---

## CRITICAL (P0) — Already Fixed

### Bug 1: Trainer Constructor Missing `runtime` Argument
| Field | Value |
|-------|-------|
| **File** | `helena_desktop/main_window.py` lines 114-124 |
| **Category** | desktop |
| **Status** | **already_fixed** |
| **Description** | AutonomousTrainer.__init__ was missing the self.runtime positional argument, causing TypeError on startup |
| **Root Cause** | Constructor called with wrong number of arguments — missing runtime as 2nd param |
| **Fix** | self.runtime now passed as 2nd arg |
| **See also** | [[Training Pipeline]] |

### Bug 2: `Intent.QUESTION` Does Not Exist
| Field | Value |
|-------|-------|
| **File** | `helena_ml/chat_engine.py` line 578 |
| **Category** | ml |
| **Status** | **already_fixed** |
| **Description** | AttributeError at runtime when LLM is available and memory results exist |
| **Root Cause** | Intent enum has no QUESTION attribute — closest match is EXPLAIN |
| **Fix** | Intent.QUESTION replaced with Intent.EXPLAIN |
| **See also** | [[Chat Engine]] |

### Bug 3: `validation_result.errors` Should Be `.issues`
| Field | Value |
|-------|-------|
| **File** | `helena_core/kernel/core.py` line 678 |
| **Category** | kernel |
| **Status** | **already_fixed** |
| **Description** | AttributeError when validation fails — ValidationResult has .issues not .errors |
| **Root Cause** | Attribute name mismatch between ValidationResult dataclass and consumer code |
| **Fix** | .errors replaced with .issues |
| **See also** | [[Kernel]] |

### Bug 4: AEGIS Firewall — Loopback Permit Allows ALL Traffic
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/firewall/engine.rs` lines 66-92 |
| **Category** | aegis |
| **Status** | **already_fixed** |
| **Description** | add_loopback_permit() only had local-port condition, no remote-address restriction. ALL inbound connections to port 47201 were permitted |
| **Root Cause** | wfp crate v0.0.3 lacked IpAddrConditionBuilder API |
| **Fix** | wfp upgraded to 0.0.7, IpAddressConditionBuilder::remote().equal(127.0.0.1) added, plus netsh safety-net rule |
| **See also** | [[AEGIS/Bug Fixes]], [[AEGIS/Overview]] |

---

## HIGH (P1) — Data Loss / Functional Bugs

### Bug 5: `wipe_memory` Dead Code on Line 103
| Field | Value |
|-------|-------|
| **File** | `helena_core/security/encryption.py` lines 99-103 |
| **Category** | security |
| **Status** | **needs_fix** |
| **Description** | Unreachable return statement on line 103 after the actual return on line 101 |
| **Fix** | Delete line 103 |

### Bug 7: train.py — Double-Counted Loss
| Field | Value |
|-------|-------|
| **File** | `helena_ml/helena_llm/train.py` lines 357, 363 |
| **Category** | ml |
| **Status** | **needs_fix** |
| **Description** | Average loss reported is ~2x actual value. total_loss accumulated twice per step |
| **Fix** | Delete line 357 (duplicate `total_loss += loss.item()`) |
| **See also** | [[HELENA-Net Model]] |

### Bug 8: `--config large` Silently Falls Back to NANO
| Field | Value |
|-------|-------|
| **File** | `helena_ml/helena_llm/train.py` lines 29, 412 |
| **Category** | ml |
| **Status** | **needs_fix** |
| **Description** | HELENA_LARGE exists in config.py but not imported or in config_map |
| **Fix** | Add HELENA_LARGE to import and config_map |
| **See also** | [[Config Reference]] |

### Bug 9: Encryption Key Lost on Restart
| Field | Value |
|-------|-------|
| **File** | `helena_core/utils/config_manager.py` lines 420-453 |
| **Category** | core |
| **Status** | **needs_fix** |
| **Description** | secrets.token_bytes(32) generates random key but never persisted. All previously encrypted data becomes permanently unreadable after restart |
| **Fix** | Persist key to .encryption_key file; load existing on startup |
| **See also** | [[Config Reference]] |

### Bug 10: Emotion Modulation Is a No-Op (3 sub-bugs)
| Field | Value |
|-------|-------|
| **File** | `helena_core/kernel/personality.py` lines 425-492 |
| **Category** | kernel |
| **Status** | **needs_fix** (re-audit fix applied) |
| **Description** | Three bugs make ALL emotion modulation non-functional: (1) intensity always 0.0, (2) case mismatch, (3) commentary same bug |
| **Re-audit fix** | Original fix lowercased `dominant` but left emotions dict UPPERCASE — `dominant in emotions` was ALWAYS False. Now uses `emotions.get(dominant.upper())` |
| **See also** | [[Personality System]] |

### Bug 11: Disk/Network IO Are Cumulative, Not Rates
| Field | Value |
|-------|-------|
| **File** | `helena_core/runtime/resources.py` lines 207-218 |
| **Category** | runtime |
| **Status** | **needs_fix** |
| **Description** | psutil counters return cumulative bytes since boot, not rates |
| **Fix** | Track previous IO counters, calculate delta_bytes / delta_time for MB/s rate |
| **See also** | [[Runtime]] |

### Bug 12: Fernet Key Format Mismatch
| Field | Value |
|-------|-------|
| **File** | `helena_core/utils/logging.py` lines 101-106, 215-218 |
| **Category** | core |
| **Status** | **needs_fix** |
| **Description** | base64.urlsafe_b64encode(32_bytes) produces 44 chars, but Fernet requires valid key material. ValueError on every encrypt/decrypt |
| **Fix** | Add PBKDF2 derivation step to produce valid Fernet key from raw bytes |

### Bug 13: MoE Routing Uses Wrong Probabilities
| Field | Value |
|-------|-------|
| **File** | `helena_ml/helena_llm/architecture.py` lines 323-332 |
| **Category** | ml |
| **Status** | **needs_fix** |
| **Description** | Expert outputs weighted by router_probs (full softmax) instead of top_k_probs (renormalized). Weights don't sum to 1.0 per token |
| **Fix** | Use top_k_probs for expert weighting with correct k-index gathering |
| **See also** | [[HELENA-Net Model]] |

### Bug 14: ChaCha20 Without Authentication
| Field | Value |
|-------|-------|
| **File** | `helena_core/security/encryption.py` lines 134-173 |
| **Category** | security |
| **Status** | **needs_fix** |
| **Description** | Docstring says ChaCha20-Poly1305 but uses raw ChaCha20 with no authentication tag. Ciphertext can be tampered undetected |
| **Fix** | Replace with ChaCha20Poly1305 AEAD cipher |

### Bug 15: Regex Pattern Used with contains()
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/etw/providers.rs` lines 118, 152 |
| **Category** | aegis |
| **Status** | **needs_fix** |
| **Description** | `"reg add.*run"` is regex but checked with `.contains()` which treats `.*` as literal. Registry Run key persistence NOT detected |
| **Fix** | Replace with two separate contains checks for "reg add" and "run" |
| **See also** | [[AEGIS/ETW System]], [[AEGIS/Bug Fixes]] |

### Bug 16: Code Editor Can Be None (Crash)
| Field | Value |
|-------|-------|
| **File** | `helena_ml/chat_engine.py` line 764 |
| **Category** | ml |
| **Status** | **needs_fix** |
| **Description** | hasattr(self, '_code_editor') returns True even if _code_editor is None |
| **Fix** | Replace hasattr check with explicit None check |
| **See also** | [[Chat Engine]] |

---

## HIGH — Already Fixed

### Bug 6: task_processor.py — Command Injection (Phantom File)
| Field | Value |
|-------|-------|
| **File** | `helena_core/kernel/task_processor.py` lines 32-33 |
| **Category** | kernel |
| **Status** | **phantom_file** — file does NOT exist |
| **Description** | Reported file doesn't exist. Bug is moot |

---

## MEDIUM (P2) — Needs Fix

### Bug 17: Similarity Calculation Wrong for L2 Distance
| Field | Value |
|-------|-------|
| **File** | `helena_core/memory/vector_store.py` line 222 |
| **Category** | memory |
| **Status** | **needs_fix** (fix applied: `1.0 / (1.0 + dist)`) |
| **Description** | similarity = 1.0 - dist assumes cosine, ChromaDB defaults to L2 |
| **See also** | [[Memory System]] |

### Bug 18: Dead Code for Disabled Rule Violations
| Field | Value |
|-------|-------|
| **File** | `helena_core/kernel/regulatory.py` lines 210-219 |
| **Category** | kernel |
| **Status** | **needs_fix** (fix applied) |
| **Description** | check() skips disabled rules, making operator-rule enforcement unreachable |
| **Fix** | Don't skip disabled operator rules — their enforcement must fire |
| **See also** | [[Personality System]] |

### Bug 19: Memory Vector Dimension Mismatch
| Field | Value |
|-------|-------|
| **File** | `helena_core/utils/config_manager.py` line 67 |
| **Category** | core |
| **Status** | **needs_fix** |
| **Description** | vector_dimension defaults to 768, but OfflineEmbedder produces 384-dim vectors |
| **Fix** | Change default from 768 to 384 |
| **See also** | [[Memory System]] |

### Bug 20: Memory Reservation Not Implemented
| Field | Value |
|-------|-------|
| **File** | `helena_core/runtime/gaming.py` line 390 |
| **Category** | runtime |
| **Status** | **needs_fix** |
| **Fix** | Add bytearray allocation with MemoryError handling |
| **See also** | [[Runtime]] |

### Bug 21: Logger API Mismatch Throughout
| Field | Value |
|-------|-------|
| **File** | `helena_core/runtime/hardware.py` multiple lines |
| **Category** | runtime |
| **Status** | **needs_fix** |
| **Description** | logger.info("Tag", "Message") — message silently dropped |
| **Fix** | Replace with logger.info("[Tag] Message") |
| **See also** | [[Runtime]] |

### Bug 22: New `System` Object Created Per PID
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/agents/network.rs` lines 286-301 |
| **Category** | aegis |
| **Status** | **needs_fix** (fix applied: System created once in scan()) |
| **Description** | System::new() is extremely expensive, called per PID |
| **Fix** | Create System once in scan(), pass to get_process_info() |
| **See also** | [[AEGIS/Network Agent]], [[AEGIS/Bug Fixes]] |

### Bug 25: Missing `save()` Calls
| Field | Value |
|-------|-------|
| **File** | `helena_training/trainer.py` lines 136-137 |
| **Category** | training |
| **Status** | **needs_fix** |
| **Fix** | Add dataset.save() and improvement_log.save() |
| **See also** | [[Training Pipeline]] |

### Bug 26: Race Condition on `active_session`
| Field | Value |
|-------|-------|
| **File** | `helena_training/trainer.py` lines 143-144 |
| **Category** | training |
| **Status** | **needs_fix** |
| **Fix** | Wrap `self.active_session = False` in `with self.lock:` |
| **See also** | [[Training Pipeline]] |

### Bug 28: Path Traversal via Category Names
| Field | Value |
|-------|-------|
| **File** | `helena_training/dataset.py` lines 21-27 |
| **Category** | training |
| **Status** | **needs_fix** (fix applied: `_safe_category()` regex) |
| **Fix** | Sanitize category names with regex |
| **See also** | [[Training Pipeline]] |

---

## MEDIUM — Already Fixed 

### Bug 23: Retaliate/Lockdown Tiers Return None
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/firewall/responder.rs` line 158 |
| **Category** | aegis |
| **Status** | **already_fixed** |
| **See also** | [[AEGIS/Bug Fixes]] |

### Bug 24: No WFP Filter ID Storage
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/firewall/rules.rs` line 42 |
| **Category** | aegis |
| **Status** | **already_fixed** |
| **Fix** | HashMap<u16, u64> now stores filter IDs |
| **See also** | [[AEGIS/Bug Fixes]] |

### Bug 27: Cleanup Removes IP Blocks on Shutdown
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/firewall/rules.rs` lines 231-238 |
| **Category** | aegis |
| **Status** | **already_fixed** |
| **Fix** | cleanup_temporary_rules() only removes non-persistent blocks |
| **See also** | [[AEGIS/Bug Fixes]] |

---

## LOW (P3) — Needs Fix

### Bug 29: Typo "propperly"
| Field | Value |
|-------|-------|
| **File** | `helena_ml/chat_engine.py` line 611 |
| **Fix** | Replace "propperly" with "properly" |
| **See also** | [[Chat Engine]] |

### Bug 30: utils.py — Unused Import
| Field | Value |
|-------|-------|
| **File** | `helena_ml/helena_llm/utils.py` line 1 |
| **Fix** | Remove `import torch.nn.functional as F` |

### Bug 31: auditor.py — Unused Import
| Field | Value |
|-------|-------|
| **File** | `helena_training/auditor.py` line 1 |
| **Fix** | Remove `from typing import List` |

### Bug 32: improver.py — Unused Import
| Field | Value |
|-------|-------|
| **File** | `helena_training/improver.py` line 1 |
| **Fix** | Remove `import random` |

### Bug 33: O(n) `remove(0)`
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/state.rs` line 242 |
| **Fix** | Vec → VecDeque, pop_front() instead of remove(0) |
| **See also** | [[AEGIS/State Management]], [[AEGIS/Bug Fixes]] |

### Bug 34: String Slice Can Panic
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/etw/consumer.rs` line 158 |
| **Fix** | Replace byte-slicing with char-boundary-safe truncation |
| **See also** | [[AEGIS/ETW System]], [[AEGIS/Bug Fixes]] |

### Bug 35: File Handle Leak + OOM Risk
| Field | Value |
|-------|-------|
| **File** | `helena_desktop/main_window.py` various |
| **Fix** | Replace `open(path, 'r').read()[:2000]` with `with open(path) as f: f.read(2000)` |

### Bug 36: start_helena.bat — Hardcoded Path
| Field | Value |
|-------|-------|
| **File** | `start_helena.bat` line 1 |
| **Fix** | Replace `C:\users\franc\...` with `%~dp0` |

### Bug 37: requirements.txt — Duplicate Dependencies
| Field | Value |
|-------|-------|
| **File** | `requirements.txt` |
| **Fix** | Remove duplicate sentence-transformers and llama-cpp-python entries |

### Bug 38: Unused `_state` Parameter — No Action
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/etw/consumer.rs` |
| **Status** | **no_action** — intentionally unused, prefixed with underscore |

### Bug 39: Thread-Unsafe Lock Creation
| Field | Value |
|-------|-------|
| **File** | `helena_integration.py` various |
| **Category** | integration |
| **Status** | **needs_fix** (re-audit fix applied: module-level guard) |
| **Description** | _security_lock created lazily via hasattr check — not thread-safe |
| **Re-audit fix** | Original fix just moved racy pattern to helper method. Correct fix uses module-level `_SECURITY_LOCK_INIT_GUARD` for double-checked locking |
| **See also** | [[AEGIS/Integration Bridge]] |

---

## Re-Audit Fixes

| Bug | Original Fix | Re-Audit Finding | Corrected Fix |
|-----|-------------|-----------------|---------------|
| **#10** | Lowercased `dominant` for comparisons | Emotions dict uses UPPERCASE keys; `dominant in emotions` was ALWAYS False → intensity always 0.0 | Use `emotions.get(dominant.upper())` for lookup |
| **#39** | Moved racy `hasattr` to helper `_get_security_lock()` | Two threads could still each create Lock and assign it, defeating mutual exclusion | Module-level `_SECURITY_LOCK_INIT_GUARD` for double-checked locking |
| **#15/34** | Byte-slicing truncation `&cmdline[..n]` | Panics on multi-byte UTF-8 characters | `truncate_str()` function with char-boundary-safe truncation |
