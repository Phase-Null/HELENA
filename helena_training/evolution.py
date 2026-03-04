"""
Evolution database – persistent SQLite store for tracking HELENA's
self-improvement history.

Stores evolution events (general milestones) and patches (code changes
with test results and performance deltas).
"""
import json
import time
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class EvolutionDB:
    """SQLite-backed evolution tracker."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── Schema ────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   REAL    NOT NULL,
                    event_type  TEXT    NOT NULL,
                    description TEXT    NOT NULL DEFAULT '',
                    details     TEXT    NOT NULL DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS patches (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   REAL    NOT NULL,
                    module      TEXT    NOT NULL DEFAULT '',
                    function    TEXT    NOT NULL DEFAULT '',
                    new_code    TEXT    NOT NULL DEFAULT '',
                    test_passed INTEGER NOT NULL DEFAULT 0,
                    test_stdout TEXT    NOT NULL DEFAULT '',
                    test_stderr TEXT    NOT NULL DEFAULT '',
                    applied     INTEGER NOT NULL DEFAULT 0,
                    perf_before TEXT    NOT NULL DEFAULT '{}',
                    perf_after  TEXT    NOT NULL DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_ts
                ON events(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_patches_ts
                ON patches(timestamp)
            """)
        logger.info("EvolutionDB initialised at %s", self.db_path)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    # ── Events ────────────────────────────────────────────────────

    def record_evolution(self, event: Dict[str, Any]) -> None:
        """Record a general evolution event."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events (timestamp, event_type, description, details) "
                "VALUES (?, ?, ?, ?)",
                (
                    event.get("timestamp", time.time()),
                    event.get("type", "unknown"),
                    event.get("description", ""),
                    json.dumps(event.get("details", {})),
                ),
            )

    def get_events(self, limit: int = 50,
                   event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Query evolution events."""
        with self._connect() as conn:
            if event_type:
                rows = conn.execute(
                    "SELECT id, timestamp, event_type, description, details "
                    "FROM events WHERE event_type = ? "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (event_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, timestamp, event_type, description, details "
                    "FROM events ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            {
                "id": r[0], "timestamp": r[1], "type": r[2],
                "description": r[3], "details": json.loads(r[4]),
            }
            for r in rows
        ]

    # ── Patches ───────────────────────────────────────────────────

    def record_patch(self, patch: Dict[str, Any],
                     test_result: Dict[str, Any],
                     applied: bool = False,
                     perf_before: Any = None,
                     perf_after: Any = None) -> None:
        """Record a code patch with test results."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO patches "
                "(timestamp, module, function, new_code, test_passed, "
                " test_stdout, test_stderr, applied, perf_before, perf_after) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    time.time(),
                    patch.get("module", ""),
                    patch.get("function", ""),
                    patch.get("new_code", ""),
                    1 if test_result.get("passed") else 0,
                    test_result.get("stdout", ""),
                    test_result.get("stderr", ""),
                    1 if applied else 0,
                    json.dumps(perf_before) if perf_before else "{}",
                    json.dumps(perf_after) if perf_after else "{}",
                ),
            )

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get patch history."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, timestamp, module, function, test_passed, "
                "applied, perf_before, perf_after "
                "FROM patches ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r[0], "timestamp": r[1], "module": r[2],
                "function": r[3], "test_passed": bool(r[4]),
                "applied": bool(r[5]),
                "perf_before": json.loads(r[6]),
                "perf_after": json.loads(r[7]),
            }
            for r in rows
        ]

    def get_latest(self) -> Dict[str, Any]:
        """Get the most recent patch record."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, timestamp, module, function, test_passed, "
                "applied, perf_before, perf_after "
                "FROM patches ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return {}
        return {
            "id": row[0], "timestamp": row[1], "module": row[2],
            "function": row[3], "test_passed": bool(row[4]),
            "applied": bool(row[5]),
            "perf_before": json.loads(row[6]),
            "perf_after": json.loads(row[7]),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM patches").fetchone()[0]
            passed = conn.execute(
                "SELECT COUNT(*) FROM patches WHERE test_passed = 1"
            ).fetchone()[0]
            applied = conn.execute(
                "SELECT COUNT(*) FROM patches WHERE applied = 1"
            ).fetchone()[0]
            events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return {
            "total_patches": total,
            "passed_patches": passed,
            "applied_patches": applied,
            "pass_rate": passed / total if total else 0.0,
            "total_events": events,
        }
