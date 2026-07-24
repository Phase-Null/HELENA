---
tags: [aegis, bugfix]
date: 2026-03-05
status: active
---

# AEGIS Bug Fixes — Security-Specific Bugs

AEGIS-specific bugs extracted from the [[Bug Fixes Registry]]. These affect the Rust security core, ETW consumers, firewall engine, and integration bridge.

---

## CRITICAL — Already Fixed

### Bug 4: AEGIS Firewall — Loopback Permit Allows ALL Traffic
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/firewall/engine.rs` lines 66-92 |
| **Severity** | CRITICAL |
| **Status** | **already_fixed** |
| **Root Cause** | `add_loopback_permit()` only had local-port condition, no remote-address restriction. ALL inbound connections to port 47201 were permitted |
| **Fix** | wfp upgraded to 0.0.7, `IpAddressConditionBuilder::remote().equal(127.0.0.1)` added, plus netsh safety-net rule |
| **See also** | [[Overview]], [[Threat Model]] |

---

## HIGH — Needs/Applied Fix

### Bug 15: Regex Pattern Used with contains()
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/etw/providers.rs` lines 118, 152 |
| **Severity** | HIGH |
| **Status** | **needs_fix** (applied) |
| **Root Cause** | `"reg add.*run"` is regex but `.contains()` treats `.*` as literal. Registry Run key persistence NOT detected |
| **Fix** | Replace with `"reg add"` + separate `"run"` check |
| **Re-audit** | Bug #34 also applies: byte-slicing `&cmdline[..150]` can panic on UTF-8. Fixed with `truncate_str()` |
| **See also** | [[ETW System]] |

### Bug 22: New `System` Object Created Per PID
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/agents/network.rs` lines 286-301 |
| **Severity** | MEDIUM |
| **Status** | **needs_fix** (applied) |
| **Root Cause** | `System::new()` is extremely expensive, called per PID in `get_process_info()` |
| **Fix** | Create System once in `scan()`, pass by reference to `get_process_info()` |
| **See also** | [[Network Agent]] |

---

## MEDIUM — Already Fixed

### Bug 23: Retaliate/Lockdown Tiers Return None
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/firewall/responder.rs` line 158 |
| **Severity** | MEDIUM |
| **Status** | **already_fixed** |
| **Root Cause** | Only Monitor/Alert/Contain/Harden had handler code. Retaliate and Lockdown were stubs returning None |
| **Fix** | Full implementations: Retaliate blocks IP + builds tier4 package; Lockdown blocks IP + activates lockdown mode |
| **See also** | [[Overview]], [[Threat Model]] |

### Bug 24: No WFP Filter ID Storage
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/firewall/rules.rs` line 42 |
| **Severity** | MEDIUM |
| **Status** | **already_fixed** |
| **Root Cause** | `blocked_ports: HashMap<u16, ()>` stored no filter ID, making individual unblocks impossible |
| **Fix** | Changed to `HashMap<u16, u64>`, stores filter IDs. Added `unblock_inbound_port()` and `remove_port_block()` |
| **See also** | [[Overview]] |

### Bug 27: Cleanup Removes IP Blocks on Shutdown
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/firewall/rules.rs` lines 231-238 |
| **Severity** | MEDIUM |
| **Status** | **already_fixed** |
| **Root Cause** | Unconditional removal of ALL IP blocks on shutdown, contradicting persistent block design |
| **Fix** | `cleanup_temporary_rules()` only removes non-persistent blocks. Added `IPRuleMeta.persistent` field. Full cleanup via `cleanup_all_rules()` available |
| **See also** | [[Threat Model]] |

---

## LOW — Needs Fix

### Bug 33: O(n) `remove(0)` → VecDeque
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/state.rs` line 242 |
| **Severity** | LOW |
| **Status** | **needs_fix** (applied) |
| **Root Cause** | `Vec::remove(0)` is O(n). Should use `VecDeque::pop_front()` which is O(1) |
| **Fix** | Changed `response_history` from `Vec` to `VecDeque`. `pop_front()` instead of `remove(0)` |
| **See also** | [[State Management]] |

### Bug 34: String Slice Can Panic on UTF-8
| Field | Value |
|-------|-------|
| **File** | `aegis_core/src/etw/consumer.rs` line 158 |
| **Severity** | LOW |
| **Status** | **needs_fix** (applied) |
| **Root Cause** | `&cmdline[..cmdline.len().min(150)]` byte-slicing can panic on multi-byte UTF-8 characters |
| **Fix** | Added `truncate_str()` function with char-boundary-safe truncation |
| **See also** | [[ETW System]] |

---

## Integration Bug

### Bug 39: Thread-Unsafe Lock Creation
| Field | Value |
|-------|-------|
| **File** | `helena_integration.py` various |
| **Severity** | LOW |
| **Status** | **needs_fix** (re-audit fix applied) |
| **Root Cause** | `_security_lock` created lazily via `hasattr` check — two threads could each create their own Lock |
| **Re-audit** | Original fix just moved racy pattern to `_get_security_lock()` helper. Correct fix uses module-level `_SECURITY_LOCK_INIT_GUARD` for double-checked locking |
| **See also** | [[Integration Bridge]] |
