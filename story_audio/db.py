from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA = r"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL UNIQUE,
    chapter_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chapter_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    source_href TEXT,
    raw_text_revision_id INTEGER,
    active_text_revision_id INTEGER,
    char_count INTEGER NOT NULL DEFAULT 0,
    audio_status TEXT NOT NULL DEFAULT 'not_created',
    active_audio_artifact_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(book_id, chapter_number)
);

CREATE TABLE IF NOT EXISTS text_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    parent_revision_id INTEGER REFERENCES text_revisions(id),
    kind TEXT NOT NULL,
    content_path TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    lexical_sha256 TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    processor_version TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qa_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    text_revision_id INTEGER REFERENCES text_revisions(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT,
    resolved_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id),
    status TEXT NOT NULL,
    from_chapter INTEGER NOT NULL,
    to_chapter INTEGER NOT NULL,
    voice_name TEXT NOT NULL,
    repair_mode TEXT NOT NULL,
    output_format TEXT NOT NULL,
    settings_json TEXT NOT NULL,
    skip_completed INTEGER NOT NULL DEFAULT 1,
    pause_requested INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    total_chapters INTEGER NOT NULL DEFAULT 0,
    completed_chapters INTEGER NOT NULL DEFAULT 0,
    failed_chapters INTEGER NOT NULL DEFAULT 0,
    current_chapter_number INTEGER,
    current_stage TEXT,
    error_message TEXT,
    scheduled_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id),
    sequence INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    text_revision_id INTEGER REFERENCES text_revisions(id),
    artifact_id INTEGER,
    error_message TEXT,
    started_at TEXT,
    finished_at TEXT,
    UNIQUE(job_id, chapter_id)
);

CREATE TABLE IF NOT EXISTS repair_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_chapter_id INTEGER NOT NULL REFERENCES job_chapters(id) ON DELETE CASCADE,
    block_index INTEGER NOT NULL,
    source_path TEXT NOT NULL,
    repaired_path TEXT,
    source_sha256 TEXT NOT NULL,
    lexical_sha256 TEXT NOT NULL,
    model_id TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    verified_at TEXT,
    UNIQUE(job_chapter_id, block_index)
);

CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_chapter_id INTEGER NOT NULL REFERENCES job_chapters(id) ON DELETE CASCADE,
    segment_index INTEGER NOT NULL,
    text_path TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    wav_path TEXT,
    audio_sha256 TEXT,
    duration_ms INTEGER,
    error_message TEXT,
    created_at TEXT NOT NULL,
    verified_at TEXT,
    UNIQUE(job_chapter_id, segment_index)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id),
    job_chapter_id INTEGER REFERENCES job_chapters(id),
    text_revision_id INTEGER REFERENCES text_revisions(id),
    artifact_type TEXT NOT NULL,
    synthesis_hash TEXT,
    export_hash TEXT,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    duration_ms INTEGER,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    verified_at TEXT,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS artifact_dependencies (
    parent_artifact_id INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    child_artifact_id INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    PRIMARY KEY(parent_artifact_id, child_artifact_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_code TEXT NOT NULL,
    job_id INTEGER,
    chapter_id INTEGER,
    details_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chapters_book_number ON chapters(book_id, chapter_number);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_job_chapters_job_status ON job_chapters(job_id, status);
CREATE INDEX IF NOT EXISTS idx_segments_job_chapter ON segments(job_chapter_id, segment_index);
CREATE INDEX IF NOT EXISTS idx_artifacts_chapter_type ON artifacts(chapter_id, artifact_type, status);
"""


class ClosingConnection(sqlite3.Connection):
    """Commit/rollback and close when used as a context manager."""

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
        return False


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.path,
            timeout=30,
            check_same_thread=False,
            factory=ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                "UPDATE jobs SET status='interrupted', current_stage='recovery', updated_at=? "
                "WHERE status IN ('running','repairing','synthesizing','assembling')",
                (utcnow(),),
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(sql, params).fetchone()

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(connection.execute(sql, params).fetchall())

    def audit(
        self,
        event_code: str,
        *,
        job_id: int | None = None,
        chapter_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO audit_events(event_code,job_id,chapter_id,details_json,created_at) VALUES(?,?,?,?,?)",
                (event_code, job_id, chapter_id, json.dumps(details or {}, ensure_ascii=False), utcnow()),
            )
