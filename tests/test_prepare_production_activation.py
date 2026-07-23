from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from story_audio.batch_prepare_clone_api import build_prepare_api_service
from story_audio.batch_prepare_runtime_integration import (
    PRODUCTION,
    build_runtime_integration,
    parse_runtime_integration_config,
    public_runtime_readiness,
)
from story_audio.batch_prepare_schema import (
    PREPARE_MIGRATION_HASHES,
    prepare_migration_runner,
    verified_prepare_migration_hashes,
)
from story_audio.db import Database
from story_audio.prepare_activation import (
    ACTIVATION_CONFIRMATION,
    PrepareActivationError,
    execute_migration,
    run_preflight,
)
from tests.base import IsolatedTestCase
from tests.batch_prepare_phase10_fixture import Phase10FixtureMixin


TOKEN = "production-prepare-synthetic-token"


def production_values(**overrides):
    values = {
        "PREPARE_RUNTIME_MODE": PRODUCTION,
        "PREPARE_FEATURE_AVAILABLE": "true",
        "PREPARE_MUTATION_ENABLED": "true",
        "PREPARE_OPERATOR_WINDOW_OPEN": "true",
        "PREPARE_CANONICAL_SCHEMA_READY": "true",
        "PREPARE_KILL_SWITCH_ACTIVE": "false",
        "PREPARE_OPERATOR_AUTH_ENABLED": "true",
        "PREPARE_OPERATOR_ID": "operator.production",
        "PREPARE_OPERATOR_TOKEN_SHA256": hashlib.sha256(TOKEN.encode()).hexdigest(),
        "PREPARE_OPERATOR_TOKEN_VERSION": "production-v1",
        "PREPARE_OPERATOR_AUTH_LOCAL_TEST_MODE": "false",
    }
    values.update(overrides)
    return values


