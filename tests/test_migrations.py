from __future__ import annotations

import sqlite3
import tempfile
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
                        "synthesizing",
                        1,
                        1,
                        "Voice",
                        "off",
                        "m4a",
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
            self.assertEqual(database.schema_version(), LATEST_SCHEMA_VERSION)
            self.assertEqual(
                database.fetch_one("SELECT title FROM books WHERE source_sha256='legacy-sha'")["title"],
                "Legacy Book",
            )
            job = database.fetch_one("SELECT status,current_stage FROM jobs")
            self.assertEqual(job["status"], "interrupted")
            self.assertEqual(job["current_stage"], "recovery")
            applied = database.fetch_all("SELECT version FROM schema_migrations")
            self.assertEqual([row["version"] for row in applied], list(range(1, LATEST_SCHEMA_VERSION + 1)))

    def test_version_one_upgrades_to_character_voice_schema_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v1.db"
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            try:
                connection.executescript(MIGRATIONS[0].sql)
                now = utcnow()
                book_id = connection.execute(
                    "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Book", "book.epub", "sha-v1", now, now),
                ).lastrowid
                connection.execute(
                    "INSERT INTO chapters(book_id,chapter_number,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (book_id, 1, "Chapter", now, now),
                )
                connection.execute(
                    "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,name TEXT,checksum TEXT,applied_at TEXT)"
                )
                connection.execute(
                    "INSERT INTO schema_migrations VALUES(1,?,?,?)",
                    (MIGRATIONS[0].name, MIGRATIONS[0].checksum, now),
                )
                connection.commit()
            finally:
                connection.close()
            database = Database(path)
            self.assertEqual(database.initialize(), LATEST_SCHEMA_VERSION)
            self.assertEqual(database.fetch_one("SELECT COUNT(*) AS n FROM books")["n"], 1)
            self.assertEqual(database.fetch_one("SELECT COUNT(*) AS n FROM chapters")["n"], 1)
            columns = {row["name"] for row in database.fetch_all("PRAGMA table_info(segments)")}
            self.assertIn("resolved_voice_id", columns)

    def test_version_two_migrates_existing_character_voice_to_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v2.db"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(MIGRATIONS[0].sql)
                connection.executescript(MIGRATIONS[1].sql)
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


if __name__ == "__main__":
    unittest.main()
