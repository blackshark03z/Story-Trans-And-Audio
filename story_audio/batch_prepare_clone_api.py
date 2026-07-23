"""Authenticated API service for clone acceptance and production PREPARE."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .batch_plan import build_batch_plan
from .batch_prepare_execution_attempt_store import BatchPrepareExecutionAttemptStore
from .batch_prepare_isolated_adapter import (
    BatchPrepareCommittedEvidenceReader,
    BatchPrepareIsolatedAdapter,
    DatabaseAuthoritativeSnapshotProvider,
)
from .batch_prepare_isolated_transaction_service import BatchPrepareIsolatedTransactionService
from .batch_prepare_operator_auth import (
    OperatorAuthDecision,
    authenticate_operator,
)
from .batch_prepare_orchestrator import BatchPrepareOrchestrator
from .batch_prepare_runtime_integration import (
    RuntimeIntegrationConfig,
    RuntimeIntegrationDescriptor,
)
from .batch_prepare_store import BatchPrepareRequestStore
from .config import Settings
from .db import Database
from .range_readiness import get_range_readiness
from .storage import ContentStore
from .voice_eligibility import EffectiveVoiceCatalog, VoiceCatalogUnavailable


MAX_REQUEST_BYTES = 16 * 1024
FORBIDDEN_PUBLIC_KEY_PARTS = (
    "token",
    "hash",
    "fingerprint",
    "digest",
    "identity",
    "authorization",
    "credential",
    "db_path",
    "sql",
    "traceback",
    "full_text",
    "casting_plan",
    "owner",
    "generation",
)


class ClonePrepareApiError(RuntimeError):
    def __init__(self, code: str, message: str, *, http_status: int):
        super().__init__(message)
        self.code = code
        self.http_status = int(http_status)


@dataclass(frozen=True)
class ClonePrepareApiResult:
    http_status: int
    payload: Mapping[str, Any]


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if not any(part in str(key).lower() for part in FORBIDDEN_PUBLIC_KEY_PARTS)
        }
    if isinstance(value, (tuple, list)):
        return [_sanitize(item) for item in value]
    return value


def _http_status(payload: Mapping[str, Any]) -> int:
    status = str(payload.get("status") or "")
    error_code = str(payload.get("error_code") or "")
    if status in {"PREPARE_SIMULATED_APPLIED", "APPLIED_REPLAYED", "APPLIED"}:
        return 200
    if status in {
        "REQUEST_APPLYING",
        "OWNERSHIP_LOST_REPLAYED",
        "PLANNED_REPLAYED",
    }:
        return 202
    if status == "INVALID_REQUEST":
        return 400
    if status == "REQUEST_ID_CONFLICT" or error_code in {
        "REQUEST_ID_CONFLICT",
        "STALE_PLAN",
        "PREPARE_CONFLICT",
    }:
        return 409
    if status in {
        "PREPARE_REJECTED",
        "PREPARE_FAILED",
        "REJECTED_REPLAYED",
        "FAILED_REPLAYED",
    }:
        return 409
    return 500


def _public_api_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = _sanitize(value)
    result = payload.get("result")
    if isinstance(result, Mapping) and result.get("job_id") is not None:
        payload["job_id"] = int(result["job_id"])
    return payload


class BatchPrepareApiService:
    """Small authenticated boundary around the accepted PREPARE orchestrator."""

    def __init__(
        self,
        *,
        config: RuntimeIntegrationConfig,
        descriptor: RuntimeIntegrationDescriptor,
        orchestrator: BatchPrepareOrchestrator,
        request_store: BatchPrepareRequestStore,
    ) -> None:
        if not descriptor.prepare_mutation_enabled:
            raise ClonePrepareApiError(
                "PREPARE_DISABLED",
                "PREPARE mutation is not authorized.",
                http_status=503,
            )
        self.config = config
        self.descriptor = descriptor
        self.orchestrator = orchestrator
        self.request_store = request_store

    def authenticate(
        self,
        authorization_header: str | None,
        *,
        credential_in_url: bool = False,
        client_operator_id: str | None = None,
    ) -> OperatorAuthDecision:
        decision = authenticate_operator(
            self.config.auth,
            authorization_header,
            credential_in_url=credential_in_url,
            client_operator_id=client_operator_id,
        )
        if not decision.authenticated:
            raise ClonePrepareApiError(
                decision.state,
                "Operator authentication failed.",
                http_status=401,
            )
        if not self.descriptor.prepare_mutation_enabled:
            raise ClonePrepareApiError(
                "PREPARE_DISABLED",
                "PREPARE mutation is disabled.",
                http_status=503,
            )
        return decision

    def prepare(
        self,
        request: Mapping[str, Any],
        *,
        authorization_header: str | None,
        credential_in_url: bool = False,
    ) -> ClonePrepareApiResult:
        self.authenticate(authorization_header, credential_in_url=credential_in_url)
        payload = dict(request)
        if self.descriptor.production_mutation_enabled:
            existing = self.request_store.get_request_by_client_request_id(
                str(payload.get("client_request_id") or "")
            )
            chapter_count = int(payload["to_chapter"]) - int(payload["from_chapter"]) + 1
            if chapter_count < 1 or chapter_count > 3:
                raise ClonePrepareApiError(
                    "CANARY_SCOPE_REJECTED",
                    "Production PREPARE is limited to one through three chapters.",
                    http_status=400,
                )
            if existing is None or existing.state != "APPLIED":
                try:
                    current_plan = self.orchestrator.current_plan_provider(
                        book_id=int(payload["book_id"]),
                        from_chapter=int(payload["from_chapter"]),
                        to_chapter=int(payload["to_chapter"]),
                        target_phase=str(payload["target_phase"]),
                    )
                except VoiceCatalogUnavailable as exc:
                    raise ClonePrepareApiError(
                        "VOICE_CATALOG_UNAVAILABLE",
                        str(exc),
                        http_status=503,
                    ) from exc
                included = current_plan.get("included")
                if not isinstance(included, list) or len(included) != chapter_count:
                    raise ClonePrepareApiError(
                        "CANARY_SCOPE_NOT_FULLY_ELIGIBLE",
                        "Every chapter in the production PREPARE canary must be eligible.",
                        http_status=409,
                    )
        payload["explicit_confirmation"] = payload.pop("confirmation", None)
        result = _public_api_payload(self.orchestrator.prepare(payload))
        return ClonePrepareApiResult(_http_status(result), result)

    def status(
        self,
        client_request_id: str,
        *,
        authorization_header: str | None,
        credential_in_url: bool = False,
    ) -> ClonePrepareApiResult:
        self.authenticate(authorization_header, credential_in_url=credential_in_url)
        record = self.request_store.get_request_by_client_request_id(client_request_id)
        if record is None:
            raise ClonePrepareApiError(
                "PREPARE_REQUEST_NOT_FOUND",
                "PREPARE request was not found.",
                http_status=404,
            )
        if record.state == "PLANNED":
            return ClonePrepareApiResult(
                200,
                {
                    "status": "PLANNED",
                    "request_id": record.id,
                    "request_state": record.state,
                    "replay": True,
                    "mutation_performed": False,
                },
            )
        replay_request = {
            "client_request_id": record.client_request_id,
            "book_id": record.book_id,
            "from_chapter": record.from_chapter,
            "to_chapter": record.to_chapter,
            "target_phase": record.target_phase,
            "plan_fingerprint": record.plan_fingerprint,
            "explicit_confirmation": True,
        }
        result = _public_api_payload(self.orchestrator.prepare(replay_request))
        return ClonePrepareApiResult(_http_status(result), result)


def build_prepare_api_service(
    *,
    settings: Settings,
    config: RuntimeIntegrationConfig,
    descriptor: RuntimeIntegrationDescriptor,
    voice_catalog_loader: Callable[[], EffectiveVoiceCatalog] | None = None,
) -> BatchPrepareApiService | None:
    if (
        not descriptor.prepare_mutation_enabled
        or descriptor.inspected_db_path != settings.db_path.resolve(strict=False)
    ):
        return None
    if descriptor.production_mutation_enabled and voice_catalog_loader is None:
        raise ClonePrepareApiError(
            "VOICE_CATALOG_GUARD_REQUIRED",
            "Production PREPARE requires the authoritative voice catalog guard.",
            http_status=503,
        )
    writable_db = Database(settings.db_path)
    store = ContentStore(settings)
    request_store = BatchPrepareRequestStore(writable_db)

    def current_plan_provider(
        *,
        book_id: int,
        from_chapter: int,
        to_chapter: int,
        target_phase: str,
    ) -> dict[str, Any]:
        readiness = get_range_readiness(
            writable_db,
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            voice_catalog=voice_catalog_loader() if voice_catalog_loader else None,
            store=store,
        )
        return build_batch_plan(readiness, target_phase=target_phase)

    allow_canonical = descriptor.production_mutation_enabled
    attempt_store = BatchPrepareExecutionAttemptStore(
        writable_db,
        allow_canonical=allow_canonical,
    )
    transaction_service = BatchPrepareIsolatedTransactionService(
        writable_db,
        allow_canonical=allow_canonical,
    )
    snapshot_provider = DatabaseAuthoritativeSnapshotProvider(
        writable_db,
        store,
        settings,
        temporary_root=settings.data_dir,
        allow_canonical=allow_canonical,
        voice_catalog_loader=voice_catalog_loader,
    )
    evidence_reader = BatchPrepareCommittedEvidenceReader(
        writable_db,
        temporary_root=settings.data_dir,
        allow_canonical=allow_canonical,
    )
    adapter = BatchPrepareIsolatedAdapter(
        db=writable_db,
        attempt_store=attempt_store,
        transaction_service=transaction_service,
        snapshot_provider=snapshot_provider,
        evidence_reader=evidence_reader,
        temporary_root=settings.data_dir,
        allow_canonical=allow_canonical,
    )
    orchestrator = BatchPrepareOrchestrator(
        current_plan_provider=current_plan_provider,
        request_store=request_store,
        future_prepare_transaction=adapter,
    )
    return BatchPrepareApiService(
        config=config,
        descriptor=descriptor,
        orchestrator=orchestrator,
        request_store=request_store,
    )


# Compatibility names keep the already accepted clone-only test contract stable.
BatchPrepareCloneApiService = BatchPrepareApiService


def build_clone_prepare_api_service(
    *,
    settings: Settings,
    config: RuntimeIntegrationConfig,
    descriptor: RuntimeIntegrationDescriptor,
) -> BatchPrepareApiService | None:
    return build_prepare_api_service(
        settings=settings,
        config=config,
        descriptor=descriptor,
    )


__all__ = [
    "BatchPrepareApiService", "BatchPrepareCloneApiService",
    "ClonePrepareApiError",
    "ClonePrepareApiResult",
    "MAX_REQUEST_BYTES",
    "build_clone_prepare_api_service", "build_prepare_api_service",
]
