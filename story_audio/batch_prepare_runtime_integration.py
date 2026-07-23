"""Fail-closed runtime integration for clone and production PREPARE."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .batch_prepare_operator_auth import (
    OperatorAuthConfig,
    parse_operator_auth_config,
    public_auth_status,
)
from .batch_prepare_runtime_wiring import RuntimePrepareConfig, parse_runtime_prepare_config
from .db import ClosingConnection, Database


DISABLED = "DISABLED"
CLONE_DISABLED = "CLONE_DISABLED"
PRODUCTION = "PRODUCTION"
REQUIRED_SCHEMA_VERSION = 15
_RUNTIME_KEYS = frozenset({
    "PREPARE_RUNTIME_MODE",
    "PREPARE_CLONE_MUTATION_TEST_AUTHORIZED",
})
_FLAG_KEYS = frozenset({
    "PREPARE_FEATURE_AVAILABLE", "PREPARE_MUTATION_ENABLED",
    "PREPARE_OPERATOR_WINDOW_OPEN", "PREPARE_CANONICAL_SCHEMA_READY",
    "PREPARE_KILL_SWITCH_ACTIVE",
})
_AUTH_KEYS = frozenset({
    "PREPARE_OPERATOR_AUTH_ENABLED", "PREPARE_OPERATOR_ID",
    "PREPARE_OPERATOR_TOKEN_SHA256", "PREPARE_OPERATOR_TOKEN_VERSION",
    "PREPARE_OPERATOR_AUTH_LOCAL_TEST_MODE",
})


class CloneRuntimeRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeIntegrationConfig:
    mode: str
    flags: RuntimePrepareConfig
    auth: OperatorAuthConfig
    clone_mutation_test_authorized: bool = False
    config_valid: bool = True
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeIntegrationDescriptor:
    status: str
    runtime_mode: str
    clone_backed: bool
    canonical_backed: bool
    inspected_db_path: Path | None
    schema_version: int | None
    required_schema_version: int
    quick_check: str | None
    feature_available: bool
    mutation_enabled: bool
    operator_window_open: bool
    kill_switch_active: bool
    authentication_state: str
    read_only_planning_available: bool
    mutation_service_constructed: bool = False
    isolated_adapter_constructed: bool = False
    request_store_constructed: bool = False
    linkage_store_constructed: bool = False
    attempt_store_constructed: bool = False
    transaction_service_constructed: bool = False
    mutation_route_registered: bool = False
    mutation_authorized: bool = False
    execution_endpoint_available: bool = False
    real_job_execution: bool = False
    writable_db_opened: bool = False
    migration_executed: bool = False
    worker_woken: bool = False
    prepare_starts_render: bool = False
    reasons: tuple[str, ...] = ()

    @property
    def clone_runtime_active(self) -> bool:
        return (
            self.runtime_mode == CLONE_DISABLED
            and self.clone_backed
            and self.schema_version == REQUIRED_SCHEMA_VERSION
            and self.quick_check == "ok"
            and self.status in {
                "KILL_SWITCHED", "SCHEMA_FLAG_NOT_READY", "DISABLED_DEFAULT",
                "OPERATOR_WINDOW_CLOSED", "AUTH_NOT_READY", "CLONE_DISABLED_READY",
                "PHASE14_TEST_AUTHORIZATION_REQUIRED", "PHASE14_LOCAL_TEST_AUTH_REQUIRED",
                "CLONE_AUTHENTICATED_TEST_READY",
            }
        )

    @property
    def clone_mutation_test_enabled(self) -> bool:
        return (
            self.clone_runtime_active
            and self.status == "CLONE_AUTHENTICATED_TEST_READY"
            and self.feature_available
            and self.mutation_enabled
            and self.operator_window_open
            and not self.kill_switch_active
            and self.authentication_state == "AUTH_CONFIGURED"
        )

    @property
    def production_mutation_enabled(self) -> bool:
        return (
            self.runtime_mode == PRODUCTION
            and self.canonical_backed
            and self.status == "PRODUCTION_AUTHENTICATED_READY"
            and self.schema_version == REQUIRED_SCHEMA_VERSION
            and self.quick_check == "ok"
            and self.feature_available
            and self.mutation_enabled
            and self.operator_window_open
            and not self.kill_switch_active
            and self.authentication_state == "AUTH_CONFIGURED"
        )

    @property
    def prepare_mutation_enabled(self) -> bool:
        return self.clone_mutation_test_enabled or self.production_mutation_enabled


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def parse_runtime_integration_config(values: Mapping[str, Any] | None = None) -> RuntimeIntegrationConfig:
    source = dict(values or {})
    mode = source.get("PREPARE_RUNTIME_MODE", DISABLED)
    errors: list[str] = []
    if not isinstance(mode, str) or mode not in {DISABLED, CLONE_DISABLED, PRODUCTION}:
        errors.append("INVALID_RUNTIME_MODE")
        mode = DISABLED
    flags = parse_runtime_prepare_config({key: source[key] for key in _FLAG_KEYS if key in source})
    auth = parse_operator_auth_config({key: source[key] for key in _AUTH_KEYS if key in source})
    test_authorized, test_error = _parse_test_authorization(
        source.get("PREPARE_CLONE_MUTATION_TEST_AUTHORIZED")
    )
    errors.extend(flags.errors)
    errors.extend(auth.errors)
    if test_error:
        errors.append(test_error)
    return RuntimeIntegrationConfig(
        mode,
        flags,
        auth,
        clone_mutation_test_authorized=test_authorized,
        config_valid=not errors,
        errors=tuple(errors),
    )


def _parse_test_authorization(value: Any) -> tuple[bool, str | None]:
    if value is None:
        return False, None
    if isinstance(value, bool):
        return value, None
    if isinstance(value, str) and value in {"true", "false"}:
        return value == "true", None
    return False, "INVALID_PREPARE_CLONE_MUTATION_TEST_AUTHORIZED"


def read_runtime_integration_config(environment: Mapping[str, Any] | None = None) -> RuntimeIntegrationConfig:
    source = dict(os.environ if environment is None else environment)
    keys = _RUNTIME_KEYS | _FLAG_KEYS | _AUTH_KEYS
    return parse_runtime_integration_config({key: source[key] for key in keys if key in source})


def _inspect_clone(path: Path) -> tuple[int, str]:
    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        schema_version = int(row[0] or 0)
    finally:
        connection.close()
    return schema_version, quick_check


def build_runtime_integration(
    config: RuntimeIntegrationConfig | Mapping[str, Any] | None = None,
    *,
    db_path: Path,
    repository_root: Path,
    canonical_db_path: Path,
    **dependency_factories: Callable[[], Any],
) -> RuntimeIntegrationDescriptor:
    parsed = config if isinstance(config, RuntimeIntegrationConfig) else parse_runtime_integration_config(config)
    del dependency_factories
    auth_status = public_auth_status(parsed.auth)["authentication_state"]
    reasons: list[str] = list(parsed.errors)
    schema_version: int | None = None
    quick_check: str | None = None
    clone_backed = False
    canonical_backed = False
    inspected_db_path: Path | None = None

    if not parsed.config_valid:
        status = "CONFIG_INVALID"
    else:
        resolved = db_path.resolve(strict=False)
        inspected_db_path = resolved
        repo = repository_root.resolve(strict=False)
        canonical = canonical_db_path.resolve(strict=False)
        canonical_backed = resolved == canonical
        if parsed.mode == DISABLED:
            if resolved.is_file():
                try:
                    schema_version, quick_check = _inspect_clone(resolved)
                except (OSError, sqlite3.Error):
                    reasons.append("DATABASE_INSPECTION_FAILED")
            status = "KILL_SWITCHED" if parsed.flags.kill_switch_active else "DISABLED_DEFAULT"
            reasons.append("DEFAULT_DISABLED_RUNTIME")
        elif parsed.mode == CLONE_DISABLED and (
            resolved == canonical or _within(resolved, repo) or _within(resolved, canonical.parent)
        ):
            status = "UNSAFE_CLONE_PATH"
            reasons.append("CLONE_PATH_REJECTED")
        elif not resolved.is_file():
            status = "DATABASE_MISSING" if parsed.mode == PRODUCTION else "CLONE_MISSING"
            reasons.append("DATABASE_PATH_MISSING")
        elif parsed.mode == PRODUCTION and not canonical_backed:
            status = "CANONICAL_PATH_REQUIRED"
            reasons.append("CANONICAL_PATH_REQUIRED")
        else:
            try:
                schema_version, quick_check = _inspect_clone(resolved)
            except (OSError, sqlite3.Error):
                status = "DATABASE_UNREADABLE"
                reasons.append("DATABASE_INSPECTION_FAILED")
            else:
                clone_backed = parsed.mode == CLONE_DISABLED
                if parsed.flags.kill_switch_active:
                    status = "KILL_SWITCHED"
                    reasons.append("KILL_SWITCH_ACTIVE")
                elif quick_check != "ok":
                    status = "QUICK_CHECK_FAILED"
                    reasons.append("QUICK_CHECK_FAILED")
                elif schema_version < REQUIRED_SCHEMA_VERSION:
                    status = "SCHEMA_NOT_READY"
                    reasons.append("SCHEMA_NOT_READY")
                elif schema_version > REQUIRED_SCHEMA_VERSION:
                    status = "SCHEMA_UNSUPPORTED"
                    reasons.append("SCHEMA_UNSUPPORTED")
                elif not parsed.flags.canonical_schema_ready:
                    status = "SCHEMA_FLAG_NOT_READY"
                    reasons.append("SCHEMA_READINESS_FLAG_FALSE")
                elif not parsed.flags.feature_available or not parsed.flags.mutation_enabled:
                    status = "DISABLED_DEFAULT"
                    reasons.append("FEATURE_OR_MUTATION_DISABLED")
                elif not parsed.flags.operator_window_open:
                    status = "OPERATOR_WINDOW_CLOSED"
                    reasons.append("OPERATOR_WINDOW_CLOSED")
                elif auth_status != "AUTH_CONFIGURED":
                    status = "AUTH_NOT_READY"
                    reasons.append("AUTH_MISSING_BLOCKS_PRODUCTION")
                elif parsed.mode == PRODUCTION and parsed.auth.local_test_mode:
                    status = "AUTH_NOT_READY"
                    reasons.append("PRODUCTION_REJECTS_LOCAL_TEST_AUTH")
                elif parsed.mode == CLONE_DISABLED and not parsed.clone_mutation_test_authorized:
                    status = "PHASE14_TEST_AUTHORIZATION_REQUIRED"
                    reasons.append("CLONE_MUTATION_TEST_NOT_AUTHORIZED")
                elif parsed.mode == CLONE_DISABLED and not parsed.auth.local_test_mode:
                    status = "PHASE14_LOCAL_TEST_AUTH_REQUIRED"
                    reasons.append("LOCAL_TEST_AUTH_MODE_REQUIRED")
                elif parsed.mode == PRODUCTION:
                    status = "PRODUCTION_AUTHENTICATED_READY"
                    reasons.append("PRODUCTION_PREPARE_ONLY")
                else:
                    status = "CLONE_AUTHENTICATED_TEST_READY"
                    reasons.append("PHASE14_CLONE_TEST_ONLY")

    return RuntimeIntegrationDescriptor(
        status=status,
        runtime_mode=parsed.mode,
        clone_backed=clone_backed,
        canonical_backed=canonical_backed,
        inspected_db_path=inspected_db_path,
        schema_version=schema_version,
        required_schema_version=REQUIRED_SCHEMA_VERSION,
        quick_check=quick_check,
        feature_available=parsed.flags.feature_available,
        mutation_enabled=(
            parsed.flags.mutation_enabled
            and (
                (parsed.clone_mutation_test_authorized and status == "CLONE_AUTHENTICATED_TEST_READY")
                or status == "PRODUCTION_AUTHENTICATED_READY"
            )
        ),
        operator_window_open=parsed.flags.operator_window_open,
        kill_switch_active=True if not parsed.config_valid else parsed.flags.kill_switch_active,
        authentication_state=auth_status,
        read_only_planning_available=True,
        reasons=tuple(reasons),
    )


def require_clone_runtime(descriptor: RuntimeIntegrationDescriptor) -> None:
    if descriptor.runtime_mode == CLONE_DISABLED and not descriptor.clone_runtime_active:
        raise CloneRuntimeRejected(f"Clone-disabled runtime rejected: {descriptor.status}")


def public_runtime_readiness(descriptor: RuntimeIntegrationDescriptor) -> dict[str, Any]:
    return {
        "status": descriptor.status,
        "runtime_mode": descriptor.runtime_mode,
        "canonical_backed": descriptor.canonical_backed,
        "schema_version": descriptor.schema_version,
        "required_schema_version": descriptor.required_schema_version,
        "feature_available": descriptor.feature_available,
        "mutation_enabled": descriptor.prepare_mutation_enabled,
        "operator_window_open": descriptor.operator_window_open,
        "kill_switch_active": descriptor.kill_switch_active,
        "authentication_state": descriptor.authentication_state,
        "mutation_service_constructed": False,
        "mutation_route_registered": False,
        "read_only_planning_available": descriptor.read_only_planning_available,
        "mutation_authorized": descriptor.prepare_mutation_enabled,
        "execution_endpoint_available": descriptor.prepare_mutation_enabled,
        "real_job_execution": False,
        "prepare_starts_render": False,
        "start_render_available": False,
        "startup_migration_enabled": False,
        "reasons": list(descriptor.reasons),
    }


class CloneReadOnlyDatabase(Database):
    """Database-compatible query facade that cannot open a writable connection."""

    def connect(self) -> sqlite3.Connection:
        uri = f"file:{self.path.resolve().as_posix()}?mode=ro&immutable=1"
        connection = sqlite3.connect(
            uri, uri=True, timeout=5, check_same_thread=False, factory=ClosingConnection
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA query_only=ON")
        return connection

    def initialize(self) -> int:
        raise CloneRuntimeRejected("Clone-disabled runtime cannot initialize or migrate a database.")

    def schema_version(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
            return int(row[0] or 0)

    @property
    def latest_schema_version(self) -> int:
        return REQUIRED_SCHEMA_VERSION

    def transaction(self):
        raise CloneRuntimeRejected("Clone-disabled runtime cannot open a transaction.")

    def audit(self, *args: Any, **kwargs: Any) -> None:
        raise CloneRuntimeRejected("Clone-disabled runtime cannot write audit events.")


__all__ = [
    "CLONE_DISABLED", "DISABLED", "PRODUCTION", "CloneReadOnlyDatabase", "CloneRuntimeRejected",
    "REQUIRED_SCHEMA_VERSION", "RuntimeIntegrationConfig", "RuntimeIntegrationDescriptor",
    "build_runtime_integration", "parse_runtime_integration_config", "public_runtime_readiness",
    "read_runtime_integration_config", "require_clone_runtime",
]
