"""SQLite-backed persistence for chat sessions and weak-area tracking.

Single-user local tool — no auth/multi-tenancy. One DB file (default grader/data.db) holds:
  - sessions: chat sessions (id, title, created_at, last_active_at)
  - messages: each session's turn history, in order
  - weak_areas: concepts a student got wrong on a graded script, with a running miss count
  - grading_events: one row per graded question (confidence, needs_human_review) — the raw log
    behind the grader's self-reported abstention rate

This is what lets tutor chat survive a server restart, lets the tutor reference past mistakes
from script grading instead of starting from zero every conversation, and lets the grader's
own reliability be measured rather than asserted.
"""

import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from grader.providers.base import ChatMessage

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);

CREATE TABLE IF NOT EXISTS weak_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    concept TEXT NOT NULL,
    miss_count INTEGER NOT NULL DEFAULT 1,
    correct_count INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(subject, concept)
);

CREATE TABLE IF NOT EXISTS grading_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    concept TEXT NOT NULL,
    is_correct INTEGER NOT NULL,
    confidence TEXT NOT NULL,
    needs_human_review INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_grading_events_subject ON grading_events(subject);
"""


@dataclass
class SessionSummary:
    id: str
    title: str
    created_at: str
    last_active_at: str


@dataclass
class WeakArea:
    subject: str
    concept: str
    miss_count: int
    correct_count: int


@dataclass
class ReliabilityStats:
    subject: str
    total_graded: int
    flagged_for_review: int

    @property
    def abstention_rate(self) -> float | None:
        return self.flagged_for_review / self.total_graded if self.total_graded else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- Chat sessions ----

    def create_session(self, title: str = "New chat") -> str:
        session_id = str(uuid.uuid4())
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, title, created_at, last_active_at) VALUES (?, ?, ?, ?)",
                (session_id, title, now, now),
            )
        return session_id

    def append_message(self, session_id: str, role: str, content: str) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content, now),
            )
            conn.execute("UPDATE sessions SET last_active_at = ? WHERE id = ?", (now, session_id))

    def get_history(self, session_id: str) -> list[ChatMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        return [ChatMessage(role=role, content=content) for role, content in rows]

    def list_sessions(self) -> list[SessionSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at, last_active_at FROM sessions ORDER BY last_active_at DESC"
            ).fetchall()
        return [SessionSummary(*row) for row in rows]

    def session_exists(self, session_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return row is not None

    def set_session_title(self, session_id: str, title: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))

    def delete_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    # ---- Weak-area tracking ----

    def record_question_result(self, subject: str, concept: str, is_correct: bool) -> None:
        now = _now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT miss_count, correct_count FROM weak_areas WHERE subject = ? AND concept = ?",
                (subject, concept),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO weak_areas (subject, concept, miss_count, correct_count, "
                    "first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (subject, concept, 0 if is_correct else 1, 1 if is_correct else 0, now, now),
                )
            else:
                miss_count, correct_count = row
                if is_correct:
                    correct_count += 1
                else:
                    miss_count += 1
                conn.execute(
                    "UPDATE weak_areas SET miss_count = ?, correct_count = ?, last_seen_at = ? "
                    "WHERE subject = ? AND concept = ?",
                    (miss_count, correct_count, now, subject, concept),
                )

    def top_weak_areas(self, subject: str | None = None, limit: int = 5) -> list[WeakArea]:
        """Concepts with more misses than correct answers, worst first."""
        query = (
            "SELECT subject, concept, miss_count, correct_count FROM weak_areas "
            "WHERE miss_count > correct_count"
        )
        params: list = []
        if subject:
            query += " AND subject = ?"
            params.append(subject)
        query += " ORDER BY (miss_count - correct_count) DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [WeakArea(*row) for row in rows]

    def recent_accuracy(self, subject: str | None = None) -> float | None:
        """Overall correct/(correct+miss) ratio across tracked concepts, or None if no data yet."""
        query = "SELECT SUM(correct_count), SUM(miss_count) FROM weak_areas"
        params: list = []
        if subject:
            query += " WHERE subject = ?"
            params.append(subject)
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        correct, miss = row
        if not correct and not miss:
            return None
        correct, miss = correct or 0, miss or 0
        return correct / (correct + miss) if (correct + miss) else None

    # ---- Grading reliability tracking ----

    def record_grading_event(
        self, subject: str, concept: str, is_correct: bool, confidence: str, needs_human_review: bool
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO grading_events (subject, concept, is_correct, confidence, "
                "needs_human_review, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (subject, concept, int(is_correct), confidence, int(needs_human_review), _now()),
            )

    def reliability_stats(self, subject: str | None = None) -> ReliabilityStats:
        """How often the grader has flagged its own output for human review — a real, queryable
        abstention rate, not just a per-question badge."""
        query = "SELECT COUNT(*), SUM(needs_human_review) FROM grading_events"
        params: list = []
        if subject:
            query += " WHERE subject = ?"
            params.append(subject)
        with self._connect() as conn:
            total, flagged = conn.execute(query, params).fetchone()
        return ReliabilityStats(
            subject=subject or "all", total_graded=total or 0, flagged_for_review=flagged or 0
        )
