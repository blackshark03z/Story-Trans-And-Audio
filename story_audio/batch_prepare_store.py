from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .batch_prepare_persistence_contract import (
    FAILURE_CODES,
    REQUEST_ID_CONFLICT,
    RESULT_SCHEMA,
    STATE_APPLIED,
    STATE_APPLYING,
    STATE_FAILED,
    STATE_PLANNED,
    STATE_REJECTED,
    PreparePersistenceContractError,
    allowed_transition,
    build_replay_contract,
    build_request_binding,
    normalize_client_request_id,
)
from .db import Database, utcnow


RESULT_PAYLOAD_MAX_BYTES = 16 * 1024


class BatchPrepareStoreError(RuntimeError):
    """Base error for durable batch PREPARE request storage."""


class BatchPrepareStoreSchemaError(BatchPrepareStoreError):
    """Raised when the durable request table is not available."""


class BatchPrepareStoreDataError(BatchPrepareStoreError):
    """Raised when stored request data violates the durable replay contract."""


class BatchPrepareRequestConflict(BatchPrepareStoreError):
    """Raised when a request ID is reused with different bound payload."""

    code = REQUEST_ID_CONFLICT


class BatchPrepareStateConflict(BatchPrepareStoreError):
    """Raised when an atomic state transition loses its compare-and-set race."""


