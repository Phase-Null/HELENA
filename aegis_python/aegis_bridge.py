# aegis_python/aegis_bridge.py
"""
AEGIS Bridge — Python side of the HELENA ↔ AEGIS IPC connection.

This module is what HELENA imports. It handles:
  - Connecting to the AEGIS Rust core
  - Sending commands (query status, approve/reject responses)
  - Receiving alerts and status reports
  - Reconnecting automatically if the connection drops

HELENA doesn't need to know anything about sockets or JSON.
She calls methods like:
  bridge.status()        → dict with current threat level etc.
  bridge.pending()       → list of responses waiting for approval
  bridge.approve(id, reason)
  bridge.reject(id, reason)

Alerts arrive asynchronously via a callback:
  bridge.on_alert = lambda alert: helena.inject_security_alert(alert)

Usage:
  from aegis_python.aegis_bridge import AegisBridge

  bridge = AegisBridge()
  bridge.on_alert = lambda a: print("ALERT:", a["summary"])
  bridge.start()   # non-blocking, runs in background thread

  status = bridge.status()
  print(status["threat_level"])
"""

import json
import socket
import threading
import time
import uuid
import logging
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("AegisBridge")

AEGIS_HOST = "127.0.0.1"
AEGIS_PORT = 47201
RECONNECT_DELAY = 5   # seconds between reconnect attempts
RECV_TIMEOUT    = 2   # socket read timeout (non-blocking feel)
REQUEST_TIMEOUT = 10  # seconds to wait for a reply to a specific request


