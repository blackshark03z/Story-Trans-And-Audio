from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from .batch_prepare_execution_attempt_store import (
    COMMITTED,
    OWNED,
    BatchPrepareExecutionAttemptStore,
    ExecutionAttemptOwnerRejected,
)
from .batch_prepare_job_link_store import BatchPrepareJobLinkInput, BatchPrepareJobLinkStore
from .batch_prepare_transaction_manager import (
    BatchPrepareTransactionManager,
    IsolatedTransactionBusy,
    assert_isolated_database_path,
)
from .batch_prepare_transaction_revalidator import (
    BatchPrepareTransactionRevalidator,
    PrepareTransactionSnapshot,
)
from .db import Database, utcnow
from .prepared_job_transaction_repository import PreparedJobTransactionRepository


FailureInjector = Callable[[str, dict[str, Any]], None]


class IsolatedPrepareServiceError(RuntimeError):
    pass


class PrepareConflict(IsolatedPrepareServiceError):
    pass


class CommittedEvidenceUnavailable(IsolatedPrepareServiceError):
    pass


class AmbiguousPrepareOutcome(IsolatedPrepareServiceError):
    pass


@dataclass(frozen=True)
class IsolatedPrepareResult:
    request_id: int
    request_identity: str
    job_id: int
    job_chapter_ids: tuple[int, ...]
    linkage_id: int
    attempt_generation: int
    transaction_reference: str
    chapter_snapshot_digest: str
    plan_fingerprint: str
    status: str = "prepared"
    committed: bool = True
    replay: bool = False
    worker_woken: bool = False
    render_started: bool = False
    eligible_for_future_applied_recording: bool = True

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["job_chapter_ids"] = list(self.job_chapter_ids)
        return result


def authorization_flags() -> dict[str, bool]:
    return {
        "isolated_only": True,
        "runtime_wiring": False,
        "canonical_activation": False,
        "production_job_creation": False,
        "api_integration": False,
        "worker_wake": False,
        "start_render": False,
        "provider_or_tts": False,
    }