class ProductionRuntimeGateTests(Phase10FixtureMixin):
    def descriptor(self, values=None, path=None):
        target = path or self.db_path
        return build_runtime_integration(
            values or production_values(),
            db_path=target,
            repository_root=self.config.root / "repository-sentinel",
            canonical_db_path=target,
        )

    def test_schema15_production_constructs_same_authenticated_prepare_service(self):
        config = parse_runtime_integration_config(production_values())
        descriptor = self.descriptor(config)
        self.assertEqual(descriptor.status, "PRODUCTION_AUTHENTICATED_READY")
        self.assertTrue(descriptor.production_mutation_enabled)
        with (
            patch(
                "story_audio.batch_prepare_transaction_manager.canonical_production_db_path",
                return_value=self.db_path,
            ),
            patch(
                "story_audio.batch_prepare_isolated_adapter.canonical_production_db_path",
                return_value=self.db_path,
            ),
        ):
            service = build_prepare_api_service(
                settings=self.config,
                config=config,
                descriptor=descriptor,
            )
            self.assertIsNotNone(service)
            plan = self.plan()
            scope = plan["scope"]
            payload = {
                "client_request_id": "production-smoke-request",
                "book_id": scope["book_id"],
                "from_chapter": scope["from_chapter"],
                "to_chapter": scope["to_chapter"],
                "target_phase": "PREPARE",
                "plan_fingerprint": plan["plan_fingerprint"],
                "confirmation": True,
            }
            result = service.prepare(
                payload,
                authorization_header=f"Bearer {TOKEN}",
            )
            replay = service.prepare(
                payload,
                authorization_header=f"Bearer {TOKEN}",
            )
        self.assertEqual(result.http_status, 200)
        self.assertEqual(replay.http_status, 200)
        self.assertEqual(replay.payload["status"], "APPLIED_REPLAYED")
        self.assertTrue(replay.payload["replay"])
        self.assertEqual(replay.payload["job_id"], result.payload["job_id"])
        self.assertEqual(self.counts()["batch_prepare_requests"], 1)
        self.assertEqual(self.counts()["batch_prepare_execution_attempts"], 1)
        self.assertEqual(self.counts()["batch_prepare_job_links"], 1)
        self.assertEqual(self.counts()["jobs"], 1)
        self.assertEqual(self.counts()["job_chapters"], 2)
        self.assertEqual(self.counts()["segments"], 0)
        self.assertEqual(self.counts()["artifacts"], 0)

    def test_production_canary_rejects_more_than_three_chapters_without_rows(self):
        config = parse_runtime_integration_config(production_values())
        descriptor = self.descriptor(config)
        with (
            patch(
                "story_audio.batch_prepare_transaction_manager.canonical_production_db_path",
                return_value=self.db_path,
            ),
            patch(
                "story_audio.batch_prepare_isolated_adapter.canonical_production_db_path",
                return_value=self.db_path,
            ),
        ):
            service = build_prepare_api_service(
                settings=self.config,
                config=config,
                descriptor=descriptor,
            )
            plan = self.plan(from_chapter=10, to_chapter=13)
            scope = plan["scope"]
            with self.assertRaisesRegex(Exception, "one through three"):
                service.prepare(
                    {
                        "client_request_id": "production-oversized-canary",
                        "book_id": scope["book_id"],
                        "from_chapter": scope["from_chapter"],
                        "to_chapter": scope["to_chapter"],
                        "target_phase": "PREPARE",
                        "plan_fingerprint": plan["plan_fingerprint"],
                        "confirmation": True,
                    },
                    authorization_header=f"Bearer {TOKEN}",
                )
        self.assertEqual(self.counts()["batch_prepare_requests"], 0)
        self.assertEqual(self.counts()["jobs"], 0)

    def test_kill_switch_auth_schema_and_path_fail_closed_before_service_construction(self):
        cases = (
            (production_values(PREPARE_KILL_SWITCH_ACTIVE="true"), "KILL_SWITCHED"),
            (
                production_values(
                    PREPARE_OPERATOR_AUTH_ENABLED="false",
                    PREPARE_OPERATOR_ID=None,
                    PREPARE_OPERATOR_TOKEN_SHA256=None,
                ),
                "AUTH_NOT_READY",
            ),
            (
                production_values(PREPARE_OPERATOR_AUTH_LOCAL_TEST_MODE="true"),
                "AUTH_NOT_READY",
            ),
        )
        for values, expected in cases:
            with self.subTest(expected=expected):
                config = parse_runtime_integration_config(values)
                descriptor = self.descriptor(config)
                self.assertEqual(descriptor.status, expected)
                self.assertFalse(descriptor.prepare_mutation_enabled)
                self.assertIsNone(
                    build_prepare_api_service(
                        settings=self.config,
                        config=config,
                        descriptor=descriptor,
                    )
                )
        noncanonical = build_runtime_integration(
            production_values(),
            db_path=self.db_path,
            repository_root=self.config.root / "repository-sentinel",
            canonical_db_path=self.temp_root / "canonical" / "app.db",
        )
        self.assertEqual(noncanonical.status, "CANONICAL_PATH_REQUIRED")
        self.assertFalse(noncanonical.prepare_mutation_enabled)
        self.assertEqual(self.counts()["jobs"], 0)

    def test_schema12_is_inspected_without_migration_and_reports_not_ready(self):
        schema12 = self.temp_root / "schema12" / "app.db"
        Database(schema12).initialize()
        before = hashlib.sha256(schema12.read_bytes()).hexdigest()
        descriptor = self.descriptor(
            production_values(PREPARE_KILL_SWITCH_ACTIVE="false"),
            path=schema12,
        )
        self.assertEqual(descriptor.status, "SCHEMA_NOT_READY")
        self.assertEqual(descriptor.schema_version, 12)
        self.assertFalse(descriptor.prepare_mutation_enabled)
        self.assertEqual(hashlib.sha256(schema12.read_bytes()).hexdigest(), before)
        connection = sqlite3.connect(schema12)
        try:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='batch_prepare_requests'"
            ).fetchone()
        finally:
            connection.close()
        self.assertIsNone(table)

    def test_readiness_is_redacted_and_start_render_is_never_available(self):
        payload = public_runtime_readiness(self.descriptor())
        self.assertTrue(payload["mutation_authorized"])
        self.assertFalse(payload["start_render_available"])
        self.assertFalse(payload["prepare_starts_render"])
        rendered = repr(payload).lower()
        self.assertNotIn(TOKEN, rendered)
        self.assertNotIn("token_sha256", rendered)

    def test_production_mode_blocks_legacy_prepare_and_start_routes(self):
        import story_audio.api as api

        descriptor = self.descriptor()
        with patch.object(api, "prepare_runtime_integration", descriptor):
            client = TestClient(api.app)
            job_payload = {
                "book_id": 1,
                "from_chapter": 1,
                "to_chapter": 1,
                "voice_name": "test",
                "repair_mode": "off",
            }
            self.assertEqual(client.post("/api/jobs/prepare", json=job_payload).status_code, 409)
            self.assertEqual(client.post("/api/jobs", json=job_payload).status_code, 409)
            self.assertEqual(client.post("/api/jobs/1/start", json={}).status_code, 409)