class AegisBridge:
    """
    Persistent connection to the AEGIS Rust core.
    Thread-safe. Reconnects automatically.
    """

    def __init__(self):
        self._sock:        Optional[socket.socket]   = None
        self._lock:        threading.Lock            = threading.Lock()
        self._running:     bool                      = False
        self._thread:      Optional[threading.Thread] = None
        self._connected:   bool                      = False

        # Pending request/response tracking
        # Key: message_id, Value: threading.Event + response container
        self._pending_requests: Dict[str, Dict] = {}
        self._pending_lock:     threading.Lock  = threading.Lock()

        # Callbacks — set these before calling start()
        self.on_alert:        Optional[Callable[[Dict], None]] = None
        self.on_connected:    Optional[Callable[[], None]]     = None
        self.on_disconnected: Optional[Callable[[], None]]     = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background connection thread. Non-blocking."""
        self._running = True
        self._thread = threading.Thread(
            target=self._connection_loop,
            name="AegisBridge",
            daemon=True
        )
        self._thread.start()
        log.info("AegisBridge started.")

    def stop(self) -> None:
        """Stop the bridge cleanly."""
        self._running = False
        self._disconnect()
        if self._thread:
            self._thread.join(timeout=5)
        log.info("AegisBridge stopped.")

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Commands (HELENA → AEGIS) ─────────────────────────────────────────────

    def status(self) -> Optional[Dict]:
        """
        Ask AEGIS for current status.
        Returns a dict or None if AEGIS is not connected.
        """
        return self._request("query_status", {})

    def pending(self) -> Optional[List[Dict]]:
        """
        Ask AEGIS for pending response packages awaiting approval.
        """
        response = self._request("query_pending", {})
        if response:
            return response.get("pending", [])
        return None

    def approve(self, package_id: str, reason: str) -> bool:
        """
        Approve a Tier 4/5 response package.
        reason must be a non-empty string — AEGIS enforces this.
        Returns True if the command was sent (not if execution succeeded).
        """
        if not reason or not reason.strip():
            log.warning("Approve called with empty reason — rejected locally.")
            return False
        return self._send({
            "kind":    "approve_response",
            "payload": {
                "package_id":  package_id,
                "reason_code": reason,
                "approved_by": "Phase-Null",
            }
        })

    def reject(self, package_id: str, reason: str = "") -> bool:
        """Reject a pending response package."""
        return self._send({
            "kind":    "reject_response",
            "payload": {
                "package_id": package_id,
                "reason":     reason,
            }
        })

    def set_threat_level(self, level: str, reason: str) -> bool:
        """
        Manually set threat level.
        level: one of IDLE, ELEVATED, ACTIVE, CRITICAL
        """
        return self._send({
            "kind":    "set_threat_level",
            "payload": {"level": level.upper(), "reason": reason}
        })

    def ping(self) -> bool:
        """
        Check if AEGIS is alive and responding.
        Returns True if a Pong is received within REQUEST_TIMEOUT seconds.
        """
        response = self._request("ping", {})
        return response is not None

    # ── Formatting helpers for HELENA ─────────────────────────────────────────

    def format_status_for_helena(self) -> str:
        """
        Returns a human-readable security briefing for HELENA to surface.
        Designed to be injected into HELENA's system context.
        """
        s = self.status()
        if not s:
            return "AEGIS security core is offline or not responding."

        lines = [
            f"AEGIS Security Status:",
            f"  Threat level:     {s.get('threat_level', 'UNKNOWN')}",
            f"  Active agents:    {s.get('active_agents', 0)}",
            f"  Events processed: {s.get('events_processed', 0)}",
            f"  Uptime:           {s.get('uptime_seconds', 0) // 60} minutes",
        ]
        pending = s.get("pending_responses", 0)
        if pending:
            lines.append(f"  ⚠ Pending approvals: {pending} (use 'security pending' to review)")
        return "\n".join(lines)

    def format_alert_for_helena(self, alert: Dict) -> str:
        """Convert a raw alert dict into a natural-language string for HELENA."""
        level   = alert.get("threat_level", "UNKNOWN")
        summary = alert.get("summary", "Security event detected.")
        pkg_id  = alert.get("package_id")

        msg = f"[SECURITY — {level}] {summary}"
        if pkg_id:
            msg += (
                f"\n  A response has been prepared (ID: {pkg_id})."
                f"\n  To approve: tell me 'approve security response {pkg_id}' and your reason."
                f"\n  To reject: tell me 'reject security response {pkg_id}'."
            )
        return msg

    # ── Internal — connection management ──────────────────────────────────────

    def _connection_loop(self) -> None:
        """Main background thread. Connects, reads, reconnects."""
        while self._running:
            try:
                self._connect()
                self._read_loop()
            except Exception as e:
                log.debug("Connection error: %s", e)
            finally:
                self._disconnect()
                if self._running:
                    log.info("AEGIS disconnected. Reconnecting in %ds...", RECONNECT_DELAY)
                    time.sleep(RECONNECT_DELAY)

    def _connect(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(RECV_TIMEOUT)
        sock.connect((AEGIS_HOST, AEGIS_PORT))

        with self._lock:
            self._sock = sock
            self._connected = True

        log.info("Connected to AEGIS on %s:%d", AEGIS_HOST, AEGIS_PORT)
        if self.on_connected:
            try:
                self.on_connected()
            except Exception:
                pass

    def _disconnect(self) -> None:
        with self._lock:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
            was_connected = self._connected
            self._connected = False

        if was_connected and self.on_disconnected:
            try:
                self.on_disconnected()
            except Exception:
                pass

        # Unblock any waiting request threads
        with self._pending_lock:
            for waiter in self._pending_requests.values():
                waiter["event"].set()

    def _read_loop(self) -> None:
        """Read newline-delimited JSON messages from AEGIS."""
        buf = b""
        while self._running:
            try:
                with self._lock:
                    sock = self._sock
                if sock is None:
                    break

                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break

                if not chunk:
                    break   # connection closed

                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if line:
                        self._handle_message(line.decode("utf-8", errors="replace"))

            except Exception as e:
                log.debug("Read loop error: %s", e)
                break

    def _handle_message(self, line: str) -> None:
        """Parse and dispatch an incoming message from AEGIS."""
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log.warning("Malformed message from AEGIS: %s", line[:100])
            return

        msg_id   = msg.get("id")
        msg_kind = msg.get("kind")
        payload  = msg.get("payload", {})

        # Check if this is a reply to a pending request
        with self._pending_lock:
            if msg_id and msg_id in self._pending_requests:
                waiter = self._pending_requests[msg_id]
                waiter["response"] = payload
                waiter["event"].set()
                return

        # Handle unsolicited messages
        if msg_kind == "alert":
            log.warning("AEGIS ALERT: %s", payload.get("summary", ""))
            if self.on_alert:
                try:
                    self.on_alert(payload)
                except Exception as e:
                    log.error("on_alert callback error: %s", e)

        elif msg_kind == "status_report":
            # Heartbeat from AEGIS — log at debug level
            log.debug("AEGIS heartbeat: threat=%s agents=%s",
                      payload.get("threat_level"),
                      payload.get("active_agents"))

        elif msg_kind == "threat_level_change":
            level = payload.get("threat_level", "UNKNOWN")
            log.warning("AEGIS threat level changed to: %s", level)
            if self.on_alert:
                try:
                    self.on_alert({
                        "threat_level": level,
                        "summary": f"Threat level escalated to {level}",
                        "findings": [],
                    })
                except Exception:
                    pass

        elif msg_kind == "error":
            log.error("AEGIS error: %s — %s",
                      payload.get("code"), payload.get("message"))

    # ── Internal — send and request ───────────────────────────────────────────

    def _send(self, msg_dict: Dict) -> bool:
        """
        Send a message to AEGIS. Fire-and-forget (no reply expected).
        Returns True if the message was sent.
        """
        msg = {
            "id":        str(uuid.uuid4()),
            "timestamp": _now_iso(),
            "source":    "helena",
            "kind":      msg_dict["kind"],
            "payload":   msg_dict.get("payload", {}),
        }
        return self._write_line(json.dumps(msg))

    def _request(self, kind: str, payload: Dict) -> Optional[Dict]:
        """
        Send a message to AEGIS and wait for a reply.
        Returns the reply payload dict, or None on timeout/error.
        """
        msg_id = str(uuid.uuid4())
        msg = {
            "id":        msg_id,
            "timestamp": _now_iso(),
            "source":    "helena",
            "kind":      kind,
            "payload":   payload,
        }

        event = threading.Event()
        waiter = {"event": event, "response": None}

        with self._pending_lock:
            self._pending_requests[msg_id] = waiter

        try:
            if not self._write_line(json.dumps(msg)):
                return None
            event.wait(timeout=REQUEST_TIMEOUT)
            return waiter["response"]
        finally:
            with self._pending_lock:
                self._pending_requests.pop(msg_id, None)

    def _write_line(self, line: str) -> bool:
        """Write a newline-terminated line to the socket. Thread-safe."""
        with self._lock:
            sock = self._sock
        if sock is None:
            log.debug("Cannot send — not connected to AEGIS.")
            return False
        try:
            data = (line + "\n").encode("utf-8")
            sock.sendall(data)
            return True
        except OSError as e:
            log.warning("Send failed: %s", e)
            return False


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
