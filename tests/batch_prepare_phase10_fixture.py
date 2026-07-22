from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from story_audio.batch_plan import build_batch_plan
from story_audio.batch_prepare_execution_attempt_store import BatchPrepareExecutionAttemptStore
from story_audio.batch_prepare_isolated_adapter import (
    BatchPrepareCommittedEvidenceReader,
    BatchPrepareIsolatedAdapter,
    DatabaseAuthoritativeSnapshotProvider,
    TEMPORARY_MARKER,
)
from story_audio.batch_prepare_isolated_transaction_service import BatchPrepareIsolatedTransactionService
from story_audio.batch_prepare_orchestrator import BatchPrepareOrchestrator
from story_audio.batch_prepare_store import BatchPrepareRequestStore
from story_audio.config import Settings, canonical_production_db_path
from story_audio.db import Database, utcnow
from story_audio.files import sha256_text
from story_audio.storage import ContentStore
from tests.phase9_fixture import schema_15_runner


class Phase10FixtureMixin(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        os.environ["STORY_AUDIO_TESTING"] = "1"
        self.temp = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temp.name).resolve()
        (self.temp_root / TEMPORARY_MARKER).write_text("PHASE10_TEMPORARY_ONLY", encoding="utf-8")
        self.db_path = self.temp_root / "phase10.db"
        self.assertNotEqual(self.db_path, canonical_production_db_path().resolve())
        self.config = Settings(
            root=self.temp_root,
            data_dir=self.temp_root,
            db_path=self.db_path,
            blobs_dir=self.temp_root / "blobs",
            output_dir=self.temp_root / "output",
            work_dir=self.temp_root / "work",
            log_dir=self.temp_root / "logs",
        )
        self.config.ensure_dirs()
        self.content_store = ContentStore(self.config)
        self.database = Database(self.db_path, migration_runner=schema_15_runner())
        self.assertEqual(self.database.initialize(), 15)
        self.book_id = self._create_book()
        self.store = BatchPrepareRequestStore(self.database)

    def tearDown(self) -> None:
        if self._original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._original_testing
        self.temp.cleanup()
        super().tearDown()

    def _create_book(self) -> int:
        now = utcnow()
        with self.database.transaction() as connection:
            book_id = int(connection.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("Phase 10", "phase10.epub", hashlib.sha256(b"phase10").hexdigest(), 4, now, now),
            ).lastrowid)
            for number in (10, 11, 12, 13):
                text = f"Narration for synthetic chapter {number}."
                content_path, content_sha = self.content_store.put_text(text)
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
                        chapter_id, "reflowed", content_path, content_sha,
                        sha256_text(text), len(text), "phase10-test", "approved", now,
                    ),
                ).lastrowid)
                casting_plan = {
                    "schema_version": 1,
                    "chapter_id": chapter_id,
                    "text_revision_id": text_id,
                    "narrator_voice_id": "custom:26",
                    "book_voice_profile": None,
                    "utterances": [
                        {
                            "utterance_id": f"phase10-{number}-1",
                            "sequence": 1,
                            "start_offset": 0,
                            "end_offset": len(text),
                            "text_sha256": sha256_text(text),
                            "role": "narrator",
                            "character_id": None,
                            "resolved_voice_id": "custom:26",
                        }
                    ],
                }
                plan_path, plan_sha = self.content_store.put_json(casting_plan, namespace="casting")
                connection.execute(
                    """INSERT INTO casting_plans(
                        chapter_id,text_revision_id,plan_revision,status,content_path,plan_sha256,
                        narrator_voice_id,created_at,approved_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        chapter_id, text_id, 1, "approved", plan_path,
                        plan_sha, "custom:26", now, now,
                    ),
                )
                connection.execute(
                    "UPDATE chapters SET active_text_revision_id=?,updated_at=? WHERE id=?",
                    (text_id, now, chapter_id),
                )
        return book_id

    def plan(self, *, from_chapter: int = 10, to_chapter: int = 11) -> dict[str, Any]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM chapters WHERE book_id=? AND chapter_number BETWEEN ? AND ? ORDER BY chapter_number,id",
                (self.book_id, from_chapter, to_chapter),
            ).fetchall()
            chapters: list[dict[str, Any]] = []
            for chapter in rows:
                plan = connection.execute(
                    "SELECT * FROM casting_plans WHERE chapter_id=? ORDER BY plan_revision DESC,id DESC LIMIT 1",
                    (int(chapter["id"]),),
                ).fetchone()
                live = connection.execute(
                    """SELECT j.id,j.status FROM jobs j JOIN job_chapters jc ON jc.job_id=j.id
                       WHERE jc.chapter_id=? AND j.status IN ('prepared','scheduled','queued','running','paused','interrupted')
                       ORDER BY j.id LIMIT 1""",
                    (int(chapter["id"]),),
                ).fetchone()
                ready = (
                    chapter["audio_status"] == "not_created"
                    and chapter["active_audio_artifact_id"] is None
                    and plan is not None
                    and plan["status"] == "approved"
                    and plan["approved_at"] is not None
                    and live is None
                )
                chapters.append(
                    {
                        "chapter_id": int(chapter["id"]),
                        "chapter_number": int(chapter["chapter_number"]),
                        "chapter_title": str(chapter["title"]),
                        "state": "READY_TO_PREPARE" if ready else "PREPARED",
                        "next_action": "PREPARE" if ready else "START_RENDER",
                        "blockers": [],
                        "active_text_revision_id": chapter["active_text_revision_id"],
                        "latest_casting_plan_id": plan["id"] if plan else None,
                        "latest_casting_plan_revision": plan["plan_revision"] if plan else None,
                        "latest_casting_plan_status": plan["status"] if plan else None,
                        "active_artifact_id": chapter["active_audio_artifact_id"],
                        "active_output_job_id": live["id"] if live else None,
                        "active_output_job_chapter_id": None,
                        "live_job_id": live["id"] if live else None,
                        "live_job_status": live["status"] if live else None,
                        "human_qa_status": "pending",
                    }
                )
        return build_batch_plan(
            {
                "scope": {
                    "book_id": self.book_id,
                    "book_title": "Phase 10",
                    "from_chapter": from_chapter,
                    "to_chapter": to_chapter,
                    "chapter_count": len(chapters),
                },
                "chapters": chapters,
                "summary": {"total": len(chapters)},
                "exceptions": [],
            },
            target_phase="PREPARE",
        )

    def plan_provider(self, **kwargs: Any) -> dict[str, Any]:
        return self.plan(
            from_chapter=int(kwargs["from_chapter"]),
            to_chapter=int(kwargs["to_chapter"]),
        )

    def request(
        self,
        plan: dict[str, Any],
        *,
        client_request_id: str = "phase10-request-1",
    ) -> dict[str, Any]:
        scope = plan["scope"]
        return {
            "client_request_id": client_request_id,
            "book_id": scope["book_id"],
            "from_chapter": scope["from_chapter"],
            "to_chapter": scope["to_chapter"],
            "target_phase": "PREPARE",
            "plan_fingerprint": plan["plan_fingerprint"],
            "explicit_confirmation": True,
        }

    def orchestrator(
        self,
        *,
        current_plan_provider=None,
        request_store=None,
        **adapter_overrides: Any,
    ) -> tuple[BatchPrepareOrchestrator, BatchPrepareIsolatedAdapter]:
        attempts = BatchPrepareExecutionAttemptStore(self.database)
        transaction_service = adapter_overrides.pop(
            "transaction_service",
            BatchPrepareIsolatedTransactionService(self.database),
        )
        snapshot_provider = adapter_overrides.pop(
            "snapshot_provider",
            DatabaseAuthoritativeSnapshotProvider(
                self.database,
                self.content_store,
                self.config,
                temporary_root=self.temp_root,
            ),
        )
        evidence_reader = adapter_overrides.pop(
            "evidence_reader",
            BatchPrepareCommittedEvidenceReader(self.database, temporary_root=self.temp_root),
        )
        adapter = BatchPrepareIsolatedAdapter(
            db=self.database,
            attempt_store=attempts,
            transaction_service=transaction_service,
            snapshot_provider=snapshot_provider,
            evidence_reader=evidence_reader,
            temporary_root=self.temp_root,
            **adapter_overrides,
        )
        orchestrator = BatchPrepareOrchestrator(
            current_plan_provider=current_plan_provider or self.plan_provider,
            request_store=request_store or self.store,
            future_prepare_transaction=adapter,
        )
        return orchestrator, adapter

    def counts(self) -> dict[str, int]:
        with self.database.connect() as connection:
            return {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in (
                    "batch_prepare_requests",
                    "batch_prepare_execution_attempts",
                    "batch_prepare_job_links",
                    "jobs",
                    "job_chapters",
                    "segments",
                    "artifacts",
                )
            }
