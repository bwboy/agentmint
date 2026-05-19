"""SQLite-backed job queue.

State machine:
    pending  ── ack sent, agent call queued
    processing ── agent call in flight
    done       ── agent returned, awaiting upload
    uploaded   ── platform received the answer (terminal)
    failed     ── agent permanently failed (terminal)

Invariants:
    - `request_id` is the natural key (issued by platform); UPSERT-safe
    - On startup, scan `pending`/`processing`/`done` and resume them:
        pending/processing → re-run the agent call
        done               → re-upload (idempotent on platform via request_id)
"""
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    request_id TEXT PRIMARY KEY,
    question_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','processing','done','uploaded','failed')),
    answer_json TEXT,
    error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""


class JobQueue:
    """Thread-safe SQLite job queue. Sync API — call from anywhere, even off the loop."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA)

    def close(self):
        with self._lock:
            self._conn.close()

    # ─── Mutations ───

    def upsert_pending(self, request_id: str, question: dict) -> bool:
        """Add a new job in `pending`. Returns False if request_id already exists
        (idempotent — caller can safely retry without duplicating work)."""
        now = time.time()
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO jobs(request_id, question_json, status, created_at, updated_at) "
                    "VALUES (?, ?, 'pending', ?, ?)",
                    (request_id, json.dumps(question, ensure_ascii=False), now, now),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def mark(self, request_id: str, status: str, *, answer: dict | None = None, error: str | None = None):
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET status=?, answer_json=COALESCE(?, answer_json), "
                "error=COALESCE(?, error), updated_at=? WHERE request_id=?",
                (
                    status,
                    json.dumps(answer, ensure_ascii=False) if answer is not None else None,
                    error,
                    now,
                    request_id,
                ),
            )

    # ─── Reads ───

    def get(self, request_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT request_id, question_json, status, answer_json, error, created_at, updated_at "
                "FROM jobs WHERE request_id=?",
                (request_id,),
            ).fetchone()
        return _row_to_dict(row) if row else None

    def list_resumable(self) -> Iterable[dict]:
        """Jobs that need to be re-run / re-uploaded after a restart or reconnect."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT request_id, question_json, status, answer_json, error, created_at, updated_at "
                "FROM jobs WHERE status IN ('pending','processing','done') "
                "ORDER BY created_at ASC"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) FROM jobs GROUP BY status"
            ).fetchall()
        out = {s: 0 for s in ("pending", "processing", "done", "uploaded", "failed")}
        for s, c in rows:
            out[s] = c
        return out


def _row_to_dict(row) -> dict:
    rid, q, status, ans, err, ca, ua = row
    return {
        "request_id": rid,
        "question": json.loads(q),
        "status": status,
        "answer": json.loads(ans) if ans else None,
        "error": err,
        "created_at": ca,
        "updated_at": ua,
    }
