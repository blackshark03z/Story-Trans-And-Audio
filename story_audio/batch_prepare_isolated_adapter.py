from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .casting import CHUNKER_VERSION, validate_approved_plan
from .batch_prepare_execution_attempt_store import (
    COMMITTED,
    EXPIRED,
    OUTCOME_AMBIGUOUS,
    OWNED,
    ROLLBACK_CONFIRMED,
    BatchPrepareExecutionAttemptStore,
)
from .batch_prepare_isolated_transaction_service import (
    AmbiguousPrepareOutcome,
    BatchPrepareIsolatedTransactionService,
    IsolatedPrepareResult,
    PrepareConflict,
)
from .batch_prepare_orchestrator import (
    FUTURE_AMBIGUOUS,
    FUTURE_FAILED_RETRYABLE,
    FUTURE_IN_PROGRESS,
    FUTURE_REJECTED,
    FUTURE_SUCCESS,
    FuturePrepareResult,
)
from .batch_prepare_persistence_contract import PrepareRequestBinding
from .batch_prepare_store import BatchPrepareRequestRecord
from .batch_prepare_transaction_manager import (
    BatchPrepareTransactionManager,
    IsolatedTransactionBusy,
    assert_isolated_database_path,
)
from .batch_prepare_transaction_revalidator import (
    AuthoritativeChapterSnapshot,
    AuthoritativeInputRejected,
    PrepareTransactionSnapshot,
    chapter_snapshot_digest,
)
from .config import Settings, canonical_production_db_path
from .db import Database, utcnow
from .storage import ContentStore


ADAPTER_SCHEMA = "story-audio-batch-prepare-isolated-adapter/v1"
RESULT_EVIDENCE_SCHEMA = "story-audio-batch-prepare-committed-evidence/v1"
OPERATOR_START_SEPARATELY = "START_RENDER_SEPARATELY"
OPERATOR_WAIT = "WAIT_AND_RETRY_STATUS"
OPERATOR_REVIEW = "REVIEW_AMBIGUOUS_PREPARE"
TEMPORARY_MARKER = ".story-audio-phase10-temporary"
MAX_PREPARE_CHAPTERS = 256


class IsolatedAdapterError(RuntimeError):
    pass


class IsolatedAdapterEvidenceError(IsolatedAdapterError):
    pass


def assert_phase10_temporary_database(
    db_path: Path,
    temporary_root: Path,
    *,
    allow_canonical: bool = False,
) -> tuple[Path, Path]:
    database = assert_isolated_database_path(
        Path(db_path),
        allow_canonical=allow_canonical,
    )
    root = Path(temporary_root).expanduser().resolve(strict=False)
    canonical_db = canonical_production_db_path().resolve(strict=False)
    canonical_data = canonical_production_db_path().parent.resolve(strict=False)
    if allow_canonical:
        if database != canonical_db or root != canonical_data:
            raise IsolatedAdapterError(
                "Canonical PREPARE authority requires the exact canonical DB and data root"
            )
        return database, root
    if database != root and root not in database.parents:
        raise IsolatedAdapterError("Phase 10 database must be inside its explicit temporary root")
    if root == canonical_data or canonical_data in root.parents:
        raise IsolatedAdapterError("Phase 10 temporary root cannot be inside canonical production data")
    marker = root / TEMPORARY_MARKER
    if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != "PHASE10_TEMPORARY_ONLY":
        raise IsolatedAdapterError("Phase 10 temporary root marker is missing or invalid")
    return database, root


def render_settings_snapshot(settings: Settings) -> dict[str, Any]:
    return {
        "tts_mode": settings.tts_mode,
        "temperature": settings.tts_temperature,
        "top_k": settings.tts_top_k,
        "max_chars": settings.tts_max_chars,
        "target_chars": settings.tts_target_chars,
        "silence_seconds": settings.tts_silence_seconds,
        "gemini_model": settings.gemini_model,
        "gemini_prompt_version": settings.gemini_prompt_version,
        "engine_version": f"vieneu:{settings.tts_mode}",
        "chunker_version": CHUNKER_VERSION,
    }


