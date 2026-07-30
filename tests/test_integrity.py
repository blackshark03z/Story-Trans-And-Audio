from __future__ import annotations

from pathlib import Path

from story_audio.db import Database
from story_audio.integrity import check_data_integrity
from tests.base import IsolatedTestCase


class IntegrityTests(IsolatedTestCase):
    def _add_missing_verified_segment(
        self,
        *,
        job_chapter_status: str,
        with_published_artifact: bool,
    ) -> None:
        database = Database(self.config.db_path)
        database.initialize()
        now = "2026-07-30T00:00:00+00:00"
        missing_wav = self.temp_root / "missing.wav"
        published = self.temp_root / "published.m4a"
        if with_published_artifact:
            published.write_bytes(b"published")

        with database.connect() as connection:
            book_id = connection.execute(
                """INSERT INTO books(
                       title,author,source_path,source_sha256,chapter_count,
                       created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                ("Book", None, "book.epub", "b" * 64, 1, now, now),
            ).lastrowid
            chapter_id = connection.execute(
                """INSERT INTO chapters(
                       book_id,chapter_number,title,char_count,audio_status,
                       created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                (book_id, 1, "Chapter", 4, "completed", now, now),
            ).lastrowid
            job_id = connection.execute(
                """INSERT INTO jobs(
                       book_id,status,from_chapter,to_chapter,voice_name,
                       repair_mode,output_format,settings_json,scheduled_at,
                       created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    book_id,
                    "completed",
                    1,
                    1,
                    "voice",
                    "off",
                    "m4a",
                    "{}",
                    now,
                    now,
                    now,
                ),
            ).lastrowid
            job_chapter_id = connection.execute(
                """INSERT INTO job_chapters(
                       job_id,chapter_id,sequence,status,finished_at
                   ) VALUES(?,?,?,?,?)""",
                (job_id, chapter_id, 1, job_chapter_status, now),
            ).lastrowid
            connection.execute(
                """INSERT INTO segments(
                       job_chapter_id,segment_index,text_path,text_sha256,status,
                       wav_path,audio_sha256,duration_ms,created_at,verified_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_chapter_id,
                    1,
                    str(self.temp_root / "text.txt"),
                    "t" * 64,
                    "verified",
                    str(missing_wav),
                    "a" * 64,
                    1000,
                    now,
                    now,
                ),
            )
            if with_published_artifact:
                connection.execute(
                    """INSERT INTO artifacts(
                           chapter_id,job_chapter_id,artifact_type,path,sha256,
                           size_bytes,duration_ms,status,created_at,verified_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        chapter_id,
                        job_chapter_id,
                        "chapter_m4a",
                        str(published),
                        "p" * 64,
                        published.stat().st_size,
                        1000,
                        "active",
                        now,
                        now,
                    ),
                )

    def test_completed_job_with_published_artifact_warns_for_pruned_checkpoint(self) -> None:
        self._add_missing_verified_segment(
            job_chapter_status="completed",
            with_published_artifact=True,
        )

        findings = check_data_integrity(self.config)
        by_name = {finding.name: finding for finding in findings}

        self.assertEqual(by_name["verified_segments"].level, "OK")
        self.assertEqual(by_name["historical_segment_files"].level, "WARN")
        self.assertEqual(by_name["historical_segment_files"].detail, "missing=1")

    def test_missing_checkpoint_without_published_artifact_remains_error(self) -> None:
        self._add_missing_verified_segment(
            job_chapter_status="running",
            with_published_artifact=False,
        )

        findings = check_data_integrity(self.config)
        by_name = {finding.name: finding for finding in findings}

        self.assertEqual(by_name["verified_segments"].level, "ERROR")
        self.assertEqual(by_name["verified_segments"].detail, "missing_resumable=1")
        self.assertEqual(by_name["historical_segment_files"].level, "OK")
