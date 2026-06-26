from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import canonical_production_db_path
from .migrations import LATEST_SCHEMA_VERSION, MigrationRunner

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

def _check_live_db_guard(path: Path) -> None:
    """Fail-closed guard preventing accidental production DB mutations.
    
    Raises RuntimeError if attempting to initialize/migrate the canonical
    production database without explicit opt-in.
    
    Test mode (STORY_AUDIO_TESTING=1) always blocks live DB access.
    Non-test mode requires STORY_AUDIO_ALLOW_LIVE_DB=1 for production DB.
    """
    canonical = canonical_production_db_path().resolve()
    requested = path.resolve()
    
    if requested != canonical:
        # Non-production path, allow
        return
    
    is_testing = os.getenv("STORY_AUDIO_TESTING", "").strip() == "1"
    allow_live = os.getenv("STORY_AUDIO_ALLOW_LIVE_DB", "").strip() == "1"
    
    if is_testing:
        # Test mode always blocks live DB, even with allow_live
        raise RuntimeError(
            f"Test mode (STORY_AUDIO_TESTING=1) attempted to initialize production DB: {canonical}\n"
            "Tests must use temporary database paths."
        )
    
    if not allow_live:
        raise RuntimeError(
            f"Attempted to initialize production database without explicit opt-in: {canonical}\n"
            "Production launcher must set STORY_AUDIO_ALLOW_LIVE_DB=1 before starting the app.\n"
            "Tests must use temporary paths and set STORY_AUDIO_TESTING=1."
        )

class Database:
    def __init__(self, path: Path, migration_runner: MigrationRunner | None = None):
        self.path = path
        self.migration_runner = migration_runner or MigrationRunner()

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

    def initialize(self) -> int:
        _check_live_db_guard(self.path)
        with self.connect() as connection:
            version = self.migration_runner.apply(connection, utcnow())
            connection.execute(
                "UPDATE jobs SET status='interrupted', current_stage='recovery', updated_at=? "
                "WHERE status IN ('running','repairing','synthesizing','assembling')",
                (utcnow(),),
            )
        return version

    def schema_version(self) -> int:
        with self.connect() as connection:
            return self.migration_runner.current_version(connection)

    @property
    def latest_schema_version(self) -> int:
        return LATEST_SCHEMA_VERSION

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