class AuthoritativeSnapshotProvider(Protocol):
    def __call__(
        self,
        *,
        binding: PrepareRequestBinding,
        plan: Mapping[str, Any],
    ) -> tuple[AuthoritativeChapterSnapshot, ...]:
        ...


LifecycleHook = Callable[[str, Mapping[str, Any]], None]


@dataclass(frozen=True)
class ExecutionAcquisition:
    request_id: int
    request_identity: str
    plan_fingerprint: str
    chapter_snapshot_digest: str
    chapters: tuple[AuthoritativeChapterSnapshot, ...]
    generation: int
    transaction_reference: str
    owner_token: str = field(repr=False)

    def __repr__(self) -> str:
        return (
            "ExecutionAcquisition("
            f"request_id={self.request_id!r}, request_identity={self.request_identity!r}, "
            f"plan_fingerprint={self.plan_fingerprint!r}, "
            f"chapter_snapshot_digest={self.chapter_snapshot_digest!r}, "
            f"chapters={self.chapters!r}, generation={self.generation!r}, "
            f"transaction_reference={self.transaction_reference!r}, owner_token=<redacted>)"
        )


@dataclass(frozen=True)
class DurablePrepareEvidence:
    request_id: int
    request_identity: str
    job_id: int
    job_chapter_ids: tuple[int, ...]
    chapter_ids: tuple[int, ...]
    chapter_numbers: tuple[int, ...]
    linkage_id: int
    execution_generation: int
    plan_fingerprint: str
    chapter_snapshot_digest: str
    transaction_committed_at: str
    prepared_status: str = "prepared"
    worker_woken: bool = False
    render_started: bool = False


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise IsolatedAdapterEvidenceError("stored lease timestamp is not timezone-aware")
    return parsed.astimezone(timezone.utc)


