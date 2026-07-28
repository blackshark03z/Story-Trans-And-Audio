"""Shared lifecycle envelope for user-triggered Production commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
from typing import Any, Callable, Mapping


COMMAND_SCHEMA = "story-audio-production-command/v1"
COMMAND_OUTCOMES = {"APPLIED", "PARTIAL", "REJECTED", "ACCEPTED", "UNKNOWN"}
_COMMAND_TYPE = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,199}$")
_SCOPE_KEYS = ("chapter", "range", "job", "artifact")


class ProductionCommandError(ValueError):
    """Fail-closed command contract violation."""


@dataclass(frozen=True)
class ProductionCommandMutation:
    outcome: str
    submitted_count: int
    applied_items: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    failed_items: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    operator_message: str = ""
    asynchronous_reference: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.outcome not in COMMAND_OUTCOMES:
            raise ProductionCommandError("Unsupported Production command outcome")
        if self.submitted_count < 0:
            raise ProductionCommandError("submitted_count must be non-negative")
        if len(self.applied_items) + len(self.failed_items) > self.submitted_count:
            raise ProductionCommandError("Command item counts exceed submitted_count")
        if self.outcome == "PARTIAL" and (
            not self.applied_items or not self.failed_items
        ):
            raise ProductionCommandError("PARTIAL requires applied and failed items")
        if self.outcome == "ACCEPTED" and not self.asynchronous_reference:
            raise ProductionCommandError(
                "ACCEPTED requires an asynchronous_reference"
            )


def _stable_token(value: Mapping[str, Any] | None) -> str | None:
    if value is None:
        return None
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _command_id(command_type: str, idempotency_key: str) -> str:
    digest = sha256(f"{command_type}\0{idempotency_key}".encode("utf-8")).hexdigest()
    return f"pc-{digest[:24]}"


def normalize_scope(scope: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(scope, Mapping):
        raise ProductionCommandError("scope must be an object")
    unknown = sorted(set(scope) - set(_SCOPE_KEYS))
    if unknown:
        raise ProductionCommandError(f"Unsupported scope fields: {', '.join(unknown)}")
    normalized = {key: scope.get(key) for key in _SCOPE_KEYS}
    if not any(value is not None for value in normalized.values()):
        raise ProductionCommandError("At least one Production scope is required")
    return normalized


class ProductionCommandService:
    """Execute an existing mutation boundary and immediately project its result."""

    def __init__(
        self,
        projector: Callable[
            [Mapping[str, Any]], tuple[Mapping[str, Any], Mapping[str, Any] | None]
        ],
    ) -> None:
        self._projector = projector

    def execute(
        self,
        *,
        command_type: str,
        idempotency_key: str,
        scope: Mapping[str, Any],
        executor: Callable[[], ProductionCommandMutation],
    ) -> dict[str, Any]:
        command_type = str(command_type or "").strip().upper()
        idempotency_key = str(idempotency_key or "").strip()
        if not _COMMAND_TYPE.fullmatch(command_type):
            raise ProductionCommandError("Invalid command_type")
        if not _IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            raise ProductionCommandError("Invalid idempotency_key")
        normalized_scope = normalize_scope(scope)
        mutation = executor()
        task_projection, preflight = self._projector(normalized_scope)
        applied_items = [dict(item) for item in mutation.applied_items]
        failed_items = [dict(item) for item in mutation.failed_items]
        return {
            "schema": COMMAND_SCHEMA,
            "command_id": _command_id(command_type, idempotency_key),
            "command_type": command_type,
            "idempotency_key": idempotency_key,
            "scope": normalized_scope,
            "outcome": mutation.outcome,
            "submitted_count": mutation.submitted_count,
            "applied_count": len(applied_items),
            "failed_count": len(failed_items),
            "applied_items": applied_items,
            "failed_items": failed_items,
            "operator_message": mutation.operator_message,
            "resulting_task_projection": dict(task_projection),
            "resulting_preflight": dict(preflight) if preflight is not None else None,
            "asynchronous_reference": (
                dict(mutation.asynchronous_reference)
                if mutation.asynchronous_reference is not None
                else None
            ),
            "state_tokens": {
                "task_projection": _stable_token(task_projection),
                "preflight": _stable_token(preflight),
            },
        }

    def rejected(
        self,
        *,
        command_type: str,
        idempotency_key: str,
        scope: Mapping[str, Any],
        message: str,
        failed_items: tuple[Mapping[str, Any], ...] = (),
    ) -> dict[str, Any]:
        normalized_scope = normalize_scope(scope)
        task_projection, preflight = self._projector(normalized_scope)
        items = [dict(item) for item in failed_items]
        submitted = max(1, len(items))
        return {
            "schema": COMMAND_SCHEMA,
            "command_id": _command_id(command_type, idempotency_key),
            "command_type": command_type,
            "idempotency_key": idempotency_key,
            "scope": normalized_scope,
            "outcome": "REJECTED",
            "submitted_count": submitted,
            "applied_count": 0,
            "failed_count": len(items) or 1,
            "applied_items": [],
            "failed_items": items or [{"reason": message}],
            "operator_message": message,
            "resulting_task_projection": dict(task_projection),
            "resulting_preflight": dict(preflight) if preflight is not None else None,
            "asynchronous_reference": None,
            "state_tokens": {
                "task_projection": _stable_token(task_projection),
                "preflight": _stable_token(preflight),
            },
        }


__all__ = [
    "COMMAND_OUTCOMES",
    "COMMAND_SCHEMA",
    "ProductionCommandError",
    "ProductionCommandMutation",
    "ProductionCommandService",
    "normalize_scope",
]
