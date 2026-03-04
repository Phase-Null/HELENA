"""
Training scheduler – manages periodic autonomous improvement cycles.

Uses threading.Timer so the main thread is never blocked.  The
scheduler respects a minimum cool-down between sessions and will
skip a cycle if the system is already training or resources are
constrained.
"""
import time
import threading
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class TrainingScheduler:
    """Periodic scheduler for HELENA's autonomous training sessions."""

    def __init__(self, trainer, config: Dict[str, Any]):
        self.trainer = trainer
        self.config = config if isinstance(config, dict) else {}

        # Scheduling parameters (seconds)
        self.interval: float = float(self.config.get("schedule_interval", 3600))
        self.min_cooldown: float = float(self.config.get("min_cooldown", 600))

        # State
        self.is_running = False
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self.last_run: float = 0.0
        self.next_run: float = 0.0
        self.run_count: int = 0
        self._history: List[Dict[str, Any]] = []

    # ── Start / stop ──────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler."""
        with self._lock:
            if self.is_running:
                return
            self.is_running = True
            self._schedule_next()
            logger.info("TrainingScheduler started (interval=%ds)", self.interval)

    def stop(self) -> None:
        """Stop the scheduler."""
        with self._lock:
            self.is_running = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            logger.info("TrainingScheduler stopped")

    def schedule_training(self, interval: int) -> None:
        """Change the training interval (seconds)."""
        with self._lock:
            self.interval = max(60, float(interval))
            # Reschedule if running
            if self.is_running:
                if self._timer is not None:
                    self._timer.cancel()
                self._schedule_next()

    # ── Internal scheduling ───────────────────────────────────────

    def _schedule_next(self) -> None:
        self.next_run = time.time() + self.interval
        self._timer = threading.Timer(self.interval, self._run_cycle)
        self._timer.daemon = True
        self._timer.start()

    def _run_cycle(self) -> None:
        """Execute one training cycle."""
        with self._lock:
            if not self.is_running:
                return

        # Cooldown check
        elapsed = time.time() - self.last_run
        if elapsed < self.min_cooldown:
            logger.debug("TrainingScheduler: skipping cycle (cooldown)")
            if self.is_running:
                self._schedule_next()
            return

        # Skip if already training
        if self.trainer.is_training():
            logger.debug("TrainingScheduler: skipping cycle (already training)")
            if self.is_running:
                self._schedule_next()
            return

        # Run the session
        start = time.time()
        try:
            result = self.trainer.start_session(reason="scheduled")
            duration = time.time() - start
            self.last_run = time.time()
            self.run_count += 1
            self._history.append({
                "timestamp": self.last_run,
                "duration": duration,
                "result": result,
            })
            # Keep history bounded
            if len(self._history) > 100:
                self._history = self._history[-100:]
            logger.info("TrainingScheduler: cycle completed in %.1fs", duration)
        except Exception as exc:
            logger.error("TrainingScheduler: cycle failed: %s", exc)

        # Schedule next
        if self.is_running:
            self._schedule_next()

    # ── Queries ───────────────────────────────────────────────────

    def get_schedule(self) -> Dict[str, Any]:
        return {
            "is_running": self.is_running,
            "interval_seconds": self.interval,
            "next_training": self.next_run if self.is_running else None,
            "last_training": self.last_run or None,
            "run_count": self.run_count,
            "history_count": len(self._history),
        }

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._history[-limit:]
