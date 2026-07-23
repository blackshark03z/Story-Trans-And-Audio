from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .db import Database, utcnow
from .batch_prepare_transaction_manager import assert_isolated_database_path


OWNED = "OWNED"
COMMITTED = "COMMITTED"
ROLLBACK_CONFIRMED = "ROLLBACK_CONFIRMED"
OUTCOME_AMBIGUOUS = "OUTCOME_AMBIGUOUS"
EXPIRED = "EXPIRED"
TERMINAL_STATES = {COMMITTED, ROLLBACK_CONFIRMED, OUTCOME_AMBIGUOUS, EXPIRED}


class BatchPrepareExecutionAttemptError(RuntimeError):
    pass


class ExecutionAttemptSchemaError(BatchPrepareExecutionAttemptError):
    pass


class ExecutionAttemptConflict(BatchPrepareExecutionAttemptError):
    pass


class ExecutionAttemptOwnerRejected(BatchPrepareExecutionAttemptError):
    pass


@dataclass(frozen=True)
class ExecutionAttemptRecord:
    id: int
    batch_prepare_request_id: int
    request_identity: str
    attempt_generation: int
    owner_token_hash: str
    lease_acquired_at: str
    lease_expires_at: str
    transaction_reference: str
    state: str
    plan_fingerprint: str
    chapter_snapshot_digest: str
    committed_job_link_id: int | None
    committed_at: str | None
    rolled_back_at: str | None
    ambiguity_reason_code: str | None
    created_at: str
    updated_at: str

    def public_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result.pop("owner_token_hash", None)
        return result


@dataclass(frozen=True)
class OwnerLease:
    record: ExecutionAttemptRecord
    owner_token: str = field(repr=False)
    replay: bool = False

    def __repr__(self) -> str:
        return f"OwnerLease(record={self.record.public_dict()!r}, owner_token=<redacted>, replay={self.replay!r})"


def _require_hex64(value: str, field: str) -> str:
    normalized = str(value or "").strip()
    if len(normalized) != 64 or normalized != normalized.lower() or any(c not in "0123456789abcdef" for c in normalized):
        raise ValueError(f"{field} must be a lowercase 64-character hex digest")
    return normalized


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("lease timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _record(row: sqlite3.Row | None) -> ExecutionAttemptRecord | None:
    if row is None:
        return None
    record = ExecutionAttemptRecord(**{field: row[field] for field in ExecutionAttemptRecord.__dataclass_fields__})
    try:
        _require_hex64(record.request_identity, "stored request_identity")
        _require_hex64(record.owner_token_hash, "stored owner_token_hash")
        _require_hex64(record.plan_fingerprint, "stored plan_fingerprint")
        _require_hex64(record.chapter_snapshot_digest, "stored chapter_snapshot_digest")
        _parse_time(record.lease_acquired_at)
        if _parse_time(record.lease_expires_at) <= _parse_time(record.lease_acquired_at):
            raise ValueError("stored lease interval is invalid")
        if record.attempt_generation <= 0 or record.state not in {OWNED, COMMITTED, ROLLBACK_CONFIRMED, OUTCOME_AMBIGUOUS, EXPIRED}:
            raise ValueError("stored execution-attempt state is invalid")
    except ValueError as exc:
        raise ExecutionAttemptSchemaError("stored execution-attempt evidence is corrupt") from exc
    return record


def _require_tables(connection: sqlite3.Connection) -> None:
    required = {"batch_prepare_requests", "batch_prepare_job_links", "batch_prepare_execution_attempts"}
    present = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?,?,?)",
        tuple(sorted(required)),
    )}
    if present != required:
        raise ExecutionAttemptSchemaError("dormant schema 15 tables are required")


