from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .batch_prepare_contract import (
    CONTRACT_ACCEPTED,
    REJECTED_NO_ELIGIBLE_CHAPTERS,
    REJECTED_STALE_PLAN,
    SUPPORTED_PHASE,
    evaluate_prepare_contract,
)
from .batch_prepare_persistence_contract import (
    REQUEST_ID_CONFLICT,
    STATE_APPLIED,
    STATE_APPLYING,
    STATE_FAILED,
    STATE_PLANNED,
    STATE_REJECTED,
    PreparePersistenceContractError,
    build_request_binding,
    build_result_payload,
)
from .batch_prepare_store import (
    BatchPrepareRequestConflict,
    BatchPrepareRequestRecord,
    BatchPrepareStateConflict,
)


ORCHESTRATION_SCHEMA = "story-audio-batch-prepare-orchestration/v1"
DESIGN_STATUS = "DESIGN_AND_ISOLATED_CONTRACT_ONLY"

STATUS_ACCEPTED = "PREPARE_SIMULATED_APPLIED"
STATUS_REJECTED = "PREPARE_REJECTED"
STATUS_FAILED = "PREPARE_FAILED"
STATUS_APPLYING = "REQUEST_APPLYING"
STATUS_CONFLICT = REQUEST_ID_CONFLICT
STATUS_INVALID = "INVALID_REQUEST"
STATUS_OWNERSHIP_LOST = "OWNERSHIP_LOST_REPLAYED"

FUTURE_SUCCESS = "SIMULATED_SUCCESS"
FUTURE_REJECTED = "SIMULATED_REJECTED"
FUTURE_FAILED_RETRYABLE = "SIMULATED_FAILED_RETRYABLE"
FUTURE_FAILED_REVIEW_REQUIRED = "SIMULATED_FAILED_REVIEW_REQUIRED"
FUTURE_AMBIGUOUS = "SIMULATED_AMBIGUOUS"

OPERATOR_NONE = "NONE"
OPERATOR_REVIEW_REQUEST = "REVIEW_REQUEST"
OPERATOR_CREATE_NEW_REQUEST = "CREATE_NEW_REQUEST"
OPERATOR_WAIT_AND_RETRY_STATUS = "WAIT_AND_RETRY_STATUS"
OPERATOR_REBUILD_PLAN = "REBUILD_PLAN"
OPERATOR_INVESTIGATE_AMBIGUOUS_APPLYING = "INVESTIGATE_AMBIGUOUS_APPLYING"

RECONCILE_STILL_IN_PROGRESS = "STILL_IN_PROGRESS"
RECONCILE_SAFE_TO_MARK_FAILED_RETRYABLE = "SAFE_TO_MARK_FAILED_RETRYABLE"
RECONCILE_OPERATOR_REVIEW_REQUIRED = "OPERATOR_REVIEW_REQUIRED"
RECONCILE_APPLIED_RESULT_RECOVERY_REQUIRED = "APPLIED_RESULT_RECOVERY_REQUIRED"
RECONCILE_REQUEST_RECORD_CORRUPT = "REQUEST_RECORD_CORRUPT"


class CurrentPlanProvider(Protocol):
    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


class PrepareRequestStore(Protocol):
    def create_or_replay_request(self, request: Mapping[str, Any]) -> BatchPrepareRequestRecord:
        ...

    def get_request(self, request_id: int) -> BatchPrepareRequestRecord | None:
        ...

    def compare_and_transition_state(
        self,
        request_id: int,
        *,
        expected_state: str,
        next_state: str,
    ) -> BatchPrepareRequestRecord:
        ...

    def record_applied_result(
        self,
        request_id: int,
        *,
        job_id: int | None,
        result_payload: Mapping[str, Any],
    ) -> BatchPrepareRequestRecord:
        ...

    def record_rejection(
        self,
        request_id: int,
        *,
        result_payload: Mapping[str, Any],
        error_code: str,
        error_message: str,
    ) -> BatchPrepareRequestRecord:
        ...

    def record_failure(
        self,
        request_id: int,
        *,
        result_payload: Mapping[str, Any],
        error_code: str,
        error_message: str,
    ) -> BatchPrepareRequestRecord:
        ...

    def build_historical_replay(self, request_id: int) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class FuturePrepareResult:
    status: str
    simulated_job_reference: str | None = None
    chapter_results: tuple[Mapping[str, Any], ...] = ()
    error_code: str | None = None
    error_message: str | None = None
    audit_fields: Mapping[str, Any] | None = None


