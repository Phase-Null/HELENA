# aegis_python/helena_integration.py
"""
HELENA ↔ AEGIS Integration Patch.

This file shows exactly what to add to HELENA's existing code
to wire AEGIS in. Nothing in HELENA's core is deleted —
these are additions only.

INSTRUCTIONS:
  1. Copy aegis_python/ into your HELENA root directory
     (alongside helena_core/, helena_ml/, etc.)

  2. Apply the changes marked below to helena_core/kernel/core.py

  3. Apply the changes marked below to helena_ml/chat_engine.py

That's it. AEGIS then starts automatically with HELENA.
"""


# ════════════════════════════════════════════════════════════════════════
# CHANGE 1 — helena_core/kernel/core.py
#
# In HELENAKernel.__init__(), AFTER the existing chat_engine init block
# (around line 460), add the following:
# ════════════════════════════════════════════════════════════════════════

CORE_PY_PATCH = '''
# ── AEGIS Security Bridge ──────────────────────────────────────────────
# Added by AEGIS integration. HELENA talks to the Rust security core here.
# AEGIS runs as a separate process — if it's not running, HELENA continues
# normally. Security features are unavailable until AEGIS is started.
try:
    from aegis_python.aegis_bridge import AegisBridge

    self.aegis = AegisBridge()

    # Wire alert callback — AEGIS alerts surface in HELENA's next response
    def _on_aegis_alert(alert):
        if self.chat_engine:
            briefing = self.aegis.format_alert_for_helena(alert)
            self.chat_engine.inject_security_alert(briefing)

    self.aegis.on_alert = _on_aegis_alert
    self.aegis.start()

    logger.info("HELENAKernel", "AEGIS security bridge started.")

except ImportError:
    self.aegis = None
    logger.warning("HELENAKernel", "AEGIS bridge not found. Security features unavailable.")
except Exception as e:
    self.aegis = None
    logger.warning("HELENAKernel", f"AEGIS bridge failed to start: {e}")
# ── End AEGIS ──────────────────────────────────────────────────────────
'''


# ════════════════════════════════════════════════════════════════════════
# CHANGE 2 — helena_core/kernel/core.py
#
# In HELENAKernel.shutdown() (wherever the existing cleanup is), add:
# ════════════════════════════════════════════════════════════════════════

SHUTDOWN_PATCH = '''
# Stop AEGIS bridge
if hasattr(self, "aegis") and self.aegis:
    self.aegis.stop()
'''


# ════════════════════════════════════════════════════════════════════════
# CHANGE 3 — helena_ml/chat_engine.py
#
# Add this method to the ChatEngine class.
# It lets AEGIS inject alerts into HELENA's context queue.
# ════════════════════════════════════════════════════════════════════════

CHAT_ENGINE_PATCH = '''
def inject_security_alert(self, message: str) -> None:
    """
    Called by AEGIS when a security event needs HELENA's attention.
    Adds the alert to a queue — HELENA surfaces it in her next response.
    Thread-safe.
    """
    if not hasattr(self, "_security_alerts"):
        self._security_alerts = []
    import threading
    if not hasattr(self, "_security_lock"):
        self._security_lock = threading.Lock()
    with self._security_lock:
        self._security_alerts.append(message)
        # Cap queue at 10 — oldest alerts drop if HELENA is overwhelmed
        if len(self._security_alerts) > 10:
            self._security_alerts.pop(0)

def get_pending_security_alerts(self) -> list:
    """
    Called at the start of each response generation to pick up
    any queued security alerts and prepend them to context.
    Clears the queue after reading.
    """
    if not hasattr(self, "_security_alerts"):
        return []
    import threading
    if not hasattr(self, "_security_lock"):
        self._security_lock = threading.Lock()
    with self._security_lock:
        alerts = list(self._security_alerts)
        self._security_alerts.clear()
    return alerts
'''


# ════════════════════════════════════════════════════════════════════════
# CHANGE 4 — helena_ml/chat_engine.py
#
# In the ChatEngine.chat() method, at the START of building the messages
# list (before the history is added), add:
# ════════════════════════════════════════════════════════════════════════

