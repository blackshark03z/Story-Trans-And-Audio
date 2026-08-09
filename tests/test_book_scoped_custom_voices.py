from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from starlette.datastructures import UploadFile

from story_audio.custom_voice import CustomVoiceError, CustomVoiceRepository
from story_audio.custom_voice_api import (
    build_voice_catalog_handler,
    create_book_custom_voice_handler,
    list_custom_voices_handler,
)
from story_audio.db import Database, utcnow
from story_audio.migrations import MigrationRunner, RUNTIME_MIGRATIONS
from story_audio.pipeline import PipelineWorker
from story_audio.storage import ContentStore
from story_audio.voice_ref import CustomVoiceContext, resolve_custom_ref


class BookScopedCustomVoiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._testing = os.environ.get("STORY_AUDIO_TESTING")
        os.environ["STORY_AUDIO_TESTING"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.db = Database(self.root / "app.db", migration_runner=MigrationRunner(RUNTIME_MIGRATIONS))
        self.db.initialize()
        self.repo = CustomVoiceRepository(self.db, ContentStore(_settings_for(self.root)))
        self.book_a = _create_book(self.db, "Book A")
        self.book_b = _create_book(self.db, "Book B")

    def tearDown(self) -> None:
        self._tmp.cleanup()
        if self._testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._testing

    def test_new_voice_is_owned_by_one_book_and_has_a_sample(self) -> None:
        voice, revision = self.repo.create_custom_voice_with_revision(
            self.book_a, "Book A Narrator", b"reference-audio", "Exact reference words"
        )

        self.assertEqual(voice.book_id, self.book_a)
        self.assertEqual(revision.custom_voice_id, voice.id)
        self.assertEqual([item.id for item in self.repo.list_custom_voices(book_id=self.book_a)], [voice.id])
        self.assertEqual(self.repo.list_custom_voices(book_id=self.book_b), [])

    def test_handler_requires_sample_and_never_crosses_book_library(self) -> None:
        upload = UploadFile(filename="sample.wav", file=io.BytesIO(b"sample-audio"))
        result = create_book_custom_voice_handler(
            self.repo, self.book_a, "Book A Voice", upload, "A valid transcript"
        )

        self.assertEqual(result["book_id"], self.book_a)
        self.assertEqual(result["initial_revision"]["revision_number"], 1)
        self.assertEqual(
            [item["id"] for item in list_custom_voices_handler(self.repo, book_id=self.book_a)],
            [result["id"]],
        )
        self.assertEqual(list_custom_voices_handler(self.repo, book_id=self.book_b), [])

    def test_failed_first_revision_removes_only_the_unreferenced_new_voice(self) -> None:
        with self.assertRaises(CustomVoiceError):
            self.repo.create_custom_voice_with_revision(
                self.book_a, "Rejected Voice", b"", "A transcript"
            )
        self.assertEqual(self.repo.list_custom_voices(book_id=self.book_a), [])

    def test_unknown_book_is_rejected(self) -> None:
        with self.assertRaises(CustomVoiceError):
            self.repo.create_custom_voice_with_revision(
                999999, "Unknown Book Voice", b"sample", "A transcript"
            )

    def test_schema16_rejects_new_unowned_voice_and_unscoped_catalog_leaks_none(self) -> None:
        with self.assertRaises(CustomVoiceError):
            self.repo.create_custom_voice("No Owner")
        voice, _ = self.repo.create_custom_voice_with_revision(
            self.book_a, "Book A Only", b"sample-audio", "A transcript"
        )
        self.assertEqual(self.repo.list_custom_voices(), [])
        catalog = build_voice_catalog_handler(self.repo, [], book_id=self.book_b)
        self.assertNotIn(f"custom:{voice.id}", {item["assignment_key"] for item in catalog["items"]})

    def test_effective_catalog_merges_legacy_with_only_the_selected_book(self) -> None:
        voice_a, _ = self.repo.create_custom_voice_with_revision(
            self.book_a, "Book A Catalog Voice", b"sample-a", "Book A transcript"
        )
        voice_b, _ = self.repo.create_custom_voice_with_revision(
            self.book_b, "Book B Catalog Voice", b"sample-b", "Book B transcript"
        )
        now = utcnow()
        with self.db.transaction() as conn:
            legacy_id = int(conn.execute(
                """INSERT INTO custom_voices(
                    book_id,display_name,description,is_active,created_at,updated_at
                ) VALUES(NULL,?,?,1,?,?)""",
                ("Legacy Catalog Voice", "schema-15 compatibility", now, now),
            ).lastrowid)
            conn.execute(
                """INSERT INTO custom_voice_revisions(
                    custom_voice_id,revision_number,audio_storage_key,audio_sha256,
                    reference_transcript,transcript_sha256,duration_ms,sample_rate,
                    channels,audio_format,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (legacy_id, 1, "audio/custom_voices/legacy.wav", "a" * 64,
                 "Legacy transcript", "b" * 64, 1000, 48000, 2, "wav", now),
            )

        keys_a = {
            item["assignment_key"]
            for item in build_voice_catalog_handler(self.repo, [], book_id=self.book_a)["items"]
        }
        keys_b = {
            item["assignment_key"]
            for item in build_voice_catalog_handler(self.repo, [], book_id=self.book_b)["items"]
        }
        self.assertEqual(keys_a, {f"custom:{legacy_id}", f"custom:{voice_a.id}"})
        self.assertEqual(keys_b, {f"custom:{legacy_id}", f"custom:{voice_b.id}"})

    def test_worker_cache_is_keyed_by_book_and_keeps_legacy_available(self) -> None:
        voice_a, _ = self.repo.create_custom_voice_with_revision(
            self.book_a, "Book A Worker Voice", b"sample-a", "Book A transcript"
        )
        voice_b, _ = self.repo.create_custom_voice_with_revision(
            self.book_b, "Book B Worker Voice", b"sample-b", "Book B transcript"
        )
        now = utcnow()
        with self.db.transaction() as conn:
            legacy_id = int(conn.execute(
                "INSERT INTO custom_voices(book_id,display_name,description,is_active,created_at,updated_at) VALUES(NULL,?,?,1,?,?)",
                ("Legacy Worker Voice", "schema-15 compatibility", now, now),
            ).lastrowid)
            conn.execute(
                """INSERT INTO custom_voice_revisions(
                    custom_voice_id,revision_number,audio_storage_key,audio_sha256,
                    reference_transcript,transcript_sha256,duration_ms,sample_rate,
                    channels,audio_format,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (legacy_id, 1, "audio/custom_voices/legacy.wav", "a" * 64,
                 "Legacy transcript", "b" * 64, 1000, 48000, 2, "wav", now),
            )

        worker = PipelineWorker.__new__(PipelineWorker)
        worker.db = self.db
        worker.store = self.repo.store
        context_a = worker._custom_voice_context_for_book(self.book_a)
        context_b = worker._custom_voice_context_for_book(self.book_b)
        self.assertIsNotNone(context_a.get(voice_a.id))
        self.assertIsNone(context_a.get(voice_b.id))
        self.assertIsNotNone(context_b.get(voice_b.id))
        self.assertIsNone(context_b.get(voice_a.id))
        self.assertIsNotNone(context_a.get(legacy_id))
        self.assertIsNotNone(context_b.get(legacy_id))
        self.assertIs(worker._custom_voice_context_for_book(self.book_a), context_a)
        self.assertIs(worker._custom_voice_context_for_book(self.book_b), context_b)

    def test_browser_acceptance_rejects_canonical_url_before_mutation(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is unavailable")
        result = subprocess.run(
            [node, "scripts/browser_book_custom_voice_acceptance.mjs", "--self-check-canonical-url"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Refusing canonical Story Audio runtime", result.stdout)


class BookScopedCustomVoiceMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._testing = os.environ.get("STORY_AUDIO_TESTING")
        os.environ["STORY_AUDIO_TESTING"] = "1"

    def tearDown(self) -> None:
        if self._testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._testing

    def test_forward_migration_preserves_legacy_identifier_and_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy-v15.db"
            before = Database(
                path,
                migration_runner=MigrationRunner(RUNTIME_MIGRATIONS[:-1]),
            )
            self.assertEqual(before.initialize(), 15)
            timestamp = utcnow()
            with before.transaction() as conn:
                book_id = conn.execute(
                    "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Historical Book", "historical.epub", "historical-sha", timestamp, timestamp),
                ).lastrowid
                voice_id = conn.execute(
                    "INSERT INTO custom_voices(display_name,description,is_active,created_at,updated_at) VALUES(?,?,?,?,?)",
                    ("Historical Voice", "kept for provenance", 1, timestamp, timestamp),
                ).lastrowid
                revision_id = conn.execute(
                    """INSERT INTO custom_voice_revisions(
                        custom_voice_id,revision_number,audio_storage_key,audio_sha256,
                        reference_transcript,transcript_sha256,duration_ms,sample_rate,
                        channels,audio_format,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (voice_id, 1, "audio/custom_voices/aa/legacy.wav", "a" * 64,
                     "Historical words", "b" * 64, 1000, 48000, 2, "wav", timestamp),
                ).lastrowid

            after = Database(path, migration_runner=MigrationRunner(RUNTIME_MIGRATIONS))
            self.assertEqual(after.initialize(), 16)
            repo = CustomVoiceRepository(after, ContentStore(_settings_for(Path(directory))))
            legacy = repo.get_custom_voice(int(voice_id))
            self.assertIsNone(legacy.book_id)
            resolved = resolve_custom_ref(
                f"custom:{voice_id}", CustomVoiceContext.from_repository(repo), repository=repo
            )
            self.assertEqual(resolved["custom_voice_revision_id"], revision_id)
            self.assertEqual(after.fetch_one("SELECT id FROM books WHERE id=?", (book_id,))["id"], book_id)


def _settings_for(root: Path):
    from dataclasses import replace
    from story_audio.config import settings

    configured = replace(
        settings,
        root=root,
        data_dir=root / "data",
        db_path=root / "app.db",
        blobs_dir=root / "data" / "blobs",
        output_dir=root / "data" / "output",
        work_dir=root / "data" / "work",
        log_dir=root / "logs",
    )
    configured.ensure_dirs()
    return configured


def _create_book(db: Database, title: str) -> int:
    timestamp = utcnow()
    with db.transaction() as conn:
        return int(conn.execute(
            "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
            (title, f"{title}.epub", f"{title}-sha", timestamp, timestamp),
        ).lastrowid)
