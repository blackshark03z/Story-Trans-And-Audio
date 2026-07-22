from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from story_audio.batch_prepare_execution_attempt_store import BatchPrepareExecutionAttemptStore
from story_audio.batch_prepare_transaction_revalidator import (
    AuthoritativeChapterSnapshot,
    PrepareTransactionSnapshot,
    chapter_snapshot_digest,
)
from story_audio.db import Database, utcnow
from story_audio.migrations import MIGRATIONS, Migration, MigrationRunner
from tests.test_batch_prepare_job_link_migration import load_schema_14_migration
from tests.test_batch_prepare_migration import load_schema_13_migration


DORMANT_EXECUTION_MIGRATION_PATH = Path(
    "story_audio/migrations/dormant/0015_batch_prepare_execution_attempts.sql"
)


def load_schema_15_migration(sql: str | None = None) -> Migration:
    migration_sql = sql if sql is not None else DORMANT_EXECUTION_MIGRATION_PATH.read_text(encoding="utf-8")
    return Migration(
        version=15,
        name="batch_prepare_execution_attempts",
        path=DORMANT_EXECUTION_MIGRATION_PATH,
        checksum=hashlib.sha256(migration_sql.encode("utf-8")).hexdigest(),
        sql=migration_sql,
    )


def schema_15_runner(sql: str | None = None) -> MigrationRunner:
    return MigrationRunner(
        [*MIGRATIONS, load_schema_13_migration(), load_schema_14_migration(), load_schema_15_migration(sql)]
    )


class Phase9FixtureMixin(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        os.environ["STORY_AUDIO_TESTING"] = "1"
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name).resolve() / "phase9.db"
        self.database = Database(self.db_path, migration_runner=schema_15_runner())
        self.assertEqual(self.database.initialize(), 15)
        self.fixture = self.create_scope()

    def tearDown(self) -> None:
        if self._original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._original_testing
        self.temp.cleanup()
        super().tearDown()

    def create_scope(
        self,
        *,
        client_request_id: str = "phase9-request-1",
        request_identity: str = "a" * 64,
        plan_fingerprint: str = "b" * 64,
        chapter_numbers: tuple[int, ...] = (10, 11),
        source_suffix: str = "one",
    ) -> dict[str, Any]:
        now = utcnow()
        with self.database.transaction() as connection:
            book_id = int(connection.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (
                    f"Phase 9 {source_suffix}", f"phase9-{source_suffix}.epub",
                    hashlib.sha256(source_suffix.encode()).hexdigest(), len(chapter_numbers), now, now,
                ),
            ).lastrowid)
            chapters: list[dict[str, Any]] = []
            for order, number in enumerate(chapter_numbers, start=1):
                chapter_id = int(connection.execute(
                    "INSERT INTO chapters(book_id,chapter_number,title,audio_status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (book_id, number, f"Chapter {number}", "not_created", now, now),
                ).lastrowid)
                text_id = int(connection.execute(
                    """INSERT INTO text_revisions(
                        chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                        processor_version,status,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        chapter_id, "reflowed", f"blobs/text/{source_suffix}-{number}.txt",
                        hashlib.sha256(f"text-{source_suffix}-{number}".encode()).hexdigest(),
                        hashlib.sha256(f"lex-{source_suffix}-{number}".encode()).hexdigest(),
                        100, "phase9-test", "approved", now,
                    ),
                ).lastrowid)
                plan_sha = hashlib.sha256(f"plan-{source_suffix}-{number}".encode()).hexdigest()
                plan_id = int(connection.execute(
                    """INSERT INTO casting_plans(
                        chapter_id,text_revision_id,plan_revision,status,content_path,plan_sha256,
                        narrator_voice_id,created_at,approved_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        chapter_id, text_id, 1, "approved", f"casting/{source_suffix}-{number}.json",
                        plan_sha, "custom:26", now, now,
                    ),
                ).lastrowid)
                connection.execute(
                    "UPDATE chapters SET active_text_revision_id=?,updated_at=? WHERE id=?",
                    (text_id, now, chapter_id),
                )
                chapters.append(
                    {
                        "book_id": book_id,
                        "chapter_id": chapter_id,
                        "chapter_number": number,
                        "text_revision_id": text_id,
                        "casting_plan_id": plan_id,
                        "casting_plan_revision": 1,
                        "casting_plan_sha256": plan_sha,
                        "narrator_voice_id": "custom:26",
                        "deterministic_order": order,
                        "eligibility_evidence": ("READY_TO_PREPARE",),
                        "casting_snapshot_json": "{}",
                        "voice_snapshot_json": "{}",
                    }
                )
            request_id = int(connection.execute(
                """INSERT INTO batch_prepare_requests(
                    client_request_id,request_identity,book_id,from_chapter,to_chapter,target_phase,
                    plan_fingerprint,state,attempt_count,applying_started_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    client_request_id, request_identity, book_id, min(chapter_numbers), max(chapter_numbers),
                    "PREPARE", plan_fingerprint, "APPLYING", 1, now, now, now,
                ),
            ).lastrowid)
        return {
            "request_id": request_id,
            "request_identity": request_identity,
            "plan_fingerprint": plan_fingerprint,
            "book_id": book_id,
            "from_chapter": min(chapter_numbers),
            "to_chapter": max(chapter_numbers),
            "chapters": chapters,
        }

    def acquire_and_snapshot(
        self,
        fixture: dict[str, Any] | None = None,
        *,
        lease_seconds: int = 120,
        transaction_reference: str | None = None,
    ) -> tuple[Any, PrepareTransactionSnapshot]:
        facts = fixture or self.fixture
        chapters = tuple(AuthoritativeChapterSnapshot(**item) for item in facts["chapters"])
        digest = chapter_snapshot_digest(chapters)
        lease = BatchPrepareExecutionAttemptStore(self.database).acquire(
            request_id=facts["request_id"],
            request_identity=facts["request_identity"],
            plan_fingerprint=facts["plan_fingerprint"],
            chapter_snapshot_digest=digest,
            lease_seconds=lease_seconds,
            transaction_reference=transaction_reference,
        )
        snapshot = PrepareTransactionSnapshot(
            request_id=facts["request_id"],
            request_identity=facts["request_identity"],
            book_id=facts["book_id"],
            from_chapter=facts["from_chapter"],
            to_chapter=facts["to_chapter"],
            target_phase="PREPARE",
            plan_fingerprint=facts["plan_fingerprint"],
            chapters=chapters,
            chapter_snapshot_digest=digest,
            owner_generation=lease.record.attempt_generation,
            owner_token=lease.owner_token,
            transaction_reference=lease.record.transaction_reference,
        )
        return lease, snapshot

    def create_request_for_scope(
        self,
        fixture: dict[str, Any],
        *,
        client_request_id: str,
        request_identity: str,
        plan_fingerprint: str,
    ) -> dict[str, Any]:
        now = utcnow()
        with self.database.transaction() as connection:
            request_id = int(connection.execute(
                """INSERT INTO batch_prepare_requests(
                    client_request_id,request_identity,book_id,from_chapter,to_chapter,target_phase,
                    plan_fingerprint,state,attempt_count,applying_started_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    client_request_id, request_identity, fixture["book_id"], fixture["from_chapter"],
                    fixture["to_chapter"], "PREPARE", plan_fingerprint, "APPLYING", 1, now, now, now,
                ),
            ).lastrowid)
        return {
            **fixture,
            "request_id": request_id,
            "request_identity": request_identity,
            "plan_fingerprint": plan_fingerprint,
        }
