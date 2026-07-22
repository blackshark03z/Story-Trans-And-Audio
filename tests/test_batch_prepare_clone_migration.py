from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from story_audio.batch_prepare_clone_rehearsal import (
    CloneMigrationError,
    apply_dormant_migration,
    collect_database_facts,
    create_external_clone,
    migration_hashes,
    migrate_clone,
    validate_migrated_clone,
)
from story_audio.db import Database
from tests.base import IsolatedTestCase


class CloneMigrationTests(IsolatedTestCase):
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

    def _clone(self, source: Path, root: Path, name: str) -> Path:
        clone = root / f"{name}.db"
        create_external_clone(source, clone, canonical_path=source, allowed_external_root=root)
        return clone

    def test_explicit_dormant_chain_reaches_schema_15_with_objects_and_invariants(self) -> None:
        source = self._source()
        root = self.temp_root / "external"
        clone = self._clone(source, root, "valid")
        baseline = collect_database_facts(clone)

        run = migrate_clone(clone)

        self.assertEqual(run.applied_versions, (13, 14, 15))
        self.assertEqual([stage.version for stage in run.stages], [13, 14, 15])
        self.assertEqual(set(migration_hashes()), {13, 14, 15})
        self.assertEqual(run.final_facts.schema_version, 15)
        self.assertEqual(run.final_facts.foreign_key_check, "ok")
        self.assertTrue(run.postflight["valid"])
        self.assertTrue(set(("batch_prepare_requests", "batch_prepare_job_links", "batch_prepare_execution_attempts"))
                        .issubset(set(run.final_facts.tables)))
        self.assertEqual(run.final_facts.counts, baseline.counts)
        self.assertEqual(run.final_facts.dormant_row_counts,
                         {"batch_prepare_requests": 0, "batch_prepare_job_links": 0,
                          "batch_prepare_execution_attempts": 0})
        self.assertTrue(validate_migrated_clone(baseline, run.final_facts, migrated_path=clone)["valid"])

    def test_each_stage_failure_rolls_back_only_its_transaction(self) -> None:
        source = self._source()
        root = self.temp_root / "external"
        for version, predecessor in ((13, 12), (14, 13), (15, 14)):
            clone = self._clone(source, root, f"failure-{version}")
            for prior in range(13, version):
                apply_dormant_migration(clone, prior)
            with self.assertRaises(CloneMigrationError):
                apply_dormant_migration(clone, version, fail_after_statement=1)
            facts = collect_database_facts(clone)
            self.assertEqual(facts.schema_version, predecessor)
            self.assertEqual(facts.quick_check, "ok")
            self.assertEqual(facts.foreign_key_check, "ok")
            self.assertEqual(facts.dormant_row_counts.get("batch_prepare_requests", 0), 0)


if __name__ == "__main__":
    unittest.main()