CHAT_METHOD_PATCH = '''
# Prepend any pending AEGIS security alerts to this response's context
security_alerts = self.get_pending_security_alerts()
if security_alerts:
    alert_context = "\\n\\n".join(security_alerts)
    # Prepend to system context so HELENA is aware before responding
    system_content = f"{system_content}\\n\\n{alert_context}" if system_content else alert_context
'''


# ════════════════════════════════════════════════════════════════════════
# NATURAL LANGUAGE SECURITY COMMANDS
#
# Add these patterns to ModeProcessor (helena_core/kernel/core.py)
# in the command detection block, so HELENA understands security commands.
#
# The existing ModeProcessor likely checks for keywords like "list files"
# or "check memory". Add the same pattern for security commands.
# ════════════════════════════════════════════════════════════════════════

SECURITY_COMMANDS = {
    # What HELENA says → what code to run
    "security status":   "self._kernel.aegis.status()",
    "threat level":      "self._kernel.aegis.status()",
    "security pending":  "self._kernel.aegis.pending()",
    "security briefing": "self._kernel.aegis.format_status_for_helena()",
}

SECURITY_COMMAND_HANDLER = '''
def _handle_security_command(self, user_message: str) -> Optional[str]:
    """
    Routes security-related commands to AEGIS.
    Returns a formatted response string, or None if not a security command.
    """
    if not hasattr(self._kernel, "aegis") or not self._kernel.aegis:
        return None  # AEGIS not available

    msg = user_message.lower().strip()

    # Status / briefing
    if any(kw in msg for kw in ["security status", "threat level", "aegis status", "security briefing"]):
        return self._kernel.aegis.format_status_for_helena()

    # Pending approvals
    if "security pending" in msg or "pending approval" in msg:
        pending = self._kernel.aegis.pending()
        if not pending:
            return "No security responses pending approval."
        lines = ["Pending security responses requiring your approval:"]
        for p in pending:
            lines.append(
                f"  ID: {p['id']}\\n"
                f"  Tier: {p['tier']}\\n"
                f"  Action: {p['description']}\\n"
                f"  Triggered by: {p['trigger']}"
            )
        lines.append("\\nTo approve: 'approve security response <id> <reason>'")
        lines.append("To reject:  'reject security response <id>'")
        return "\\n".join(lines)

    # Approve
    import re
    approve_match = re.search(
        r"approve\\s+(?:security\\s+)?response\\s+([a-f0-9]+)\\s+(.+)",
        msg
    )
    if approve_match:
        pkg_id = approve_match.group(1)
        reason = approve_match.group(2).strip()
        ok = self._kernel.aegis.approve(pkg_id, reason)
        if ok:
            return f"Approval command sent for response {pkg_id}. AEGIS is executing."
        return f"Could not send approval — AEGIS may not be connected."

    # Reject
    reject_match = re.search(r"reject\\s+(?:security\\s+)?response\\s+([a-f0-9]+)", msg)
    if reject_match:
        pkg_id = reject_match.group(1)
        ok = self._kernel.aegis.reject(pkg_id)
        return f"Response {pkg_id} rejected." if ok else "Reject command failed."

    return None
'''


if __name__ == "__main__":
    print("This file contains integration instructions.")
    print("Read the comments and apply the patches to HELENA's source.")
    print()
    print("Patches to apply:")
    print("  1. CORE_PY_PATCH      → helena_core/kernel/core.py (after chat_engine init)")
    print("  2. SHUTDOWN_PATCH     → helena_core/kernel/core.py (in shutdown())")
    print("  3. CHAT_ENGINE_PATCH  → helena_ml/chat_engine.py (new methods)")
    print("  4. CHAT_METHOD_PATCH  → helena_ml/chat_engine.py (in chat() method)")
    print("  5. SECURITY_COMMAND_HANDLER → helena_core/kernel/core.py (ModeProcessor)")
