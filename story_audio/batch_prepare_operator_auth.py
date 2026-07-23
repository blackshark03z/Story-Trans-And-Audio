"""Fail-closed single-operator authentication boundary for future PREPARE APIs.

The provider is intentionally independent from FastAPI and from every mutation
service.  Phase 13 validates credentials, but never grants mutation authority.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Any, Mapping


AUTH_DISABLED = "AUTH_DISABLED"
AUTH_CONFIG_MISSING = "AUTH_CONFIG_MISSING"
AUTH_CONFIG_INVALID = "AUTH_CONFIG_INVALID"
AUTH_CREDENTIAL_MISSING = "AUTH_CREDENTIAL_MISSING"
AUTH_CREDENTIAL_MALFORMED = "AUTH_CREDENTIAL_MALFORMED"
AUTH_CREDENTIAL_INVALID = "AUTH_CREDENTIAL_INVALID"
AUTH_OPERATOR_UNKNOWN = "AUTH_OPERATOR_UNKNOWN"
AUTHENTICATED_OPERATOR = "AUTHENTICATED_OPERATOR"
AUTH_REDACTION_FAILURE = "AUTH_REDACTION_FAILURE"

MAX_TOKEN_BYTES = 512
MAX_OPERATOR_ID_LENGTH = 64
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_OPERATOR_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_TRUE = frozenset({"1", "true", "enabled"})
_FALSE = frozenset({"0", "false", "disabled"})


@dataclass(frozen=True)
class OperatorAuthConfig:
    enabled: bool = False
    operator_id: str | None = None
    token_sha256: str | None = None
    token_version: str | None = None
    local_test_mode: bool = False
    config_valid: bool = True
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperatorAuthDecision:
    state: str
    authenticated: bool
    operator_identity_ref: str | None = None
    token_version: str | None = None
    mutation_authorized: bool = False
    reasons: tuple[str, ...] = ()


def _parse_bool(name: str, value: Any, *, default: bool) -> tuple[bool, str | None]:
    if value is None:
        return default, None
    if isinstance(value, bool):
        return value, None
    if isinstance(value, str):
        normalized = value.lower()
        if normalized in _TRUE:
            return True, None
        if normalized in _FALSE:
            return False, None
    return default, f"INVALID_{name}"


def parse_operator_auth_config(values: Mapping[str, Any] | None = None) -> OperatorAuthConfig:
    source = dict(values or {})
    enabled, enabled_error = _parse_bool(
        "PREPARE_OPERATOR_AUTH_ENABLED",
        source.get("PREPARE_OPERATOR_AUTH_ENABLED"),
        default=False,
    )
    local_test_mode, local_error = _parse_bool(
        "PREPARE_OPERATOR_AUTH_LOCAL_TEST_MODE",
        source.get("PREPARE_OPERATOR_AUTH_LOCAL_TEST_MODE"),
        default=False,
    )
    operator_id = source.get("PREPARE_OPERATOR_ID")
    token_sha256 = source.get("PREPARE_OPERATOR_TOKEN_SHA256")
    token_version = source.get("PREPARE_OPERATOR_TOKEN_VERSION")
    errors = [error for error in (enabled_error, local_error) if error]

    if operator_id is not None and (
        not isinstance(operator_id, str) or not _OPERATOR_ID.fullmatch(operator_id)
    ):
        errors.append("INVALID_OPERATOR_ID")
    if token_sha256 is not None and (
        not isinstance(token_sha256, str) or not _HEX64.fullmatch(token_sha256)
    ):
        errors.append("INVALID_TOKEN_SHA256")
    if token_version is not None and (
        not isinstance(token_version, str)
        or not token_version
        or len(token_version) > 32
        or not _OPERATOR_ID.fullmatch(token_version)
    ):
        errors.append("INVALID_TOKEN_VERSION")
    if enabled:
        if operator_id is None:
            errors.append("MISSING_OPERATOR_ID")
        if token_sha256 is None:
            errors.append("MISSING_TOKEN_SHA256")

    return OperatorAuthConfig(
        enabled=enabled,
        operator_id=operator_id if isinstance(operator_id, str) else None,
        token_sha256=token_sha256 if isinstance(token_sha256, str) else None,
        token_version=token_version if isinstance(token_version, str) else None,
        local_test_mode=local_test_mode,
        config_valid=not errors,
        errors=tuple(errors),
    )


def auth_configuration_state(config: OperatorAuthConfig) -> str:
    if not config.enabled:
        return AUTH_DISABLED if config.config_valid else AUTH_CONFIG_INVALID
    if not config.operator_id or not config.token_sha256:
        return AUTH_CONFIG_MISSING
    if not config.config_valid:
        return AUTH_CONFIG_INVALID
    return "AUTH_CONFIGURED"


def authenticate_operator(
    config: OperatorAuthConfig,
    authorization_header: str | None,
    *,
    client_operator_id: str | None = None,
    credential_in_url: bool = False,
) -> OperatorAuthDecision:
    state = auth_configuration_state(config)
    if state != "AUTH_CONFIGURED":
        return OperatorAuthDecision(state, False, reasons=tuple(config.errors))
    if credential_in_url:
        return OperatorAuthDecision(AUTH_CREDENTIAL_MALFORMED, False, reasons=("URL_CREDENTIAL_REJECTED",))
    if client_operator_id is not None:
        return OperatorAuthDecision(AUTH_OPERATOR_UNKNOWN, False, reasons=("CLIENT_OPERATOR_ID_REJECTED",))
    if authorization_header is None:
        return OperatorAuthDecision(AUTH_CREDENTIAL_MISSING, False)
    if not isinstance(authorization_header, str) or not authorization_header.startswith("Bearer "):
        return OperatorAuthDecision(AUTH_CREDENTIAL_MALFORMED, False)
    token = authorization_header[7:]
    if not token or token != token.strip() or any(char.isspace() for char in token):
        return OperatorAuthDecision(AUTH_CREDENTIAL_MALFORMED, False)
    token_bytes = token.encode("utf-8")
    if len(token_bytes) > MAX_TOKEN_BYTES:
        return OperatorAuthDecision(AUTH_CREDENTIAL_MALFORMED, False, reasons=("TOKEN_TOO_LARGE",))
    presented_hash = hashlib.sha256(token_bytes).hexdigest()
    valid = hmac.compare_digest(presented_hash, config.token_sha256 or "")
    del token, token_bytes, presented_hash
    if not valid:
        return OperatorAuthDecision(AUTH_CREDENTIAL_INVALID, False)
    return OperatorAuthDecision(
        AUTHENTICATED_OPERATOR,
        True,
        operator_identity_ref=config.operator_id,
        token_version=config.token_version,
        mutation_authorized=False,
        reasons=("PHASE13_AUTHENTICATION_ONLY",),
    )


def public_auth_status(config: OperatorAuthConfig) -> dict[str, Any]:
    return {
        "authentication_state": auth_configuration_state(config),
        "authentication_enabled": config.enabled,
        "local_test_mode": config.local_test_mode,
        "mutation_authorized": False,
    }


__all__ = [
    "AUTHENTICATED_OPERATOR", "AUTH_CONFIG_INVALID", "AUTH_CONFIG_MISSING",
    "AUTH_CREDENTIAL_INVALID", "AUTH_CREDENTIAL_MALFORMED", "AUTH_CREDENTIAL_MISSING",
    "AUTH_DISABLED", "AUTH_OPERATOR_UNKNOWN", "AUTH_REDACTION_FAILURE", "MAX_TOKEN_BYTES",
    "OperatorAuthConfig", "OperatorAuthDecision", "auth_configuration_state",
    "authenticate_operator", "parse_operator_auth_config", "public_auth_status",
]