class BatchPrepareIsolatedTransactionService:
    """Dormant same-transaction PREPARE proof for disposable databases only."""

    def __init__(
        self,
        db: Database,
        *,
        busy_timeout_ms: int = 5000,
        allow_canonical: bool = False,
    ):
        self.db_path = assert_isolated_database_path(
            Path(db.path),
            allow_canonical=allow_canonical,
        )
        self.db = db
        self.manager = BatchPrepareTransactionManager(
            self.db_path,
            busy_timeout_ms=busy_timeout_ms,
            allow_canonical=allow_canonical,
        )
        self.attempts = BatchPrepareExecutionAttemptStore(
            db,
            allow_canonical=allow_canonical,
        )
        self.revalidator = BatchPrepareTransactionRevalidator(self.attempts)
        self.jobs = PreparedJobTransactionRepository()
        self.links = BatchPrepareJobLinkStore(
            db,
            allow_canonical=allow_canonical,
        )

    def prepare(
        self,
        snapshot: PrepareTransactionSnapshot,
        *,
        failure_injector: FailureInjector | None = None,
    ) -> IsolatedPrepareResult:
        injector = failure_injector or (lambda _stage, _context: None)
        provisional_job_id: int | None = None
        owner_validated = False
        transaction = None
        committed = False
        commit_started = False
        try:
            transaction = self.manager.begin(snapshot.transaction_reference)
            connection = transaction.require_active()
            request = connection.execute(
                "SELECT * FROM batch_prepare_requests WHERE id=?", (int(snapshot.request_id),)
            ).fetchone()
            if request is None or request["request_identity"] != snapshot.request_identity:
                raise ExecutionAttemptOwnerRejected("request identity is not authoritative")
            attempt = self.attempts.validate_owner_in_connection(
                connection,
                request_id=snapshot.request_id,
                request_identity=snapshot.request_identity,
                generation=snapshot.owner_generation,
                owner_token=snapshot.owner_token,
                plan_fingerprint=snapshot.plan_fingerprint,
                chapter_snapshot_digest=snapshot.chapter_snapshot_digest,
                transaction_reference=snapshot.transaction_reference,
                allow_committed_recovery=True,
            )
            owner_validated = True
            if attempt.state == COMMITTED:
                transaction.rollback()
                transaction.close()
                return self.recover(snapshot, failure_injector=injector, replay=True)
            if attempt.state != OWNED:
                raise ExecutionAttemptOwnerRejected("only an owned attempt may execute PREPARE")
            validated = self.revalidator.validate(connection, snapshot)
            injector("after_request_validation", {"request_id": snapshot.request_id})
            existing = connection.execute(
                "SELECT id FROM batch_prepare_job_links WHERE batch_prepare_request_id=?",
                (int(snapshot.request_id),),
            ).fetchone()
            if existing is not None:
                raise PrepareConflict("owned request unexpectedly already has a durable linkage")
            conflict = self.revalidator.find_conflict(connection, [item.chapter_id for item in validated.chapters])
            if conflict is not None:
                raise PrepareConflict(
                    f"chapter already belongs to Job #{int(conflict['id'])} in status {conflict['status']}"
                )
            injector("after_conflict_check", {"request_id": snapshot.request_id})

            def writer_hook(stage: str, context: dict[str, Any]) -> None:
                nonlocal provisional_job_id
                if stage == "after_job_insert":
                    provisional_job_id = int(context["job_id"])
                injector(stage, context)

            write = self.jobs.insert(
                transaction,
                validated,
                settings_json=self._settings_json(validated.chapters),
                stage_hook=writer_hook,
            )
            provisional_job_id = write.job_id
            timestamp = utcnow()
            link_result = self.links.create_or_replay_in_connection(
                connection,
                BatchPrepareJobLinkInput(
                    batch_prepare_request_id=snapshot.request_id,
                    request_identity=snapshot.request_identity,
                    job_id=write.job_id,
                    plan_fingerprint=snapshot.plan_fingerprint,
                    chapter_snapshot_digest=snapshot.chapter_snapshot_digest,
                    expected_chapter_count=len(validated.chapters),
                    actual_chapter_count=len(write.job_chapter_ids),
                    transaction_committed_at=timestamp,
                    transaction_reference=snapshot.transaction_reference,
                    evidence_source="phase9_isolated_same_transaction",
                ),
            )
            if link_result.replay:
                raise PrepareConflict("new Job write cannot replay an existing linkage")
            injector("after_linkage_insert", {"linkage_id": link_result.record.id, "job_id": write.job_id})
            self.attempts.mark_committed_in_connection(
                connection,
                request_id=snapshot.request_id,
                generation=snapshot.owner_generation,
                job_link_id=link_result.record.id,
                committed_at=timestamp,
            )
            injector("after_attempt_update", {"linkage_id": link_result.record.id})
            injector("before_commit", {"job_id": write.job_id})
            commit_started = True
            transaction.commit()
            committed = True
        except IsolatedTransactionBusy:
            raise
        except Exception as exc:
            if transaction is not None and transaction.active:
                transaction.rollback()
            if transaction is not None:
                transaction.close()
            if committed or commit_started:
                recovered = self._recover_after_uncertain_commit(snapshot, injector)
                if recovered is not None:
                    return recovered
                try:
                    self.attempts.mark_outcome_ambiguous(
                        request_id=snapshot.request_id,
                        generation=snapshot.owner_generation,
                        reason_code="COMMIT_OUTCOME_NOT_PROVEN",
                    )
                except Exception:
                    pass
                raise AmbiguousPrepareOutcome("commit outcome could not be proven; transaction was not rerun") from exc
            if owner_validated:
                self._record_confirmed_rollback(snapshot, provisional_job_id)
            elif transaction is None:
                self._record_begin_failure_rollback(snapshot)
            raise
        finally:
            if transaction is not None and transaction.connection:
                try:
                    transaction.close()
                except sqlite3.Error:
                    pass
        injector("after_commit_before_evidence", {"request_id": snapshot.request_id})
        return self.recover(snapshot, failure_injector=injector, replay=False)

    @staticmethod
    def _settings_json(chapters) -> str:
        snapshots: list[dict[str, Any]] = []
        for chapter in chapters:
            try:
                decoded = json.loads(chapter.voice_snapshot_json)
            except (TypeError, json.JSONDecodeError) as exc:
                raise IsolatedPrepareServiceError("voice snapshot JSON is invalid") from exc
            settings = decoded.get("tts_settings") if isinstance(decoded, dict) else None
            if settings is not None:
                if not isinstance(settings, dict):
                    raise IsolatedPrepareServiceError("voice snapshot TTS settings must be an object")
                snapshots.append(settings)
        if not snapshots:
            return "{}"
        canonical = json.dumps(snapshots[0], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if any(
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) != canonical
            for item in snapshots[1:]
        ) or len(snapshots) != len(chapters):
            raise IsolatedPrepareServiceError("all prepared chapters must pin the same TTS settings")
        return canonical

    def recover(
        self,
        snapshot: PrepareTransactionSnapshot,
        *,
        failure_injector: FailureInjector | None = None,
        replay: bool = True,
    ) -> IsolatedPrepareResult:
        injector = failure_injector or (lambda _stage, _context: None)
        try:
            with self.db.connect() as connection:
                attempt = self.attempts.validate_owner_in_connection(
                    connection,
                    request_id=snapshot.request_id,
                    request_identity=snapshot.request_identity,
                    generation=snapshot.owner_generation,
                    owner_token=snapshot.owner_token,
                    plan_fingerprint=snapshot.plan_fingerprint,
                    chapter_snapshot_digest=snapshot.chapter_snapshot_digest,
                    transaction_reference=snapshot.transaction_reference,
                    allow_committed_recovery=True,
                )
                if attempt.state != COMMITTED or attempt.committed_job_link_id is None:
                    raise CommittedEvidenceUnavailable("execution attempt is not durably committed")
                link = connection.execute(
                    "SELECT * FROM batch_prepare_job_links WHERE id=?", (attempt.committed_job_link_id,)
                ).fetchone()
                if link is None:
                    raise CommittedEvidenceUnavailable("committed attempt linkage is missing")
                job = connection.execute("SELECT * FROM jobs WHERE id=?", (int(link["job_id"]),)).fetchone()
                chapters = connection.execute(
                    "SELECT * FROM job_chapters WHERE job_id=? ORDER BY sequence,id", (int(link["job_id"]),)
                ).fetchall()
                expected_ids = [item.chapter_id for item in snapshot.chapters]
                actual_ids = [int(row["chapter_id"]) for row in chapters]
                exact_chapter_pins = len(chapters) == len(snapshot.chapters) and all(
                    int(row["sequence"]) == item.deterministic_order
                    and row["status"] == "pending"
                    and int(row["text_revision_id"] or 0) == item.text_revision_id
                    and int(row["casting_plan_id"] or 0) == item.casting_plan_id
                    and row["casting_plan_sha256"] == item.casting_plan_sha256
                    and row["voice_snapshot_json"] == item.voice_snapshot_json
                    for row, item in zip(chapters, snapshot.chapters)
                )
                valid = (
                    job is not None
                    and job["status"] == "prepared"
                    and int(job["book_id"]) == snapshot.book_id
                    and int(job["from_chapter"]) == snapshot.from_chapter
                    and int(job["to_chapter"]) == snapshot.to_chapter
                    and int(job["total_chapters"]) == len(snapshot.chapters)
                    and job["started_at"] is None
                    and job["finished_at"] is None
                    and link["request_identity"] == snapshot.request_identity
                    and link["plan_fingerprint"] == snapshot.plan_fingerprint
                    and link["chapter_snapshot_digest"] == snapshot.chapter_snapshot_digest
                    and link["transaction_reference"] == snapshot.transaction_reference
                    and int(link["worker_woken"]) == 0
                    and int(link["render_started"]) == 0
                    and int(link["expected_chapter_count"]) == len(snapshot.chapters)
                    and int(link["actual_chapter_count"]) == len(snapshot.chapters)
                    and actual_ids == expected_ids
                    and exact_chapter_pins
                )
                if not valid:
                    raise CommittedEvidenceUnavailable("durable PREPARE evidence is corrupt or mismatched")
                injector("after_evidence_reload", {"job_id": int(job["id"])})
                return IsolatedPrepareResult(
                    request_id=snapshot.request_id,
                    request_identity=snapshot.request_identity,
                    job_id=int(job["id"]),
                    job_chapter_ids=tuple(int(row["id"]) for row in chapters),
                    linkage_id=int(link["id"]),
                    attempt_generation=snapshot.owner_generation,
                    transaction_reference=snapshot.transaction_reference,
                    chapter_snapshot_digest=snapshot.chapter_snapshot_digest,
                    plan_fingerprint=snapshot.plan_fingerprint,
                    replay=replay,
                )
        except CommittedEvidenceUnavailable:
            raise
        except Exception as exc:
            raise CommittedEvidenceUnavailable("committed PREPARE evidence reload failed") from exc

    def _recover_after_uncertain_commit(
        self, snapshot: PrepareTransactionSnapshot, injector: FailureInjector
    ) -> IsolatedPrepareResult | None:
        try:
            return self.recover(snapshot, failure_injector=injector, replay=True)
        except (CommittedEvidenceUnavailable, ExecutionAttemptOwnerRejected):
            return None

    def _record_confirmed_rollback(
        self, snapshot: PrepareTransactionSnapshot, provisional_job_id: int | None
    ) -> None:
        with self.db.connect() as connection:
            link = connection.execute(
                "SELECT 1 FROM batch_prepare_job_links WHERE batch_prepare_request_id=?",
                (int(snapshot.request_id),),
            ).fetchone()
            job = (
                connection.execute("SELECT 1 FROM jobs WHERE id=?", (int(provisional_job_id),)).fetchone()
                if provisional_job_id is not None
                else None
            )
        if link is not None or job is not None:
            raise AmbiguousPrepareOutcome("rollback absence proof failed")
        self.attempts.mark_rollback_confirmed(
            request_id=snapshot.request_id,
            generation=snapshot.owner_generation,
        )

    def _record_begin_failure_rollback(self, snapshot: PrepareTransactionSnapshot) -> None:
        with self.db.connect() as connection:
            self.attempts.validate_owner_in_connection(
                connection,
                request_id=snapshot.request_id,
                request_identity=snapshot.request_identity,
                generation=snapshot.owner_generation,
                owner_token=snapshot.owner_token,
                plan_fingerprint=snapshot.plan_fingerprint,
                chapter_snapshot_digest=snapshot.chapter_snapshot_digest,
                transaction_reference=snapshot.transaction_reference,
            )
        self._record_confirmed_rollback(snapshot, None)


__all__ = [
    "AmbiguousPrepareOutcome",
    "BatchPrepareIsolatedTransactionService",
    "CommittedEvidenceUnavailable",
    "IsolatedPrepareResult",
    "IsolatedPrepareServiceError",
    "PrepareConflict",
    "authorization_flags",
]
