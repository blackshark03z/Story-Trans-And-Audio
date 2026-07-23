from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .batch_prepare_persistence_contract import STATE_APPLIED, STATE_APPLYING
from .batch_prepare_transaction_manager import assert_isolated_database_path
from .db import Database, utcnow


LINKAGE_TABLE = "batch_prepare_job_links"
LINKAGE_SCHEMA_VERSION = 1
TRANSACTION_EVIDENCE_VERSION = 1
PREPARED_STATUS = "prepared"

REQUEST_LINK_CONFLICT = "REQUEST_LINK_CONFLICT"
JOB_LINK_CONFLICT = "JOB_LINK_CONFLICT"
LINKAGE_EVIDENCE_CONFLICT = "LINKAGE_EVIDENCE_CONFLICT"
LINKAGE_RECORD_CORRUPT = "LINKAGE_RECORD_CORRUPT"
LINKAGE_TABLE_MISSING = "LINKAGE_TABLE_MISSING"
PARENT_REQUEST_INVALID = "PARENT_REQUEST_INVALID"
PARENT_JOB_INVALID = "PARENT_JOB_INVALID"

HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")


class BatchPrepareJobLinkError(RuntimeError):
    """Base error for durable request-to-Job linkage storage."""

    code = "BATCH_PREPARE_JOB_LINK_ERROR"


class BatchPrepareJobLinkSchemaError(BatchPrepareJobLinkError):
    code = LINKAGE_TABLE_MISSING


class BatchPrepareJobLinkConflict(BatchPrepareJobLinkError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class BatchPrepareJobLinkValidationError(BatchPrepareJobLinkError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class BatchPrepareJobLinkCorruptError(BatchPrepareJobLinkValidationError):
    def __init__(self, message: str):
        super().__init__(LINKAGE_RECORD_CORRUPT, message)


@dataclass(frozen=True)
class BatchPrepareJobLinkInput:
    batch_prepare_request_id: int
    request_identity: str
    job_id: int
    plan_fingerprint: str
    chapter_snapshot_digest: str
    expected_chapter_count: int
    actual_chapter_count: int
    transaction_committed_at: str
    prepared_status: str = PREPARED_STATUS
    transaction_evidence_version: int = TRANSACTION_EVIDENCE_VERSION
    worker_woken: bool = False
    render_started: bool = False
    result_schema_version: int = LINKAGE_SCHEMA_VERSION
    transaction_reference: str | None = None
    evidence_source: str = "future_prepare_transaction"


@dataclass(frozen=True)
class BatchPrepareJobLinkRecord:
    id: int
    batch_prepare_request_id: int
    request_identity: str
    job_id: int
    plan_fingerprint: str
    chapter_snapshot_digest: str
    expected_chapter_count: int
    actual_chapter_count: int
    prepared_status: str
    transaction_evidence_version: int
    transaction_committed_at: str
    worker_woken: bool
    render_started: bool
    result_schema_version: int
    transaction_reference: str | None
    evidence_source: str
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BatchPrepareJobLinkResult:
    record: BatchPrepareJobLinkRecord
    replay: bool


def _assert_not_canonical(path: Path, *, allow_canonical: bool = False) -> None:
    try:
        assert_isolated_database_path(path, allow_canonical=allow_canonical)
    except RuntimeError:
        raise BatchPrepareJobLinkValidationError(
            PARENT_JOB_INVALID,
            "batch prepare job link store is isolated-only and must not target the canonical DB",
        ) from None


def _require_hex64(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not HEX_64_RE.match(value):
        raise BatchPrepareJobLinkValidationError(PARENT_REQUEST_INVALID, f"{field_name} must be lowercase SHA-256 hex")
    return value


def _normalize_input(raw: BatchPrepareJobLinkInput | Mapping[str, Any]) -> BatchPrepareJobLinkInput:
    if isinstance(raw, BatchPrepareJobLinkInput):
        item = raw
    elif isinstance(raw, Mapping):
        item = BatchPrepareJobLinkInput(**dict(raw))
    else:
        raise BatchPrepareJobLinkValidationError(PARENT_REQUEST_INVALID, "linkage input must be an object")
    if int(item.batch_prepare_request_id) <= 0:
        raise BatchPrepareJobLinkValidationError(PARENT_REQUEST_INVALID, "request id must be positive")
    if int(item.job_id) <= 0:
        raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "job id must be positive")
    _require_hex64(item.request_identity, "request_identity")
    _require_hex64(item.plan_fingerprint, "plan_fingerprint")
    _require_hex64(item.chapter_snapshot_digest, "chapter_snapshot_digest")
    if int(item.expected_chapter_count) <= 0 or int(item.actual_chapter_count) <= 0:
        raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "chapter counts must be positive")
    if int(item.expected_chapter_count) != int(item.actual_chapter_count):
        raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "chapter counts must match")
    if item.prepared_status != PREPARED_STATUS:
        raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "prepared_status must be prepared")
    if int(item.transaction_evidence_version) != TRANSACTION_EVIDENCE_VERSION:
        raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "unsupported transaction evidence version")
    if not str(item.transaction_committed_at or "").strip():
        raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "transaction committed timestamp is required")
    if bool(item.worker_woken):
        raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "worker_woken must be false")
    if bool(item.render_started):
        raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "render_started must be false")
    if int(item.result_schema_version) != LINKAGE_SCHEMA_VERSION:
        raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "unsupported linkage result schema version")
    if item.transaction_reference is not None and len(str(item.transaction_reference)) > 200:
        raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "transaction reference is too long")
    if not str(item.evidence_source or "").strip() or len(str(item.evidence_source)) > 200:
        raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "evidence source is invalid")
    return item