class BatchPrepareExecutionAttemptStore:
    def __init__(self, db: Database, *, allow_canonical: bool = False):
        assert_isolated_database_path(
            Path(db.path),
            allow_canonical=allow_canonical,
        )
        self.db = db

    def acquire(
        self,
        *,
        request_id: int,
        request_identity: str,
        plan_fingerprint: str,
        chapter_snapshot_digest: str,
        lease_seconds: int = 120,
        transaction_reference: str | None = None,
        replay_owner_token: str | None = None,
        now: str | None = None,
    ) -> OwnerLease:
        identity = _require_hex64(request_identity, "request_identity")
        fingerprint = _require_hex64(plan_fingerprint, "plan_fingerprint")
        digest = _require_hex64(chapter_snapshot_digest, "chapter_snapshot_digest")
        if not 1 <= int(lease_seconds) <= 3600:
            raise ValueError("lease_seconds must be between 1 and 3600")
        acquired = _parse_time(now or utcnow())
        with self.db.transaction() as connection:
            _require_tables(connection)
            request = connection.execute("SELECT * FROM batch_prepare_requests WHERE id=?", (int(request_id),)).fetchone()
            if request is None or request["request_identity"] != identity:
                raise ExecutionAttemptOwnerRejected("request identity is not authoritative")
            if request["state"] != "APPLYING" or request["target_phase"] != "PREPARE":
                raise ExecutionAttemptOwnerRejected("request is not an APPLYING PREPARE request")
            if request["plan_fingerprint"] != fingerprint:
                raise ExecutionAttemptOwnerRejected("request plan fingerprint changed")
            current = _record(connection.execute(
                "SELECT * FROM batch_prepare_execution_attempts WHERE batch_prepare_request_id=? ORDER BY attempt_generation DESC LIMIT 1",
                (int(request_id),),
            ).fetchone())
            if current and current.state == OWNED:
                if (
                    replay_owner_token
                    and hmac.compare_digest(current.owner_token_hash, _token_hash(replay_owner_token))
                    and current.plan_fingerprint == fingerprint
                    and current.chapter_snapshot_digest == digest
                    and _parse_time(current.lease_expires_at) > acquired
                    and (transaction_reference is None or transaction_reference == current.transaction_reference)
                ):
                    return OwnerLease(current, replay_owner_token, replay=True)
                if _parse_time(current.lease_expires_at) > acquired:
                    raise ExecutionAttemptConflict("request already has an unexpired owner")
                connection.execute(
                    "UPDATE batch_prepare_execution_attempts SET state='EXPIRED',updated_at=? WHERE id=? AND state='OWNED'",
                    (acquired.isoformat(), current.id),
                )
            elif current and current.state != EXPIRED:
                raise ExecutionAttemptConflict("terminal execution attempt requires recovery or a fresh request")
            generation = (current.attempt_generation if current else 0) + 1
            raw_token = secrets.token_urlsafe(32)
            reference = str(transaction_reference or f"prepare-{int(request_id)}-g{generation}-{secrets.token_hex(8)}").strip()
            if not 1 <= len(reference) <= 200:
                raise ValueError("transaction_reference must contain 1-200 characters")
            expires = acquired + timedelta(seconds=int(lease_seconds))
            try:
                cursor = connection.execute(
                    """INSERT INTO batch_prepare_execution_attempts(
                        batch_prepare_request_id,request_identity,attempt_generation,owner_token_hash,
                        lease_acquired_at,lease_expires_at,transaction_reference,state,plan_fingerprint,
                        chapter_snapshot_digest,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        int(request_id), identity, generation, _token_hash(raw_token), acquired.isoformat(),
                        expires.isoformat(), reference, OWNED, fingerprint, digest,
                        acquired.isoformat(), acquired.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ExecutionAttemptConflict("ownership acquisition lost a database race") from exc
            result = _record(connection.execute(
                "SELECT * FROM batch_prepare_execution_attempts WHERE id=?", (int(cursor.lastrowid),)
            ).fetchone())
            return OwnerLease(result, raw_token)  # type: ignore[arg-type]

    def get_current(self, request_id: int) -> ExecutionAttemptRecord | None:
        with self.db.connect() as connection:
            _require_tables(connection)
            return _record(connection.execute(
                "SELECT * FROM batch_prepare_execution_attempts WHERE batch_prepare_request_id=? ORDER BY attempt_generation DESC LIMIT 1",
                (int(request_id),),
            ).fetchone())

    def validate_owner_in_connection(
        self,
        connection: sqlite3.Connection,
        *,
        request_id: int,
        request_identity: str,
        generation: int,
        owner_token: str,
        plan_fingerprint: str,
        chapter_snapshot_digest: str,
        transaction_reference: str,
        now: str | None = None,
        allow_committed_recovery: bool = False,
    ) -> ExecutionAttemptRecord:
        _require_tables(connection)
        record = _record(connection.execute(
            "SELECT * FROM batch_prepare_execution_attempts WHERE batch_prepare_request_id=? AND attempt_generation=?",
            (int(request_id), int(generation)),
        ).fetchone())
        if record is None:
            raise ExecutionAttemptOwnerRejected("owner generation does not exist")
        expected_state = {OWNED, COMMITTED} if allow_committed_recovery else {OWNED}
        valid = (
            record.state in expected_state
            and record.request_identity == _require_hex64(request_identity, "request_identity")
            and hmac.compare_digest(record.owner_token_hash, _token_hash(str(owner_token)))
            and record.plan_fingerprint == _require_hex64(plan_fingerprint, "plan_fingerprint")
            and record.chapter_snapshot_digest == _require_hex64(chapter_snapshot_digest, "chapter_snapshot_digest")
            and record.transaction_reference == str(transaction_reference)
        )
        if not valid:
            raise ExecutionAttemptOwnerRejected("owner token, fence, or immutable binding is stale")
        if record.state == OWNED and _parse_time(record.lease_expires_at) <= _parse_time(now or utcnow()):
            raise ExecutionAttemptOwnerRejected("owner lease expired")
        return record

    def renew_lease(
        self,
        *,
        request_id: int,
        generation: int,
        owner_token: str,
        lease_seconds: int = 120,
        now: str | None = None,
    ) -> ExecutionAttemptRecord:
        if not 1 <= int(lease_seconds) <= 3600:
            raise ValueError("lease_seconds must be between 1 and 3600")
        current_time = _parse_time(now or utcnow())
        with self.db.transaction() as connection:
            record = self.get_by_generation_in_connection(connection, request_id, generation)
            if record.state != OWNED or not hmac.compare_digest(record.owner_token_hash, _token_hash(owner_token)):
                raise ExecutionAttemptOwnerRejected("only the current owner can renew the lease")
            if _parse_time(record.lease_expires_at) <= current_time:
                raise ExecutionAttemptOwnerRejected("expired owners cannot renew")
            expires = current_time + timedelta(seconds=int(lease_seconds))
            connection.execute(
                "UPDATE batch_prepare_execution_attempts SET lease_expires_at=?,updated_at=? WHERE id=? AND state='OWNED'",
                (expires.isoformat(), current_time.isoformat(), record.id),
            )
            return self.get_by_generation_in_connection(connection, request_id, generation)

    def get_by_generation_in_connection(
        self, connection: sqlite3.Connection, request_id: int, generation: int
    ) -> ExecutionAttemptRecord:
        _require_tables(connection)
        result = _record(connection.execute(
            "SELECT * FROM batch_prepare_execution_attempts WHERE batch_prepare_request_id=? AND attempt_generation=?",
            (int(request_id), int(generation)),
        ).fetchone())
        if result is None:
            raise KeyError("execution attempt not found")
        return result

    def mark_committed_in_connection(
        self,
        connection: sqlite3.Connection,
        *,
        request_id: int,
        generation: int,
        job_link_id: int,
        committed_at: str | None = None,
    ) -> ExecutionAttemptRecord:
        when = committed_at or utcnow()
        attempt = self.get_by_generation_in_connection(connection, request_id, generation)
        link = connection.execute(
            "SELECT * FROM batch_prepare_job_links WHERE id=?", (int(job_link_id),)
        ).fetchone()
        if (
            link is None
            or int(link["batch_prepare_request_id"]) != int(request_id)
            or link["request_identity"] != attempt.request_identity
            or link["plan_fingerprint"] != attempt.plan_fingerprint
            or link["chapter_snapshot_digest"] != attempt.chapter_snapshot_digest
            or link["transaction_reference"] != attempt.transaction_reference
        ):
            raise ExecutionAttemptConflict("committed linkage does not match the owned execution attempt")
        updated = connection.execute(
            """UPDATE batch_prepare_execution_attempts
               SET state='COMMITTED',committed_job_link_id=?,committed_at=?,updated_at=?
               WHERE batch_prepare_request_id=? AND attempt_generation=? AND state='OWNED'""",
            (int(job_link_id), when, when, int(request_id), int(generation)),
        )
        if updated.rowcount != 1:
            raise ExecutionAttemptConflict("execution attempt is no longer owned")
        return self.get_by_generation_in_connection(connection, request_id, generation)

    def mark_rollback_confirmed(self, *, request_id: int, generation: int, rolled_back_at: str | None = None) -> ExecutionAttemptRecord:
        return self._mark_terminal(request_id, generation, ROLLBACK_CONFIRMED, rolled_back_at=rolled_back_at or utcnow())

    def mark_outcome_ambiguous(self, *, request_id: int, generation: int, reason_code: str) -> ExecutionAttemptRecord:
        reason = str(reason_code or "").strip()
        if not 1 <= len(reason) <= 100:
            raise ValueError("ambiguity reason code must contain 1-100 characters")
        return self._mark_terminal(request_id, generation, OUTCOME_AMBIGUOUS, ambiguity_reason_code=reason)

    def _mark_terminal(self, request_id: int, generation: int, state: str, **values: str) -> ExecutionAttemptRecord:
        with self.db.transaction() as connection:
            now = utcnow()
            if state == ROLLBACK_CONFIRMED:
                sql = "UPDATE batch_prepare_execution_attempts SET state=?,rolled_back_at=?,updated_at=? WHERE batch_prepare_request_id=? AND attempt_generation=? AND state='OWNED'"
                params = (state, values["rolled_back_at"], now, int(request_id), int(generation))
            else:
                sql = "UPDATE batch_prepare_execution_attempts SET state=?,ambiguity_reason_code=?,updated_at=? WHERE batch_prepare_request_id=? AND attempt_generation=? AND state='OWNED'"
                params = (state, values["ambiguity_reason_code"], now, int(request_id), int(generation))
            if connection.execute(sql, params).rowcount != 1:
                raise ExecutionAttemptConflict("terminal execution attempts are immutable")
            return self.get_by_generation_in_connection(connection, request_id, generation)

    def list_expired(self, *, now: str | None = None) -> list[ExecutionAttemptRecord]:
        cutoff = now or utcnow()
        with self.db.connect() as connection:
            _require_tables(connection)
            return [_record(row) for row in connection.execute(
                "SELECT * FROM batch_prepare_execution_attempts WHERE state='OWNED' AND lease_expires_at<=? ORDER BY lease_expires_at,id",
                (cutoff,),
            ).fetchall()]  # type: ignore[list-item]

    def build_recovery_evidence(self, request_id: int, generation: int) -> dict[str, Any]:
        with self.db.connect() as connection:
            attempt = self.get_by_generation_in_connection(connection, request_id, generation)
            link = None
            if attempt.committed_job_link_id is not None:
                link = connection.execute(
                    "SELECT * FROM batch_prepare_job_links WHERE id=?", (attempt.committed_job_link_id,)
                ).fetchone()
            return {
                "schema": "story-audio-batch-prepare-execution-recovery/v1",
                "attempt": attempt.public_dict(),
                "linkage": dict(link) if link else None,
            }


__all__ = [
    "BatchPrepareExecutionAttemptError",
    "BatchPrepareExecutionAttemptStore",
    "COMMITTED",
    "EXPIRED",
    "ExecutionAttemptConflict",
    "ExecutionAttemptOwnerRejected",
    "ExecutionAttemptRecord",
    "ExecutionAttemptSchemaError",
    "OUTCOME_AMBIGUOUS",
    "OWNED",
    "OwnerLease",
    "ROLLBACK_CONFIRMED",
]
