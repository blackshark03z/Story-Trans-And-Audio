from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from story_audio.batch_prepare_clone_rehearsal import (
    collect_database_facts,
    create_clone_backup,
    create_external_clone,
    migrate_clone,
    restore_clone_backup,
)
from story_audio.db import Database
from tests.base import IsolatedTestCase


class CloneRollbackTests(IsolatedTestCase):
    def test_migrated_clone_restores_exact_backup_and_archives_sidecars(self) -> None:
        source = self.config.db_path
        Database(source).initialize()
        connection = sqlite3.connect(source)
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.execute("PRAGMA journal_mode=DELETE")
        finally:
            connection.close()
        root = self.temp_root / "external"
        clone = root / "run" / "clone.db"
        backup = root / "run" / "pre_migration.db"
        archive = root / "run" / "failed_clone.db"
        create_external_clone(source, clone, canonical_path=source, allowed_external_root=root)
        backup_evidence = create_clone_backup(clone, backup, allowed_external_root=root)
        migrate_clone(clone)
        clone.with_name(clone.name + "-wal").write_bytes(b"stale wal sidecar")
        clone.with_name(clone.name + "-shm").write_bytes(b"stale shm sidecar")

        evidence = restore_clone_backup(clone, backup, archive=archive, allowed_external_root=root)

        self.assertTrue(backup_evidence.exact_hash_match)
        self.assertTrue(evidence.exact_backup_hash_restored)
        self.assertFalse(evidence.already_restored)
        self.assertTrue(evidence.logical_baseline_restored)
        self.assertEqual(evidence.restored_schema, 12)
        self.assertEqual(set(evidence.sidecars_archived), {"failed_clone.db-wal", "failed_clone.db-shm"})
        self.assertEqual(collect_database_facts(clone).sha256, backup_evidence.backup.sha256)
        self.assertTrue(archive.is_file())
        self.assertFalse(clone.with_name(clone.name + "-wal").exists())
        self.assertFalse(clone.with_name(clone.name + "-shm").exists())

        repeated = restore_clone_backup(clone, backup, allowed_external_root=root)
        self.assertTrue(repeated.already_restored)
        self.assertTrue(repeated.exact_backup_hash_restored)


if __name__ == "__main__":
    unittest.main()
