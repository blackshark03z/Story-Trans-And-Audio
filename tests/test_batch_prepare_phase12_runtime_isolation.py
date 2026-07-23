from __future__ import annotations

import ast
import unittest
from pathlib import Path

from story_audio.batch_prepare_runtime_wiring import build_disabled_runtime_wiring
from story_audio.batch_prepare_runtime_rollout_contract import (
    AUTH_MISSING_BLOCKS_PRODUCTION,
)


ROOT = Path(__file__).resolve().parents[1]


class Phase12RuntimeIsolationTests(unittest.TestCase):
    def test_wiring_module_has_no_runtime_or_provider_imports(self) -> None:
        tree = ast.parse((ROOT / "story_audio" / "batch_prepare_runtime_wiring.py").read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        forbidden = ("api", "db", "pipeline", "worker", "tts", "provider", "sqlite", "migrations")
        self.assertFalse(any(any(token in name.lower() for token in forbidden) for name in imports))

    def test_route_and_ui_are_present_but_fail_closed_by_runtime_readiness(self) -> None:
        api = (ROOT / "story_audio" / "api.py").read_text(encoding="utf-8")
        ui = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        self.assertIn('/api/production/batch-prepare"', api)
        self.assertIn("batch_prepare_api_service is None", api)
        self.assertNotIn("batch_prepare_runtime_wiring", api)
        self.assertIn("/api/production/prepare-readiness", ui)
        self.assertIn("/api/production/batch-prepare", ui)
        self.assertIn("readiness?.mutation_authorized", ui)
        self.assertIn("startRenderAllowed", ui)

    def test_schema_and_auth_states_remain_non_mutating(self) -> None:
        for schema in (None, 12, 13, 16):
            plan = build_disabled_runtime_wiring(
                {
                    "PREPARE_KILL_SWITCH_ACTIVE": False,
                    "PREPARE_CANONICAL_SCHEMA_READY": True,
                    "PREPARE_FEATURE_AVAILABLE": True,
                    "PREPARE_MUTATION_ENABLED": True,
                    "PREPARE_OPERATOR_WINDOW_OPEN": True,
                },
                schema_version=schema,
                runtime_identity_explicit=True,
                auth_classification=AUTH_MISSING_BLOCKS_PRODUCTION,
            )
            self.assertEqual(plan.state, "SCHEMA_NOT_READY")
            self.assertFalse(plan.route_registered)
            self.assertFalse(plan.migration_executed)
            self.assertFalse(plan.job_created)

    def test_clone_module_is_the_only_mutation_boundary_and_is_external(self) -> None:
        source = (ROOT / "story_audio" / "batch_prepare_clone_rehearsal.py").read_text(encoding="utf-8")
        self.assertIn("SQLITE_ONLINE_BACKUP_FROM_READONLY_SOURCE", source)
        self.assertIn("DEFAULT_EXTERNAL_ROOT", source)
        self.assertNotIn("canonical_production_db_path().write", source)


if __name__ == "__main__":
    unittest.main()
