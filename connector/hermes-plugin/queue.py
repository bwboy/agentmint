"""Local SQLite job queue — survives Hermes restarts and WS disconnects.

State machine:
    pending     — question received, ack sent, awaiting Hermes to produce answer
    answered    — Hermes called adapter.send(); answer payload built, awaiting upload
    uploaded    — platform acknowledged (terminal)
    failed      — adapter reported error to platform (terminal)

Idempotency: request_id is the PK. On reconnect we scan {pending, answered} and
re-issue them to Hermes / re-upload them.
"""
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    request_id    TEXT PRIMARY KEY,
    question_json TEXT NOT NULL,
    chat_id       TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('pending','answered','uploaded','failed')),
    answer_json   TEXT,
    error         TEXT,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status   ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_chat_id  ON jobs(chat_id);
"""


class JobQueue:
    """Thread-safe SQLite queue. Sync API."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(Path(db_path).expanduser()),
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA)

    def close(self):
        with self._lock:
            self._conn.close()

    # ─── Insertions / updates ───

    def upsert_pending(self, request_id: str, chat_id: str, question: dict) -> bool:
        """Insert a fresh pending job. Returns False if request_id already known
        (callers can safely retry; the platform may re-deliver the same question
        across reconnects)."""
        now = time.time()
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO jobs(request_id, chat_id, question_json, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'pending', ?, ?)",
                    (request_id, chat_id, json.dumps(question, ensure_ascii=False), now, now),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def mark(self, request_id: str, status: str, *, answer: dict | None = None, error: str | None = None) -> bool:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE jobs SET status=?, "
                "answer_json=COALESCE(?, answer_json), "
                "error=COALESCE(?, error), "
                "updated_at=? WHERE request_id=?",
                (
                    status,
                    json.dumps(answer, ensure_ascii=False) if answer is not None else None,
                    error,
                    now,
                    request_id,
                ),
            )
        return cur.rowcount > 0

    # ─── Lookups ───

    def by_chat(self, chat_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT request_id, chat_id, question_json, status, answer_json, error "
                "FROM jobs WHERE chat_id=? ORDER BY created_at DESC LIMIT 1",
                (chat_id,),
            ).fetchone()
        return _row_to_dict(row) if row else None

    def by_request_id(self, request_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT request_id, chat_id, question_json, status, answer_json, error "
                "FROM jobs WHERE request_id=?",
                (request_id,),
            ).fetchone()
        return _row_to_dict(row) if row else None

    def list_resumable(self) -> Iterable[dict]:
        """Jobs that need to be replayed: pending (re-issue to Hermes) or
        answered (re-upload to platform)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT request_id, chat_id, question_json, status, answer_json, error "
                "FROM jobs WHERE status IN ('pending','answered') ORDER BY created_at ASC"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) FROM jobs GROUP BY status"
            ).fetchall()
        out = {s: 0 for s in ("pending", "answered", "uploaded", "failed")}
        for s, c in rows:
            out[s] = c
        return out


def _row_to_dict(row) -> dict:
    rid, cid, q, status, ans, err = row
    return {
        "request_id": rid,
        "chat_id": cid,
        "question": json.loads(q),
        "status": status,
        "answer": json.loads(ans) if ans else None,
        "error": err,
    }
