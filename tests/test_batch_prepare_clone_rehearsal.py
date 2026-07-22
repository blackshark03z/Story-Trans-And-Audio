from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from story_audio.batch_prepare_clone_rehearsal import (
    ClonePathRejected,
    collect_database_facts,
    create_external_clone,
    validate_canonical_source,
    validate_external_destination,
)
from story_audio.db import Database
from tests.base import IsolatedTestCase


class CloneRehearsalTests(IsolatedTestCase):
    def _source(self) -> Path:
        source = self.config.db_path
        Database(source).initialize()
        connection = sqlite3.connect(source)
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.execute("PRAGMA journal_mode=DELETE")
        finally:
            connection.close()
        return source

    def test_online_backup_preserves_source_and_logical_baseline(self) -> None:
        source = self._source()
        root = self.temp_root / "external"
        clone = root / "run" / "clone.db"
        before = collect_database_facts(source)

        evidence = create_external_clone(
            source,
            clone,
            canonical_path=source,
            allowed_external_root=root,
        )

        after = collect_database_facts(source)
        self.assertTrue(evidence.source_unchanged)
        self.assertEqual(before, after)
        self.assertFalse(source.with_name(source.name + "-wal").exists())
        self.assertFalse(source.with_name(source.name + "-shm").exists())
        self.assertEqual(evidence.clone.schema_version, 12)
        self.assertEqual(evidence.clone.counts, before.counts)
        self.assertEqual(evidence.clone.chapter_369, before.chapter_369)
        self.assertEqual(evidence.clone.plan_369, before.plan_369)

    def test_source_and_destination_guards_fail_closed(self) -> None:
        source = self._source()
        root = self.temp_root / "external"
        with self.assertRaises(ClonePathRejected):
            validate_canonical_source(self.temp_root / "not-the-source.db", canonical_path=source)
        with self.assertRaises(ClonePathRejected):
            validate_external_destination(self.temp_root / "outside.db", allowed_external_root=root)
        with self.assertRaises(ClonePathRejected):
            validate_external_destination(
                Path.cwd() / "phase12-forbidden.db",
                allowed_external_root=root,
            )

    def test_clone_destination_must_be_new_and_external(self) -> None:
        source = self._source()
        root = self.temp_root / "external"
        clone = root / "clone.db"
        create_external_clone(source, clone, canonical_path=source, allowed_external_root=root)
        with self.assertRaises(ClonePathRejected):
            create_external_clone(source, clone, canonical_path=source, allowed_external_root=root)


if __name__ == "__main__":
    unittest.main()