class DatabaseAuthoritativeSnapshotProvider:
    """Build immutable pins from an isolated database before the write transaction."""

    def __init__(
        self,
        db: Database,
        store: ContentStore,
        settings: Settings,
        *,
        temporary_root: Path,
        allow_canonical: bool = False,
    ):
        self.db = db
        self.store = store
        self.settings_snapshot = render_settings_snapshot(settings)
        _, root = assert_phase10_temporary_database(
            Path(db.path),
            temporary_root,
            allow_canonical=allow_canonical,
        )
        if settings.blobs_dir.resolve(strict=False) != store.config.blobs_dir.resolve(strict=False):
            raise IsolatedAdapterError("Phase 10 content store and settings do not share one blob root")
        blobs = settings.blobs_dir.resolve(strict=False)
        if blobs != root and root not in blobs.parents:
            raise IsolatedAdapterError("Phase 10 blob storage must be inside the explicit temporary root")

    def __call__(
        self,
        *,
        binding: PrepareRequestBinding,
        plan: Mapping[str, Any],
    ) -> tuple[AuthoritativeChapterSnapshot, ...]:
        rows = list(plan.get("eligible_chapters") or plan.get("included") or [])
        if not rows:
            raise IsolatedAdapterError("authoritative snapshot requires eligible chapters")
        if len(rows) > MAX_PREPARE_CHAPTERS:
            raise IsolatedAdapterError("PREPARE scope exceeds the bounded historical result capacity")
        ordered = sorted(rows, key=lambda row: (int(row.get("chapter_number") or 0), int(row.get("chapter_id") or 0)))
        snapshots: list[AuthoritativeChapterSnapshot] = []
        with self.db.connect() as connection:
            for order, item in enumerate(ordered, start=1):
                chapter_id = int(item.get("chapter_id") or 0)
                chapter = connection.execute("SELECT * FROM chapters WHERE id=?", (chapter_id,)).fetchone()
                plan_row = connection.execute(
                    "SELECT * FROM casting_plans WHERE chapter_id=? ORDER BY plan_revision DESC,id DESC LIMIT 1",
                    (chapter_id,),
                ).fetchone()
                if chapter is None or plan_row is None:
                    raise IsolatedAdapterError("eligible chapter authority is missing")
                expected = (
                    int(chapter["book_id"]) == binding.book_id,
                    binding.from_chapter <= int(chapter["chapter_number"]) <= binding.to_chapter,
                    int(chapter["active_text_revision_id"] or 0) == int(item.get("active_text_revision_id") or 0),
                    int(plan_row["id"]) == int(item.get("latest_casting_plan_id") or 0),
                    int(plan_row["plan_revision"]) == int(item.get("latest_casting_plan_revision") or 0),
                    plan_row["status"] == "approved",
                    plan_row["approved_at"] is not None,
                    int(plan_row["text_revision_id"]) == int(chapter["active_text_revision_id"] or 0),
                )
                if not all(expected):
                    raise IsolatedAdapterError("plan facts changed before authoritative snapshot binding")
                approved_row, approved_plan = validate_approved_plan(self.db, self.store, int(plan_row["id"]))
                if int(approved_row["id"]) != int(plan_row["id"]):
                    raise IsolatedAdapterError("approved Casting Plan identity changed")
                pin = {
                    "casting_plan_id": int(plan_row["id"]),
                    "casting_plan_sha256": str(plan_row["plan_sha256"]),
                    "text_revision_id": int(plan_row["text_revision_id"]),
                    "narrator_voice_id": approved_plan["narrator_voice_id"],
                    "book_voice_profile": approved_plan.get("book_voice_profile"),
                    "utterances": approved_plan["utterances"],
                    "resolved_character_voices": {
                        str(utterance["character_id"]): utterance["resolved_voice_id"]
                        for utterance in approved_plan["utterances"]
                        if utterance["role"] == "character"
                    },
                    "engine_version": self.settings_snapshot["engine_version"],
                    "tts_settings": self.settings_snapshot,
                    "chunker_version": CHUNKER_VERSION,
                }
                encoded_pin = json.dumps(pin, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                snapshots.append(
                    AuthoritativeChapterSnapshot(
                        book_id=binding.book_id,
                        chapter_id=chapter_id,
                        chapter_number=int(chapter["chapter_number"]),
                        text_revision_id=int(plan_row["text_revision_id"]),
                        casting_plan_id=int(plan_row["id"]),
                        casting_plan_revision=int(plan_row["plan_revision"]),
                        casting_plan_sha256=str(plan_row["plan_sha256"]),
                        narrator_voice_id=str(plan_row["narrator_voice_id"]),
                        deterministic_order=order,
                        casting_snapshot_json=encoded_pin,
                        voice_snapshot_json=encoded_pin,
                    )
                )
        return tuple(snapshots)


class BatchPrepareCommittedEvidenceReader:
    """Reload committed evidence without requiring the process-local raw owner token."""

    def __init__(
        self,
        db: Database,
        *,
        temporary_root: Path,
        allow_canonical: bool = False,
    ):
        self.db = db
        assert_phase10_temporary_database(
            Path(db.path),
            temporary_root,
            allow_canonical=allow_canonical,
        )

    def read(self, *, request_id: int, request_identity: str) -> DurablePrepareEvidence:
        with self.db.connect() as connection:
            request = connection.execute(
                "SELECT * FROM batch_prepare_requests WHERE id=?", (int(request_id),)
            ).fetchone()
            attempts = connection.execute(
                "SELECT * FROM batch_prepare_execution_attempts WHERE batch_prepare_request_id=? ORDER BY attempt_generation DESC,id DESC",
                (int(request_id),),
            ).fetchall()
            links = connection.execute(
                "SELECT * FROM batch_prepare_job_links WHERE batch_prepare_request_id=? ORDER BY id",
                (int(request_id),),
            ).fetchall()
            if request is None or request["request_identity"] != request_identity:
                raise IsolatedAdapterEvidenceError("request identity is not authoritative")
            if len(attempts) != 1 or attempts[0]["state"] != COMMITTED:
                raise IsolatedAdapterEvidenceError("exactly one committed execution attempt is required")
            attempt = attempts[0]
            if len(links) != 1 or int(attempt["committed_job_link_id"] or 0) != int(links[0]["id"]):
                raise IsolatedAdapterEvidenceError("committed attempt linkage is missing or ambiguous")
            link = links[0]
            job = connection.execute("SELECT * FROM jobs WHERE id=?", (int(link["job_id"]),)).fetchone()
            chapters = connection.execute(
                """SELECT jc.*,c.chapter_number FROM job_chapters jc
                   JOIN chapters c ON c.id=jc.chapter_id
                   WHERE jc.job_id=? ORDER BY jc.sequence,jc.id""",
                (int(link["job_id"]),),
            ).fetchall()
            exact_sequences = [int(row["sequence"]) for row in chapters] == list(range(1, len(chapters) + 1))
            chapter_ids = tuple(int(row["chapter_id"]) for row in chapters)
            try:
                job_settings = json.loads(job["settings_json"]) if job is not None else None
                render_pins = [json.loads(row["voice_snapshot_json"]) for row in chapters]
                render_compatible = isinstance(job_settings, dict) and all(
                    isinstance(pin, dict)
                    and int(pin.get("text_revision_id") or 0) == int(row["text_revision_id"] or 0)
                    and int(pin.get("casting_plan_id") or 0) == int(row["casting_plan_id"] or 0)
                    and pin.get("casting_plan_sha256") == row["casting_plan_sha256"]
                    and pin.get("tts_settings") == job_settings
                    and pin.get("chunker_version") == CHUNKER_VERSION
                    and isinstance(pin.get("utterances"), list)
                    and len(pin["utterances"]) > 0
                    and all(
                        {"sequence", "start_offset", "end_offset", "text_sha256", "role", "resolved_voice_id"}
                        <= set(utterance)
                        for utterance in pin["utterances"]
                    )
                    for row, pin in zip(chapters, render_pins)
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                render_compatible = False
            valid = (
                job is not None
                and job["status"] == "prepared"
                and int(job["book_id"]) == int(request["book_id"])
                and int(job["from_chapter"]) == int(request["from_chapter"])
                and int(job["to_chapter"]) == int(request["to_chapter"])
                and int(job["total_chapters"]) == len(chapters)
                and job["started_at"] is None
                and job["finished_at"] is None
                and link["request_identity"] == request_identity
                and link["plan_fingerprint"] == request["plan_fingerprint"]
                and link["plan_fingerprint"] == attempt["plan_fingerprint"]
                and link["chapter_snapshot_digest"] == attempt["chapter_snapshot_digest"]
                and link["transaction_reference"] == attempt["transaction_reference"]
                and int(link["expected_chapter_count"]) == len(chapters)
                and int(link["actual_chapter_count"]) == len(chapters)
                and int(link["worker_woken"]) == 0
                and int(link["render_started"]) == 0
                and len(chapters) > 0
                and len(chapter_ids) == len(set(chapter_ids))
                and exact_sequences
                and render_compatible
                and all(
                    row["status"] == "pending"
                    and row["artifact_id"] is None
                    and row["text_revision_id"] is not None
                    and row["casting_plan_id"] is not None
                    and bool(str(row["casting_plan_sha256"] or ""))
                    and bool(str(row["voice_snapshot_json"] or ""))
                    for row in chapters
                )
            )
            if not valid:
                raise IsolatedAdapterEvidenceError("durable PREPARE evidence is corrupt or mismatched")
            return DurablePrepareEvidence(
                request_id=int(request_id),
                request_identity=request_identity,
                job_id=int(job["id"]),
                job_chapter_ids=tuple(int(row["id"]) for row in chapters),
                chapter_ids=chapter_ids,
                chapter_numbers=tuple(int(row["chapter_number"]) for row in chapters),
                linkage_id=int(link["id"]),
                execution_generation=int(attempt["attempt_generation"]),
                plan_fingerprint=str(link["plan_fingerprint"]),
                chapter_snapshot_digest=str(link["chapter_snapshot_digest"]),
                transaction_committed_at=str(link["transaction_committed_at"]),
            )


class BatchPrepareIsolatedAdapter:
    """Phase 10 adapter injected into the existing orchestrator on temporary DBs only."""

    def __init__(
        self,
        *,
        db: Database,
        attempt_store: BatchPrepareExecutionAttemptStore,
        transaction_service: BatchPrepareIsolatedTransactionService,
        snapshot_provider: AuthoritativeSnapshotProvider,
        evidence_reader: BatchPrepareCommittedEvidenceReader,
        lease_seconds: int = 120,
        lifecycle_hook: LifecycleHook | None = None,
        transaction_failure_injector: Callable[[str, dict[str, Any]], None] | None = None,
        clock: Callable[[], str] = utcnow,
        temporary_root: Path,
        recovery_busy_timeout_ms: int = 250,
        allow_canonical: bool = False,
    ) -> None:
        database_path, self.temporary_root = assert_phase10_temporary_database(
            Path(db.path),
            temporary_root,
            allow_canonical=allow_canonical,
        )
        self.db = db
        self.attempt_store = attempt_store
        self.transaction_service = transaction_service
        self.snapshot_provider = snapshot_provider
        self.evidence_reader = evidence_reader
        self.lease_seconds = int(lease_seconds)
        self.lifecycle_hook = lifecycle_hook or (lambda _stage, _context: None)
        self.transaction_failure_injector = transaction_failure_injector
        self.clock = clock
        self.recovery_manager = BatchPrepareTransactionManager(
            database_path,
            busy_timeout_ms=int(recovery_busy_timeout_ms),
            allow_canonical=allow_canonical,
        )
        for dependency in (attempt_store, transaction_service, snapshot_provider, evidence_reader):
            dependency_db = getattr(dependency, "db", None)
            if dependency_db is None or Path(dependency_db.path).resolve(strict=False) != database_path:
                raise IsolatedAdapterError("all Phase 10 DB-backed dependencies must share one temporary database")

    def acquire(self, context: Mapping[str, Any]) -> ExecutionAcquisition:
        binding = PrepareRequestBinding(**dict(context["request"]))
        chapters = self.snapshot_provider(binding=binding, plan=context["plan"])
        digest = chapter_snapshot_digest(chapters)
        lease = self.attempt_store.acquire(
            request_id=int(context["request_id"]),
            request_identity=binding.request_identity,
            plan_fingerprint=binding.plan_fingerprint,
            chapter_snapshot_digest=digest,
            lease_seconds=self.lease_seconds,
        )
        acquisition = ExecutionAcquisition(
            request_id=int(context["request_id"]),
            request_identity=binding.request_identity,
            plan_fingerprint=binding.plan_fingerprint,
            chapter_snapshot_digest=digest,
            chapters=chapters,
            generation=lease.record.attempt_generation,
            transaction_reference=lease.record.transaction_reference,
            owner_token=lease.owner_token,
        )
        self.lifecycle_hook("after_execution_ownership", self._safe_acquisition_context(acquisition))
        return acquisition

    def cancel_acquisition(self, acquisition: ExecutionAcquisition, *, reason: str) -> None:
        self.attempt_store.mark_rollback_confirmed(
            request_id=acquisition.request_id,
            generation=acquisition.generation,
        )
        self.lifecycle_hook("acquisition_cancelled", {"request_id": acquisition.request_id, "reason": str(reason)})

    def prepare(self, context: Mapping[str, Any]) -> FuturePrepareResult:
        acquisition = context.get("execution_acquisition")
        if not isinstance(acquisition, ExecutionAcquisition):
            raise IsolatedAdapterError("execution acquisition is required")
        binding = PrepareRequestBinding(**dict(context["request"]))
        if int(context["request_id"]) != acquisition.request_id or binding.request_identity != acquisition.request_identity:
            raise IsolatedAdapterError("request ownership binding changed")
        try:
            second_chapters = self.snapshot_provider(binding=binding, plan=context["plan"])
        except Exception:
            self.cancel_acquisition(acquisition, reason="PLAN_STALE_BEFORE_TRANSACTION")
            raise
        second_digest = chapter_snapshot_digest(second_chapters)
        if second_digest != acquisition.chapter_snapshot_digest or second_chapters != acquisition.chapters:
            self.cancel_acquisition(acquisition, reason="PLAN_STALE_BEFORE_TRANSACTION")
            raise IsolatedAdapterError("authoritative snapshot changed before transaction")
        snapshot = PrepareTransactionSnapshot(
            request_id=acquisition.request_id,
            request_identity=acquisition.request_identity,
            book_id=binding.book_id,
            from_chapter=binding.from_chapter,
            to_chapter=binding.to_chapter,
            target_phase=binding.target_phase,
            plan_fingerprint=binding.plan_fingerprint,
            chapters=second_chapters,
            chapter_snapshot_digest=second_digest,
            owner_generation=acquisition.generation,
            owner_token=acquisition.owner_token,
            transaction_reference=acquisition.transaction_reference,
        )
        self.lifecycle_hook("before_transaction", self._safe_acquisition_context(acquisition))
        try:
            result = self.transaction_service.prepare(
                snapshot,
                failure_injector=self.transaction_failure_injector,
            )
        except AmbiguousPrepareOutcome:
            return self._ambiguous_result(acquisition)
        except IsolatedTransactionBusy:
            return FuturePrepareResult(
                status=FUTURE_IN_PROGRESS,
                durable_fields={
                    "recovery_classification": "STILL_IN_PROGRESS",
                    "operator_action": OPERATOR_WAIT,
                },
            )
        except PrepareConflict:
            return FuturePrepareResult(
                status=FUTURE_REJECTED,
                error_code="PREPARE_CONFLICT",
                error_message="Another prepared or active Job owns part of this chapter scope.",
            )
        except AuthoritativeInputRejected:
            return FuturePrepareResult(
                status=FUTURE_REJECTED,
                error_code="PREPARE_CONFLICT",
                error_message="Authoritative chapter, revision, or Casting Plan inputs changed.",
            )
        except Exception:
            try:
                evidence = self.evidence_reader.read(
                    request_id=acquisition.request_id,
                    request_identity=acquisition.request_identity,
                )
            except IsolatedAdapterEvidenceError:
                raise
            return self._success_result(
                evidence,
                recovery_source="post_commit_exception_recovery",
                replay=True,
            )
        evidence = self.evidence_reader.read(
            request_id=acquisition.request_id,
            request_identity=acquisition.request_identity,
        )
        try:
            self.lifecycle_hook("after_commit_before_applied", self._safe_evidence_context(evidence))
        except Exception:
            evidence = self.evidence_reader.read(
                request_id=acquisition.request_id,
                request_identity=acquisition.request_identity,
            )
        return self._success_result(evidence, recovery_source="transaction_commit", replay=result.replay)

    def recover_applying(
        self,
        *,
        record: BatchPrepareRequestRecord,
        binding: PrepareRequestBinding,
    ) -> FuturePrepareResult | None:
        attempt = self.attempt_store.get_current(record.id)
        if attempt is None:
            # Request ownership commits before execution-attempt acquisition. A concurrent
            # observer must treat this short window as in-progress, not terminal failure.
            return None
        if attempt.state == COMMITTED:
            try:
                evidence = self.evidence_reader.read(
                    request_id=record.id,
                    request_identity=binding.request_identity,
                )
            except IsolatedAdapterEvidenceError as exc:
                return self._review_result(str(exc))
            return self._success_result(evidence, recovery_source="committed_evidence_recovery", replay=True)
        if attempt.state == OUTCOME_AMBIGUOUS:
            return self._ambiguous_result_from_record(attempt.attempt_generation, attempt.chapter_snapshot_digest)
        if attempt.state in {ROLLBACK_CONFIRMED, EXPIRED}:
            return FuturePrepareResult(
                status=FUTURE_FAILED_RETRYABLE,
                error_code="FAILED_RETRYABLE",
                error_message="No committed Job exists; use a fresh client_request_id after review.",
                durable_fields={"recovery_classification": "EXPIRED_OWNER_NO_COMMIT"},
            )
        if attempt.state == OWNED:
            if _parse_time(attempt.lease_expires_at) > _parse_time(self.clock()):
                return None
            classified = self._classify_expired_owner(record.id, attempt.attempt_generation)
            if classified is None:
                return None
            if classified == COMMITTED:
                try:
                    evidence = self.evidence_reader.read(
                        request_id=record.id,
                        request_identity=binding.request_identity,
                    )
                except IsolatedAdapterEvidenceError:
                    return self._review_result("CORRUPT_COMMITTED_STATE")
                return self._success_result(evidence, recovery_source="expired_observer_commit_recovery", replay=True)
            if classified != EXPIRED:
                return self._review_result("CORRUPT_COMMITTED_STATE")
            return FuturePrepareResult(
                status=FUTURE_FAILED_RETRYABLE,
                error_code="FAILED_RETRYABLE",
                error_message="Execution lease expired without committed evidence; use a fresh request after review.",
                durable_fields={"recovery_classification": "EXPIRED_OWNER_NO_COMMIT"},
            )
        return self._review_result("execution attempt state is not recoverable automatically")

    def _classify_expired_owner(self, request_id: int, generation: int) -> str | None:
        try:
            transaction = self.recovery_manager.begin(f"phase10-expiry:{request_id}:{generation}")
        except IsolatedTransactionBusy:
            return None
        try:
            connection = transaction.require_active()
            current = self.attempt_store.get_by_generation_in_connection(connection, request_id, generation)
            if current.state == COMMITTED:
                transaction.rollback()
                return COMMITTED
            if current.state != OWNED:
                transaction.rollback()
                return current.state
            if _parse_time(current.lease_expires_at) > _parse_time(self.clock()):
                transaction.rollback()
                return OWNED
            link = connection.execute(
                "SELECT 1 FROM batch_prepare_job_links WHERE batch_prepare_request_id=?",
                (int(request_id),),
            ).fetchone()
            if link is not None:
                transaction.rollback()
                return OUTCOME_AMBIGUOUS
            updated = connection.execute(
                """UPDATE batch_prepare_execution_attempts SET state='EXPIRED',updated_at=?
                   WHERE batch_prepare_request_id=? AND attempt_generation=? AND state='OWNED'""",
                (self.clock(), int(request_id), int(generation)),
            )
            if updated.rowcount != 1:
                transaction.rollback()
                return None
            transaction.commit()
            return EXPIRED
        finally:
            transaction.close()

    def validate_applied_result(
        self,
        *,
        record: BatchPrepareRequestRecord,
        binding: PrepareRequestBinding,
        result: FuturePrepareResult,
    ) -> None:
        if result.job_id is None or record.request_identity != binding.request_identity:
            raise IsolatedAdapterEvidenceError("APPLIED result is not bound to the durable request")
        evidence = self.evidence_reader.read(
            request_id=record.id,
            request_identity=binding.request_identity,
        )
        durable = dict(result.durable_fields or {})
        references = tuple(tuple(int(value) for value in row) for row in durable.get("chapter_job_chapter_refs") or ())
        chapter_ids = tuple(row[0] for row in references if len(row) == 2)
        job_chapter_ids = tuple(row[1] for row in references if len(row) == 2)
        valid = (
            evidence.job_id == int(result.job_id)
            and evidence.plan_fingerprint == binding.plan_fingerprint
            and evidence.chapter_snapshot_digest == durable.get("chapter_snapshot_digest")
            and evidence.execution_generation == int(durable.get("execution_generation") or 0)
            and evidence.chapter_ids == chapter_ids
            and evidence.job_chapter_ids == job_chapter_ids
            and durable.get("transaction_committed") is True
            and durable.get("durable_linkage_verified") is True
            and durable.get("worker_woken") is False
            and durable.get("render_started") is False
        )
        if not valid:
            raise IsolatedAdapterEvidenceError("APPLIED payload does not match durable committed evidence")

    @staticmethod
    def _safe_acquisition_context(acquisition: ExecutionAcquisition) -> dict[str, Any]:
        return {
            "request_id": acquisition.request_id,
            "generation": acquisition.generation,
            "chapter_snapshot_digest": acquisition.chapter_snapshot_digest,
        }

    @staticmethod
    def _safe_evidence_context(evidence: DurablePrepareEvidence) -> dict[str, Any]:
        return {
            "request_id": evidence.request_id,
            "job_id": evidence.job_id,
            "linkage_id": evidence.linkage_id,
            "generation": evidence.execution_generation,
        }

    @staticmethod
    def _success_result(
        evidence: DurablePrepareEvidence,
        *,
        recovery_source: str,
        replay: bool,
    ) -> FuturePrepareResult:
        chapter_results: tuple[Mapping[str, Any], ...] = ()
        durable = {
            "adapter_schema": ADAPTER_SCHEMA,
            "evidence_schema": RESULT_EVIDENCE_SCHEMA,
            "chapter_snapshot_digest": evidence.chapter_snapshot_digest,
            "future_job_reference": f"job:{evidence.job_id}",
            "chapter_count": len(evidence.job_chapter_ids),
            "chapter_job_chapter_refs": [
                [chapter_id, job_chapter_id]
                for chapter_id, job_chapter_id in zip(evidence.chapter_ids, evidence.job_chapter_ids)
            ],
            "prepared_status": evidence.prepared_status,
            "transaction_committed": True,
            "transaction_committed_at": evidence.transaction_committed_at,
            "execution_generation": evidence.execution_generation,
            "durable_linkage_verified": True,
            "worker_woken": False,
            "render_started": False,
            "recovery_source": recovery_source,
            "operator_action": OPERATOR_START_SEPARATELY,
            "real_job_execution": False,
            "mutation_authorized": False,
            "execution_endpoint_available": False,
            "prepare_starts_render": False,
        }
        return FuturePrepareResult(
            status=FUTURE_SUCCESS,
            simulated_job_reference=f"job:{evidence.job_id}",
            job_id=evidence.job_id,
            chapter_results=chapter_results,
            audit_fields={
                "durable_linkage_id": evidence.linkage_id,
                "evidence_replayed": replay,
            },
            durable_fields=durable,
        )

    @staticmethod
    def _review_result(message: str) -> FuturePrepareResult:
        return FuturePrepareResult(
            status=FUTURE_AMBIGUOUS,
            error_code="FAILED_REVIEW_REQUIRED",
            error_message="Durable PREPARE evidence is ambiguous or corrupt and requires operator review.",
            durable_fields={
                "recovery_classification": str(message)[:100],
                "operator_action": OPERATOR_REVIEW,
            },
        )

    @staticmethod
    def _ambiguous_result(acquisition: ExecutionAcquisition) -> FuturePrepareResult:
        return BatchPrepareIsolatedAdapter._ambiguous_result_from_record(
            acquisition.generation,
            acquisition.chapter_snapshot_digest,
        )

    @staticmethod
    def _ambiguous_result_from_record(generation: int, digest: str) -> FuturePrepareResult:
        return FuturePrepareResult(
            status=FUTURE_AMBIGUOUS,
            error_code="FAILED_REVIEW_REQUIRED",
            error_message="Commit outcome is ambiguous and was not rerun.",
            durable_fields={
                "recovery_classification": "OUTCOME_AMBIGUOUS",
                "execution_generation": int(generation),
                "chapter_snapshot_digest": digest,
                "operator_action": OPERATOR_REVIEW,
            },
        )


def authorization_flags() -> dict[str, bool]:
    return {
        "isolated_only": True,
        "temporary_database_only": True,
        "runtime_wiring": False,
        "canonical_activation": False,
        "production_prepare": False,
        "api_route": False,
        "ui_control": False,
        "worker_wake": False,
        "start_render": False,
        "provider_or_tts": False,
    }


__all__ = [
    "ADAPTER_SCHEMA",
    "BatchPrepareCommittedEvidenceReader",
    "BatchPrepareIsolatedAdapter",
    "DatabaseAuthoritativeSnapshotProvider",
    "DurablePrepareEvidence",
    "ExecutionAcquisition",
    "IsolatedAdapterError",
    "IsolatedAdapterEvidenceError",
    "MAX_PREPARE_CHAPTERS",
    "TEMPORARY_MARKER",
    "assert_phase10_temporary_database",
    "authorization_flags",
    "render_settings_snapshot",
]
