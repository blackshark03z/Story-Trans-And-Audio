"""Pure, unreachable Phase 12 PREPARE runtime wiring skeleton.

This module intentionally does not import the application, database, migration,
worker, adapter, store, or provider layers.  It describes a disabled plan only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .batch_prepare_runtime_rollout_contract import (
    AUTH_MISSING_BLOCKS_PRODUCTION,
    AUTH_PRESENT_AND_REUSABLE,
)


AUTH_REQUIRED = AUTH_PRESENT_AND_REUSABLE
SCHEMA_REQUIRED = 15
BOOL_TRUE = frozenset({"true", "1", "enabled"})
BOOL_FALSE = frozenset({"false", "0", "disabled"})
FLAG_NAMES = {
    "PREPARE_FEATURE_AVAILABLE": "feature_available",
    "PREPARE_MUTATION_ENABLED": "mutation_enabled",
    "PREPARE_OPERATOR_WINDOW_OPEN": "operator_window_open",
    "PREPARE_CANONICAL_SCHEMA_READY": "canonical_schema_ready",
    "PREPARE_KILL_SWITCH_ACTIVE": "kill_switch_active",
}
AUTHORIZATION_FIELDS = {
    "runtime_implementation_authorized": False,
    "canonical_activation_authorized": False,
    "production_prepare_authorized": False,
    "api_mutation_route_authorized": False,
    "ui_control_authorized": False,
    "worker_wake_authorized": False,
    "start_render_authorized": False,
    "provider_tts_authorized": False,
}


@dataclass(frozen=True)
class RuntimePrepareConfig:
    feature_available: bool = False
    mutation_enabled: bool = False
    operator_window_open: bool = False
    canonical_schema_ready: bool = False
    kill_switch_active: bool = True
    config_valid: bool = True
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class DisabledRuntimeWiringPlan:
    state: str
    auth_classification: str
    schema_version: int | None
    runtime_identity_explicit: bool
    read_only_planning_available: bool
    mutation_service_construction_forbidden: bool
    mutation_service_constructed: bool
    request_store_constructed: bool
    attempt_store_constructed: bool
    linkage_store_constructed: bool
    transaction_service_constructed: bool
    isolated_adapter_invoked: bool
    writable_db_opened: bool
    migration_executed: bool
    route_registered: bool
    batch_prepare_route_registered: bool
    status_mutation_route_registered: bool
    job_created: bool
    worker_woken: bool
    start_render_started: bool
    public_authorization: Mapping[str, bool]
    reasons: tuple[str, ...]


def _parse_bool(name: str, value: Any) -> tuple[bool, str | None]:
    if isinstance(value, bool):
        return value, None
    if isinstance(value, int) and value in (0, 1):
        return bool(value), None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in BOOL_TRUE:
            return True, None
        if normalized in BOOL_FALSE:
            return False, None
    return False, f"INVALID_{name}"


def parse_runtime_prepare_config(values: Mapping[str, Any] | None = None) -> RuntimePrepareConfig:
    source = dict(values or {})
    parsed = {
        "feature_available": False,
        "mutation_enabled": False,
        "operator_window_open": False,
        "canonical_schema_ready": False,
        "kill_switch_active": True,
    }
    errors: list[str] = []
    errors.extend(f"UNKNOWN_FLAG_{name}" for name in sorted(set(source) - set(FLAG_NAMES)))
    for external, field in FLAG_NAMES.items():
        if external not in source:
            continue
        parsed[field], error = _parse_bool(external, source[external])
        if error:
            errors.append(error)
            if field == "kill_switch_active":
                parsed[field] = True
            else:
                parsed[field] = False
    return RuntimePrepareConfig(**parsed, config_valid=not errors, errors=tuple(errors))


def read_runtime_prepare_config(environment: Mapping[str, Any] | None = None) -> RuntimePrepareConfig:
    source = dict(environment) if environment is not None else dict(os.environ)
    return parse_runtime_prepare_config({key: source[key] for key in FLAG_NAMES if key in source})


def _state(
    config: RuntimePrepareConfig,
    *,
    schema_version: int | None,
    runtime_identity_explicit: bool,
    auth_classification: str,
) -> tuple[str, tuple[str, ...]]:
    if not config.config_valid:
        return "CONFIG_INVALID", config.errors
    if config.kill_switch_active:
        return "KILL_SWITCHED", ("KILL_SWITCH_ACTIVE",)
    if schema_version != SCHEMA_REQUIRED or not config.canonical_schema_ready:
        return "SCHEMA_NOT_READY", ("SCHEMA_NOT_READY",)
    if not config.feature_available or not config.mutation_enabled:
        return "DISABLED_DEFAULT", ("FEATURE_OR_MUTATION_DISABLED",)
    if not config.operator_window_open:
        return "OPERATOR_WINDOW_CLOSED", ("OPERATOR_WINDOW_CLOSED",)
    if not runtime_identity_explicit:
        return "AUTH_NOT_READY", ("RUNTIME_IDENTITY_NOT_EXPLICIT",)
    if auth_classification != AUTH_REQUIRED:
        return "AUTH_NOT_READY", ("AUTH_MISSING_BLOCKS_PRODUCTION",)
    return "DESIGN_SKELETON_READY", ("PHASE12_CONSTRUCTION_CEILING",)


def build_disabled_runtime_wiring(
    config: RuntimePrepareConfig | Mapping[str, Any] | None = None,
    *,
    schema_version: int | None = 12,
    runtime_identity_explicit: bool = False,
    auth_classification: str = AUTH_MISSING_BLOCKS_PRODUCTION,
    read_only_planning_available: bool = True,
    **dependency_factories: Callable[[], Any],
) -> DisabledRuntimeWiringPlan:
    parsed = config if isinstance(config, RuntimePrepareConfig) else parse_runtime_prepare_config(config)
    state, reasons = _state(
        parsed,
        schema_version=schema_version,
        runtime_identity_explicit=runtime_identity_explicit,
        auth_classification=auth_classification,
    )
    # Phase 12 has an immutable construction ceiling.  The factories are accepted
    # only so tests can prove that even hostile/misleading inputs are never called.
    del dependency_factories
    return DisabledRuntimeWiringPlan(
        state=state,
        auth_classification=auth_classification,
        schema_version=schema_version,
        runtime_identity_explicit=runtime_identity_explicit,
        read_only_planning_available=bool(read_only_planning_available),
        mutation_service_construction_forbidden=True,
        mutation_service_constructed=False,
        request_store_constructed=False,
        attempt_store_constructed=False,
        linkage_store_constructed=False,
        transaction_service_constructed=False,
        isolated_adapter_invoked=False,
        writable_db_opened=False,
        migration_executed=False,
        route_registered=False,
        batch_prepare_route_registered=False,
        status_mutation_route_registered=False,
        job_created=False,
        worker_woken=False,
        start_render_started=False,
        public_authorization=dict(AUTHORIZATION_FIELDS),
        reasons=reasons,
    )


def public_wiring_status(plan: DisabledRuntimeWiringPlan) -> dict[str, Any]:
    return {
        "state": plan.state,
        "auth_classification": plan.auth_classification,
        "schema_version": plan.schema_version,
        "read_only_planning_available": plan.read_only_planning_available,
        "mutation_service_construction_forbidden": True,
        "route_registered": False,
        "batch_prepare_route_registered": False,
        "status_mutation_route_registered": False,
        "writable_db_opened": False,
        "migration_executed": False,
        "worker_woken": False,
        "start_render_started": False,
        "reasons": list(plan.reasons),
        **dict(AUTHORIZATION_FIELDS),
    }


__all__ = [
    "AUTHORIZATION_FIELDS", "AUTH_REQUIRED", "DisabledRuntimeWiringPlan",
    "RuntimePrepareConfig", "SCHEMA_REQUIRED", "build_disabled_runtime_wiring",
    "parse_runtime_prepare_config", "public_wiring_status", "read_runtime_prepare_config",
]
