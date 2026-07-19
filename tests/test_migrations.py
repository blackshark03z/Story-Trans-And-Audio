from __future__ import annotations

import sqlite3
import tempfile
import os
import unittest
from pathlib import Path

from story_audio.db import Database, utcnow
from story_audio.migrations import (
    MIGRATIONS,
    FutureSchemaVersionError,
    LATEST_SCHEMA_VERSION,
    MigrationChecksumError,
)

class MigrationTests(unittest.TestCase):

    def setUp(self) -> None:
        super().setUp()
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        os.environ["STORY_AUDIO_TESTING"] = "1"
    
    def tearDown(self) -> None:
        if self._original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._original_testing
        super().tearDown()

    def test_legacy_unversioned_database_upgrades_and_preserves_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(MIGRATIONS[0].sql)
                now = utcnow()
                cursor = connection.execute(
                    "INSERT INTO books(title,author,source_path,source_sha256,chapter_count,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    ("Legacy Book", "Author", "book.epub", "legacy-sha", 1, now, now),
                )
                book_id = int(cursor.lastrowid)
                connection.execute(
                    """INSERT INTO jobs(
                        book_id,status,from_chapter,to_chapter,voice_name,repair_mode,
                        output_format,settings_json,total_chapters,scheduled_at,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        book_id,
                        "completed",
                        1,
                        1,
                        "default",
                        "auto",
                        "mp3",
                        "{}",
                        1,
                        now,
                        now,
                        now,
                    ),
                )
                connection.commit()
            finally:
                connection.close()
            database = Database(path)
            self.assertEqual(database.initialize(), LATEST_SCHEMA_VERSION)
            book = database.fetch_one("SELECT * FROM books WHERE id=?", (book_id,))
            self.assertEqual(book["title"], "Legacy Book")

    def test_version_one_upgrades_to_character_voice_schema_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v1.db"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(MIGRATIONS[0].sql)
                now = utcnow()
                book_id = connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Book", "book.epub", "v1-sha", now, now),
                ).lastrowid
                connection.execute(
                    "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,name TEXT,checksum TEXT,applied_at TEXT)"
                )
                connection.execute(
                    "INSERT INTO schema_migrations VALUES(?,?,?,?)",
                    (MIGRATIONS[0].version, MIGRATIONS[0].name, MIGRATIONS[0].checksum, now),
                )
                connection.commit()
            finally:
                connection.close()
            database = Database(path)
            self.assertEqual(database.initialize(), LATEST_SCHEMA_VERSION)
            tables = {row["name"] for row in database.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("characters", tables)

    def test_version_two_migrates_existing_character_voice_to_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v2.db"
            connection = sqlite3.connect(path)
            try:
                for migration in MIGRATIONS[:2]:
                    connection.executescript(migration.sql)
                now = utcnow()
                book_id = connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Book", "book.epub", "v2-sha", now, now),
                ).lastrowid
                connection.execute(
                    "INSERT INTO characters(book_id,display_name,default_voice_id,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (book_id, "Legacy", "legacy-voice", now, now),
                )
                connection.execute(
                    "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,name TEXT,checksum TEXT,applied_at TEXT)"
                )
                for migration in MIGRATIONS[:2]:
                    connection.execute(
                        "INSERT INTO schema_migrations VALUES(?,?,?,?)",
                        (migration.version, migration.name, migration.checksum, now),
                    )
                connection.commit()
            finally:
                connection.close()
            database = Database(path)
            self.assertEqual(database.initialize(), LATEST_SCHEMA_VERSION)
            character = database.fetch_one("SELECT * FROM characters")
            self.assertEqual(character["default_voice_id"], "legacy-voice")
            self.assertEqual(character["voice_override_id"], "legacy-voice")
            self.assertIsNone(character["gender"])

    def test_version_three_upgrades_to_character_bible_without_losing_voice_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v3.db"
            connection = sqlite3.connect(path)
            try:
                for migration in MIGRATIONS[:3]:
                    connection.executescript(migration.sql)
                now = utcnow()
                book_id = connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Book", "book.epub", "v3-sha", now, now),
                ).lastrowid
                connection.execute(
                    "INSERT INTO characters(book_id,display_name,default_voice_id,voice_override_id,gender,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (book_id, "Legacy", "legacy", "legacy", "male", now, now),
                )
                connection.execute(
                    "INSERT INTO book_voice_profiles(book_id,narrator_voice_id,male_dialogue_voice_id,female_dialogue_voice_id,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (book_id, "narrator", "male", "female", now, now),
                )
                connection.execute(
                    "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,name TEXT,checksum TEXT,applied_at TEXT)"
                )
                for migration in MIGRATIONS[:3]:
                    connection.execute("INSERT INTO schema_migrations VALUES(?,?,?,?)", (migration.version, migration.name, migration.checksum, now))
                connection.commit()
            finally:
                connection.close()
            database = Database(path)
            self.assertEqual(database.initialize(), LATEST_SCHEMA_VERSION)
            character = database.fetch_one("SELECT * FROM characters")
            self.assertEqual(character["canonical_name"], "Legacy")
            self.assertEqual(character["voice_override_id"], "legacy")
            self.assertEqual(database.fetch_one("SELECT narrator_voice_id FROM book_voice_profiles")["narrator_voice_id"], "narrator")

    def test_version_four_upgrades_to_speaker_drafts_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v4.db"
            connection = sqlite3.connect(path)
            try:
                for migration in MIGRATIONS[:4]:
                    connection.executescript(migration.sql)
                now = utcnow()
                book_id = connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Book", "book.epub", "v4-sha", now, now),
                ).lastrowid
                connection.execute(
                    "INSERT INTO characters(book_id,display_name,default_voice_id,canonical_name,canonical_name_normalized,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (book_id, "An", "", "An", "an", now, now),
                )
                connection.execute(
                    "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,name TEXT,checksum TEXT,applied_at TEXT)"
                )
                for migration in MIGRATIONS[:4]:
                    connection.execute(
                        "INSERT INTO schema_migrations VALUES(?,?,?,?)",
                        (migration.version, migration.name, migration.checksum, now),
                    )
                connection.commit()
            finally:
                connection.close()
            database = Database(path)
            self.assertEqual(database.initialize(), LATEST_SCHEMA_VERSION)
            self.assertEqual(database.fetch_one("SELECT COUNT(*) AS n FROM characters")["n"], 1)
            tables = {row["name"] for row in database.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("speaker_assignment_drafts", tables)
            self.assertIn("speaker_assignment_reviews", tables)
            draft_columns = {
                row["name"] for row in database.fetch_all("PRAGMA table_info(speaker_assignment_drafts)")
            }
            self.assertIn("approved_at", draft_columns)

    def test_initialize_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "app.db")
            database.initialize()
            database.initialize()
            count = database.fetch_one("SELECT COUNT(*) AS count FROM schema_migrations")["count"]
            self.assertEqual(count, LATEST_SCHEMA_VERSION)

    def test_future_schema_fails_safely(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "app.db")
            database.initialize()
            with database.connect() as connection:
                connection.execute(
                    "INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES(?,?,?,?)",
                    (LATEST_SCHEMA_VERSION + 1, "future", "future", utcnow()),
                )
            with self.assertRaises(FutureSchemaVersionError):
                database.initialize()

    def test_modified_applied_migration_fails_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "app.db")
            database.initialize()
            with database.connect() as connection:
                connection.execute(
                    "UPDATE schema_migrations SET checksum='tampered' WHERE version=1"
                )
            with self.assertRaises(MigrationChecksumError):
                database.initialize()

    def test_fresh_database_migrates_to_latest_with_snapshot_and_repair_block_columns(self) -> None:
        """Fresh database should migrate cleanly to latest and have expected workflow columns."""
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "fresh.db")
            version = database.initialize()
            self.assertEqual(version, LATEST_SCHEMA_VERSION)
            with database.connect() as connection:
                columns = connection.execute("PRAGMA table_info(segments)").fetchall()
                column_names = {col[1] for col in columns}
                expected_snapshot_columns = {
                    "voice_source_type",
                    "voice_provider",
                    "voice_model",
                    "logical_voice_ref",
                    "effective_voice_ref",
                    "custom_voice_revision_id",
                    "reference_audio_sha256",
                    "reference_audio_storage_key",
                    "reference_transcript",
                    "reference_transcript_sha256",
                    "synthesis_settings_json",
                    "casting_plan_id",
                    "voice_resolution_reason",
                    "voice_snapshot_version",
                }
                self.assertTrue(
                    expected_snapshot_columns.issubset(column_names),
                    f"Missing snapshot columns: {expected_snapshot_columns - column_names}"
                )
                # Verify indices exist
                indices = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='segments'"
                ).fetchall()
                index_names = {idx[0] for idx in indices}
                self.assertIn("idx_segments_custom_voice_revision", index_names)
                self.assertIn("idx_segments_snapshot_version", index_names)
                self.assertIn("idx_segments_casting_plan", index_names)
                repair_block_columns = connection.execute("PRAGMA table_info(audio_repair_blocks)").fetchall()
                repair_block_column_names = {col[1] for col in repair_block_columns}
                self.assertTrue(
                    {
                        "job_id",
                        "job_chapter_id",
                        "first_segment_id",
                        "last_segment_id",
                        "source_text_sha256",
                        "candidate_wav_path",
                        "status",
                    }.issubset(repair_block_column_names)
                )

    def test_v6_to_latest_upgrade_preserves_legacy_segments(self) -> None:
        """v6 database upgrades to latest, legacy segments survive with NULL snapshot fields."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v6.db"
            connection = sqlite3.connect(path)
            try:
                # Apply migrations up to v6
                for migration in MIGRATIONS[:6]:
                    connection.executescript(migration.sql)
                now = utcnow()
                # Insert test data
                book_id = connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Test Book", "test.epub", "test-sha", now, now),
                ).lastrowid
                chapter_id = connection.execute(
                    "INSERT INTO chapters(book_id,chapter_number,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (book_id, 1, "Chapter 1", now, now),
                ).lastrowid
                job_id = connection.execute(
                    """INSERT INTO jobs(
                        book_id,status,from_chapter,to_chapter,voice_name,repair_mode,
                        output_format,settings_json,total_chapters,scheduled_at,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (book_id, "pending", 1, 1, "default", "auto", "mp3", "{}", 1, now, now, now),
                ).lastrowid
                job_chapter_id = connection.execute(
                    "INSERT INTO job_chapters(job_id,chapter_id,sequence,status) VALUES(?,?,?,?)",
                    (job_id, chapter_id, 1, "pending"),
                ).lastrowid
                segment_id = connection.execute(
                    """INSERT INTO segments(
                        job_chapter_id,segment_index,text_path,text_sha256,status,
                        attempt_count,created_at,utterance_sequence,speaker_role,resolved_voice_id
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (job_chapter_id, 0, "text.txt", "text-sha", "pending", 0, now, 0, "narrator", "vi-VN-HoaiMyNeural"),
                ).lastrowid
                # Mark migrations as applied
                connection.execute(
                    "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,name TEXT,checksum TEXT,applied_at TEXT)"
                )
                for migration in MIGRATIONS[:6]:
                    connection.execute(
                        "INSERT INTO schema_migrations VALUES(?,?,?,?)",
                        (migration.version, migration.name, migration.checksum, now),
                    )
                connection.commit()
            finally:
                connection.close()
            
            # Upgrade to latest
            database = Database(path)
            version = database.initialize()
            self.assertEqual(version, LATEST_SCHEMA_VERSION)
            
            # Verify legacy segment still exists with NULL snapshot fields
            segment = database.fetch_one("SELECT * FROM segments WHERE id=?", (segment_id,))
            self.assertIsNotNone(segment)
            self.assertEqual(segment["resolved_voice_id"], "vi-VN-HoaiMyNeural")
            self.assertIsNone(segment["voice_source_type"])
            self.assertIsNone(segment["voice_provider"])
            self.assertIsNone(segment["voice_model"])
            self.assertIsNone(segment["logical_voice_ref"])
            self.assertIsNone(segment["effective_voice_ref"])
            self.assertIsNone(segment["custom_voice_revision_id"])
            self.assertIsNone(segment["reference_audio_sha256"])
            self.assertIsNone(segment["synthesis_settings_json"])
            self.assertIsNone(segment["casting_plan_id"])
            self.assertIsNone(segment["voice_snapshot_version"])

    def test_v7_foreign_key_restriction_prevents_custom_voice_deletion(self) -> None:
        """Segments referencing custom_voice_revision_id prevent deletion via ON DELETE RESTRICT."""
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "fk_test.db")
            database.initialize()
            
            now = utcnow()
            with database.connect() as connection:
                # Create custom voice and revision
                custom_voice_id = connection.execute(
                    "INSERT INTO custom_voices(display_name,created_at,updated_at) VALUES(?,?,?)",
                    ("Test Voice", now, now),
                ).lastrowid
                revision_id = connection.execute(
                    """INSERT INTO custom_voice_revisions(
                        custom_voice_id,revision_number,audio_storage_key,audio_sha256,
                        reference_transcript,transcript_sha256,duration_ms,sample_rate,
                        channels,audio_format,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (custom_voice_id, 1, "key", "audio-sha", "transcript", "trans-sha", 1000, 16000, 1, "wav", now),
                ).lastrowid
                
                # Create book, chapter, job, job_chapter
                book_id = connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Book", "book.epub", "book-sha", now, now),
                ).lastrowid
                chapter_id = connection.execute(
                    "INSERT INTO chapters(book_id,chapter_number,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (book_id, 1, "Chapter 1", now, now),
                ).lastrowid
                job_id = connection.execute(
                    """INSERT INTO jobs(
                        book_id,status,from_chapter,to_chapter,voice_name,repair_mode,
                        output_format,settings_json,total_chapters,scheduled_at,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (book_id, "pending", 1, 1, "default", "auto", "mp3", "{}", 1, now, now, now),
                ).lastrowid
                job_chapter_id = connection.execute(
                    "INSERT INTO job_chapters(job_id,chapter_id,sequence,status) VALUES(?,?,?,?)",
                    (job_id, chapter_id, 1, "pending"),
                ).lastrowid
                
                # Create segment with snapshot referencing custom_voice_revision_id
                connection.execute(
                    """INSERT INTO segments(
                        job_chapter_id,segment_index,text_path,text_sha256,status,attempt_count,
                        created_at,utterance_sequence,custom_voice_revision_id,voice_snapshot_version
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (job_chapter_id, 0, "seg.txt", "seg-sha", "pending", 0, now, 0, revision_id, 1),
                )
                connection.commit()
                
                # Attempt to delete the custom_voice_revision should fail
                with self.assertRaises(sqlite3.IntegrityError) as ctx:
                    connection.execute("DELETE FROM custom_voice_revisions WHERE id=?", (revision_id,))
                self.assertIn("FOREIGN KEY constraint failed", str(ctx.exception))

    def test_v7_casting_plan_fk_restriction_prevents_deletion(self) -> None:
        """Attempting to delete a referenced casting_plan raises IntegrityError due to ON DELETE RESTRICT."""
        import tempfile
        from pathlib import Path
        import sqlite3
        from story_audio.db import Database, utcnow
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "restrict_test.db")
            database.initialize()
            
            now = utcnow()
            with database.connect() as connection:
                book_id = connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Book", "book.epub", "book-sha", now, now),
                ).lastrowid
                chapter_id = connection.execute(
                    "INSERT INTO chapters(book_id,chapter_number,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (book_id, 1, "Chapter 1", now, now),
                ).lastrowid
                text_rev_id = connection.execute(
                    "INSERT INTO text_revisions(chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,processor_version,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (chapter_id, "original", "text.txt", "text-sha", "lexical-sha", 100, "1.0", "valid", now),
                ).lastrowid
                
                plan_id = connection.execute(
                    "INSERT INTO casting_plans(chapter_id,text_revision_id,plan_revision,status,content_path,plan_sha256,narrator_voice_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (chapter_id, text_rev_id, 1, "approved", "plan.json", "plan-sha", "narrator-voice", now),
                ).lastrowid
                
                job_id = connection.execute(
                    "INSERT INTO jobs(book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,settings_json,total_chapters,scheduled_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (book_id, "pending", 1, 1, "default", "auto", "mp3", "{}", 1, now, now, now),
                ).lastrowid
                job_chapter_id = connection.execute(
                    "INSERT INTO job_chapters(job_id,chapter_id,sequence,status) VALUES(?,?,?,?)",
                    (job_id, chapter_id, 1, "pending"),
                ).lastrowid
                
                segment_id = connection.execute(
                    "INSERT INTO segments(job_chapter_id,segment_index,text_path,text_sha256,status,attempt_count,created_at,utterance_sequence,casting_plan_id,voice_snapshot_version) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (job_chapter_id, 0, "seg.txt", "seg-sha", "pending", 0, now, 0, plan_id, 1),
                ).lastrowid
                connection.commit()
                
                # Attempt to delete casting_plan should fail
                with self.assertRaises(sqlite3.IntegrityError) as ctx:
                    connection.execute("DELETE FROM casting_plans WHERE id=?", (plan_id,))
                self.assertIn("FOREIGN KEY constraint failed", str(ctx.exception))
                
                # Verify both rows still exist
                plan = connection.execute("SELECT id FROM casting_plans WHERE id=?", (plan_id,)).fetchone()
                self.assertIsNotNone(plan)
                segment = connection.execute("SELECT casting_plan_id FROM segments WHERE id=?", (segment_id,)).fetchone()
                self.assertEqual(segment[0], plan_id)

