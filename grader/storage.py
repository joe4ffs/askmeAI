"""SQLite-backed persistence for chat sessions and weak-area tracking.

Single-user local tool — no auth/multi-tenancy. One DB file (default grader/data.db) holds:
  - sessions: chat sessions (id, title, created_at, last_active_at)
  - messages: each session's turn history, in order
  - weak_areas: concepts a student got wrong on a graded script, with a running miss/correct
    count — also the source of mastery_by_concept()'s per-concept mastery percentage
  - grading_events: one row per graded question (confidence, needs_human_review) — the raw log
    behind the grader's self-reported abstention rate
  - flashcards: auto-generated from wrong answers during script grading (front/back built
    directly from that question's explanation/correction, no extra model call), with a simple
    correct-streak so review sessions surface unmastered cards first

This is what lets tutor chat survive a server restart, lets the tutor reference past mistakes
from script grading instead of starting from zero every conversation, lets the grader's own
reliability be measured rather than asserted, and turns a single graded script into an ongoing
study loop instead of a one-off result.
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

CREATE TABLE IF NOT EXISTS flashcards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    concept TEXT NOT NULL,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    correct_streak INTEGER NOT NULL DEFAULT 0,
    times_reviewed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_flashcards_subject ON flashcards(subject);
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


MASTERY_STREAK_TARGET = 3  # correct reviews in a row before a flashcard is considered "mastered"


@dataclass
class Flashcard:
    id: int
    subject: str
    concept: str
    front: str
    back: str
    correct_streak: int
    times_reviewed: int
    created_at: str
    last_reviewed_at: str | None

    @property
    def mastered(self) -> bool:
        return self.correct_streak >= MASTERY_STREAK_TARGET


@dataclass
class ConceptMastery:
    subject: str
    concept: str
    correct_count: int
    miss_count: int

    @property
    def total_attempts(self) -> int:
        return self.correct_count + self.miss_count

    @property
    def mastery_pct(self) -> float:
        return self.correct_count / self.total_attempts if self.total_attempts else 0.0


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

    def mastery_by_concept(self, subject: str | None = None) -> list[ConceptMastery]:
        """Per-concept correct/miss breakdown, worst mastery first — the full picture behind
        top_weak_areas (which only surfaces net-negative concepts)."""
        query = "SELECT subject, concept, correct_count, miss_count FROM weak_areas"
        params: list = []
        if subject:
            query += " WHERE subject = ?"
            params.append(subject)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        items = [ConceptMastery(*row) for row in rows]
        return sorted(items, key=lambda m: m.mastery_pct)

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

    # ---- Flashcards ----

    def create_flashcard(self, subject: str, concept: str, front: str, back: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO flashcards (subject, concept, front, back, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (subject, concept, front, back, _now()),
            )
            return cursor.lastrowid

    def due_flashcards(self, subject: str | None = None, limit: int = 20) -> list[Flashcard]:
        """Cards not yet mastered (correct_streak below target), least-recently-reviewed first —
        never-reviewed cards (last_reviewed_at IS NULL) come first of all."""
        query = (
            "SELECT id, subject, concept, front, back, correct_streak, times_reviewed, "
            "created_at, last_reviewed_at FROM flashcards WHERE correct_streak < ?"
        )
        params: list = [MASTERY_STREAK_TARGET]
        if subject:
            query += " AND subject = ?"
            params.append(subject)
        query += " ORDER BY last_reviewed_at IS NOT NULL, last_reviewed_at ASC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Flashcard(*row) for row in rows]

    def all_flashcards(self, subject: str | None = None) -> list[Flashcard]:
        query = (
            "SELECT id, subject, concept, front, back, correct_streak, times_reviewed, "
            "created_at, last_reviewed_at FROM flashcards"
        )
        params: list = []
        if subject:
            query += " WHERE subject = ?"
            params.append(subject)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Flashcard(*row) for row in rows]

    def record_flashcard_review(self, card_id: int, got_it_right: bool) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT correct_streak FROM flashcards WHERE id = ?", (card_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"No flashcard with id {card_id!r}")
            new_streak = row[0] + 1 if got_it_right else 0
            conn.execute(
                "UPDATE flashcards SET correct_streak = ?, times_reviewed = times_reviewed + 1, "
                "last_reviewed_at = ? WHERE id = ?",
                (new_streak, _now(), card_id),
            )

    def delete_flashcard(self, card_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM flashcards WHERE id = ?", (card_id,))
