from __future__ import annotations

import os
import unittest

from story_audio.batch_prepare_runtime_rollout_contract import (
    AUTH_MISSING_BLOCKS_PRODUCTION,
    AUTH_PRESENT_AND_REUSABLE,
)
from story_audio.batch_prepare_runtime_wiring import (
    build_disabled_runtime_wiring,
    parse_runtime_prepare_config,
    public_wiring_status,
    read_runtime_prepare_config,
)


ALL_FLAGS = {
    "PREPARE_FEATURE_AVAILABLE": True,
    "PREPARE_MUTATION_ENABLED": True,
    "PREPARE_OPERATOR_WINDOW_OPEN": True,
    "PREPARE_CANONICAL_SCHEMA_READY": True,
    "PREPARE_KILL_SWITCH_ACTIVE": False,
}


class RuntimeWiringTests(unittest.TestCase):
    def test_defaults_are_disabled_and_kill_switched(self) -> None:
        plan = build_disabled_runtime_wiring()
        self.assertEqual(plan.state, "KILL_SWITCHED")
        self.assertTrue(plan.mutation_service_construction_forbidden)
        self.assertFalse(plan.route_registered)
        self.assertFalse(plan.writable_db_opened)
        self.assertFalse(plan.worker_woken)
        self.assertEqual(plan.auth_classification, AUTH_MISSING_BLOCKS_PRODUCTION)

    def test_invalid_and_unknown_flags_fail_closed(self) -> None:
        config = parse_runtime_prepare_config({"PREPARE_MUTATION_ENABLED": "maybe", "UNREVIEWED": True})
        self.assertFalse(config.config_valid)
        self.assertTrue(config.kill_switch_active)
        self.assertEqual(build_disabled_runtime_wiring(config).state, "CONFIG_INVALID")

    def test_schema_identity_and_auth_are_required_for_design_only_state(self) -> None:
        plan = build_disabled_runtime_wiring(
            ALL_FLAGS,
            schema_version=15,
            runtime_identity_explicit=True,
            auth_classification=AUTH_PRESENT_AND_REUSABLE,
        )
        self.assertEqual(plan.state, "DESIGN_SKELETON_READY")
        self.assertTrue(plan.mutation_service_construction_forbidden)
        self.assertFalse(plan.mutation_service_constructed)
        self.assertFalse(plan.request_store_constructed)
        self.assertFalse(plan.attempt_store_constructed)
        self.assertFalse(plan.linkage_store_constructed)
        self.assertFalse(plan.transaction_service_constructed)
        self.assertFalse(plan.isolated_adapter_invoked)
        self.assertFalse(plan.batch_prepare_route_registered)
        self.assertFalse(plan.job_created)

    def test_dependency_factories_are_never_called(self) -> None:
        calls: list[str] = []

        def hostile() -> None:
            calls.append("called")
            raise AssertionError("Phase 12 must not construct runtime dependencies")

        build_disabled_runtime_wiring(ALL_FLAGS, schema_version=15, runtime_identity_explicit=True,
                                      auth_classification=AUTH_PRESENT_AND_REUSABLE,
                                      db_factory=hostile, adapter_factory=hostile)
        self.assertEqual(calls, [])

    def test_environment_reader_does_not_mutate_environment(self) -> None:
        before = dict(os.environ)
        read_runtime_prepare_config({"PREPARE_FEATURE_AVAILABLE": "false"})
        self.assertEqual(dict(os.environ), before)

    def test_public_status_contains_no_enabled_mutation_controls(self) -> None:
        status = public_wiring_status(build_disabled_runtime_wiring(ALL_FLAGS, schema_version=15,
                                                                    runtime_identity_explicit=True,
                                                                    auth_classification=AUTH_PRESENT_AND_REUSABLE))
        self.assertFalse(status["route_registered"])
        self.assertFalse(status["batch_prepare_route_registered"])
        self.assertFalse(status["writable_db_opened"])
        self.assertFalse(status["worker_woken"])
        self.assertFalse(status["production_prepare_authorized"])


if __name__ == "__main__":
    unittest.main()
