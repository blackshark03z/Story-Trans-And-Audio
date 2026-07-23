from __future__ import annotations

import hashlib
import inspect
import shutil
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from story_audio.batch_prepare_clone_rehearsal import apply_dormant_migration
from story_audio.batch_prepare_runtime_integration import (
    CLONE_DISABLED,
    CloneReadOnlyDatabase,
    CloneRuntimeRejected,
    build_runtime_integration,
    parse_runtime_integration_config,
    public_runtime_readiness,
    require_clone_runtime,
)
from story_audio.db import Database
from tests.base import IsolatedTestCase


class RuntimeIntegrationTests(IsolatedTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def setUp(self):
        super().setUp()
        self.external = self.temp_root / "external"
        self.external.mkdir()
        source = self.temp_root / "source" / "app.db"
        Database(source).initialize()
        self.clone = self.external / "app.db"
        shutil.copyfile(source, self.clone)
        apply_dormant_migration(self.clone, 13)
        apply_dormant_migration(self.clone, 14)
        apply_dormant_migration(self.clone, 15)
        self.values = {
            "PREPARE_RUNTIME_MODE": CLONE_DISABLED,
            "PREPARE_KILL_SWITCH_ACTIVE": "true",
        }

    def test_default_is_disabled_and_kill_switched(self):
        descriptor = build_runtime_integration(
            {}, db_path=Path.cwd() / "data" / "app.db",
            repository_root=Path.cwd(), canonical_db_path=Path.cwd() / "data" / "app.db",
        )
        self.assertEqual(descriptor.runtime_mode, "DISABLED")
        self.assertTrue(descriptor.kill_switch_active)
        self.assertFalse(descriptor.mutation_authorized)

    def test_schema15_clone_is_readiness_eligible_but_mutation_disabled(self):
        descriptor = self.descriptor()
        self.assertEqual(descriptor.status, "KILL_SWITCHED")
        self.assertEqual(descriptor.schema_version, 15)
        self.assertTrue(descriptor.clone_runtime_active)
        self.assertFalse(descriptor.mutation_service_constructed)
        self.assertFalse(descriptor.mutation_enabled)

    def test_all_flags_and_auth_still_cannot_enable_mutation(self):
        token_hash = hashlib.sha256(b"synthetic").hexdigest()
        values = {
            "PREPARE_RUNTIME_MODE": CLONE_DISABLED,
            "PREPARE_FEATURE_AVAILABLE": "true",
            "PREPARE_MUTATION_ENABLED": "true",
            "PREPARE_OPERATOR_WINDOW_OPEN": "true",
            "PREPARE_CANONICAL_SCHEMA_READY": "true",
            "PREPARE_KILL_SWITCH_ACTIVE": "false",
            "PREPARE_OPERATOR_AUTH_ENABLED": "true",
            "PREPARE_OPERATOR_ID": "operator.test",
            "PREPARE_OPERATOR_TOKEN_SHA256": token_hash,
        }
        descriptor = self.descriptor(values)
        self.assertEqual(descriptor.status, "CLONE_DISABLED_READY")
        self.assertFalse(descriptor.mutation_enabled)
        self.assertFalse(descriptor.mutation_authorized)
        self.assertFalse(descriptor.execution_endpoint_available)

    def test_missing_auth_blocks_production_when_other_flags_are_open(self):
        values = {
            "PREPARE_RUNTIME_MODE": CLONE_DISABLED,
            "PREPARE_FEATURE_AVAILABLE": "true",
            "PREPARE_MUTATION_ENABLED": "true",
            "PREPARE_OPERATOR_WINDOW_OPEN": "true",
            "PREPARE_CANONICAL_SCHEMA_READY": "true",
            "PREPARE_KILL_SWITCH_ACTIVE": "false",
        }
        descriptor = self.descriptor(values)
        self.assertEqual(descriptor.status, "AUTH_NOT_READY")
        self.assertTrue(descriptor.clone_runtime_active)
        self.assertFalse(descriptor.mutation_authorized)

    def test_dependency_factories_are_never_constructed(self):
        calls = []
        self.descriptor(db_factory=lambda: calls.append("db"), adapter_factory=lambda: calls.append("adapter"))
        self.assertEqual(calls, [])

    def descriptor(self, values=None, path=None, **factories):
        return build_runtime_integration(
            self.values if values is None else values,
            db_path=self.clone if path is None else path,
            repository_root=Path.cwd(),
            canonical_db_path=Path.cwd() / "data" / "app.db",
            **factories,
        )

    def test_invalid_mode_and_unknown_flag_fail_closed(self):
        invalid = parse_runtime_integration_config({"PREPARE_RUNTIME_MODE": "UNKNOWN"})
        self.assertFalse(invalid.config_valid)
        descriptor = self.descriptor({"PREPARE_RUNTIME_MODE": "UNKNOWN"})
        self.assertEqual(descriptor.status, "CONFIG_INVALID")
        unknown = self.descriptor({"PREPARE_RUNTIME_MODE": CLONE_DISABLED, "PREPARE_MUTATION_ENABLED": "maybe"})
        self.assertEqual(unknown.status, "CONFIG_INVALID")

    def test_missing_canonical_and_repository_paths_are_rejected(self):
        missing = self.descriptor(path=self.external / "missing.db")
        self.assertEqual(missing.status, "CLONE_MISSING")
        canonical = self.descriptor(path=Path.cwd() / "data" / "app.db")
        self.assertEqual(canonical.status, "UNSAFE_CLONE_PATH")
        repository = self.descriptor(path=Path.cwd() / "phase13.db")
        self.assertEqual(repository.status, "UNSAFE_CLONE_PATH")

    def test_schema12_14_and_future_schema_fail_closed(self):
        source = self.temp_root / "source" / "app.db"
        schema12 = self.external / "schema12.db"
        shutil.copyfile(source, schema12)
        self.assertEqual(self.descriptor(path=schema12).schema_version, 12)
        schema14 = self.external / "schema14.db"
        shutil.copyfile(source, schema14)
        apply_dormant_migration(schema14, 13)
        apply_dormant_migration(schema14, 14)
        self.assertEqual(self.descriptor(path=schema14).schema_version, 14)
        future = self.external / "future.db"
        shutil.copyfile(self.clone, future)
        connection = sqlite3.connect(future)
        connection.execute(
            "INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES(16,'future',?,?)",
            ("0" * 64, "test"),
        )
        connection.commit()
        connection.close()
        self.assertEqual(self.descriptor(path=future).status, "KILL_SWITCHED")
        values = dict(self.values, PREPARE_KILL_SWITCH_ACTIVE="false")
        self.assertEqual(self.descriptor(values, future).status, "SCHEMA_UNSUPPORTED")

    def test_quick_check_failure_is_rejected(self):
        with patch(
            "story_audio.batch_prepare_runtime_integration._inspect_clone",
            return_value=(15, "corrupt"),
        ):
            descriptor = self.descriptor(dict(self.values, PREPARE_KILL_SWITCH_ACTIVE="false"))
        self.assertEqual(descriptor.status, "QUICK_CHECK_FAILED")
        with self.assertRaises(CloneRuntimeRejected):
            require_clone_runtime(descriptor)

    def test_readiness_payload_is_bounded_and_safe(self):
        payload = public_runtime_readiness(self.descriptor())
        rendered = repr(payload)
        for forbidden in (str(self.clone), "token_sha256", "environment", "traceback", "SELECT"):
            self.assertNotIn(forbidden, rendered)
        for field in (
            "mutation_service_constructed", "mutation_route_registered", "mutation_authorized",
            "execution_endpoint_available", "real_job_execution", "prepare_starts_render",
        ):
            self.assertFalse(payload[field])

    def test_read_only_facade_cannot_write_initialize_transact_or_audit(self):
        before = hashlib.sha256(self.clone.read_bytes()).hexdigest()
        database = CloneReadOnlyDatabase(self.clone)
        self.assertEqual(database.schema_version(), 15)
        self.assertEqual(database.fetch_one("SELECT COUNT(*) n FROM jobs")["n"], 0)
        with database.connect() as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("INSERT INTO books(title,created_at) VALUES('blocked','now')")
        for operation in (database.initialize, database.transaction, lambda: database.audit("blocked")):
            with self.assertRaises(CloneRuntimeRejected):
                operation()
        self.assertEqual(hashlib.sha256(self.clone.read_bytes()).hexdigest(), before)
        self.assertFalse(Path(str(self.clone) + "-wal").exists())
        self.assertFalse(Path(str(self.clone) + "-shm").exists())

    def test_invalid_clone_runtime_cannot_start(self):
        with self.assertRaises(CloneRuntimeRejected):
            require_clone_runtime(self.descriptor(path=self.external / "missing.db"))

    def test_module_has_no_adapter_pipeline_or_provider_dependency(self):
        import story_audio.batch_prepare_runtime_integration as module

        source = inspect.getsource(module)
        for forbidden in (
            "batch_prepare_isolated_adapter", "prepare_job(", "create_job(", "worker.wake(",
            "Gemini", "tts_service",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