class ActivationPreflightTests(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.canonical = self.temp_root / "canonical" / "app.db"
        Database(self.canonical).initialize()
        self.external = self.temp_root / "external"
        self.external.mkdir()
        self.backup = self.external / "canonical-schema12-backup.db"

    def test_normal_runner_remains_schema12_and_explicit_runner_supports_15(self):
        self.assertEqual(Database(self.canonical).latest_schema_version, 12)
        self.assertEqual(
            Database(
                self.canonical,
                migration_runner=prepare_migration_runner(),
            ).latest_schema_version,
            15,
        )
        self.assertEqual(verified_prepare_migration_hashes(), PREPARE_MIGRATION_HASHES)

    def test_preflight_creates_verified_external_backup_without_source_mutation(self):
        before = hashlib.sha256(self.canonical.read_bytes()).hexdigest()
        with patch.dict(os.environ, {"STORY_AUDIO_TESTING": "1"}, clear=True):
            result = run_preflight(
                self.backup,
                canonical_path=self.canonical,
                external_root=self.external,
                script_path=Path("scripts/prepare_activation.py").resolve(),
            )
        self.assertEqual(result["status"], "GO_FOR_EXPLICIT_ACTIVATION_APPROVAL")
        self.assertTrue(self.backup.is_file())
        self.assertTrue(Path(result["evidence_path"]).is_file())
        self.assertTrue(result["source_unchanged"])
        self.assertEqual(result["canonical"]["schema_version"], 12)
        self.assertEqual(result["backup"]["schema_version"], 12)
        self.assertEqual(hashlib.sha256(self.canonical.read_bytes()).hexdigest(), before)
        self.assertIn("--execute-migration", result["migration_command"])
        self.assertIn("--rollback", result["rollback_command"])
        self.assertTrue(result["canary_rules"]["chapter_369_forbidden"])

    def test_execution_is_impossible_in_test_mode_even_with_exact_confirmation(self):
        with patch.dict(os.environ, {"STORY_AUDIO_TESTING": "1"}, clear=True):
            with self.assertRaisesRegex(PrepareActivationError, "forbidden in test mode"):
                execute_migration(
                    self.backup,
                    confirmation=ACTIVATION_CONFIRMATION,
                    canonical_path=self.canonical,
                )
        self.assertEqual(Database(self.canonical).schema_version(), 12)

    def test_activation_cli_reports_fail_closed_error_without_traceback(self):
        result = subprocess.run(
            [
                sys.executable,
                str(Path("scripts/prepare_activation.py").resolve()),
                "--backup",
                str(self.backup),
                "--execute-migration",
                "--confirm",
                "WRONG_CONFIRMATION",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "STORY_AUDIO_TESTING": "1"},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("PREPARE activation blocked:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(Database(self.canonical).schema_version(), 12)


class ProductionLifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_production_startup_uses_preinspected_state_and_never_opens_worker(self):
        import story_audio.api as api

        database = MagicMock()
        worker = MagicMock()
        descriptor = SimpleNamespace(runtime_mode=PRODUCTION)
        with (
            patch.object(api, "prepare_runtime_integration", descriptor),
            patch.object(api, "db", database),
            patch.object(api, "worker", worker),
        ):
            async with api.lifespan(api.app):
                pass
        database.schema_version.assert_not_called()
        database.initialize.assert_not_called()
        worker.start.assert_not_called()
        worker.wake.assert_not_called()
        worker.stop.assert_not_called()
