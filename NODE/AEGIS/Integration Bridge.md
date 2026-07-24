---
tags: [aegis, integration]
date: 2026-03-05
status: active
component: aegis_python/helena_integration.py
bugs: [39]
---

# Integration Bridge — AEGIS ↔ HELENA

The integration bridge connects AEGIS's Rust security core to HELENA's Python runtime. It provides patch instructions for modifying HELENA's existing source files to wire AEGIS in — nothing is deleted, only additions.

> [!info] Installation
> 1. Copy `aegis_python/` into HELENA root directory
> 2. Apply patches to `helena_core/kernel/core.py`
> 3. Apply patches to `helena_ml/chat_engine.py`
> 4. AEGIS starts automatically with HELENA

---

## Patch System

### CORE_PY_PATCH — Kernel Integration (after ChatEngine init, ~line 460)

```python
try:
    from aegis_python.aegis_bridge import AegisBridge
    self.aegis = AegisBridge()

    def _on_aegis_alert(alert):
        if self.chat_engine:
            briefing = self.aegis.format_alert_for_helena(alert)
            self.chat_engine.inject_security_alert(briefing)

    self.aegis.on_alert = _on_aegis_alert
    self.aegis.start()
except ImportError:
    self.aegis = None  # Security features unavailable
except Exception as e:
    self.aegis = None  # Bridge failed
```

### SHUTDOWN_PATCH — Kernel Shutdown

```python
if hasattr(self, "aegis") and self.aegis:
    self.aegis.stop()
```

### CHAT_ENGINE_PATCH — Alert Injection Methods

Two methods added to ChatEngine:

**`inject_security_alert(message: str)`**
- Thread-safe alert injection via `self._get_security_lock()`
- Queue capped at 10 messages — oldest dropped if HELENA is overwhelmed
- Uses `_security_alerts` list

**`get_pending_security_alerts() -> list`**
- Called at start of each response generation
- Returns all queued alerts, clears queue after reading

**`_get_security_lock()`**
- Thread-safe lazy lock initialization using **module-level guard**

> [!warning] Bug #39 — Thread-Unsafe Lock Creation
> Original: `_security_lock` created via `if not hasattr(self, '_security_lock')` — two threads racing could each create their own Lock, defeating mutual exclusion.
> 
> **Re-audit fix**: The original BUGFIX #39 just moved the racy pattern to a helper method. The correct fix uses a **module-level lock** (`_SECURITY_LOCK_INIT_GUARD`) for double-checked locking:
> ```python
> _SECURITY_LOCK_INIT_GUARD = _threading_mod.Lock()
> 
> def _get_security_lock(self):
>     if not hasattr(self, "_security_lock"):
>         with _SECURITY_LOCK_INIT_GUARD:
>             if not hasattr(self, "_security_lock"):  # double-check
>                 self._security_lock = threading.Lock()
>     return self._security_lock
> ```
> See [[Bug Fixes Registry#Bug 39]].

### CHAT_METHOD_PATCH — Alert Context Injection

Prepends pending security alerts to the system prompt:
```python
security_alerts = self.get_pending_security_alerts()
if security_alerts:
    alert_context = "\n\n".join(security_alerts)
    system_content = f"{system_content}\n\n{alert_context}"
```

---

## Security Commands (Natural Language)

| Command | HELENA Response |
|---------|----------------|
| "security status" / "threat level" | `self._kernel.aegis.status()` |
| "security pending" | `self._kernel.aegis.pending()` — shows pending response packages |
| "security briefing" | `self._kernel.aegis.format_status_for_helena()` |
| "approve security response <id> <reason>" | Approves a pending response for execution |
| "reject security response <id>" | Rejects and archives a pending response |

---

## Alert Flow

```
AEGIS Rust Core → Agent Report → Dispatch Loop (main.rs)
  → Message::Alert → IPC → AegisBridge Python → _on_aegis_alert()
  → self.aegis.format_alert_for_helena(alert) → ChatEngine.inject_security_alert(briefing)
  → self._security_alerts queue → ChatEngine.get_pending_security_alerts()
  → Prepended to system prompt → HELENA aware before responding
```

---

## Related Notes

- [[Overview]] — AEGIS entry point and IPC server
- [[State Management]] — ResponsePackage approval/rejection
- [[Chat Engine]] — inject_security_alert() and get_pending_security_alerts()
- [[Bug Fixes]] — Bug #39 (thread-unsafe lock)
