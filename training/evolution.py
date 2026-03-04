# helena_training/evolution.py
import sqlite3
import json
import time
from pathlib import Path

class EvolutionDB:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(str(db_path))
        self._init_db()

    def _init_db(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS patches (
                id TEXT PRIMARY KEY,
                timestamp REAL,
                description TEXT,
                patch_json TEXT,
                test_passed BOOLEAN,
                applied BOOLEAN,
                performance_before REAL,
                performance_after REAL
            )
        ''')
        self.conn.commit()

    def record_patch(self, patch, test_result, applied, perf_before=None, perf_after=None):
        self.conn.execute('''
            INSERT INTO patches (id, timestamp, description, patch_json, test_passed, applied, performance_before, performance_after)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            patch['id'], time.time(), patch['description'],
            json.dumps(patch), test_result['passed'], applied,
            perf_before, perf_after
        ))
        self.conn.commit()