@dataclass(frozen=True)
class BatchPrepareRequestRecord:
    id: int
    client_request_id: str
    request_identity: str
    book_id: int
    from_chapter: int
    to_chapter: int
    target_phase: str
    plan_fingerprint: str
    state: str
    job_id: int | None
    result_schema_version: int | None
    result_payload: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    attempt_count: int
    applying_started_at: str | None
    completed_at: str | None
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _row_to_record(row: sqlite3.Row | None) -> BatchPrepareRequestRecord | None:
    if row is None:
        return None
    payload = None
    raw_payload = row["result_payload_json"]
    if raw_payload:
        try:
            decoded_payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise BatchPrepareStoreDataError("Stored result payload is not valid JSON") from exc
        if not isinstance(decoded_payload, dict):
            raise BatchPrepareStoreDataError("Stored result payload must be a JSON object")
        payload = decoded_payload
    return BatchPrepareRequestRecord(
        id=int(row["id"]),
        client_request_id=str(row["client_request_id"]),
        request_identity=str(row["request_identity"]),
        book_id=int(row["book_id"]),
        from_chapter=int(row["from_chapter"]),
        to_chapter=int(row["to_chapter"]),
        target_phase=str(row["target_phase"]),
        plan_fingerprint=str(row["plan_fingerprint"]),
        state=str(row["state"]),
        job_id=int(row["job_id"]) if row["job_id"] is not None else None,
        result_schema_version=int(row["result_schema_version"]) if row["result_schema_version"] is not None else None,
        result_payload=payload,
        error_code=row["error_code"],
        error_message=row["error_message"],
        attempt_count=int(row["attempt_count"]),
        applying_started_at=row["applying_started_at"],
        completed_at=row["completed_at"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _require_table(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_prepare_requests'"
    ).fetchone()
    if row is None:
        raise BatchPrepareStoreSchemaError(
            "batch_prepare_requests table is not available; schema 13 has not been explicitly activated"
        )


def _safe_json_payload(payload: Mapping[str, Any], *, expected_state: str) -> str:
    if not isinstance(payload, Mapping):
        raise PreparePersistenceContractError("result payload must be a JSON object")
    encoded = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > RESULT_PAYLOAD_MAX_BYTES:
        raise PreparePersistenceContractError("result payload exceeds the 16 KiB storage limit")
    decoded = json.loads(encoded)
    if decoded.get("schema") != RESULT_SCHEMA:
        raise PreparePersistenceContractError("result payload schema is invalid")
    if decoded.get("result_schema_version") != 1:
        raise PreparePersistenceContractError("result_schema_version must be 1")
    if str(decoded.get("state") or "").upper() != expected_state:
        raise PreparePersistenceContractError("result payload state does not match request state")
    build_replay_contract(
        existing_state=expected_state,
        stored_result_payload=decoded,
        error_code=decoded.get("error_code"),
    )
    return encoded


class BatchPrepareRequestStore:
    """Durable request store for PREPARE idempotency records only."""

    def __init__(self, db: Database):
        self.db = db

    def create_or_replay_request(self, request: Mapping[str, Any]) -> BatchPrepareRequestRecord:
        try:
            binding = build_request_binding(request)
        except PreparePersistenceContractError:
            client_request_id = None
            if isinstance(request, Mapping):
                try:
                    client_request_id = normalize_client_request_id(request.get("client_request_id"))
                except PreparePersistenceContractError:
                    client_request_id = None
            if client_request_id:
                with self.db.connect() as connection:
                    _require_table(connection)
                    if self._get_by_client_request_id(connection, client_request_id):
                        raise BatchPrepareRequestConflict(
                            "client_request_id is already bound to a different PREPARE request"
                        )
            raise
        now = utcnow()
        with self.db.transaction() as connection:
            _require_table(connection)
            try:
                cursor = connection.execute(
                    """INSERT INTO batch_prepare_requests(
                        client_request_id,request_identity,book_id,from_chapter,to_chapter,
                        target_phase,plan_fingerprint,state,attempt_count,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        binding.client_request_id,
                        binding.request_identity,
                        binding.book_id,
                        binding.from_chapter,
                        binding.to_chapter,
                        binding.target_phase,
                        binding.plan_fingerprint,
                        STATE_PLANNED,
                        0,
                        now,
                        now,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM batch_prepare_requests WHERE id=?",
                    (int(cursor.lastrowid),),
                ).fetchone()
                return _row_to_record(row)  # type: ignore[return-value]
            except sqlite3.IntegrityError:
                existing = self._get_by_client_request_id(connection, binding.client_request_id)
                if existing and existing.request_identity == binding.request_identity:
                    return existing
                raise BatchPrepareRequestConflict("client_request_id is already bound to a different PREPARE request")

    def get_request(self, request_id: int) -> BatchPrepareRequestRecord | None:
        with self.db.connect() as connection:
            _require_table(connection)
            return _row_to_record(
                connection.execute("SELECT * FROM batch_prepare_requests WHERE id=?", (int(request_id),)).fetchone()
            )

    def get_request_by_client_request_id(self, client_request_id: str) -> BatchPrepareRequestRecord | None:
        binding_id = str(client_request_id or "").strip()
        with self.db.connect() as connection:
            _require_table(connection)
            return self._get_by_client_request_id(connection, binding_id)

    def compare_and_transition_state(
        self,
        request_id: int,
        *,
        expected_state: str,
        next_state: str,
    ) -> BatchPrepareRequestRecord:
        expected = str(expected_state or "").upper()
        target = str(next_state or "").upper()
        if not allowed_transition(expected, target):
            raise BatchPrepareStateConflict(f"Transition {expected}->{target} is not allowed")
        now = utcnow()
        applying_started_at = now if target == STATE_APPLYING else None
        completed_at = now if target in {STATE_APPLIED, STATE_REJECTED, STATE_FAILED} else None
        with self.db.transaction() as connection:
            _require_table(connection)
            cursor = connection.execute(
                """UPDATE batch_prepare_requests
                   SET state=?,
                       applying_started_at=COALESCE(?, applying_started_at),
                       completed_at=COALESCE(?, completed_at),
                       attempt_count=attempt_count + CASE WHEN ?='APPLYING' THEN 1 ELSE 0 END,
                       updated_at=?
                   WHERE id=? AND state=?""",
                (target, applying_started_at, completed_at, target, now, int(request_id), expected),
            )
            if cursor.rowcount != 1:
                raise BatchPrepareStateConflict("Request state changed before transition could be applied")
            row = connection.execute("SELECT * FROM batch_prepare_requests WHERE id=?", (int(request_id),)).fetchone()
            return _row_to_record(row)  # type: ignore[return-value]

    def record_applied_result(
        self,
        request_id: int,
        *,
        job_id: int,
        result_payload: Mapping[str, Any],
    ) -> BatchPrepareRequestRecord:
        return self._record_terminal_result(
            request_id,
            next_state=STATE_APPLIED,
            job_id=int(job_id),
            result_payload=result_payload,
            error_code=None,
            error_message=None,
        )

    def record_rejection(
        self,
        request_id: int,
        *,
        result_payload: Mapping[str, Any],
        error_code: str,
        error_message: str,
    ) -> BatchPrepareRequestRecord:
        return self._record_terminal_result(
            request_id,
            next_state=STATE_REJECTED,
            job_id=None,
            result_payload=result_payload,
            error_code=error_code,
            error_message=error_message,
        )

    def record_failure(
        self,
        request_id: int,
        *,
        result_payload: Mapping[str, Any],
        error_code: str,
        error_message: str,
    ) -> BatchPrepareRequestRecord:
        return self._record_terminal_result(
            request_id,
            next_state=STATE_FAILED,
            job_id=None,
            result_payload=result_payload,
            error_code=error_code,
            error_message=error_message,
        )

    def list_stale_applying_requests(self, *, older_than: str, limit: int = 100) -> list[BatchPrepareRequestRecord]:
        with self.db.connect() as connection:
            _require_table(connection)
            rows = connection.execute(
                """SELECT * FROM batch_prepare_requests
                   WHERE state='APPLYING' AND applying_started_at IS NOT NULL AND applying_started_at < ?
                   ORDER BY applying_started_at ASC, id ASC
                   LIMIT ?""",
                (older_than, int(limit)),
            ).fetchall()
            return [_row_to_record(row) for row in rows if row is not None]  # type: ignore[list-item]

    def build_historical_replay(self, request_id: int) -> dict[str, Any]:
        record = self.get_request(request_id)
        if record is None:
            raise KeyError(f"batch_prepare_request {request_id} not found")
        return build_replay_contract(
            existing_state=record.state,
            stored_result_payload=record.result_payload,
            error_code=record.error_code,
        )

    def _get_by_client_request_id(
        self,
        connection: sqlite3.Connection,
        client_request_id: str,
    ) -> BatchPrepareRequestRecord | None:
        return _row_to_record(
            connection.execute(
                "SELECT * FROM batch_prepare_requests WHERE client_request_id=?",
                (client_request_id,),
            ).fetchone()
        )

    def _record_terminal_result(
        self,
        request_id: int,
        *,
        next_state: str,
        job_id: int | None,
        result_payload: Mapping[str, Any],
        error_code: str | None,
        error_message: str | None,
    ) -> BatchPrepareRequestRecord:
        if error_code is not None and error_code not in FAILURE_CODES:
            raise PreparePersistenceContractError("error_code is not part of the public failure taxonomy")
        if error_message is not None and len(error_message) > 1000:
            raise PreparePersistenceContractError("error_message is too long")
        encoded_payload = _safe_json_payload(result_payload, expected_state=next_state)
        now = utcnow()
        with self.db.transaction() as connection:
            _require_table(connection)
            cursor = connection.execute(
                """UPDATE batch_prepare_requests
                   SET state=?,
                       job_id=?,
                       result_schema_version=1,
                       result_payload_json=?,
                       error_code=?,
                       error_message=?,
                       completed_at=?,
                       updated_at=?
                   WHERE id=? AND state='APPLYING'""",
                (
                    next_state,
                    job_id,
                    encoded_payload,
                    error_code,
                    error_message,
                    now,
                    now,
                    int(request_id),
                ),
            )
            if cursor.rowcount != 1:
                raise BatchPrepareStateConflict("Only APPLYING requests can record terminal results")
            row = connection.execute("SELECT * FROM batch_prepare_requests WHERE id=?", (int(request_id),)).fetchone()
            return _row_to_record(row)  # type: ignore[return-value]


__all__ = [
    "BatchPrepareRequestConflict",
    "BatchPrepareRequestRecord",
    "BatchPrepareRequestStore",
    "BatchPrepareStateConflict",
    "BatchPrepareStoreDataError",
    "BatchPrepareStoreError",
    "BatchPrepareStoreSchemaError",
    "RESULT_PAYLOAD_MAX_BYTES",
]
