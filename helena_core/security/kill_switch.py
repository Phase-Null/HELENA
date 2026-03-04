# helena_core/security/kill_switch.py
"""
HELENA Kill Switch – multi-stage emergency shutdown system.

Stages (from blueprint)
-----------------------
Stage 1 – ALERT:      Log anomaly, notify operator.  System continues.
Stage 2 – RESTRICT:   Disable network, external APIs, module loading.
Stage 3 – CONTAIN:    Suspend all non-critical tasks, isolate training.
Stage 4 – SHUTDOWN:   Graceful shutdown: persist memory, flush logs, stop.
Stage 5 – HARD_KILL:  Immediate process termination (last resort).

The kill switch can be triggered programmatically (e.g. by the
regulatory core or anomaly detection) or manually by the operator.
"""
import os
import sys
import time
import signal
import logging
import threading
from enum import IntEnum
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class KillStage(IntEnum):
    NOMINAL = 0
    ALERT = 1
    RESTRICT = 2
    CONTAIN = 3
    SHUTDOWN = 4
    HARD_KILL = 5


@dataclass
class KillEvent:
    """Record of a kill-switch activation."""
    stage: KillStage
    reason: str
    source: str          # "operator", "regulatory", "anomaly", "thermal", …
    timestamp: float = field(default_factory=time.time)
    details: Dict[str, Any] = field(default_factory=dict)


class KillSwitch:
    """
    Multi-stage emergency shutdown controller.

    Usage::

        ks = KillSwitch(kernel=kernel, runtime=runtime)
        ks.trigger(KillStage.ALERT, reason="Anomalous memory growth", source="runtime")
        ks.trigger(KillStage.SHUTDOWN, reason="Operator request", source="operator")
    """

    def __init__(self, kernel=None, runtime=None, memory=None) -> None:
        self.kernel = kernel
        self.runtime = runtime
        self.memory = memory

        self._lock = threading.Lock()
        self.current_stage = KillStage.NOMINAL
        self._history: List[KillEvent] = []
        self._max_history = 200

        # Callbacks per stage – populated by subsystems
        self._callbacks: Dict[KillStage, List[Callable]] = {
            stage: [] for stage in KillStage
        }

        # Operator confirmation required for stage >= SHUTDOWN
        self.operator_confirmed = False

        logger.info("KillSwitch initialised (stage: NOMINAL)")

    # ── Registration ──────────────────────────────────────────────

    def on_stage(self, stage: KillStage, callback: Callable) -> None:
        """Register a callback to be invoked when *stage* is reached."""
        self._callbacks[stage].append(callback)

    # ── Trigger ───────────────────────────────────────────────────

    def trigger(self, stage: KillStage, reason: str,
                source: str = "system",
                details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Activate the kill switch at the given *stage*.

        Returns a status dict describing what actions were taken.
        """
        with self._lock:
            if stage <= self.current_stage and stage != KillStage.NOMINAL:
                return {"status": "already_at_or_above", "current": self.current_stage.name}

            event = KillEvent(
                stage=stage, reason=reason, source=source,
                details=details or {},
            )
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

            logger.warning(
                "KillSwitch TRIGGERED – Stage %d (%s) by %s: %s",
                stage, stage.name, source, reason,
            )

            self.current_stage = stage
            actions_taken: List[str] = []

            # Execute stage actions cumulatively
            if stage >= KillStage.ALERT:
                actions_taken.extend(self._do_alert(event))
            if stage >= KillStage.RESTRICT:
                actions_taken.extend(self._do_restrict(event))
            if stage >= KillStage.CONTAIN:
                actions_taken.extend(self._do_contain(event))
            if stage >= KillStage.SHUTDOWN:
                actions_taken.extend(self._do_shutdown(event))
            if stage >= KillStage.HARD_KILL:
                self._do_hard_kill(event)

            # Fire registered callbacks
            for cb in self._callbacks.get(stage, []):
                try:
                    cb(event)
                except Exception as exc:
                    logger.error("KillSwitch callback error: %s", exc)

            return {
                "status": "triggered",
                "stage": stage.name,
                "actions": actions_taken,
                "reason": reason,
            }

    def reset(self, source: str = "operator") -> Dict[str, Any]:
        """Reset kill switch to NOMINAL (operator only)."""
        with self._lock:
            prev = self.current_stage
            self.current_stage = KillStage.NOMINAL
            self.operator_confirmed = False
            logger.info("KillSwitch RESET from %s by %s", prev.name, source)
            return {"status": "reset", "previous_stage": prev.name}

    # ── Stage implementations ─────────────────────────────────────

    def _do_alert(self, event: KillEvent) -> List[str]:
        """Stage 1: Log and notify."""
        actions = ["logged_alert"]
        logger.warning("KILL-ALERT: %s (source: %s)", event.reason, event.source)
        return actions

    def _do_restrict(self, event: KillEvent) -> List[str]:
        """Stage 2: Disable external access."""
        actions = ["restricted_external_access"]
        if self.kernel:
            try:
                self.kernel.set_lockdown_mode(True)
                actions.append("kernel_lockdown_enabled")
            except Exception as exc:
                logger.error("KillSwitch restrict failed: %s", exc)
        return actions

    def _do_contain(self, event: KillEvent) -> List[str]:
        """Stage 3: Suspend non-critical tasks."""
        actions = ["contained_tasks"]
        if self.kernel:
            try:
                self.kernel._clear_non_critical_tasks()
                actions.append("non_critical_tasks_cleared")
            except Exception as exc:
                logger.error("KillSwitch contain failed: %s", exc)
        if self.runtime:
            try:
                self.runtime.emergency_throttle()
                actions.append("runtime_emergency_throttled")
            except Exception as exc:
                logger.error("KillSwitch throttle failed: %s", exc)
        return actions

    def _do_shutdown(self, event: KillEvent) -> List[str]:
        """Stage 4: Graceful shutdown."""
        actions = ["graceful_shutdown_initiated"]
        # Persist memory
        if self.memory:
            try:
                self.memory.save()
                actions.append("memory_persisted")
            except Exception as exc:
                logger.error("KillSwitch memory save failed: %s", exc)
        # Shutdown kernel
        if self.kernel:
            try:
                self.kernel.shutdown()
                actions.append("kernel_shutdown")
            except Exception as exc:
                logger.error("KillSwitch kernel shutdown failed: %s", exc)
        # Shutdown runtime
        if self.runtime:
            try:
                self.runtime.shutdown()
                actions.append("runtime_shutdown")
            except Exception as exc:
                logger.error("KillSwitch runtime shutdown failed: %s", exc)
        return actions

    def _do_hard_kill(self, event: KillEvent) -> None:
        """Stage 5: Immediate termination."""
        logger.critical("KILL-HARD: Immediate termination – %s", event.reason)
        # Attempt to flush logs
        for handler in logging.getLogger().handlers:
            try:
                handler.flush()
            except Exception:
                pass
        os._exit(1)

    # ── Queries ───────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        return {
            "stage": self.current_stage.name,
            "stage_value": int(self.current_stage),
            "history_count": len(self._history),
            "last_event": self._history[-1].__dict__ if self._history else None,
        }

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [
            {
                "stage": e.stage.name,
                "reason": e.reason,
                "source": e.source,
                "timestamp": e.timestamp,
                "details": e.details,
            }
            for e in self._history[-limit:]
        ]
