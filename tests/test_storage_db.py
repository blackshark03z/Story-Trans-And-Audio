from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from story_audio.config import settings
from story_audio.db import Database
from story_audio.storage import ContentStore


class StorageDatabaseTests(unittest.TestCase):
    def test_content_store_is_addressed_by_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                settings,
                root=root,
                data_dir=root / "data",
                db_path=root / "data" / "app.db",
                blobs_dir=root / "data" / "blobs",
                output_dir=root / "data" / "output",
                work_dir=root / "data" / "work",
                log_dir=root / "logs",
            )
            config.ensure_dirs()
            store = ContentStore(config)
            first_path, first_hash = store.put_text("Nội dung")
            second_path, second_hash = store.put_text("Nội dung")
            self.assertEqual((first_path, first_hash), (second_path, second_hash))
            self.assertEqual(store.read_text(first_path), "Nội dung")

    def test_database_initializes_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "app.db")
            db.initialize()
            tables = {row["name"] for row in db.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"books", "chapters", "text_revisions", "jobs", "segments", "artifacts"}.issubset(tables))


if __name__ == "__main__":
    unittest.main()
