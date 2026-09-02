from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from story_audio.db import Database, utcnow
from story_audio.files import sha256_file
from story_audio.pipeline import PipelineWorker
from story_audio.storage import ContentStore
from tests.base import IsolatedTestCase


class StartupCleanupAuthorityTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config = replace(
            self.config,
            successful_segment_retention_hours=1,
            worker_poll_seconds=60,
        )
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)
        self.authority = {"allowed": True}
        self.worker = PipelineWorker(
            self.db,
            self.store,
            MagicMock(),
            self.config,
            maintenance_authorized=lambda: self.authority["allowed"],
        )
        self.segment_path, self.final_path, self.cas_path = self._seed_eligible_segment()

    def _seed_eligible_segment(self) -> tuple[Path, Path, Path]:
        now = utcnow()
        finished_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        segment_path = self.config.work_dir / "job_1" / "chapter_1" / "segment_000.wav"
        final_path = self.config.output_dir / "job_1" / "chapter_1" / "final.m4a"
        cas_path = self.config.blobs_dir / "audio" / "fixture-cas.wav"
        for path, contents in (
            (segment_path, b"eligible-segment"),
            (final_path, b"final-artifact"),
            (cas_path, b"cas-artifact"),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        with self.db.connect() as connection:
            connection.execute(
                "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                ("Fixture book", "fixture.epub", "fixture-source", now, now),
            )
            connection.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                (1, 1, "Fixture chapter", now, now),
            )
            connection.execute(
                """INSERT INTO jobs(book_id,status,from_chapter,to_chapter,voice_name,repair_mode,
                       output_format,settings_json,scheduled_at,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (1, "completed", 1, 1, "fixture", "off", "m4a", "{}", now, now, now),
            )
            connection.execute(
                "INSERT INTO job_chapters(job_id,chapter_id,sequence,status,finished_at) VALUES(?,?,?,?,?)",
                (1, 1, 1, "completed", finished_at),
            )
            connection.execute(
                """INSERT INTO segments(job_chapter_id,segment_index,text_path,text_sha256,status,
                       wav_path,created_at) VALUES(?,?,?,?,?,?,?)""",
                (1, 0, "fixture.txt", "fixture-text", "verified", str(segment_path), now),
            )
            connection.execute(
                """INSERT INTO artifacts(chapter_id,job_chapter_id,artifact_type,path,sha256,size_bytes,
                       status,created_at,verified_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    1,
                    1,
                    "chapter_m4a",
                    str(final_path),
                    sha256_file(final_path),
                    final_path.stat().st_size,
                    "active",
                    now,
                    now,
                ),
            )
        return segment_path, final_path, cas_path

    def _cleanup_audit_count(self) -> int:
        return int(self.db.fetch_one(
            "SELECT COUNT(*) AS n FROM audit_events WHERE event_code='segment_cleanup_completed'"
        )["n"])

    def _segment_wav_path(self) -> str | None:
        return self.db.fetch_one("SELECT wav_path FROM segments WHERE id=1")["wav_path"]

    def _seed_second_eligible_segment(self) -> Path:
        path = self.config.work_dir / "job_1" / "chapter_1" / "segment_001.wav"
        path.write_bytes(b"second-eligible-segment")
        with self.db.connect() as connection:
            connection.execute(
                """INSERT INTO segments(job_chapter_id,segment_index,text_path,text_sha256,status,
                       wav_path,created_at) VALUES(?,?,?,?,?,?,?)""",
                (1, 1, "fixture-2.txt", "fixture-text-2", "verified", str(path), utcnow()),
            )
        return path

    def test_startup_before_readiness_performs_no_cleanup_write(self) -> None:
        self.assertFalse(self.worker._run_due_maintenance())

        self.assertTrue(self.segment_path.is_file())
        self.assertEqual(str(self.segment_path), self._segment_wav_path())
        self.assertEqual(0, self._cleanup_audit_count())

    def test_cleanup_flag_false_blocks_cleanup_without_audit(self) -> None:
        self.worker.mark_application_ready()
        self.authority["allowed"] = False

        self.assertFalse(self.worker._run_due_maintenance())
        self.assertEqual({"files": 0, "bytes_freed": 0}, self.worker.cleanup_expired_segments())

        self.assertTrue(self.segment_path.is_file())
        self.assertEqual(str(self.segment_path), self._segment_wav_path())
        self.assertEqual(0, self._cleanup_audit_count())

    def test_prepare_kill_switch_is_independent_from_cleanup_authority(self) -> None:
        from story_audio import api

        for kill_switch_active, cleanup_enabled in ((False, False), (True, True)):
            descriptor = SimpleNamespace(
                runtime_mode="PRODUCTION",
                canonical_backed=True,
                quick_check="ok",
                schema_version=16,
                kill_switch_active=kill_switch_active,
                segment_cleanup_enabled=cleanup_enabled,
            )
            self.assertTrue(api._maintenance_runtime_available(descriptor))
            self.authority["allowed"] = descriptor.segment_cleanup_enabled
            self.worker.mark_application_ready()
            ran = self.worker._run_due_maintenance()
            self.assertEqual(cleanup_enabled, ran)
            if not cleanup_enabled:
                self.assertTrue(self.segment_path.is_file())
                self.assertEqual(str(self.segment_path), self._segment_wav_path())
                self.assertEqual(0, self._cleanup_audit_count())

    def test_ready_authorized_cleanup_preserves_final_and_cas_then_repeats_on_interval(self) -> None:
        self.worker.mark_application_ready()

        self.assertTrue(self.worker._run_due_maintenance())
        self.assertFalse(self.segment_path.exists())
        self.assertIsNone(self._segment_wav_path())
        self.assertEqual(1, self._cleanup_audit_count())
        self.assertTrue(self.final_path.is_file())
        self.assertTrue(self.cas_path.is_file())

        second_path = self._seed_second_eligible_segment()
        self.assertFalse(self.worker._run_due_maintenance())
        self.assertTrue(second_path.is_file())
        self.worker._last_cleanup -= 301
        self.assertTrue(self.worker._run_due_maintenance())
        self.assertFalse(second_path.exists())
        self.assertEqual(2, self._cleanup_audit_count())

    def test_lifespan_starts_authority_gated_maintenance_without_render_authority(self) -> None:
        from story_audio import api

        calls: list[str] = []
        original_db, original_worker, original_descriptor = (
            api.db,
            api.worker,
            api.prepare_runtime_integration,
        )
        api.db = SimpleNamespace(initialize=lambda: calls.append("initialize"))
        api.worker = SimpleNamespace(
            mark_application_ready=lambda: calls.append("ready"),
            start=lambda **kwargs: calls.append("start"),
            stop=lambda: calls.append("stop"),
        )
        api.prepare_runtime_integration = SimpleNamespace(
            runtime_mode="PRODUCTION",
            production_render_enabled=False,
            canonical_backed=True,
            quick_check="ok",
            schema_version=16,
        )
        try:
            async def exercise_lifespan() -> None:
                async with api.lifespan(api.app):
                    self.assertEqual(["ready", "start"], calls)

            asyncio.run(exercise_lifespan())
        finally:
            api.db, api.worker, api.prepare_runtime_integration = (
                original_db,
                original_worker,
                original_descriptor,
            )
        self.assertEqual(["ready", "start", "stop"], calls)

    def test_verified_schema_window_uses_a_writable_maintenance_database(self) -> None:
        from story_audio import api

        descriptor = SimpleNamespace(
            runtime_mode="PRODUCTION",
            canonical_backed=True,
            quick_check="ok",
            schema_version=16,
        )
        primary = MagicMock()

        maintenance_db = api._build_maintenance_database(
            self.config.db_path,
            descriptor,
            primary,
        )

        self.assertIsInstance(maintenance_db, Database)
        self.assertIsNot(maintenance_db, primary)

    def test_maintenance_only_worker_never_picks_up_jobs(self) -> None:
        self.worker._maintenance_only = True
        def stop_loop() -> None:
            self.worker._stop.set()
            self.worker._wake.set()

        with (
            patch.object(self.worker, "_next_job") as next_job,
            patch.object(self.worker, "_run_due_maintenance", side_effect=stop_loop),
        ):
            self.worker._loop()

        next_job.assert_not_called()