class FuturePrepareTransaction(Protocol):
    def prepare(self, context: Mapping[str, Any]) -> FuturePrepareResult:
        ...


def _scope(binding) -> dict[str, int]:
    return {
        "book_id": binding.book_id,
        "from_chapter": binding.from_chapter,
        "to_chapter": binding.to_chapter,
    }


def _safe_error_message(message: str | None, fallback: str) -> str:
    text = str(message or fallback)
    for marker in ("Traceback", "sqlite", "SELECT ", "INSERT ", "UPDATE ", "DELETE "):
        text = text.replace(marker, "[redacted]")
    return text[:1000]


def _status_for_state(record: BatchPrepareRequestRecord) -> tuple[str, str]:
    if record.state == STATE_APPLIED:
        return "APPLIED_REPLAYED", OPERATOR_NONE
    if record.state == STATE_REJECTED:
        if record.error_code == "STALE_PLAN":
            return "REJECTED_REPLAYED", OPERATOR_REBUILD_PLAN
        return "REJECTED_REPLAYED", OPERATOR_CREATE_NEW_REQUEST
    if record.state == STATE_FAILED:
        return "FAILED_REPLAYED", OPERATOR_REVIEW_REQUEST
    if record.state == STATE_APPLYING:
        return STATUS_APPLYING, OPERATOR_WAIT_AND_RETRY_STATUS
    return "PLANNED_REPLAYED", OPERATOR_WAIT_AND_RETRY_STATUS


def _public_response(
    *,
    status: str,
    record: BatchPrepareRequestRecord | None,
    binding: Any | None,
    replay: bool,
    ownership_acquired: bool,
    future_transaction_called: bool,
    result: Mapping[str, Any] | None,
    error_code: str | None,
    error_message: str | None,
    operator_action: str,
) -> dict[str, Any]:
    scope = _scope(binding) if binding else None
    plan_fingerprint = binding.plan_fingerprint if binding else (record.plan_fingerprint if record else None)
    return {
        "schema": ORCHESTRATION_SCHEMA,
        "status": status,
        "design_status": DESIGN_STATUS,
        "request_id": record.id if record else None,
        "client_request_id": binding.client_request_id if binding else (record.client_request_id if record else None),
        "request_identity": binding.request_identity if binding else (record.request_identity if record else None),
        "request_state": record.state if record else None,
        "scope": scope,
        "target_phase": SUPPORTED_PHASE,
        "plan_fingerprint": plan_fingerprint,
        "replay": replay,
        "ownership_acquired": ownership_acquired,
        "future_transaction_called": future_transaction_called,
        "result": dict(result or {}),
        "error_code": error_code,
        "error_message": _safe_error_message(error_message, "") if error_message else None,
        "operator_action": operator_action,
        "mutation_authorized": False,
        "execution_endpoint_available": False,
        "real_job_execution": False,
        "prepare_starts_render": False,
    }


def _response_from_record(
    store: PrepareRequestStore,
    record: BatchPrepareRequestRecord,
    *,
    binding: Any | None = None,
    replay: bool = True,
    status_override: str | None = None,
) -> dict[str, Any]:
    status, action = _status_for_state(record)
    result: Mapping[str, Any] | None = record.result_payload
    if record.state in {STATE_APPLIED, STATE_REJECTED, STATE_FAILED}:
        result = store.build_historical_replay(record.id).get("stored_result_payload") or record.result_payload
    return _public_response(
        status=status_override or status,
        record=record,
        binding=binding,
        replay=replay,
        ownership_acquired=False,
        future_transaction_called=False,
        result=result,
        error_code=record.error_code,
        error_message=record.error_message,
        operator_action=action,
    )