def _require_table(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (LINKAGE_TABLE,),
    ).fetchone()
    if row is None:
        raise BatchPrepareJobLinkSchemaError(
            "batch_prepare_job_links table is not available; schema 14 has not been explicitly activated"
        )


def _row_to_record(row: sqlite3.Row | None) -> BatchPrepareJobLinkRecord | None:
    if row is None:
        return None
    record = BatchPrepareJobLinkRecord(
        id=int(row["id"]),
        batch_prepare_request_id=int(row["batch_prepare_request_id"]),
        request_identity=str(row["request_identity"]),
        job_id=int(row["job_id"]),
        plan_fingerprint=str(row["plan_fingerprint"]),
        chapter_snapshot_digest=str(row["chapter_snapshot_digest"]),
        expected_chapter_count=int(row["expected_chapter_count"]),
        actual_chapter_count=int(row["actual_chapter_count"]),
        prepared_status=str(row["prepared_status"]),
        transaction_evidence_version=int(row["transaction_evidence_version"]),
        transaction_committed_at=str(row["transaction_committed_at"]),
        worker_woken=bool(int(row["worker_woken"])),
        render_started=bool(int(row["render_started"])),
        result_schema_version=int(row["result_schema_version"]),
        transaction_reference=row["transaction_reference"],
        evidence_source=str(row["evidence_source"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
    _validate_stored_record(record)
    return record


def _validate_stored_record(record: BatchPrepareJobLinkRecord) -> None:
    try:
        _require_hex64(record.request_identity, "request_identity")
        _require_hex64(record.plan_fingerprint, "plan_fingerprint")
        _require_hex64(record.chapter_snapshot_digest, "chapter_snapshot_digest")
    except BatchPrepareJobLinkValidationError as exc:
        raise BatchPrepareJobLinkCorruptError(str(exc)) from exc
    if record.expected_chapter_count <= 0 or record.actual_chapter_count <= 0:
        raise BatchPrepareJobLinkCorruptError("stored linkage has non-positive chapter count")
    if record.expected_chapter_count != record.actual_chapter_count:
        raise BatchPrepareJobLinkCorruptError("stored linkage count mismatch")
    if record.prepared_status != PREPARED_STATUS:
        raise BatchPrepareJobLinkCorruptError("stored linkage is not prepared")
    if record.transaction_evidence_version != TRANSACTION_EVIDENCE_VERSION:
        raise BatchPrepareJobLinkCorruptError("stored linkage evidence version is unsupported")
    if not record.transaction_committed_at:
        raise BatchPrepareJobLinkCorruptError("stored linkage missing committed timestamp")
    if record.worker_woken or record.render_started:
        raise BatchPrepareJobLinkCorruptError("stored linkage contradicts no-render evidence")
    if record.result_schema_version != LINKAGE_SCHEMA_VERSION:
        raise BatchPrepareJobLinkCorruptError("stored linkage result schema is unsupported")


def _same_evidence(record: BatchPrepareJobLinkRecord, item: BatchPrepareJobLinkInput) -> bool:
    return (
        record.batch_prepare_request_id == int(item.batch_prepare_request_id)
        and record.request_identity == item.request_identity
        and record.job_id == int(item.job_id)
        and record.plan_fingerprint == item.plan_fingerprint
        and record.chapter_snapshot_digest == item.chapter_snapshot_digest
        and record.expected_chapter_count == int(item.expected_chapter_count)
        and record.actual_chapter_count == int(item.actual_chapter_count)
        and record.prepared_status == item.prepared_status
        and record.transaction_evidence_version == int(item.transaction_evidence_version)
        and record.transaction_committed_at == item.transaction_committed_at
        and record.worker_woken is bool(item.worker_woken)
        and record.render_started is bool(item.render_started)
        and record.result_schema_version == int(item.result_schema_version)
        and record.transaction_reference == item.transaction_reference
        and record.evidence_source == item.evidence_source
    )


class BatchPrepareJobLinkStore:
    """Immutable request-to-Job linkage store for isolated schema-14 validation."""

    def __init__(self, db: Database, *, allow_canonical: bool = False):
        self.db = db
        self.allow_canonical = bool(allow_canonical)

    def create_or_replay(
        self,
        linkage: BatchPrepareJobLinkInput | Mapping[str, Any],
    ) -> BatchPrepareJobLinkResult:
        _assert_not_canonical(
            self.db.path,
            allow_canonical=self.allow_canonical,
        )
        item = _normalize_input(linkage)
        with self.db.transaction() as connection:
            return self.create_or_replay_in_connection(connection, item)

    def create_or_replay_in_connection(
        self,
        connection: sqlite3.Connection,
        linkage: BatchPrepareJobLinkInput | Mapping[str, Any],
    ) -> BatchPrepareJobLinkResult:
        """Write linkage using the caller's active transaction without committing it."""
        _assert_not_canonical(
            self.db.path,
            allow_canonical=self.allow_canonical,
        )
        if not connection.in_transaction:
            raise BatchPrepareJobLinkValidationError(
                PARENT_JOB_INVALID,
                "caller-owned linkage transaction is not active",
            )
        item = _normalize_input(linkage)
        now = utcnow()
        _require_table(connection)
        existing = self._get_existing_for_input(connection, item)
        if existing:
            return BatchPrepareJobLinkResult(self._classify_existing(existing, item), replay=True)
        self._validate_parent_request(connection, item, allow_applied_replay=False)
        self._validate_parent_job(connection, item)
        try:
            cursor = connection.execute(
                """INSERT INTO batch_prepare_job_links(
                    batch_prepare_request_id,request_identity,job_id,plan_fingerprint,
                    chapter_snapshot_digest,expected_chapter_count,actual_chapter_count,
                    prepared_status,transaction_evidence_version,transaction_committed_at,
                    worker_woken,render_started,result_schema_version,transaction_reference,
                    evidence_source,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    int(item.batch_prepare_request_id), item.request_identity, int(item.job_id),
                    item.plan_fingerprint, item.chapter_snapshot_digest,
                    int(item.expected_chapter_count), int(item.actual_chapter_count),
                    item.prepared_status, int(item.transaction_evidence_version),
                    item.transaction_committed_at, 1 if item.worker_woken else 0,
                    1 if item.render_started else 0, int(item.result_schema_version),
                    item.transaction_reference, item.evidence_source, now, now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM batch_prepare_job_links WHERE id=?",
                (int(cursor.lastrowid),),
            ).fetchone()
            return BatchPrepareJobLinkResult(_row_to_record(row), replay=False)  # type: ignore[arg-type]
        except sqlite3.IntegrityError:
            existing = self._get_existing_for_input(connection, item)
            if existing:
                return BatchPrepareJobLinkResult(self._classify_existing(existing, item), replay=True)
            raise BatchPrepareJobLinkConflict(
                LINKAGE_EVIDENCE_CONFLICT,
                "linkage insert lost a database uniqueness race",
            )

    def get_by_request_id(self, request_id: int) -> BatchPrepareJobLinkRecord | None:
        with self.db.connect() as connection:
            _require_table(connection)
            return _row_to_record(
                connection.execute(
                    "SELECT * FROM batch_prepare_job_links WHERE batch_prepare_request_id=?",
                    (int(request_id),),
                ).fetchone()
            )

    def get_by_request_identity(self, request_identity: str) -> BatchPrepareJobLinkRecord | None:
        _require_hex64(request_identity, "request_identity")
        with self.db.connect() as connection:
            _require_table(connection)
            return _row_to_record(
                connection.execute(
                    "SELECT * FROM batch_prepare_job_links WHERE request_identity=?",
                    (request_identity,),
                ).fetchone()
            )

    def get_by_job_id(self, job_id: int) -> BatchPrepareJobLinkRecord | None:
        with self.db.connect() as connection:
            _require_table(connection)
            return _row_to_record(
                connection.execute("SELECT * FROM batch_prepare_job_links WHERE job_id=?", (int(job_id),)).fetchone()
            )

    def build_historical_linkage_evidence(self, request_id: int) -> dict[str, Any]:
        record = self.get_by_request_id(request_id)
        if record is None:
            raise KeyError(f"batch_prepare_job_link for request {request_id} not found")
        return {
            "schema": "story-audio-batch-prepare-job-linkage-evidence/v1",
            "result_schema_version": record.result_schema_version,
            "request_identity": record.request_identity,
            "job_id": record.job_id,
            "prepared_status": record.prepared_status,
            "expected_chapter_count": record.expected_chapter_count,
            "actual_chapter_count": record.actual_chapter_count,
            "chapter_snapshot_digest": record.chapter_snapshot_digest,
            "plan_fingerprint": record.plan_fingerprint,
            "transaction_evidence_version": record.transaction_evidence_version,
            "transaction_committed_at": record.transaction_committed_at,
            "worker_woken": record.worker_woken,
            "render_started": record.render_started,
            "replay_source": "durable_request_job_linkage",
        }

    def validate_existing_linkage_consistency(self, request_id: int) -> BatchPrepareJobLinkRecord:
        record = self.get_by_request_id(request_id)
        if record is None:
            raise KeyError(f"batch_prepare_job_link for request {request_id} not found")
        with self.db.connect() as connection:
            _require_table(connection)
            self._validate_parent_request(connection, _input_from_record(record), allow_applied_replay=True)
            self._validate_parent_job(connection, _input_from_record(record))
        return record

    def _get_existing_for_input(
        self,
        connection: sqlite3.Connection,
        item: BatchPrepareJobLinkInput,
    ) -> BatchPrepareJobLinkRecord | None:
        rows = connection.execute(
            """SELECT * FROM batch_prepare_job_links
               WHERE batch_prepare_request_id=? OR request_identity=? OR job_id=?
               ORDER BY id""",
            (int(item.batch_prepare_request_id), item.request_identity, int(item.job_id)),
        ).fetchall()
        if len(rows) > 1:
            raise BatchPrepareJobLinkCorruptError("multiple stored linkages match one linkage input")
        return _row_to_record(rows[0]) if rows else None

    def _classify_existing(
        self,
        record: BatchPrepareJobLinkRecord,
        item: BatchPrepareJobLinkInput,
    ) -> BatchPrepareJobLinkRecord:
        if _same_evidence(record, item):
            return record
        if record.batch_prepare_request_id == int(item.batch_prepare_request_id) or record.request_identity == item.request_identity:
            if record.job_id != int(item.job_id):
                raise BatchPrepareJobLinkConflict(REQUEST_LINK_CONFLICT, "request is already linked to another Job")
            raise BatchPrepareJobLinkConflict(LINKAGE_EVIDENCE_CONFLICT, "request/Job linkage evidence differs")
        if record.job_id == int(item.job_id):
            raise BatchPrepareJobLinkConflict(JOB_LINK_CONFLICT, "Job is already linked to another request")
        raise BatchPrepareJobLinkConflict(LINKAGE_EVIDENCE_CONFLICT, "linkage conflicts with existing evidence")

    def _validate_parent_request(
        self,
        connection: sqlite3.Connection,
        item: BatchPrepareJobLinkInput,
        *,
        allow_applied_replay: bool,
    ) -> None:
        row = connection.execute(
            "SELECT * FROM batch_prepare_requests WHERE id=?",
            (int(item.batch_prepare_request_id),),
        ).fetchone()
        if row is None:
            raise BatchPrepareJobLinkValidationError(PARENT_REQUEST_INVALID, "parent request does not exist")
        if row["request_identity"] != item.request_identity:
            raise BatchPrepareJobLinkValidationError(PARENT_REQUEST_INVALID, "parent request identity mismatch")
        if row["target_phase"] != "PREPARE":
            raise BatchPrepareJobLinkValidationError(PARENT_REQUEST_INVALID, "parent request target phase is not PREPARE")
        if row["plan_fingerprint"] != item.plan_fingerprint:
            raise BatchPrepareJobLinkValidationError(PARENT_REQUEST_INVALID, "parent request fingerprint mismatch")
        allowed_states = {STATE_APPLYING}
        if allow_applied_replay:
            allowed_states.add(STATE_APPLIED)
        if row["state"] not in allowed_states:
            raise BatchPrepareJobLinkValidationError(PARENT_REQUEST_INVALID, "parent request is not APPLYING")

    def _validate_parent_job(self, connection: sqlite3.Connection, item: BatchPrepareJobLinkInput) -> None:
        job = connection.execute("SELECT * FROM jobs WHERE id=?", (int(item.job_id),)).fetchone()
        if job is None:
            raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "parent Job does not exist")
        if job["status"] != PREPARED_STATUS:
            raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "parent Job is not prepared")
        request = connection.execute(
            "SELECT book_id,from_chapter,to_chapter FROM batch_prepare_requests WHERE id=?",
            (int(item.batch_prepare_request_id),),
        ).fetchone()
        if request is not None:
            if int(job["book_id"]) != int(request["book_id"]):
                raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "parent Job book mismatch")
            if int(job["from_chapter"]) != int(request["from_chapter"]) or int(job["to_chapter"]) != int(request["to_chapter"]):
                raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "parent Job scope mismatch")
        if job["started_at"] is not None or job["finished_at"] is not None:
            raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "parent Job has start/finish evidence")
        rows = connection.execute(
            "SELECT chapter_id FROM job_chapters WHERE job_id=? ORDER BY sequence,id",
            (int(item.job_id),),
        ).fetchall()
        chapter_count = len(rows)
        if chapter_count != int(item.expected_chapter_count):
            raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "JobChapter count mismatch")
        chapter_ids = [int(row["chapter_id"]) for row in rows]
        if len(chapter_ids) != len(set(chapter_ids)):
            raise BatchPrepareJobLinkValidationError(PARENT_JOB_INVALID, "duplicate JobChapter chapter binding")


def _input_from_record(record: BatchPrepareJobLinkRecord) -> BatchPrepareJobLinkInput:
    return BatchPrepareJobLinkInput(
        batch_prepare_request_id=record.batch_prepare_request_id,
        request_identity=record.request_identity,
        job_id=record.job_id,
        plan_fingerprint=record.plan_fingerprint,
        chapter_snapshot_digest=record.chapter_snapshot_digest,
        expected_chapter_count=record.expected_chapter_count,
        actual_chapter_count=record.actual_chapter_count,
        transaction_committed_at=record.transaction_committed_at,
        prepared_status=record.prepared_status,
        transaction_evidence_version=record.transaction_evidence_version,
        worker_woken=record.worker_woken,
        render_started=record.render_started,
        result_schema_version=record.result_schema_version,
        transaction_reference=record.transaction_reference,
        evidence_source=record.evidence_source,
    )


__all__ = [
    "JOB_LINK_CONFLICT",
    "LINKAGE_EVIDENCE_CONFLICT",
    "LINKAGE_RECORD_CORRUPT",
    "LINKAGE_TABLE_MISSING",
    "PARENT_JOB_INVALID",
    "PARENT_REQUEST_INVALID",
    "REQUEST_LINK_CONFLICT",
    "BatchPrepareJobLinkConflict",
    "BatchPrepareJobLinkCorruptError",
    "BatchPrepareJobLinkError",
    "BatchPrepareJobLinkInput",
    "BatchPrepareJobLinkRecord",
    "BatchPrepareJobLinkResult",
    "BatchPrepareJobLinkSchemaError",
    "BatchPrepareJobLinkStore",
    "BatchPrepareJobLinkValidationError",
]