def _chapter_results_from_plan(plan: Mapping[str, Any], result_status: str, created_or_reused: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in plan.get("included") or []:
        rows.append(
            {
                "chapter_id": row.get("chapter_id"),
                "chapter_number": row.get("chapter_number"),
                "plan_eligibility": row.get("eligibility"),
                "result_status": result_status,
                "job_chapter_id": None,
                "reason_codes": list(row.get("reason_codes") or []),
                "created_or_reused": created_or_reused,
            }
        )
    return rows


def _build_payload(
    binding,
    *,
    state: str,
    chapter_results: Sequence[Mapping[str, Any]],
    error_code: str | None = None,
    error_message: str | None = None,
    simulated_job_reference: str | None = None,
    audit_fields: Mapping[str, Any] | None = None,
    attempt_count: int = 0,
) -> dict[str, Any]:
    payload = build_result_payload(
        binding,
        state=state,
        job_id=None,
        chapter_results=[dict(row) for row in chapter_results],
        error_code=error_code,
        error_message=_safe_error_message(error_message, "public safe message") if error_message else None,
        attempt_count=attempt_count,
    )
    payload["real_job_execution"] = False
    if simulated_job_reference is not None:
        payload["simulated_job_reference"] = simulated_job_reference
        payload["future_job_reference"] = simulated_job_reference
    if audit_fields:
        payload["audit_fields"] = dict(audit_fields)
    return payload


class BatchPrepareOrchestrator:
    def __init__(
        self,
        *,
        current_plan_provider: CurrentPlanProvider,
        request_store: PrepareRequestStore,
        future_prepare_transaction: FuturePrepareTransaction,
    ) -> None:
        self.current_plan_provider = current_plan_provider
        self.request_store = request_store
        self.future_prepare_transaction = future_prepare_transaction

    def prepare(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(request, Mapping):
            return _public_response(
                status=STATUS_INVALID,
                record=None,
                binding=None,
                replay=False,
                ownership_acquired=False,
                future_transaction_called=False,
                result=None,
                error_code="INVALID_REQUEST",
                error_message="Request must be an object.",
                operator_action=OPERATOR_REVIEW_REQUEST,
            )
        request_dict = dict(request)
        intake = evaluate_prepare_contract(request_dict, self.current_plan_provider)
        if intake["status"] not in {CONTRACT_ACCEPTED, REJECTED_NO_ELIGIBLE_CHAPTERS}:
            return _public_response(
                status=STATUS_REJECTED,
                record=None,
                binding=None,
                replay=False,
                ownership_acquired=False,
                future_transaction_called=False,
                result={"contract": intake},
                error_code=_error_code_for_contract_status(str(intake["status"])),
                error_message=str(intake.get("reason") or "Request rejected."),
                operator_action=_operator_action_for_contract_status(str(intake["status"])),
            )
        try:
            binding = build_request_binding(request_dict)
            record = self.request_store.create_or_replay_request(request_dict)
        except BatchPrepareRequestConflict as exc:
            return _public_response(
                status=STATUS_CONFLICT,
                record=None,
                binding=None,
                replay=True,
                ownership_acquired=False,
                future_transaction_called=False,
                result=None,
                error_code=REQUEST_ID_CONFLICT,
                error_message=str(exc),
                operator_action=OPERATOR_CREATE_NEW_REQUEST,
            )
        except PreparePersistenceContractError as exc:
            return _public_response(
                status=STATUS_INVALID,
                record=None,
                binding=None,
                replay=False,
                ownership_acquired=False,
                future_transaction_called=False,
                result={"contract": intake},
                error_code="INVALID_REQUEST",
                error_message=str(exc),
                operator_action=OPERATOR_REVIEW_REQUEST,
            )

        if record.state != STATE_PLANNED:
            return _response_from_record(self.request_store, record, binding=binding)

        if intake["status"] == REJECTED_NO_ELIGIBLE_CHAPTERS:
            payload = _build_payload(
                binding,
                state=STATE_REJECTED,
                chapter_results=[],
                error_code="NO_ELIGIBLE_CHAPTERS",
                error_message="Current PREPARE plan has no eligible chapters.",
            )
            rejected = self.request_store.record_rejection(
                record.id,
                result_payload=payload,
                error_code="NO_ELIGIBLE_CHAPTERS",
                error_message="Current PREPARE plan has no eligible chapters.",
            )
            return _response_from_record(self.request_store, rejected, binding=binding, replay=False, status_override=STATUS_REJECTED)

        try:
            applying = self.request_store.compare_and_transition_state(
                record.id,
                expected_state=STATE_PLANNED,
                next_state=STATE_APPLYING,
            )
        except BatchPrepareStateConflict:
            current = self.request_store.get_request(record.id)
            if current is None:
                return _public_response(
                    status=STATUS_FAILED,
                    record=record,
                    binding=binding,
                    replay=False,
                    ownership_acquired=False,
                    future_transaction_called=False,
                    result=None,
                    error_code="FAILED_REVIEW_REQUIRED",
                    error_message="Request disappeared during ownership acquisition.",
                    operator_action=OPERATOR_REVIEW_REQUEST,
                )
            return _response_from_record(self.request_store, current, binding=binding, status_override=STATUS_OWNERSHIP_LOST)

        second = evaluate_prepare_contract(request_dict, self.current_plan_provider)
        if second["status"] != CONTRACT_ACCEPTED:
            payload = _build_payload(
                binding,
                state=STATE_REJECTED,
                chapter_results=[],
                error_code=_error_code_for_contract_status(str(second["status"])),
                error_message=str(second.get("reason") or "Request rejected before future transaction."),
                attempt_count=applying.attempt_count,
            )
            rejected = self.request_store.record_rejection(
                applying.id,
                result_payload=payload,
                error_code=str(payload["error_code"]),
                error_message=str(payload["error_message"]),
            )
            return _response_from_record(self.request_store, rejected, binding=binding, replay=False, status_override=STATUS_REJECTED)

        try:
            future_result = self.future_prepare_transaction.prepare(
                {
                    "request": binding.as_dict(),
                    "plan": second,
                    "eligible_chapters": list(second.get("eligible_chapters") or second.get("included") or []),
                    "execution_authorized": False,
                    "real_job_execution": False,
                }
            )
        except Exception as exc:  # noqa: BLE001 - service boundary must fail closed with public-safe output.
            payload = _build_payload(
                binding,
                state=STATE_FAILED,
                chapter_results=_chapter_results_from_plan(second, "FAILED", "not_created"),
                error_code="FAILED_REVIEW_REQUIRED",
                error_message=_safe_error_message(str(exc), "Future transaction failed."),
                attempt_count=applying.attempt_count,
            )
            failed = self.request_store.record_failure(
                applying.id,
                result_payload=payload,
                error_code="FAILED_REVIEW_REQUIRED",
                error_message=str(payload["error_message"]),
            )
            return _response_from_record(self.request_store, failed, binding=binding, replay=False, status_override=STATUS_FAILED)

        try:
            return self._persist_future_result(binding, applying, future_result)
        except Exception as exc:  # noqa: BLE001 - persistence failure must not be reported as success.
            return _public_response(
                status=STATUS_FAILED,
                record=applying,
                binding=binding,
                replay=False,
                ownership_acquired=True,
                future_transaction_called=True,
                result=None,
                error_code="FAILED_REVIEW_REQUIRED",
                error_message=_safe_error_message(str(exc), "Terminal result persistence failed."),
                operator_action=OPERATOR_REVIEW_REQUEST,
            )

    def _persist_future_result(
        self,
        binding,
        applying: BatchPrepareRequestRecord,
        future_result: FuturePrepareResult,
    ) -> dict[str, Any]:
        status = str(future_result.status or "").upper()
        chapters = list(future_result.chapter_results)
        if status == FUTURE_SUCCESS:
            payload = _build_payload(
                binding,
                state=STATE_APPLIED,
                chapter_results=chapters,
                simulated_job_reference=future_result.simulated_job_reference,
                audit_fields=future_result.audit_fields,
                attempt_count=applying.attempt_count,
            )
            applied = self.request_store.record_applied_result(applying.id, job_id=None, result_payload=payload)
            response = _response_from_record(self.request_store, applied, binding=binding, replay=False, status_override=STATUS_ACCEPTED)
            response["ownership_acquired"] = True
            response["future_transaction_called"] = True
            return response
        if status == FUTURE_REJECTED:
            code = future_result.error_code or "PREPARE_CONFLICT"
            payload = _build_payload(
                binding,
                state=STATE_REJECTED,
                chapter_results=chapters,
                error_code=code,
                error_message=future_result.error_message or "Future transaction rejected the request.",
                audit_fields=future_result.audit_fields,
                attempt_count=applying.attempt_count,
            )
            rejected = self.request_store.record_rejection(
                applying.id,
                result_payload=payload,
                error_code=code,
                error_message=str(payload["error_message"]),
            )
            response = _response_from_record(self.request_store, rejected, binding=binding, replay=False, status_override=STATUS_REJECTED)
            response["ownership_acquired"] = True
            response["future_transaction_called"] = True
            return response
        code = "FAILED_RETRYABLE" if status == FUTURE_FAILED_RETRYABLE else "FAILED_REVIEW_REQUIRED"
        if status == FUTURE_AMBIGUOUS:
            code = "FAILED_REVIEW_REQUIRED"
        payload = _build_payload(
            binding,
            state=STATE_FAILED,
            chapter_results=chapters,
            error_code=future_result.error_code or code,
            error_message=future_result.error_message or "Future transaction did not produce a durable success.",
            audit_fields=future_result.audit_fields,
            attempt_count=applying.attempt_count,
        )
        failed = self.request_store.record_failure(
            applying.id,
            result_payload=payload,
            error_code=str(payload["error_code"]),
            error_message=str(payload["error_message"]),
        )
        response = _response_from_record(self.request_store, failed, binding=binding, replay=False, status_override=STATUS_FAILED)
        response["ownership_acquired"] = True
        response["future_transaction_called"] = True
        return response


def _error_code_for_contract_status(status: str) -> str:
    if status == REJECTED_STALE_PLAN:
        return "STALE_PLAN"
    if status == REJECTED_NO_ELIGIBLE_CHAPTERS:
        return "NO_ELIGIBLE_CHAPTERS"
    if "CONFIRMATION" in status:
        return "CONFIRMATION_REQUIRED"
    if "UNSUPPORTED_PHASE" in status:
        return "UNSUPPORTED_PHASE"
    return "INVALID_REQUEST"


def _operator_action_for_contract_status(status: str) -> str:
    if status == REJECTED_STALE_PLAN:
        return OPERATOR_REBUILD_PLAN
    if status == REJECTED_NO_ELIGIBLE_CHAPTERS:
        return OPERATOR_CREATE_NEW_REQUEST
    return OPERATOR_REVIEW_REQUEST


def classify_stale_applying_request(
    *,
    record: BatchPrepareRequestRecord,
    current_plan: Mapping[str, Any] | None,
    execution_evidence: Mapping[str, Any] | None = None,
    is_stale: bool,
) -> dict[str, Any]:
    if record.state != STATE_APPLYING:
        return {
            "schema": ORCHESTRATION_SCHEMA,
            "decision": RECONCILE_REQUEST_RECORD_CORRUPT,
            "operator_action": OPERATOR_REVIEW_REQUEST,
            "automatic_mutation": False,
            "reason": "Only APPLYING records can be reconciled by this classifier.",
        }
    if not is_stale:
        return {
            "schema": ORCHESTRATION_SCHEMA,
            "decision": RECONCILE_STILL_IN_PROGRESS,
            "operator_action": OPERATOR_WAIT_AND_RETRY_STATUS,
            "automatic_mutation": False,
            "reason": "Request is not older than the review cutoff.",
        }
    evidence = dict(execution_evidence or {})
    evidence_status = str(evidence.get("status") or "none").upper()
    current_fingerprint = str((current_plan or {}).get("plan_fingerprint") or "")
    if current_fingerprint and current_fingerprint != record.plan_fingerprint:
        return {
            "schema": ORCHESTRATION_SCHEMA,
            "decision": RECONCILE_OPERATOR_REVIEW_REQUIRED,
            "operator_action": OPERATOR_REBUILD_PLAN,
            "automatic_mutation": False,
            "reason": "Current plan fingerprint no longer matches the durable request.",
        }
    if evidence_status in {"APPLIED", "COMPLETED"}:
        return {
            "schema": ORCHESTRATION_SCHEMA,
            "decision": RECONCILE_APPLIED_RESULT_RECOVERY_REQUIRED,
            "operator_action": OPERATOR_REVIEW_REQUEST,
            "automatic_mutation": False,
            "reason": "External evidence indicates success but no durable APPLIED result is stored.",
        }
    if evidence_status in {"AMBIGUOUS", "CONFLICT"}:
        return {
            "schema": ORCHESTRATION_SCHEMA,
            "decision": RECONCILE_OPERATOR_REVIEW_REQUIRED,
            "operator_action": OPERATOR_INVESTIGATE_AMBIGUOUS_APPLYING,
            "automatic_mutation": False,
            "reason": "External evidence is ambiguous.",
        }
    return {
        "schema": ORCHESTRATION_SCHEMA,
        "decision": RECONCILE_SAFE_TO_MARK_FAILED_RETRYABLE,
        "operator_action": OPERATOR_CREATE_NEW_REQUEST,
        "automatic_mutation": False,
        "reason": "No execution evidence is attached to the stale APPLYING request.",
    }


__all__ = [
    "BatchPrepareOrchestrator",
    "FuturePrepareResult",
    "FUTURE_AMBIGUOUS",
    "FUTURE_FAILED_RETRYABLE",
    "FUTURE_FAILED_REVIEW_REQUIRED",
    "FUTURE_REJECTED",
    "FUTURE_SUCCESS",
    "classify_stale_applying_request",
]
