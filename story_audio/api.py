from __future__ import annotations

import json
import os
import signal
import threading
import time
import unicodedata
import uuid
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Literal

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.background import BackgroundTask

from .audio_archive import AudioArchiveError, build_archive_plan, create_archive
from .config import canonical_production_db_path, settings
from .casting import (
    CastingError,
    approve_plan,
    casting_context,
    create_casting_draft,
    create_character,
    deactivate_character,
    get_plan,
    list_characters,
    update_character,
    validate_approved_plan,
)
from .character_bible import (
    CharacterBibleError,
    apply_character_bible_import,
    parse_character_bible,
    plan_character_bible_import,
)
from .chapter_voice_overrides import (
    ChapterVoiceOverrideError,
    apply_chapter_voice_override,
)
from .character_assignment import (
    CharacterAssignmentError,
    add_character_aliases,
    apply_speaker_character_mapping,
    clear_speaker_character_mapping,
    create_assignment_character,
)
from .active_output import annotate_chapter_rows, annotate_job_rows, get_active_output_bindings
from .artifact_configuration import artifact_configuration_summary
from .batch_plan import build_batch_plan
from .batch_prepare_clone_api import (
    MAX_REQUEST_BYTES,
    ClonePrepareApiError,
    build_prepare_api_service,
)
from .batch_prepare_runtime_integration import (
    CLONE_DISABLED,
    PRODUCTION,
    CloneReadOnlyDatabase,
    build_runtime_integration,
    public_runtime_readiness,
    read_runtime_integration_config,
    require_clone_runtime,
)
from .production_runtime_readiness import production_runtime_readiness
from .runtime_operator_session import (
    RuntimeOperatorSession,
    mutation_service_construction_allowed,
)
from .batch_prepare_schema import PREPARE_SCHEMA_VERSION, prepare_migration_runner
from .book_voice_registry import BookVoiceRegistryError, get_book_voice_registry
from .custom_voice import CustomVoiceRepository
from .custom_voice_api import (
    build_voice_catalog_handler,
    create_custom_voice_handler,
    create_custom_voice_revision_handler,
    deactivate_custom_voice_handler,
    get_custom_voice_handler,
    get_custom_voice_revision_handler,
    list_custom_voice_revisions_handler,
    list_custom_voices_handler,
    reactivate_custom_voice_handler,
    set_preferred_synthesis_revision_handler,
)
from .db import Database, collect_query_metrics, utcnow
from .diagnostics import (
    DiagnosticNotFound,
    RetryConflict,
    get_job_chapter_diagnostics,
    get_job_diagnostics,
    get_segment_diagnostics,
    retry_job_chapter,
    retry_segment,
)
from .human_approval import (
    resolve_authoritative_human_approval,
    resolve_repair_draft_evidence,
    resolve_repair_draft_review_evidence,
    resolve_repair_plan_evidence,
)
from .epub import import_epub
from .gemini import GeminiSpeakerAssignmentError, GeminiSpeakerReviewSuggestionError
from .pipeline import (
    JOB_PREPARED_STATUS,
    JobPreparationConflict,
    JobStartConflict,
    PipelineWorker,
    create_job,
    prepare_job,
    start_prepared_job,
)
from .production_task_projection import get_production_task_projection
from .production_preflight import get_production_preflight
from .production_commands import (
    ProductionCommandError,
    ProductionCommandMutation,
    ProductionCommandService,
)
from .range_input import (
    RangeInputError,
    approve_ready_casting_plans,
    approve_ready_speaker_drafts,
    get_range_input_snapshot,
    prepare_range_inputs,
)
from .range_readiness import get_range_readiness
from .storage import ContentStore
from .storage_cleanup import (
    CONFIRMATION as STORAGE_CLEANUP_CONFIRMATION,
    StorageCleanupError,
    build_report as build_storage_report,
    execute_cleanup,
)
from .speaker_assignment import (
    SpeakerAssignmentError,
    generate_speaker_assignment_draft,
    get_speaker_assignment_draft,
)
from .speaker_review import (
    SpeakerReviewNotFound,
    SpeakerReviewConflict,
    SpeakerReviewError,
    approve_speaker_assignment_draft_only,
    approve_speaker_review,
    create_casting_plan_draft_from_speaker_review,
    get_speaker_review_draft,
    list_speaker_review_drafts,
    review_speaker_assignment_row,
)
from .speaker_review_suggestions import (
    SpeakerReviewSuggestionError,
    accept_speaker_review_suggestion,
    approve_high_confidence_suggestions,
    approve_speaker_review_batch_items,
    generate_speaker_review_suggestions,
    get_speaker_review_queue,
    record_speaker_suggestion_decision,
    record_speaker_suggestion_note,
    restore_speaker_suggestion_pending,
)
from .tts import tts_service
from .text_correction import (
    TextCorrectionConflict,
    TextCorrectionError,
    TextCorrectionNotFound,
    apply_targeted_text_correction,
)
from .text_diff import TextDiffError, build_revision_diff, list_revision_metadata
from .voice_preview import VoicePreviewService
from .voice_profile import (
    VoiceProfileError,
    get_book_voice_profile,
    profile_validation,
    resolve_voice,
    set_book_voice_profile,
    set_character_gender,
    set_character_voice_override,
)
from .video_export import (
    VideoExportError,
    create_video_export,
    inspect_video_export,
    load_video_export_file,
)
from .voice_ref import CustomVoiceContext, is_custom_ref, resolve_custom_ref
from .voice_eligibility import (
    VoiceCatalogAuthority,
    VoiceCatalogUnavailable,
    VoiceEligibilityBlocked,
    inspect_voice_ref,
    require_casting_plan_eligible,
)


def _build_runtime_database(path: Path, integration):
    if integration.runtime_mode == CLONE_DISABLED or (
        integration.runtime_mode == PRODUCTION
        and not getattr(integration, "production_render_enabled", False)
    ):
        return CloneReadOnlyDatabase(path)
    migration_runner = (
        prepare_migration_runner()
        if integration.schema_version == PREPARE_SCHEMA_VERSION
        else None
    )
    return Database(path, migration_runner=migration_runner)


settings.ensure_dirs()
prepare_runtime_config = read_runtime_integration_config()
prepare_runtime_integration = build_runtime_integration(
    prepare_runtime_config,
    db_path=settings.db_path,
    repository_root=settings.root,
    canonical_db_path=canonical_production_db_path(),
)
require_clone_runtime(prepare_runtime_integration)
runtime_operator_session = RuntimeOperatorSession.from_environment(
    prepare_runtime_integration,
    prepare_runtime_config.auth,
)
db = _build_runtime_database(settings.db_path, prepare_runtime_integration)
store = ContentStore(settings)
custom_voice_repo = CustomVoiceRepository(db, store)


def _voice_catalog_payload() -> dict[str, Any]:
    return build_voice_catalog_handler(custom_voice_repo, tts_service.voices())


def _load_voice_catalog():
    return VoiceCatalogAuthority(_voice_catalog_payload).load()


_prepare_service_construction_allowed = mutation_service_construction_allowed(
    prepare_runtime_integration,
    runtime_operator_session,
)
batch_prepare_api_service = (
    build_prepare_api_service(
        settings=settings,
        config=prepare_runtime_config,
        descriptor=prepare_runtime_integration,
        voice_catalog_loader=_load_voice_catalog,
    )
    if _prepare_service_construction_allowed
    else None
)
worker = PipelineWorker(db, store, tts_service, settings)
voice_previews = VoicePreviewService(
    tts_service, settings, custom_voice_repo=custom_voice_repo, store=store
)
production_operation_lock = threading.RLock()


def _production_runtime_readiness() -> dict[str, Any]:
    return production_runtime_readiness(
        prepare_runtime_integration,
        session=runtime_operator_session,
        output_root=settings.output_dir,
        # Read-only catalog fixtures intentionally expose no provider status.
        # Treat that as unavailable instead of failing the readiness endpoint.
        provider_configured=tts_service.provider_available(),
        mutation_service_constructed=batch_prepare_api_service is not None,
    )


def _request_prepare_authorization(request: Request) -> str | None:
    return runtime_operator_session.authorization_header(request)


def _serialized_production_mutation(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with production_operation_lock:
            return function(*args, **kwargs)

    return wrapped


def _build_custom_voice_context() -> CustomVoiceContext | None:
    """Build Custom Voice context from the global repository.
    
    Returns context with active custom voices that have revisions,
    or None if no custom voices are available.
    """
    try:
        return CustomVoiceContext.from_repository(custom_voice_repo)
    except Exception:
        # If context building fails, return None to allow preset-only operation
        return None


class ImportRequest(BaseModel):
    path: str


class JobRequest(BaseModel):
    book_id: int
    from_chapter: int = Field(ge=1)
    to_chapter: int = Field(ge=1)
    voice_name: str
    repair_mode: str = "all_selected"
    output_format: str = "m4a"
    skip_completed: bool = True
    casting_plan_id: int | None = None


def _job_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, VoiceCatalogUnavailable):
        return HTTPException(
            503,
            {
                "code": "VOICE_CATALOG_UNAVAILABLE",
                "message": str(exc),
                "retryable": True,
            },
        )
    if isinstance(exc, VoiceEligibilityBlocked):
        return HTTPException(
            409,
            {
                "code": "VOICE_ELIGIBILITY_BLOCKED",
                "message": str(exc),
                "issues": list(exc.issues),
            },
        )
    if isinstance(exc, LookupError):
        return HTTPException(404, str(exc))
    if isinstance(exc, (JobPreparationConflict, JobStartConflict)):
        return HTTPException(409, str(exc))
    return HTTPException(400, str(exc))


class VoicePreviewRequest(BaseModel):
    voice_id: str | None = Field(default=None, min_length=1, max_length=200)
    custom_voice_revision_id: int | None = Field(default=None, gt=0)
    preview_text: str | None = Field(default=None, max_length=500)


class CharacterCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    default_voice_id: str | None = Field(default=None, max_length=200)
    voice_override_id: str | None = Field(default=None, max_length=200)
    gender: str | None = None


class AssignmentCharacterCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: int = Field(gt=0)
    display_name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    gender: str | None = None
    role: str = "unknown"


class AssignmentAliasPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: int = Field(gt=0)
    character_id: int = Field(gt=0)
    aliases: list[str] = Field(min_length=1, max_length=20)


class SpeakerCharacterMappingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: int = Field(gt=0)
    speaker_key: str = Field(min_length=1, max_length=200)
    character_id: int = Field(gt=0)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    expected_registry_fingerprint: str | None = Field(default=None, max_length=4000)


class SpeakerCharacterClearPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: int = Field(gt=0)
    speaker_key: str = Field(min_length=1, max_length=200)
    expected_registry_fingerprint: str | None = Field(default=None, max_length=4000)


class CharacterUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    default_voice_id: str | None = Field(default=None, min_length=1, max_length=200)
    gender: str | None = None
    role: str | None = None
    age_group: str | None = None
    description: str | None = Field(default=None, max_length=4000)
    speech_style: str | None = Field(default=None, max_length=4000)
    visual_notes: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=4000)


class BookVoiceProfileRequest(BaseModel):
    narrator_voice_id: str = Field(min_length=1, max_length=200)
    male_dialogue_voice_id: str = Field(min_length=1, max_length=200)
    female_dialogue_voice_id: str = Field(min_length=1, max_length=200)
    unknown_fallback: str = "narrator"
    unknown_voice_id: str | None = Field(default=None, max_length=200)


class CharacterOverrideRequest(BaseModel):
    voice_override_id: str | None = Field(default=None, max_length=200)
    gender: str | None = None


class VoiceResolveRequest(BaseModel):
    speaker_type: str
    character_id: int | None = None
    inferred_gender: str | None = None
    gender: str | None = None
    use_character_override: bool = True
    voice_override_id: str | None = Field(default=None, max_length=200)


class CharacterBibleImportRequest(BaseModel):
    payload: dict[str, Any]
    source_label: str = Field(default="api-character-bible.json", max_length=255)
    update_existing: bool = False


class CastingAssignment(BaseModel):
    utterance_id: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    role: str
    character_id: int | None = None


class CastingDraftRequest(BaseModel):
    text_revision_id: int
    narrator_voice_id: str
    assignments: list[CastingAssignment] = Field(default_factory=list)


class SpeakerAssignmentDraftRequest(BaseModel):
    mode: str = "unassigned_only"
    utterance_ids: list[str] | None = None
    force_refresh: bool = False


class SpeakerReviewDecision(BaseModel):
    utterance_id: str = Field(min_length=1, max_length=100)
    speaker_type: str
    character_id: int | None = None
    decision_source: str


class SpeakerReviewApprovalRequest(BaseModel):
    base_casting_plan_revision_id: int | None = None
    expected_draft_fingerprint: str = Field(min_length=64, max_length=64)
    expected_text_revision_id: int
    decisions: list[SpeakerReviewDecision] = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=200)


class SpeakerAssignmentRowReviewRequest(BaseModel):
    decision: str = Field(
        pattern="^(MARK_NARRATOR|KEEP_UNKNOWN|MAP_TO_EXISTING_CHARACTER)$"
    )
    character_id: int | None = None
    operator_note: str | None = Field(default=None, max_length=4000)


class SpeakerReviewCastingPlanDraftRequest(BaseModel):
    speaker_draft_id: int = Field(gt=0)
    base_casting_plan_revision_id: int | None = None
    expected_draft_fingerprint: str = Field(min_length=64, max_length=64)
    expected_text_revision_id: int
    decisions: list[SpeakerReviewDecision] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=1, max_length=200)
    operator_note: str | None = Field(default=None, max_length=4000)


class HumanQaPositionMarker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: float = Field(ge=0)
    segment_id: int | None = Field(default=None, gt=0)
    utterance_id: str | None = Field(default=None, max_length=100)
    issue_type: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=1000)


class HumanQaFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_speed_target: float | None = Field(default=None, ge=0.5, le=2.0)
    repeated_words: bool = False
    local_pacing_adjustment_required: bool = False
    issue_types: list[
        Literal["repeated_words", "overall_pacing", "local_pacing", "other"]
    ] = Field(default_factory=list, max_length=4)
    operator_note: str | None = Field(default=None, max_length=4000)
    position_markers: list[HumanQaPositionMarker] = Field(
        default_factory=list, max_length=50
    )


class HumanApprovalRequest(BaseModel):
    status: str = Field(pattern="^(approved|needs_fixes)$")
    notes: str | None = Field(default=None, max_length=4000)
    qa_feedback: HumanQaFeedback | None = None


class RepairPlanConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int = Field(gt=0)
    artifact_id: int = Field(gt=0)
    qa_evidence_id: int = Field(gt=0)
    repeated_words: bool = False
    global_speed_target: float | None = Field(default=None, ge=0.5, le=2.0)
    local_pacing_adjustment_required: bool = False
    operator_note: str | None = Field(default=None, max_length=4000)


class ApplyRepairPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int = Field(gt=0)
    artifact_id: int = Field(gt=0)
    qa_evidence_id: int = Field(gt=0)
    repair_plan_evidence_id: int = Field(gt=0)


class RepairMarkerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp_seconds: float | None = Field(default=None, ge=0)
    nearest_utterance: str | None = Field(default=None, max_length=1000)
    issue: Literal["repeated_words", "too_slow", "too_fast", "needs_pause"]
    note: str | None = Field(default=None, max_length=2000)
    local_pace: float | None = Field(default=None, ge=0.5, le=2.0)


class RepairDraftReviewConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int = Field(gt=0)
    artifact_id: int = Field(gt=0)
    qa_evidence_id: int = Field(gt=0)
    repair_plan_evidence_id: int = Field(gt=0)
    repair_draft_evidence_id: int = Field(gt=0)
    markers: list[RepairMarkerRequest] = Field(default_factory=list, max_length=100)


class StorageCleanupRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=100)


class RuntimeRestartRequest(BaseModel):
    confirmation: Literal["RESTART_STORY_AUDIO"]


class TargetedTextCorrectionRequest(BaseModel):
    base_revision_id: int = Field(gt=0)
    expected_text: str
    replacement_text: str
    reason: str = Field(max_length=4000)


class BatchPrepareApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: str = Field(min_length=8, max_length=200)
    book_id: int = Field(gt=0)
    from_chapter: int = Field(ge=0)
    to_chapter: int = Field(ge=0)
    target_phase: Literal["PREPARE"]
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmation: Literal[True]


class RangeInputScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: int = Field(gt=0)
    from_chapter: int = Field(ge=0)
    to_chapter: int = Field(ge=0)
    skip_completed: bool = True


class RangeSpeakerDraftRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int = Field(gt=0)
    draft_id: int = Field(gt=0)


class RangeSpeakerApprovalRequest(RangeInputScopeRequest):
    chapters: list[RangeSpeakerDraftRef] = Field(min_length=1, max_length=50)


class RangeCastingPlanRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int = Field(gt=0)
    plan_id: int = Field(gt=0)


class RangeCastingApprovalRequest(RangeInputScopeRequest):
    chapters: list[RangeCastingPlanRef] = Field(min_length=1, max_length=50)


class ProductionCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_type: str = Field(
        min_length=3,
        max_length=80,
        pattern=r"^[A-Za-z][A-Za-z0-9_]{2,79}$",
    )
    idempotency_key: str = Field(
        min_length=8,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,199}$",
    )
    scope: dict[str, Any]
    payload: dict[str, Any] = Field(default_factory=dict)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    prepare_only_runtime = (
        prepare_runtime_integration.runtime_mode == CLONE_DISABLED
        or (
            prepare_runtime_integration.runtime_mode == PRODUCTION
            and not getattr(
                prepare_runtime_integration,
                "production_render_enabled",
                False,
            )
        )
    )
    if not prepare_only_runtime:
        db.initialize()
        worker.start()
    yield
    if not prepare_only_runtime:
        worker.stop()


app = FastAPI(title="Story Audio", version="0.1.0", lifespan=lifespan)


def as_dict(row) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _parse_human_approval(raw: Any) -> dict[str, Any] | None:
    if raw in (None, ""):
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _active_artifact_snapshot(chapter: dict[str, Any]) -> dict[str, Any] | None:
    artifact_id = int(chapter.get("active_audio_artifact_id") or 0)
    if not artifact_id:
        return None
    artifact = db.fetch_one(
        """
        SELECT a.id,
               a.path,
               a.sha256,
               a.duration_ms,
               a.job_chapter_id,
               jc.job_id
        FROM artifacts a
        LEFT JOIN job_chapters jc ON jc.id = a.job_chapter_id
        WHERE a.id = ?
        """,
        (artifact_id,),
    )
    if not artifact:
        return None
    return {
        "artifact_id": int(artifact["id"]),
        "job_id": int(artifact["job_id"]) if artifact["job_id"] else None,
        "output_path": artifact["path"],
        "sha256": artifact["sha256"],
        "duration_ms": int(artifact["duration_ms"]) if artifact["duration_ms"] is not None else None,
    }


def _decorate_human_approval(
    chapter: dict[str, Any], approval: dict[str, Any] | None, active_output: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    chapter_data = dict(chapter)
    active_artifact_id = int(
        active_output.get("active_output_artifact_id")
        or chapter_data.get("active_audio_artifact_id")
        or 0
    )
    normalized = dict(approval) if approval else None
    warning = None
    if normalized:
        stored_artifact_id = int(normalized.get("artifact_id") or 0)
        matches_active = bool(stored_artifact_id and active_artifact_id and stored_artifact_id == active_artifact_id)
        normalized["matches_active_artifact"] = matches_active
        if normalized.get("status") == "approved" and not matches_active:
            warning = "Bản audio hiện tại khác với bản đã chốt trước đó. Cần kiểm tra lại."
        if warning:
            normalized["warning"] = warning
    else:
        matches_active = False

    status = "pending"
    label = "Chưa chốt"
    if normalized:
        raw_status = str(normalized.get("status") or "").lower()
        if raw_status == "approved" and normalized.get("matches_active_artifact", matches_active):
            status = "accepted"
            label = "Đã chốt"
        elif raw_status == "approved":
            status = "approved_stale"
            label = "Đã chốt"
        elif raw_status == "needs_fixes" and normalized.get(
            "matches_active_artifact", matches_active
        ):
            status = "needs_fixes"
            label = "Cần sửa"
    chapter_data["human_qa_status"] = status
    chapter_data["human_approval_status"] = normalized.get("status") if normalized else "pending"
    chapter_data["human_approval_label"] = label
    chapter_data["human_approval_warning"] = warning
    return chapter_data, normalized


def _character_bible_plan(book_id: int, request: CharacterBibleImportRequest) -> dict[str, Any]:
    raw = json.dumps(request.payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    parsed = parse_character_bible(raw, source_label=request.source_label)
    requested_voices = {
        record.get("voice_override_id") for record in parsed.records
        if record.get("voice_override_id")
    }
    allowed_voices = _preset_voice_ids() if requested_voices else None
    return plan_character_bible_import(
        db,
        book_id,
        parsed,
        allowed_voice_ids=allowed_voices,
        update_existing=request.update_existing,
    )


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    epubs = sorted(str(path.resolve()) for path in settings.root.glob("*.epub"))
    return {
        "gemini_configured": bool(settings.gemini_key()),
        "gemini_model": settings.gemini_model,
        "tts_status": tts_service.status,
        "tts_error": tts_service.error,
        "undo_seconds": settings.undo_seconds,
        "available_epubs": epubs,
    }


@app.get("/api/runtime")
def get_runtime_identity() -> dict[str, Any]:
    data_root = settings.data_dir.resolve()
    db_path = settings.db_path.resolve()
    live_db = canonical_production_db_path().resolve()
    live_root = live_db.parent
    worker_thread = getattr(worker, "_thread", None)
    return {
        "root": str(settings.root.resolve()),
        "data_root": str(data_root),
        "db_path": str(db_path),
        "schema_version": db.schema_version(),
        "latest_schema_version": db.latest_schema_version,
        "canonical_live_data_root": str(live_root),
        "canonical_live_db_path": str(live_db),
        "is_canonical_live_data_root": data_root == live_root,
        "is_canonical_live_db": db_path == live_db,
        "worker_available": bool(worker_thread and worker_thread.is_alive()),
        "supervised_restart_available": os.environ.get("STORY_AUDIO_SUPERVISED") == "1",
    }


@app.get("/api/production/prepare-readiness")
def production_prepare_readiness(response: Response) -> dict[str, Any]:
    payload = _production_runtime_readiness()
    runtime_operator_session.apply_cookie(response)
    return payload


def _prepare_service():
    if batch_prepare_api_service is None:
        if prepare_runtime_integration.schema_version != 15:
            raise HTTPException(503, {"code": "SCHEMA_NOT_READY"})
        if prepare_runtime_integration.kill_switch_active:
            raise HTTPException(503, {"code": "KILL_SWITCH_ACTIVE"})
        if prepare_runtime_integration.authentication_state != "AUTH_CONFIGURED":
            raise HTTPException(503, {"code": "AUTH_NOT_READY"})
        if (
            prepare_runtime_integration.runtime_mode == PRODUCTION
            and not runtime_operator_session.verified
        ):
            raise HTTPException(503, {"code": "AUTH_NOT_READY"})
        raise HTTPException(503, {"code": "PREPARE_DISABLED"})
    return batch_prepare_api_service


def _clone_prepare_error(exc: ClonePrepareApiError) -> HTTPException:
    if str(exc.code).startswith("AUTH_"):
        return HTTPException(
            exc.http_status,
            {
                "code": "AUTH_NOT_READY",
                "message": "Không thể chuẩn bị audio vì môi trường sản xuất chưa được xác thực. Hệ thống chưa gửi yêu cầu PREPARE.",
            },
        )
    return HTTPException(exc.http_status, {"code": exc.code, "message": str(exc)})


@app.post("/api/production/batch-prepare")
async def production_batch_prepare(request: Request) -> dict[str, Any]:
    if request.query_params:
        raise HTTPException(400, {"code": "URL_AUTHORITY_REJECTED"})
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BYTES:
                raise HTTPException(413, {"code": "REQUEST_TOO_LARGE"})
        except ValueError as exc:
            raise HTTPException(400, {"code": "INVALID_CONTENT_LENGTH"}) from exc
    body = await request.body()
    if len(body) > MAX_REQUEST_BYTES:
        raise HTTPException(413, {"code": "REQUEST_TOO_LARGE"})
    try:
        decoded = json.loads(body)
        payload = BatchPrepareApiRequest.model_validate(decoded)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise HTTPException(400, {"code": "INVALID_REQUEST_BODY"}) from exc
    try:
        with production_operation_lock:
            result = _prepare_service().prepare(
                payload.model_dump(),
                authorization_header=_request_prepare_authorization(request),
            )
    except ClonePrepareApiError as exc:
        raise _clone_prepare_error(exc) from exc
    if result.http_status != 200:
        raise HTTPException(result.http_status, dict(result.payload))
    return dict(result.payload)


@app.get("/api/production/batch-prepare/{client_request_id}")
def production_batch_prepare_status(
    client_request_id: str,
    request: Request,
) -> dict[str, Any]:
    if request.query_params:
        raise HTTPException(400, {"code": "URL_AUTHORITY_REJECTED"})
    try:
        result = _prepare_service().status(
            client_request_id,
            authorization_header=_request_prepare_authorization(request),
        )
    except ClonePrepareApiError as exc:
        raise _clone_prepare_error(exc) from exc
    if result.http_status != 200:
        raise HTTPException(result.http_status, dict(result.payload))
    return dict(result.payload)


@app.post("/api/books/import")
def import_book(request: ImportRequest) -> dict[str, Any]:
    try:
        return import_epub(Path(request.path), db, store)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/books")
def list_books() -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """SELECT b.*,
            SUM(CASE WHEN c.audio_status='completed' THEN 1 ELSE 0 END) AS audio_chapters
            FROM books b LEFT JOIN chapters c ON c.book_id=b.id
            GROUP BY b.id ORDER BY b.id DESC"""
    )
    return [dict(row) for row in rows]


@app.get("/api/audio-library")
def audio_library() -> dict[str, Any]:
    rows = db.fetch_all(
        """
        SELECT c.id AS chapter_id,
               c.book_id,
               c.chapter_number,
               c.title AS chapter_title,
               c.audio_status,
               c.active_audio_artifact_id,
               c.human_approval_json,
               b.title AS book_title,
               a.id AS artifact_id,
               a.artifact_type,
               a.sha256,
               a.size_bytes,
               a.duration_ms,
               a.status AS artifact_status,
               a.created_at AS artifact_created_at,
               a.verified_at AS artifact_verified_at
        FROM chapters c
        JOIN books b ON b.id = c.book_id
        JOIN artifacts a
             ON a.id = c.active_audio_artifact_id
            AND a.deleted_at IS NULL
        WHERE c.active_audio_artifact_id IS NOT NULL
        ORDER BY b.title COLLATE NOCASE, c.chapter_number, c.id
        """
    )
    chapter_ids = [int(row["chapter_id"]) for row in rows]
    active_bindings = get_active_output_bindings(db, chapter_ids)
    items: list[dict[str, Any]] = []
    seen_chapters: set[int] = set()
    for row in rows:
        chapter_id = int(row["chapter_id"])
        if chapter_id in seen_chapters:
            continue
        binding = active_bindings.get(chapter_id, {})
        artifact_id = int(row["artifact_id"])
        if binding.get("active_output_artifact_id") != artifact_id:
            continue
        chapter_data, human_approval = _decorate_human_approval(
            {
                "id": chapter_id,
                "active_audio_artifact_id": row["active_audio_artifact_id"],
                "human_approval_json": row["human_approval_json"],
            },
            _parse_human_approval(row["human_approval_json"]),
            binding,
        )
        seen_chapters.add(chapter_id)
        item = {
            "book_id": int(row["book_id"]),
            "book_title": row["book_title"],
            "chapter_id": chapter_id,
            "chapter_number": int(row["chapter_number"]),
            "chapter_title": row["chapter_title"],
            "audio_status": row["audio_status"],
            "artifact_id": artifact_id,
            "artifact_kind": row["artifact_type"],
            "artifact_status": row["artifact_status"],
            "file_url": f"/api/artifacts/{artifact_id}/file",
            "download_url": f"/api/artifacts/{artifact_id}/file",
            "sha256": row["sha256"],
            "size_bytes": int(row["size_bytes"]) if row["size_bytes"] is not None else None,
            "duration_ms": int(row["duration_ms"]) if row["duration_ms"] is not None else None,
            "artifact_created_at": row["artifact_created_at"],
            "artifact_verified_at": row["artifact_verified_at"],
            "job_id": binding.get("active_output_job_id"),
            "job_chapter_id": binding.get("active_output_job_chapter_id"),
            "job_chapter_status": binding.get("active_output_job_chapter_status"),
            "casting_plan_id": binding.get("active_output_casting_plan_id"),
            "casting_plan_revision": binding.get("active_output_casting_plan_revision"),
            "requested_voice": binding.get("active_output_job_voice_name"),
            "applied_narrator_voice": binding.get("active_output_narrator_voice_id"),
            "human_qa_status": chapter_data["human_qa_status"],
            "human_approval_status": chapter_data["human_approval_status"],
            "human_approval_label": chapter_data["human_approval_label"],
            "human_approval_warning": chapter_data["human_approval_warning"],
            "qa_feedback": (human_approval or {}).get("qa_feedback", {}),
            "human_approval_matches_active_artifact": (
                human_approval.get("matches_active_artifact") if human_approval else None
            ),
        }
        item["video_export"] = inspect_video_export(db, settings, artifact_id)
        items.append(item)
    return {"items": items, "total": len(items)}


@app.get("/api/artifacts/{artifact_id}/configuration")
def artifact_configuration(artifact_id: int) -> dict[str, Any]:
    result = artifact_configuration_summary(db, artifact_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Artifact configuration was not found")
    return result


def _archive_plan_payload(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key != "entries"}


def _audio_archive_error(exc: AudioArchiveError) -> HTTPException:
    status = 404 if exc.code == "BOOK_NOT_FOUND" else 409 if exc.issues else 400
    return HTTPException(
        status,
        {"code": exc.code, "message": str(exc), "issues": exc.issues},
    )


@app.get("/api/audio-library/range-archive-readiness")
def audio_library_range_archive_readiness(
    book_id: int = Query(..., gt=0),
    from_chapter: int = Query(..., ge=0),
    to_chapter: int = Query(..., ge=0),
) -> dict[str, Any]:
    try:
        plan = build_archive_plan(
            db,
            output_root=settings.output_dir,
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
        )
    except AudioArchiveError as exc:
        raise _audio_archive_error(exc) from exc
    return _archive_plan_payload(plan)


def _remove_temporary_archive(path: Path) -> None:
    path.unlink(missing_ok=True)


@app.get("/api/audio-library/range-archive")
def audio_library_range_archive(
    book_id: int = Query(..., gt=0),
    from_chapter: int = Query(..., ge=0),
    to_chapter: int = Query(..., ge=0),
):
    try:
        plan = build_archive_plan(
            db,
            output_root=settings.output_dir,
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
        )
        if not plan["ready"]:
            raise AudioArchiveError(
                "ARCHIVE_RANGE_INCOMPLETE",
                "The selected range has missing or invalid active outputs.",
                issues=list(plan["issues"]),
            )
        archive_path = (
            settings.work_dir / "archive_downloads" / f"{uuid.uuid4().hex}.zip"
        )
        archive = create_archive(plan, archive_path)
    except AudioArchiveError as exc:
        raise _audio_archive_error(exc) from exc
    return FileResponse(
        archive["path"],
        media_type="application/zip",
        filename=archive["archive_name"],
        background=BackgroundTask(_remove_temporary_archive, archive["path"]),
    )


@app.get("/api/production/range-readiness")
def production_range_readiness(
    book_id: int = Query(..., gt=0),
    from_chapter: int = Query(..., ge=0),
    to_chapter: int = Query(..., ge=0),
) -> dict[str, Any]:
    try:
        voice_catalog = _load_voice_catalog()
        return get_range_readiness(
            db,
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            voice_catalog=voice_catalog,
            store=store,
        )
    except VoiceCatalogUnavailable as exc:
        raise _job_http_error(exc) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/production/task-projection")
def production_task_projection(
    book_id: int = Query(..., gt=0),
    from_chapter: int = Query(..., ge=0),
    to_chapter: int = Query(..., ge=0),
    inspected_chapter_id: int | None = Query(None, gt=0),
) -> dict[str, Any]:
    """Return the canonical read-only task projection for the workbench."""

    try:
        voice_catalog = _load_voice_catalog()
        return get_production_task_projection(
            db,
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            inspected_chapter_id=inspected_chapter_id,
            voice_catalog=voice_catalog,
            store=store,
            config=settings,
            custom_voice_context=_build_custom_voice_context(),
        )
    except VoiceCatalogUnavailable as exc:
        raise _job_http_error(exc) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/production/preflight")
def production_preflight(
    book_id: int = Query(..., gt=0),
    from_chapter: int = Query(..., ge=0),
    to_chapter: int = Query(..., ge=0),
    skip_completed: bool = Query(True),
) -> dict[str, Any]:
    """Return one read-only review of production data and execution gates."""

    try:
        voice_catalog = _load_voice_catalog()
        runtime_readiness = _production_runtime_readiness()
        return get_production_preflight(
            db,
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            skip_completed=skip_completed,
            voice_catalog=voice_catalog,
            store=store,
            config=settings,
            runtime_readiness=runtime_readiness,
            custom_voice_context=_build_custom_voice_context(),
        )
    except VoiceCatalogUnavailable as exc:
        raise _job_http_error(exc) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/production/book-voice-registry")
def production_book_voice_registry(
    book_id: int = Query(..., gt=0),
    from_chapter: int = Query(..., ge=0),
    to_chapter: int = Query(..., ge=0),
    skip_completed: bool = Query(False),
) -> dict[str, Any]:
    """Return the book-scoped voice assignment read model for a selected range."""

    try:
        return get_book_voice_registry(
            db,
            store,
            settings,
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            skip_completed=skip_completed,
            voice_catalog=_load_voice_catalog(),
            custom_voice_context=_build_custom_voice_context(),
        )
    except VoiceCatalogUnavailable as exc:
        raise _job_http_error(exc) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (BookVoiceRegistryError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/production/speaker-review-suggestions")
def production_speaker_review_suggestions(
    book_id: int = Query(..., gt=0),
    from_chapter: int = Query(..., ge=0),
    to_chapter: int = Query(..., ge=0),
    skip_completed: bool = Query(True),
) -> Response:
    """Return the AI speaker-suggestion queue for the selected range."""

    try:
        timings: dict[str, float] = {}
        total_started = time.perf_counter()
        with collect_query_metrics() as query_metrics:
            started = time.perf_counter()
            voice_catalog = _load_voice_catalog()
            timings["voice_catalog"] = time.perf_counter() - started
            started = time.perf_counter()
            custom_voice_context = _build_custom_voice_context()
            timings["custom_voice_context"] = time.perf_counter() - started
            started = time.perf_counter()
            registry = get_book_voice_registry(
                db,
                store,
                settings,
                book_id=book_id,
                from_chapter=from_chapter,
                to_chapter=to_chapter,
                skip_completed=skip_completed,
                voice_catalog=voice_catalog,
                custom_voice_context=custom_voice_context,
            )
            timings["registry"] = time.perf_counter() - started
            result = get_speaker_review_queue(
                db,
                store,
                settings,
                book_id=book_id,
                from_chapter=from_chapter,
                to_chapter=to_chapter,
                skip_completed=skip_completed,
                registry=registry,
                voice_catalog=voice_catalog,
                custom_voice_context=custom_voice_context,
                timings=timings,
            )
            started = time.perf_counter()
            response = JSONResponse(content=result)
            timings["json_serialization"] = time.perf_counter() - started
        timings["total"] = time.perf_counter() - total_started
        response.headers["Server-Timing"] = ", ".join(
            f"{name};dur={duration * 1000:.1f}"
            for name, duration in (
                *timings.items(),
                ("sqlite", query_metrics.sqlite_seconds),
                ("db_connect", query_metrics.connection_seconds),
            )
        )
        response.headers["X-Speaker-Review-Query-Count"] = str(
            query_metrics.query_count
        )
        return response
    except VoiceCatalogUnavailable as exc:
        raise _job_http_error(exc) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (BookVoiceRegistryError, SpeakerReviewSuggestionError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


def _production_command_range(scope: dict[str, Any]) -> dict[str, Any]:
    range_scope = scope.get("range")
    if isinstance(range_scope, dict):
        return {
            "book_id": int(range_scope["book_id"]),
            "from_chapter": int(range_scope["from_chapter"]),
            "to_chapter": int(range_scope["to_chapter"]),
            "skip_completed": bool(range_scope.get("skip_completed", True)),
        }
    chapter_scope = scope.get("chapter")
    chapter_id = (
        int(chapter_scope["id"])
        if isinstance(chapter_scope, dict)
        else int(chapter_scope)
        if chapter_scope is not None
        else None
    )
    job_scope = scope.get("job")
    job_id = (
        int(job_scope["id"])
        if isinstance(job_scope, dict)
        else int(job_scope)
        if job_scope is not None
        else None
    )
    artifact_scope = scope.get("artifact")
    artifact_id = (
        int(artifact_scope["id"])
        if isinstance(artifact_scope, dict)
        else int(artifact_scope)
        if artifact_scope is not None
        else None
    )
    if artifact_id is not None:
        row = db.fetch_one(
            """SELECT c.id AS chapter_id,c.book_id,c.chapter_number
               FROM artifacts a
               JOIN chapters c ON c.id=a.chapter_id
               WHERE a.id=?""",
            (artifact_id,),
        )
    elif job_id is not None:
        row = db.fetch_one(
            """SELECT NULL AS chapter_id,book_id,from_chapter AS chapter_number,
                      to_chapter
               FROM jobs WHERE id=?""",
            (job_id,),
        )
        if row:
            return {
                "book_id": int(row["book_id"]),
                "from_chapter": int(row["chapter_number"]),
                "to_chapter": int(row["to_chapter"]),
                "skip_completed": False,
            }
    elif chapter_id is not None:
        row = db.fetch_one(
            "SELECT id AS chapter_id,book_id,chapter_number FROM chapters WHERE id=?",
            (chapter_id,),
        )
    else:
        row = None
    if not row:
        raise LookupError("Production command scope was not found")
    return {
        "book_id": int(row["book_id"]),
        "from_chapter": int(row["chapter_number"]),
        "to_chapter": int(row["chapter_number"]),
        "skip_completed": False,
    }


def _speaker_review_unresolved_keys(
    payload: dict[str, Any],
    *,
    required: bool = False,
    single: bool = False,
) -> list[str]:
    raw = payload.get("unresolved_keys")
    if single:
        key = str(payload.get("unresolved_key") or "").strip()
        if not key:
            raise ProductionCommandError("unresolved_key is required")
        return [key]
    if not isinstance(raw, list):
        if required:
            raise ProductionCommandError("unresolved_keys is required")
        return []
    keys = [str(item).strip() for item in raw if str(item).strip()]
    if required and not keys:
        raise ProductionCommandError("unresolved_keys is required")
    if len(keys) != len(set(keys)):
        raise ProductionCommandError("unresolved_keys contains duplicates")
    return keys


def _speaker_review_command_context(
    payload: dict[str, Any],
    scope: dict[str, Any],
) -> tuple[dict[str, Any], Any, Any, dict[str, Any]]:
    command_range = _production_command_range(scope)
    expected = {
        "book_id": int(command_range["book_id"]),
        "from_chapter": int(command_range["from_chapter"]),
        "to_chapter": int(command_range["to_chapter"]),
        "skip_completed": bool(command_range.get("skip_completed", True)),
    }
    for field in ("book_id", "from_chapter", "to_chapter"):
        if field in payload and int(payload[field]) != expected[field]:
            raise ProductionCommandError("Speaker review payload does not match command scope")
    if "skip_completed" in payload and bool(payload["skip_completed"]) != expected["skip_completed"]:
        raise ProductionCommandError("Speaker review skip_completed does not match command scope")
    voice_catalog = _load_voice_catalog()
    custom_voice_context = _build_custom_voice_context()
    registry = get_book_voice_registry(
        db,
        store,
        settings,
        book_id=expected["book_id"],
        from_chapter=expected["from_chapter"],
        to_chapter=expected["to_chapter"],
        skip_completed=expected["skip_completed"],
        voice_catalog=voice_catalog,
        custom_voice_context=custom_voice_context,
    )
    return expected, voice_catalog, custom_voice_context, registry


def _speaker_review_mutation_range(command_range: dict[str, Any]) -> dict[str, int]:
    return {
        "book_id": int(command_range["book_id"]),
        "from_chapter": int(command_range["from_chapter"]),
        "to_chapter": int(command_range["to_chapter"]),
    }


def _project_production_command(
    scope: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    command_range = _production_command_range(scope)
    voice_catalog = _load_voice_catalog()
    custom_context = _build_custom_voice_context()
    task = get_production_task_projection(
        db,
        book_id=command_range["book_id"],
        from_chapter=command_range["from_chapter"],
        to_chapter=command_range["to_chapter"],
        voice_catalog=voice_catalog,
        store=store,
        config=settings,
        custom_voice_context=custom_context,
    )
    runtime_readiness = _production_runtime_readiness()
    try:
        preflight = get_production_preflight(
            db,
            **command_range,
            voice_catalog=voice_catalog,
            store=store,
            config=settings,
            runtime_readiness=runtime_readiness,
            custom_voice_context=custom_context,
        )
    except (LookupError, ValueError, VoiceCatalogUnavailable):
        preflight = None
    return task, preflight


def _range_command_mutation(
    result: dict[str, Any],
    *,
    submitted_count: int,
    complete_message: str,
) -> ProductionCommandMutation:
    applied = tuple(dict(item) for item in result.get("results") or [])
    failed = tuple(
        {
            **dict(item),
            "reason": str(item.get("error") or item.get("reason") or "Cần kiểm tra lại."),
        }
        for item in result.get("failures") or []
    )
    if applied and failed:
        outcome = "PARTIAL"
        message = f"{complete_message} {len(applied)}/{submitted_count}; {len(failed)} mục cần kiểm tra."
    elif failed:
        outcome = "REJECTED"
        message = f"Không thể hoàn tất thao tác; {len(failed)} mục cần kiểm tra."
    else:
        outcome = "APPLIED"
        message = complete_message
    return ProductionCommandMutation(
        outcome=outcome,
        submitted_count=submitted_count,
        applied_items=applied,
        failed_items=failed,
        operator_message=message,
    )


def _confirm_repair_plan(
    request: RepairPlanConfirmationRequest,
    *,
    scope: dict[str, Any],
) -> dict[str, Any]:
    """Persist one editable, artifact-scoped repair decision as audit evidence."""

    command_range = _production_command_range(scope)
    if command_range["from_chapter"] != command_range["to_chapter"]:
        raise ProductionCommandError("Kế hoạch sửa chỉ áp dụng cho đúng một chương.")
    chapter = db.fetch_one(
        """
        SELECT id,book_id,chapter_number,active_audio_artifact_id,human_approval_json
        FROM chapters WHERE id=?
        """,
        (request.chapter_id,),
    )
    if not chapter:
        raise LookupError("Không tìm thấy chương cần lập kế hoạch sửa.")
    if (
        int(chapter["book_id"]) != int(command_range["book_id"])
        or int(chapter["chapter_number"]) != int(command_range["from_chapter"])
    ):
        raise ProductionCommandError("Phạm vi xác nhận không khớp với Chương cần sửa.")
    if int(chapter["active_audio_artifact_id"] or 0) != int(request.artifact_id):
        raise ProductionCommandError("Artifact cần sửa không còn là audio hiện tại của chương.")

    approval = resolve_authoritative_human_approval(
        db,
        int(request.chapter_id),
        active_artifact_id=int(request.artifact_id),
    )
    if (
        not approval
        or str(approval.get("status") or "").lower() != "needs_fixes"
        or int(approval.get("artifact_id") or 0) != int(request.artifact_id)
    ):
        raise ProductionCommandError("Cần một kết quả Human QA 'Cần sửa' cho Artifact hiện tại.")

    qa_event = db.fetch_one(
        """
        SELECT id,details_json FROM audit_events
        WHERE id=? AND chapter_id=? AND event_code='human_qa_recorded'
        """,
        (int(request.qa_evidence_id), int(request.chapter_id)),
    )
    if not qa_event:
        raise ProductionCommandError("Không tìm thấy bằng chứng Human QA nguồn.")
    try:
        qa_details = json.loads(qa_event["details_json"] or "{}")
    except (TypeError, ValueError) as exc:
        raise ProductionCommandError("Bằng chứng Human QA nguồn không hợp lệ.") from exc
    if (
        not isinstance(qa_details, dict)
        or str(qa_details.get("status") or "").lower() != "needs_fixes"
        or int(qa_details.get("artifact_id") or 0) != int(request.artifact_id)
    ):
        raise ProductionCommandError("Bằng chứng Human QA không khớp Artifact cần sửa.")

    selection = {
        "repeated_words": bool(request.repeated_words),
        "global_speed_target": request.global_speed_target,
        "local_pacing_adjustment_required": bool(
            request.local_pacing_adjustment_required
        ),
        "operator_note": (request.operator_note or "").strip() or None,
    }
    if not (
        selection["repeated_words"]
        or selection["global_speed_target"] is not None
        or selection["local_pacing_adjustment_required"]
        or selection["operator_note"]
    ):
        raise ProductionCommandError("Chọn ít nhất một nội dung sửa trước khi xác nhận.")

    existing = resolve_repair_plan_evidence(
        db,
        int(request.chapter_id),
        active_artifact_id=int(request.artifact_id),
    )
    if existing and {
        key: existing.get(key) for key in selection
    } == selection and int(existing.get("qa_evidence_id") or 0) == int(request.qa_evidence_id):
        return {"repair_plan": existing, "idempotent_reused": True}

    details = {
        "artifact_id": int(request.artifact_id),
        "qa_evidence_id": int(request.qa_evidence_id),
        **selection,
    }
    if existing:
        details["supersedes_evidence_id"] = int(existing["evidence_id"])
    recorded_at = utcnow()
    with db.transaction() as connection:
        cursor = connection.execute(
            """
            INSERT INTO audit_events(event_code,job_id,chapter_id,details_json,created_at)
            VALUES(?,?,?,?,?)
            """,
            (
                "repair_plan_confirmed",
                approval.get("job_id"),
                int(request.chapter_id),
                json.dumps(details, ensure_ascii=False),
                recorded_at,
            ),
        )
    return {
        "repair_plan": {
            "evidence_id": int(cursor.lastrowid),
            "recorded_at": recorded_at,
            **details,
        },
        "idempotent_reused": False,
    }


def _apply_repair_plan(
    request: ApplyRepairPlanRequest,
    *,
    scope: dict[str, Any],
) -> dict[str, Any]:
    """Create one reviewable, immutable repair draft from confirmed QA evidence."""

    command_range = _production_command_range(scope)
    if command_range["from_chapter"] != command_range["to_chapter"]:
        raise ProductionCommandError("Bản sửa chỉ áp dụng cho đúng một chương.")
    chapter = db.fetch_one(
        """
        SELECT id,book_id,chapter_number,active_text_revision_id,active_audio_artifact_id
        FROM chapters WHERE id=?
        """,
        (int(request.chapter_id),),
    )
    if not chapter:
        raise LookupError("Không tìm thấy chương cần áp dụng bản sửa.")
    if (
        int(chapter["book_id"]) != int(command_range["book_id"])
        or int(chapter["chapter_number"]) != int(command_range["from_chapter"])
        or int(chapter["active_audio_artifact_id"] or 0) != int(request.artifact_id)
    ):
        raise ProductionCommandError("Phạm vi hoặc Artifact không còn khớp bản sửa đã xác nhận.")

    plan = resolve_repair_plan_evidence(
        db,
        int(request.chapter_id),
        active_artifact_id=int(request.artifact_id),
    )
    if (
        not plan
        or int(plan.get("evidence_id") or 0) != int(request.repair_plan_evidence_id)
        or int(plan.get("qa_evidence_id") or 0) != int(request.qa_evidence_id)
    ):
        raise ProductionCommandError("Kế hoạch sửa đã xác nhận không còn khớp bằng chứng QA.")
    approval = resolve_authoritative_human_approval(
        db, int(request.chapter_id), active_artifact_id=int(request.artifact_id)
    )
    if (
        not approval
        or str(approval.get("status") or "").lower() != "needs_fixes"
        or int(approval.get("artifact_id") or 0) != int(request.artifact_id)
    ):
        raise ProductionCommandError("Artifact hiện tại không còn ở trạng thái Human QA cần sửa.")
    casting_plan = db.fetch_one(
        """
        SELECT id,plan_revision,status,text_revision_id FROM casting_plans
        WHERE chapter_id=? AND status='approved' AND archived_at IS NULL
        ORDER BY plan_revision DESC,id DESC LIMIT 1
        """,
        (int(request.chapter_id),),
    )
    if not casting_plan or int(casting_plan["text_revision_id"] or 0) != int(chapter["active_text_revision_id"]):
        raise ProductionCommandError("Cần Final Voice Map đã duyệt khớp văn bản hiện tại trước khi tạo bản sửa.")

    from .human_approval import resolve_repair_draft_evidence

    existing = resolve_repair_draft_evidence(
        db,
        int(request.chapter_id),
        active_artifact_id=int(request.artifact_id),
    )
    if existing:
        if int(existing.get("repair_plan_evidence_id") or 0) != int(request.repair_plan_evidence_id):
            raise ProductionCommandError("Đã có một bản sửa khác cho Artifact hiện tại.")
        return {"repair_draft": existing, "idempotent_reused": True}

    details = {
        "artifact_id": int(request.artifact_id),
        "qa_evidence_id": int(request.qa_evidence_id),
        "repair_plan_evidence_id": int(request.repair_plan_evidence_id),
        "text_revision_id": int(chapter["active_text_revision_id"]),
        "casting_plan_id": int(casting_plan["id"]),
        "casting_plan_revision": int(casting_plan["plan_revision"]),
        "repeated_words": bool(plan.get("repeated_words")),
        "global_speed_target": plan.get("global_speed_target"),
        "local_pacing_adjustment_required": bool(plan.get("local_pacing_adjustment_required")),
        "review_items": [
            "repeated_words_locations" if plan.get("repeated_words") else None,
            "local_pacing" if plan.get("local_pacing_adjustment_required") else None,
        ],
    }
    details["review_items"] = [item for item in details["review_items"] if item]
    recorded_at = utcnow()
    with db.transaction() as connection:
        cursor = connection.execute(
            """
            INSERT INTO audit_events(event_code,job_id,chapter_id,details_json,created_at)
            VALUES(?,?,?,?,?)
            """,
            ("repair_draft_created", approval.get("job_id"), int(request.chapter_id), json.dumps(details, ensure_ascii=False), recorded_at),
        )
    return {
        "repair_draft": {"evidence_id": int(cursor.lastrowid), "recorded_at": recorded_at, **details},
        "idempotent_reused": False,
    }


def _confirm_repair_draft(
    request: RepairDraftReviewConfirmationRequest,
    *,
    scope: dict[str, Any],
) -> dict[str, Any]:
    """Record one final human review of an immutable repair draft without rendering."""

    command_range = _production_command_range(scope)
    if command_range["from_chapter"] != command_range["to_chapter"]:
        raise ProductionCommandError("Chỉ có thể kiểm tra bản sửa của đúng một chương.")
    chapter = db.fetch_one(
        """
        SELECT id,book_id,chapter_number,active_text_revision_id,active_audio_artifact_id
        FROM chapters WHERE id=?
        """,
        (int(request.chapter_id),),
    )
    if not chapter:
        raise LookupError("Không tìm thấy chương cần kiểm tra bản sửa.")
    if (
        int(chapter["book_id"]) != int(command_range["book_id"])
        or int(chapter["chapter_number"]) != int(command_range["from_chapter"])
        or int(chapter["active_audio_artifact_id"] or 0) != int(request.artifact_id)
    ):
        raise ProductionCommandError("Phạm vi hoặc Artifact không còn khớp bản sửa cần kiểm tra.")

    approval = resolve_authoritative_human_approval(
        db, int(request.chapter_id), active_artifact_id=int(request.artifact_id)
    )
    if (
        not approval
        or str(approval.get("status") or "").lower() != "needs_fixes"
        or int(approval.get("artifact_id") or 0) != int(request.artifact_id)
    ):
        raise ProductionCommandError("Artifact hiện tại không còn ở trạng thái Human QA cần sửa.")

    from .human_approval import (
        resolve_repair_draft_evidence,
        resolve_repair_draft_review_evidence,
        resolve_repair_plan_evidence,
    )

    plan = resolve_repair_plan_evidence(
        db, int(request.chapter_id), active_artifact_id=int(request.artifact_id)
    )
    if (
        not plan
        or int(plan.get("evidence_id") or 0) != int(request.repair_plan_evidence_id)
        or int(plan.get("qa_evidence_id") or 0) != int(request.qa_evidence_id)
    ):
        raise ProductionCommandError("Kế hoạch sửa đã xác nhận không còn khớp bằng chứng QA.")
    draft = resolve_repair_draft_evidence(
        db, int(request.chapter_id), active_artifact_id=int(request.artifact_id)
    )
    if (
        not draft
        or int(draft.get("evidence_id") or 0) != int(request.repair_draft_evidence_id)
        or int(draft.get("repair_plan_evidence_id") or 0)
        != int(request.repair_plan_evidence_id)
        or int(draft.get("qa_evidence_id") or 0) != int(request.qa_evidence_id)
        or int(draft.get("text_revision_id") or 0)
        != int(chapter["active_text_revision_id"] or 0)
    ):
        raise ProductionCommandError("Bản sửa không còn khớp nội dung hoặc bằng chứng hiện tại.")
    current_casting_plan = db.fetch_one(
        """
        SELECT id,plan_revision FROM casting_plans
        WHERE chapter_id=? AND status='approved' AND archived_at IS NULL
        ORDER BY plan_revision DESC,id DESC LIMIT 1
        """,
        (int(request.chapter_id),),
    )
    if (
        not current_casting_plan
        or int(current_casting_plan["id"]) != int(draft.get("casting_plan_id") or 0)
        or int(current_casting_plan["plan_revision"])
        != int(draft.get("casting_plan_revision") or 0)
    ):
        raise ProductionCommandError("Bản đồ giọng đã duyệt không còn khớp bản sửa.")

    existing = resolve_repair_draft_review_evidence(
        db,
        int(request.chapter_id),
        repair_draft_evidence_id=int(request.repair_draft_evidence_id),
        active_artifact_id=int(request.artifact_id),
    )
    if existing:
        return {"repair_draft_review": existing, "idempotent_reused": True}

    markers = [
        {
            "timestamp_seconds": marker.timestamp_seconds,
            "nearest_utterance": (marker.nearest_utterance or "").strip() or None,
            "issue": marker.issue,
            "note": (marker.note or "").strip() or None,
            "local_pace": marker.local_pace,
        }
        for marker in request.markers
    ]
    details = {
        "artifact_id": int(request.artifact_id),
        "qa_evidence_id": int(request.qa_evidence_id),
        "repair_plan_evidence_id": int(request.repair_plan_evidence_id),
        "repair_draft_evidence_id": int(request.repair_draft_evidence_id),
        "text_revision_id": int(draft["text_revision_id"]),
        "casting_plan_id": int(draft["casting_plan_id"]),
        "casting_plan_revision": int(draft["casting_plan_revision"]),
        "repeated_words": bool(draft.get("repeated_words")),
        "global_speed_target": draft.get("global_speed_target"),
        "local_pacing_adjustment_required": bool(
            draft.get("local_pacing_adjustment_required")
        ),
        "markers": markers,
        "marker_count": len(markers),
        "status": "reviewed_confirmed",
    }
    recorded_at = utcnow()
    with db.transaction() as connection:
        cursor = connection.execute(
            """
            INSERT INTO audit_events(event_code,job_id,chapter_id,details_json,created_at)
            VALUES(?,?,?,?,?)
            """,
            (
                "repair_draft_reviewed",
                approval.get("job_id"),
                int(request.chapter_id),
                json.dumps(details, ensure_ascii=False),
                recorded_at,
            ),
        )
    return {
        "repair_draft_review": {
            "evidence_id": int(cursor.lastrowid),
            "recorded_at": recorded_at,
            **details,
        },
        "idempotent_reused": False,
    }


def _production_command_executor(
    request: ProductionCommandRequest,
    *,
    authorization_header: str | None,
):
    command_type = request.command_type.strip().upper()
    payload = dict(request.payload)
    scope = dict(request.scope)

    def execute() -> ProductionCommandMutation:
        if command_type == "CONFIRM_REPAIR_DRAFT":
            result = _confirm_repair_draft(
                RepairDraftReviewConfirmationRequest.model_validate(payload),
                scope=scope,
            )
            review = result["repair_draft_review"]
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=(
                    {
                        "chapter_id": int(payload["chapter_id"]),
                        "artifact_id": int(review["artifact_id"]),
                        "repair_draft_evidence_id": int(
                            review["repair_draft_evidence_id"]
                        ),
                        "repair_draft_review_evidence_id": int(review["evidence_id"]),
                        "reused": bool(result["idempotent_reused"]),
                    },
                ),
                operator_message="Bản sửa đã được kiểm tra và xác nhận.",
            )
        if command_type == "APPLY_REPAIR_PLAN":
            result = _apply_repair_plan(ApplyRepairPlanRequest.model_validate(payload), scope=scope)
            draft = result["repair_draft"]
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({"chapter_id": int(payload["chapter_id"]), "repair_draft_evidence_id": int(draft["evidence_id"]), "reused": bool(result["idempotent_reused"])} ,),
                operator_message="Đã tạo bản sửa để kiểm tra.",
            )
        if command_type == "CONFIRM_REPAIR_PLAN":
            result = _confirm_repair_plan(
                RepairPlanConfirmationRequest.model_validate(payload),
                scope=scope,
            )
            plan = result["repair_plan"]
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=(
                    {
                        "chapter_id": int(payload["chapter_id"]),
                        "artifact_id": int(plan["artifact_id"]),
                        "repair_plan_evidence_id": int(plan["evidence_id"]),
                        "reused": bool(result["idempotent_reused"]),
                    },
                ),
                operator_message="Kế hoạch sửa đã được xác nhận.",
            )
        if command_type == "PREPARE_RANGE_INPUTS":
            result = production_prepare_range_inputs(
                RangeInputScopeRequest.model_validate(payload)
            )
            submitted = len(result.get("results") or []) + len(result.get("failures") or [])
            return _range_command_mutation(
                result,
                submitted_count=max(1, submitted),
                complete_message="Đã chuẩn bị dữ liệu phạm vi.",
            )
        if command_type == "APPROVE_SPEAKER_DRAFTS":
            parsed = RangeSpeakerApprovalRequest.model_validate(payload)
            result = production_approve_range_speaker_drafts(parsed)
            return _range_command_mutation(
                result,
                submitted_count=len(parsed.chapters),
                complete_message=f"Đã duyệt {len(result.get('results') or [])}/{len(parsed.chapters)} chương.",
            )
        if command_type == "APPROVE_CASTING_PLANS":
            parsed = RangeCastingApprovalRequest.model_validate(payload)
            result = production_approve_range_casting_plans(parsed)
            return _range_command_mutation(
                result,
                submitted_count=len(parsed.chapters),
                complete_message=f"Đã duyệt {len(result.get('results') or [])}/{len(parsed.chapters)} bản đồ giọng.",
            )
        if command_type in {"GENERATE_SPEAKER_SUGGESTIONS", "REGENERATE_SPEAKER_SUGGESTION"}:
            command_range, voice_catalog, custom_context, registry = _speaker_review_command_context(
                payload,
                scope,
            )
            unresolved_keys = _speaker_review_unresolved_keys(
                payload,
                required=True,
                single=command_type == "REGENERATE_SPEAKER_SUGGESTION",
            )
            result = generate_speaker_review_suggestions(
                db,
                store,
                settings,
                **command_range,
                registry=registry,
                voice_catalog=voice_catalog,
                custom_voice_context=custom_context,
                unresolved_keys=unresolved_keys,
                force_refresh=(
                    command_type == "REGENERATE_SPEAKER_SUGGESTION"
                    or bool(payload.get("force_refresh", False))
                ),
                expected_input_fingerprint=payload.get("expected_input_fingerprint"),
                idempotency_key=request.idempotency_key,
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=max(1, int(result.get("target_count") or 0)),
                applied_items=(
                    {
                        "type": "speaker_review_analysis",
                        "analysis_run_id": result.get("analysis_run_id"),
                        "input_fingerprint": result.get("input_fingerprint"),
                        "target_count": int(result.get("target_count") or 0),
                        "chunk_count": int(result.get("chunk_count") or 0),
                        "request_count": int(result.get("request_count") or 0),
                        "cache_hit_count": int(result.get("cache_hit_count") or 0),
                        "cache_miss_count": int(result.get("cache_miss_count") or 0),
                        "reused": bool(result.get("reused")),
                        "summary": dict(result.get("summary") or {}),
                    },
                ),
                operator_message=(
                    "Đã tạo đề xuất Gemini để con người duyệt; chưa áp dụng mapping, "
                    "chưa tạo job và chưa render."
                ),
            )
        if command_type == "DEFER_SPEAKER_SUGGESTION":
            command_range, _voice_catalog, _custom_context, _registry = _speaker_review_command_context(
                payload,
                scope,
            )
            del command_range
            analysis_run_id = str(payload.get("analysis_run_id") or "").strip()
            unresolved_key = _speaker_review_unresolved_keys(payload, single=True)[0]
            if not analysis_run_id:
                raise ProductionCommandError("analysis_run_id is required")
            result = record_speaker_suggestion_decision(
                db,
                store,
                analysis_run_id=analysis_run_id,
                unresolved_key=unresolved_key,
                decision="DEFERRED",
                reviewer_payload=dict(payload.get("reviewer_payload") or {}),
                idempotency_key=request.idempotency_key,
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=(
                    {
                        "type": "speaker_review_decision",
                        "analysis_run_id": analysis_run_id,
                        "unresolved_key": unresolved_key,
                        "decision": result.get("decision", {}).get("decision", "DEFERRED"),
                        "reused": bool(result.get("reused")),
                    },
                ),
                operator_message="Đã đánh dấu đề xuất này để xử lý sau.",
            )
        if command_type == "ADD_SPEAKER_REVIEW_NOTE":
            command_range, _voice_catalog, _custom_context, _registry = _speaker_review_command_context(
                payload,
                scope,
            )
            del command_range
            analysis_run_id = str(payload.get("analysis_run_id") or "").strip()
            unresolved_key = _speaker_review_unresolved_keys(payload, single=True)[0]
            if not analysis_run_id:
                raise ProductionCommandError("analysis_run_id is required")
            result = record_speaker_suggestion_note(
                db,
                store,
                analysis_run_id=analysis_run_id,
                unresolved_key=unresolved_key,
                note=str((payload.get("reviewer_payload") or {}).get("note") or ""),
                idempotency_key=request.idempotency_key,
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=(
                    {
                        "type": "speaker_review_note",
                        "analysis_run_id": analysis_run_id,
                        "unresolved_key": unresolved_key,
                        "reused": bool(result.get("reused")),
                    },
                ),
                operator_message="Đã lưu ghi chú; quyết định hiệu lực không thay đổi.",
            )
        if command_type == "RESTORE_SPEAKER_SUGGESTION_PENDING":
            command_range, _voice_catalog, _custom_context, _registry = _speaker_review_command_context(
                payload,
                scope,
            )
            del command_range
            analysis_run_id = str(payload.get("analysis_run_id") or "").strip()
            unresolved_key = _speaker_review_unresolved_keys(payload, single=True)[0]
            if not analysis_run_id:
                raise ProductionCommandError("analysis_run_id is required")
            result = restore_speaker_suggestion_pending(
                db,
                store,
                analysis_run_id=analysis_run_id,
                unresolved_key=unresolved_key,
                reviewer_payload=dict(payload.get("reviewer_payload") or {}),
                idempotency_key=request.idempotency_key,
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=(
                    {
                        "type": "speaker_review_restored_pending",
                        "analysis_run_id": analysis_run_id,
                        "unresolved_key": unresolved_key,
                        "reused": bool(result.get("reused")),
                    },
                ),
                operator_message="Đã khôi phục mục về hàng Cần duyệt và giữ nguyên lịch sử.",
            )
        if command_type == "CREATE_SPEAKER_REPLACEMENT_DECISION":
            command_range, _voice_catalog, _custom_context, _registry = _speaker_review_command_context(
                payload,
                scope,
            )
            del command_range
            analysis_run_id = str(payload.get("analysis_run_id") or "").strip()
            unresolved_key = _speaker_review_unresolved_keys(payload, single=True)[0]
            if not analysis_run_id:
                raise ProductionCommandError("analysis_run_id is required")
            result = record_speaker_suggestion_decision(
                db,
                store,
                analysis_run_id=analysis_run_id,
                unresolved_key=unresolved_key,
                decision="REPLACEMENT_DRAFT",
                reviewer_payload=dict(payload.get("reviewer_payload") or {}),
                idempotency_key=request.idempotency_key,
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=(
                    {
                        "type": "speaker_review_replacement_draft",
                        "analysis_run_id": analysis_run_id,
                        "unresolved_key": unresolved_key,
                        "reused": bool(result.get("reused")),
                    },
                ),
                operator_message="Đã tạo quyết định thay thế; bản cũ vẫn được giữ trong lịch sử.",
            )
        if command_type == "MARK_SPEAKER_SUGGESTION_UNCERTAIN":
            command_range, _voice_catalog, _custom_context, _registry = _speaker_review_command_context(
                payload,
                scope,
            )
            del command_range
            analysis_run_id = str(payload.get("analysis_run_id") or "").strip()
            unresolved_key = _speaker_review_unresolved_keys(payload, single=True)[0]
            if not analysis_run_id:
                raise ProductionCommandError("analysis_run_id is required")
            result = record_speaker_suggestion_decision(
                db,
                store,
                analysis_run_id=analysis_run_id,
                unresolved_key=unresolved_key,
                decision="MARKED_UNCERTAIN",
                reviewer_payload=dict(payload.get("reviewer_payload") or {}),
                idempotency_key=request.idempotency_key,
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=(
                    {
                        "type": "speaker_review_uncertain",
                        "analysis_run_id": analysis_run_id,
                        "unresolved_key": unresolved_key,
                        "reused": bool(result.get("reused")),
                    },
                ),
                operator_message="Đã chuyển đề xuất sang hàng Cần quyết định.",
            )
        if command_type in {"ACCEPT_SPEAKER_SUGGESTION", "EDIT_AND_ACCEPT_SPEAKER_SUGGESTION"}:
            command_range, voice_catalog, custom_context, _registry = _speaker_review_command_context(
                payload,
                scope,
            )
            analysis_run_id = str(payload.get("analysis_run_id") or "").strip()
            unresolved_key = _speaker_review_unresolved_keys(payload, single=True)[0]
            if not analysis_run_id:
                raise ProductionCommandError("analysis_run_id is required")
            result = accept_speaker_review_suggestion(
                db,
                store,
                settings,
                **_speaker_review_mutation_range(command_range),
                analysis_run_id=analysis_run_id,
                unresolved_key=unresolved_key,
                reviewer_payload=dict(payload.get("reviewer_payload") or {}),
                voice_catalog=voice_catalog,
                custom_voice_context=custom_context,
                idempotency_key=request.idempotency_key,
                decision_override=(
                    "ACCEPTED"
                    if command_type == "ACCEPT_SPEAKER_SUGGESTION"
                    else "EDITED_AND_ACCEPTED"
                ),
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=(
                    {
                        "type": "speaker_review_acceptance",
                        "analysis_run_id": analysis_run_id,
                        "unresolved_key": unresolved_key,
                        "applied": result.get("applied"),
                        "review": result.get("review"),
                    },
                ),
                operator_message=(
                    "Đã áp dụng quyết định người nói cho lần PREPARE/render tiếp theo. "
                    "Audio hiện tại không bị thay đổi."
                ),
            )
        if command_type == "CORRECT_APPROVED_SPEAKER_SUGGESTION":
            command_range, voice_catalog, custom_context, _registry = _speaker_review_command_context(
                payload,
                scope,
            )
            analysis_run_id = str(payload.get("analysis_run_id") or "").strip()
            unresolved_key = _speaker_review_unresolved_keys(payload, single=True)[0]
            if not analysis_run_id:
                raise ProductionCommandError("analysis_run_id is required")
            result = accept_speaker_review_suggestion(
                db,
                store,
                settings,
                **_speaker_review_mutation_range(command_range),
                analysis_run_id=analysis_run_id,
                unresolved_key=unresolved_key,
                reviewer_payload=dict(payload.get("reviewer_payload") or {}),
                voice_catalog=voice_catalog,
                custom_voice_context=custom_context,
                idempotency_key=request.idempotency_key,
                decision_override="CORRECTED",
                require_approved=True,
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=(
                    {
                        "type": "speaker_review_correction",
                        "analysis_run_id": analysis_run_id,
                        "unresolved_key": unresolved_key,
                        "applied": result.get("applied"),
                        "review": result.get("review"),
                    },
                ),
                operator_message=(
                    "Đã lưu quyết định thay thế cho lần PREPARE/render tiếp theo. "
                    "Audio đã chấp nhận hiện tại không bị thay đổi."
                ),
            )
        if command_type == "APPROVE_SPEAKER_REVIEW_BATCH":
            command_range, voice_catalog, custom_context, _registry = _speaker_review_command_context(
                payload,
                scope,
            )
            submitted_items = payload.get("items")
            if isinstance(submitted_items, list) and submitted_items:
                result = approve_speaker_review_batch_items(
                    db,
                    store,
                    settings,
                    **_speaker_review_mutation_range(command_range),
                    items=[
                        dict(item)
                        for item in submitted_items
                        if isinstance(item, dict)
                    ],
                    voice_catalog=voice_catalog,
                    custom_voice_context=custom_context,
                    idempotency_key=request.idempotency_key,
                )
                applied_items = tuple(
                    {
                        "type": "speaker_review_batch_acceptance",
                        "analysis_run_id": item["analysis_run_id"],
                        "unresolved_key": item["unresolved_key"],
                    }
                    for item in result.get("items") or []
                )
            else:
                analysis_run_id = str(payload.get("analysis_run_id") or "").strip()
                if not analysis_run_id:
                    raise ProductionCommandError("analysis_run_id is required")
                unresolved_keys = _speaker_review_unresolved_keys(payload, required=True)
                result = approve_high_confidence_suggestions(
                    db,
                    store,
                    settings,
                    **_speaker_review_mutation_range(command_range),
                    analysis_run_id=analysis_run_id,
                    unresolved_keys=unresolved_keys,
                    voice_catalog=voice_catalog,
                    custom_voice_context=custom_context,
                    idempotency_key=request.idempotency_key,
                )
                applied_items = tuple(
                    {
                        "type": "speaker_review_batch_acceptance",
                        "analysis_run_id": analysis_run_id,
                        "unresolved_key": key,
                    }
                    for key in unresolved_keys
                )
            decision_ids = [int(value) for value in result.get("decision_ids") or []]
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=int(result.get("submitted_count") or len(applied_items)),
                applied_items=applied_items,
                result_metadata={
                    "requested_count": int(
                        result.get("submitted_count") or len(applied_items)
                    ),
                    "approved_count": len(applied_items),
                    "excluded_count": int(payload.get("excluded_count") or 0),
                    "decision_ids": decision_ids,
                    "queue_counts": result.get("queue_counts") or {},
                },
                operator_message=(
                    "Đã duyệt các đề xuất tin cậy cao được chọn. "
                    "Không có PREPARE hoặc render tự động."
                ),
            )
        if command_type == "CREATE_SPEAKER_PROPOSAL":
            chapter_id = int(payload.pop("chapter_id"))
            result = create_speaker_assignment_draft(
                chapter_id, SpeakerAssignmentDraftRequest.model_validate(payload)
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({
                    "chapter_id": chapter_id,
                    "draft_id": result.get("id"),
                    "reused": bool(result.get("reused")),
                },),
                operator_message="Đã tạo hoặc tái sử dụng đề xuất người nói.",
            )
        if command_type == "SAVE_SPEAKER_DECISION":
            chapter_id = int(payload.pop("chapter_id"))
            draft_id = int(payload.pop("draft_id"))
            target_id = str(payload.pop("target_id"))
            result = review_speaker_assignment_target(
                chapter_id,
                draft_id,
                target_id,
                SpeakerAssignmentRowReviewRequest.model_validate(payload),
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({
                    "chapter_id": chapter_id,
                    "draft_id": draft_id,
                    "target_id": target_id,
                    "reused": bool(result.get("review", {}).get("idempotent_reused")),
                },),
                operator_message="Đã lưu quyết định người nói.",
            )
        if command_type == "APPROVE_SPEAKER_DRAFT":
            chapter_id = int(payload["chapter_id"])
            draft_id = int(payload["draft_id"])
            result = approve_speaker_assignment_draft_without_casting(
                chapter_id, draft_id
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({
                    "chapter_id": chapter_id,
                    "draft_id": draft_id,
                    "reused": bool(result.get("idempotent_reused")),
                },),
                operator_message="Đã duyệt Speaker Draft.",
            )
        if command_type == "CREATE_CASTING_PLAN_DRAFT":
            chapter_id = int(payload.pop("chapter_id"))
            result = create_speaker_review_casting_plan_draft(
                chapter_id,
                SpeakerReviewCastingPlanDraftRequest.model_validate(payload),
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({
                    "chapter_id": chapter_id,
                    "casting_plan_id": result.get("casting_plan_id") or result.get("id"),
                    "reused": bool(result.get("idempotent_reused")),
                },),
                operator_message="Đã tạo bản nháp bản đồ giọng.",
            )
        if command_type == "SAVE_CASTING_DRAFT":
            chapter_id = int(payload.pop("chapter_id"))
            result = save_casting_draft(
                chapter_id, CastingDraftRequest.model_validate(payload)
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({
                    "chapter_id": chapter_id,
                    "casting_plan_id": result.get("id"),
                    "plan_revision": result.get("plan_revision"),
                    "reused": bool(result.get("idempotent_reused")),
                },),
                operator_message="Đã lưu bản nháp bản đồ giọng.",
            )
        if command_type == "SAVE_VOICE_ASSIGNMENT":
            character_id = int(payload.pop("character_id"))
            result = write_character_voice_override(
                character_id, CharacterOverrideRequest.model_validate(payload)
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({
                    "character_id": character_id,
                    "voice_override_id": result.get("voice_override_id"),
                },),
                operator_message="Đã lưu giọng hiệu lực cho nhân vật.",
            )
        if command_type == "CREATE_CHARACTER":
            parsed = AssignmentCharacterCreatePayload.model_validate(payload)
            result = create_assignment_character(
                db,
                book_id=parsed.book_id,
                display_name=parsed.display_name,
                aliases=parsed.aliases,
                gender=parsed.gender,
                role=parsed.role,
                idempotency_key=request.idempotency_key,
            )
            character = dict(result["character"])
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=(
                    {
                        "type": "character",
                        "book_id": parsed.book_id,
                        "character_id": int(character["id"]),
                        "display_name": character["display_name"],
                        "created": bool(result.get("created")),
                        "reused": bool(result.get("reused")),
                        "aliases": list(result.get("aliases") or []),
                    },
                ),
                operator_message=(
                    "Đã tạo nhân vật mới. Nhân vật chỉ ảnh hưởng audio sau khi được gán với dòng thoại."
                    if result.get("created")
                    else "Đã tái sử dụng nhân vật sẵn có; không tạo bản trùng."
                ),
            )
        if command_type == "ADD_CHARACTER_ALIAS":
            parsed = AssignmentAliasPayload.model_validate(payload)
            result = add_character_aliases(
                db,
                book_id=parsed.book_id,
                character_id=parsed.character_id,
                aliases=parsed.aliases,
                idempotency_key=request.idempotency_key,
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=max(1, len(parsed.aliases)),
                applied_items=(
                    {
                        "type": "character_aliases",
                        "book_id": parsed.book_id,
                        "character_id": parsed.character_id,
                        "aliases": list(result.get("aliases") or []),
                        "added_count": int(result.get("added_count") or 0),
                        "reused_count": int(result.get("reused_count") or 0),
                    },
                ),
                operator_message="Đã lưu tên gọi khác cho nhân vật.",
            )
        if command_type in {"MAP_SPEAKER_TO_CHARACTER", "MAP_RANGE_SPEAKER_TO_CHARACTER"}:
            command_range = _production_command_range(scope)
            parsed = SpeakerCharacterMappingPayload.model_validate(payload)
            result = apply_speaker_character_mapping(
                db,
                store,
                book_id=parsed.book_id,
                from_chapter=int(command_range["from_chapter"]),
                to_chapter=int(command_range["to_chapter"]),
                speaker_key=parsed.speaker_key,
                character_id=parsed.character_id,
                aliases=parsed.aliases,
                voice_catalog=_load_voice_catalog(),
                idempotency_key=request.idempotency_key,
                custom_voice_context=_build_custom_voice_context(),
            )
            applied_items = tuple(
                {
                    **dict(item),
                    "speaker_key": result["speaker_key"],
                    "character_id": result.get("character_id"),
                    "operation": result["operation"],
                }
                for item in result.get("applied") or []
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=max(1, int(result.get("utterance_count") or 0)),
                applied_items=applied_items,
                operator_message=(
                    "Đã gán người nói với nhân vật. Audio đã có không bị thay đổi; "
                    "lần PREPARE/render sau sẽ dùng mapping mới."
                ),
            )
        if command_type == "CLEAR_SPEAKER_CHARACTER_MAPPING":
            command_range = _production_command_range(scope)
            parsed = SpeakerCharacterClearPayload.model_validate(payload)
            result = clear_speaker_character_mapping(
                db,
                store,
                book_id=parsed.book_id,
                from_chapter=int(command_range["from_chapter"]),
                to_chapter=int(command_range["to_chapter"]),
                speaker_key=parsed.speaker_key,
                voice_catalog=_load_voice_catalog(),
                idempotency_key=request.idempotency_key,
                custom_voice_context=_build_custom_voice_context(),
            )
            applied_items = tuple(
                {
                    **dict(item),
                    "speaker_key": result["speaker_key"],
                    "operation": result["operation"],
                }
                for item in result.get("applied") or []
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=max(1, int(result.get("utterance_count") or 0)),
                applied_items=applied_items,
                operator_message=(
                    "Đã bỏ mapping nhân vật cho người nói này. Dòng thoại quay về trạng thái "
                    "chưa xác định cho lần PREPARE/render sau."
                ),
            )
        if command_type == "SET_BOOK_VOICE_DEFAULT":
            command_range = _production_command_range(scope)
            book_id = int(payload.get("book_id") or command_range["book_id"])
            speaker_key = str(payload["speaker_key"]).strip()
            voice_id = str(payload["voice_id"]).strip()
            if not voice_id:
                raise ProductionCommandError("A selectable voice is required")
            if speaker_key in {"narrator", "unknown"}:
                profile = get_book_voice_profile(db, book_id)
                if not profile:
                    raise ProductionCommandError("Book Voice Profile is missing")
                profile_payload = {
                    "narrator_voice_id": (
                        voice_id if speaker_key == "narrator" else profile["narrator_voice_id"]
                    ),
                    "male_dialogue_voice_id": profile["male_dialogue_voice_id"],
                    "female_dialogue_voice_id": profile["female_dialogue_voice_id"],
                    "unknown_fallback": (
                        "explicit_voice" if speaker_key == "unknown" else profile["unknown_fallback"]
                    ),
                    "unknown_voice_id": (
                        voice_id if speaker_key == "unknown" else profile["unknown_voice_id"]
                    ),
                }
                result = write_book_voice_profile(
                    book_id,
                    BookVoiceProfileRequest.model_validate(profile_payload),
                )
                applied = {
                    "type": "book_voice_profile",
                    "book_id": book_id,
                    "speaker_key": speaker_key,
                    "voice_id": voice_id,
                    "config_version": result.get("config_version"),
                }
            elif speaker_key.startswith("character:"):
                character_id = int(payload.get("character_id") or speaker_key.split(":", 1)[1])
                result = write_character_voice_override(
                    character_id,
                    CharacterOverrideRequest.model_validate(
                        {
                            "gender": payload.get("gender"),
                            "voice_override_id": voice_id,
                        }
                    ),
                )
                applied = {
                    "type": "character_voice",
                    "book_id": book_id,
                    "character_id": character_id,
                    "speaker_key": speaker_key,
                    "voice_id": result.get("voice_override_id"),
                }
            else:
                raise ProductionCommandError("Unsupported speaker key")
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=(applied,),
                operator_message=(
                    "Da luu mac dinh giong cho sach. "
                    "Audio va Job da co khong bi thay doi."
                ),
            )
        if command_type in {
            "SET_CHAPTER_VOICE_OVERRIDE",
            "SET_RANGE_VOICE_OVERRIDE",
            "CLEAR_CHAPTER_VOICE_OVERRIDE",
            "CLEAR_RANGE_VOICE_OVERRIDE",
        }:
            command_range = _production_command_range(scope)
            is_clear = command_type.startswith("CLEAR_")
            is_chapter = "_CHAPTER_" in command_type
            if is_chapter and command_range["from_chapter"] != command_range["to_chapter"]:
                raise ProductionCommandError(
                    "Ghi đè giọng theo chương chỉ áp dụng cho đúng một chương. "
                    f"Phạm vi hiện tại: Chương {int(command_range['from_chapter'])}-"
                    f"{int(command_range['to_chapter'])}."
                )
            voice_id = None if is_clear else str(payload.get("voice_id") or "").strip()
            if not is_clear and not voice_id:
                raise ProductionCommandError("A selectable voice is required")
            result = apply_chapter_voice_override(
                db,
                store,
                book_id=int(payload.get("book_id") or command_range["book_id"]),
                from_chapter=int(command_range["from_chapter"]),
                to_chapter=int(command_range["to_chapter"]),
                speaker_key=str(payload["speaker_key"]).strip(),
                operation="clear" if is_clear else "set",
                voice_id=voice_id,
                voice_catalog=_load_voice_catalog(),
                idempotency_key=request.idempotency_key,
                custom_voice_context=_build_custom_voice_context(),
            )
            applied_items = tuple(
                {
                    **dict(item),
                    "speaker_key": result["speaker_key"],
                    "voice_id": result.get("voice_id"),
                    "operation": result["operation"],
                }
                for item in result.get("applied") or []
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=max(1, int(result.get("chapter_count") or 0)),
                applied_items=applied_items,
                operator_message=(
                    "Da go ghi de giong cho pham vi da chon."
                    if is_clear
                    else "Da ap dung giong cho pham vi da chon."
                ),
            )
        if command_type == "SAVE_VOICE_ASSIGNMENTS":
            book_id = int(payload["book_id"])
            profile_request = BookVoiceProfileRequest.model_validate(payload["profile"])
            assignments = list(payload.get("assignments") or [])
            submitted = 1 + len(assignments)
            applied: list[dict[str, Any]] = []
            failed: list[dict[str, Any]] = []
            try:
                profile = write_book_voice_profile(book_id, profile_request)
                applied.append({
                    "type": "book_voice_profile",
                    "book_id": book_id,
                    "config_version": profile.get("config_version"),
                })
            except HTTPException as exc:
                failed.append({
                    "type": "book_voice_profile",
                    "book_id": book_id,
                    "reason": str(exc.detail),
                })
            if failed:
                for item in assignments:
                    failed.append({
                        "type": "character_voice",
                        "character_id": int(item["character_id"]),
                        "reason": "Book Voice Profile was not saved.",
                    })
            else:
                for item in assignments:
                    character_id = int(item["character_id"])
                    try:
                        result = write_character_voice_override(
                            character_id,
                            CharacterOverrideRequest.model_validate({
                                key: value
                                for key, value in item.items()
                                if key != "character_id"
                            }),
                        )
                        applied.append({
                            "type": "character_voice",
                            "character_id": character_id,
                            "voice_override_id": result.get("voice_override_id"),
                        })
                    except (HTTPException, ValidationError, ValueError) as exc:
                        failed.append({
                            "type": "character_voice",
                            "character_id": character_id,
                            "reason": str(
                                exc.detail if isinstance(exc, HTTPException) else exc
                            ),
                        })
            outcome = (
                "PARTIAL"
                if applied and failed
                else "REJECTED" if failed else "APPLIED"
            )
            return ProductionCommandMutation(
                outcome=outcome,
                submitted_count=submitted,
                applied_items=tuple(applied),
                failed_items=tuple(failed),
                operator_message=(
                    f"Đã lưu {len(applied)}/{submitted} cấu hình giọng."
                    if failed
                    else "Đã lưu cấu hình giọng và mở bước duyệt bản đồ giọng."
                ),
            )
        if command_type == "APPROVE_CASTING_PLAN":
            plan_id = int(payload["casting_plan_id"])
            result = approve_casting(plan_id)
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({
                    "chapter_id": result.get("chapter_id"),
                    "casting_plan_id": plan_id,
                    "plan_revision": result.get("plan_revision"),
                },),
                operator_message="Đã duyệt bản đồ giọng cuối.",
            )
        if command_type in {"PREPARE", "PREPARE_REPLACEMENT"}:
            replacement_artifact_id = None
            if command_type == "PREPARE_REPLACEMENT":
                artifact_scope = request.scope.get("artifact")
                replacement_artifact_id = (
                    int(artifact_scope["id"])
                    if isinstance(artifact_scope, dict)
                    else int(artifact_scope)
                    if artifact_scope is not None
                    else None
                )
                if replacement_artifact_id is None:
                    raise ProductionCommandError(
                        "Replacement PREPARE requires the rejected Artifact scope."
                    )
                replacement = db.fetch_one(
                    """SELECT c.id AS chapter_id,c.chapter_number,c.book_id,
                              c.active_audio_artifact_id,c.human_approval_json
                       FROM artifacts a
                       JOIN chapters c ON c.id=a.chapter_id
                       WHERE a.id=? AND a.deleted_at IS NULL""",
                    (replacement_artifact_id,),
                )
                if (
                    not replacement
                    or int(replacement["active_audio_artifact_id"] or 0)
                    != replacement_artifact_id
                ):
                    raise ProductionCommandError(
                        "Replacement Artifact is not the active chapter output."
                    )
                approval = _parse_human_approval(
                    replacement["human_approval_json"]
                )
                if (
                    not approval
                    or str(approval.get("status") or "").lower() != "needs_fixes"
                    or int(approval.get("artifact_id") or 0)
                    != replacement_artifact_id
                ):
                    raise ProductionCommandError(
                        "Replacement PREPARE requires a durable needs_fixes verdict."
                    )
                repair_draft = resolve_repair_draft_evidence(
                    db,
                    int(replacement["chapter_id"]),
                    active_artifact_id=replacement_artifact_id,
                )
                repair_review = (
                    resolve_repair_draft_review_evidence(
                        db,
                        int(replacement["chapter_id"]),
                        repair_draft_evidence_id=int(repair_draft["evidence_id"]),
                        active_artifact_id=replacement_artifact_id,
                    )
                    if repair_draft
                    else None
                )
                if (
                    not repair_draft
                    or not repair_review
                    or int(repair_review.get("text_revision_id") or 0)
                    != int(repair_draft.get("text_revision_id") or 0)
                    or int(repair_review.get("casting_plan_id") or 0)
                    != int(repair_draft.get("casting_plan_id") or 0)
                    or int(repair_review.get("casting_plan_revision") or 0)
                    != int(repair_draft.get("casting_plan_revision") or 0)
                ):
                    raise ProductionCommandError(
                        "Replacement PREPARE requires the current reviewed repair draft."
                    )
            if "plan_fingerprint" in payload:
                parsed = BatchPrepareApiRequest.model_validate(payload)
                if command_type == "PREPARE_REPLACEMENT" and (
                    int(parsed.book_id) != int(replacement["book_id"])
                    or int(parsed.from_chapter)
                    != int(replacement["chapter_number"])
                    or int(parsed.to_chapter)
                    != int(replacement["chapter_number"])
                ):
                    raise ProductionCommandError(
                        "Replacement PREPARE must target exactly the rejected chapter."
                    )
                result = _prepare_service().prepare(
                    parsed.model_dump(),
                    authorization_header=authorization_header,
                )
                if result.http_status != 200:
                    raise ProductionCommandError(
                        str(
                            result.payload.get("message")
                            or result.payload.get("code")
                            or "PREPARE bị từ chối."
                        )
                    )
                body = dict(result.payload)
                fallback_count = parsed.to_chapter - parsed.from_chapter + 1
            else:
                parsed_job = JobRequest.model_validate(payload)
                body = prepare_job_route(parsed_job)
                fallback_count = parsed_job.to_chapter - parsed_job.from_chapter + 1
            job_id = body.get("job_id") or body.get("result", {}).get("job_id")
            prepared_rows = (
                db.fetch_all(
                    """SELECT c.id AS chapter_id,c.chapter_number,jc.id AS job_chapter_id
                       FROM job_chapters jc
                       JOIN chapters c ON c.id=jc.chapter_id
                       WHERE jc.job_id=?
                       ORDER BY jc.sequence""",
                    (int(job_id),),
                )
                if job_id is not None
                else []
            )
            prepared_status = (
                body.get("state")
                or body.get("status")
                or body.get("result", {}).get("state")
                or body.get("result", {}).get("status")
                or "prepared"
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=fallback_count,
                applied_items=tuple(
                    {
                        "chapter_id": int(row["chapter_id"]),
                        "chapter_number": int(row["chapter_number"]),
                        "job_chapter_id": int(row["job_chapter_id"]),
                        "job_id": job_id,
                        "status": prepared_status,
                    }
                    for row in prepared_rows
                ),
                operator_message=(
                    "Đã chuẩn bị bản render lại. Bản audio bị từ chối vẫn được giữ trong lịch sử."
                    if command_type == "PREPARE_REPLACEMENT"
                    else "Đã chuẩn bị phạm vi. Chưa bắt đầu render."
                ),
            )
        if command_type == "START_RENDER":
            job_id = int(payload["job_id"])
            if (
                prepare_runtime_integration.runtime_mode == PRODUCTION
                and not getattr(
                    prepare_runtime_integration,
                    "production_render_enabled",
                    False,
                )
            ):
                raise HTTPException(409, {"code": "START_RENDER_UNAVAILABLE"})
            result = start_prepared_job(
                db,
                settings,
                job_id=job_id,
                voice_catalog=_load_voice_catalog(),
                store=store,
                command_idempotency_key=request.idempotency_key,
            )
            if not result.get("idempotent_reused"):
                worker.wake()
            return ProductionCommandMutation(
                outcome="ACCEPTED",
                submitted_count=1,
                applied_items=({
                    "job_id": job_id,
                    "status": result.get("status"),
                    "reused": bool(result.get("idempotent_reused")),
                },),
                operator_message="Đã nhận lệnh bắt đầu render.",
                asynchronous_reference={
                    "type": "job",
                    "id": job_id,
                    "status": result.get("status"),
                    "status_url": f"/api/jobs/{job_id}",
                },
            )
        if command_type == "RETRY_RENDER":
            job_id = int(payload["job_id"])
            result = job_action(job_id, "retry")
            return ProductionCommandMutation(
                outcome="ACCEPTED",
                submitted_count=1,
                applied_items=({"job_id": job_id, "status": result.get("status")},),
                operator_message="Đã nhận lệnh thử lại phần recoverable.",
                asynchronous_reference={
                    "type": "job",
                    "id": job_id,
                    "status": result.get("status") or "queued",
                    "status_url": f"/api/jobs/{job_id}",
                },
            )
        if command_type == "JOB_ACTION":
            job_id = int(payload["job_id"])
            action = str(payload["action"]).strip().lower()
            if action not in {"pause", "resume", "cancel"}:
                raise ProductionCommandError("Unsupported Job action")
            result = job_action(job_id, action)
            asynchronous = action == "resume"
            return ProductionCommandMutation(
                outcome="ACCEPTED" if asynchronous else "APPLIED",
                submitted_count=1,
                applied_items=({
                    "job_id": job_id,
                    "action": action,
                    "status": result.get("status"),
                },),
                operator_message={
                    "pause": "Đã ghi nhận yêu cầu tạm dừng.",
                    "resume": "Đã nhận lệnh tiếp tục render.",
                    "cancel": "Đã ghi nhận yêu cầu hủy.",
                }[action],
                asynchronous_reference=(
                    {
                        "type": "job",
                        "id": job_id,
                        "status": result.get("status") or "queued",
                        "status_url": f"/api/jobs/{job_id}",
                    }
                    if asynchronous
                    else None
                ),
            )
        if command_type == "RETRY_JOB_CHAPTER":
            job_id = int(payload["job_id"])
            job_chapter_id = int(payload["job_chapter_id"])
            row = db.fetch_one(
                """SELECT jc.status,jc.job_id,j.status AS job_status
                   FROM job_chapters jc
                   JOIN jobs j ON j.id=jc.job_id
                   WHERE jc.id=?""",
                (job_chapter_id,),
            )
            if not row or int(row["job_id"]) != job_id:
                raise LookupError("JobChapter does not belong to the requested Job")
            reused = row["status"] == "pending" and row["job_status"] == "queued"
            result = (
                {"verified_segments_reused": None, "segments_reset": None}
                if reused
                else retry_chapter(job_chapter_id)
            )
            return ProductionCommandMutation(
                outcome="ACCEPTED",
                submitted_count=1,
                applied_items=({
                    "job_id": job_id,
                    "job_chapter_id": job_chapter_id,
                    "status": "queued",
                    "reused": reused,
                    "verified_segments_reused": result.get("verified_segments_reused"),
                    "segments_reset": result.get("segments_reset"),
                },),
                operator_message="Đã xếp lại chương lỗi và giữ nguyên segment hợp lệ.",
                asynchronous_reference={
                    "type": "job",
                    "id": job_id,
                    "status": "queued",
                    "status_url": f"/api/jobs/{job_id}",
                },
            )
        if command_type == "RETRY_SEGMENT":
            job_id = int(payload["job_id"])
            segment_id = int(payload["segment_id"])
            row = db.fetch_one(
                """SELECT s.status,jc.job_id,j.status AS job_status
                   FROM segments s
                   JOIN job_chapters jc ON jc.id=s.job_chapter_id
                   JOIN jobs j ON j.id=jc.job_id
                   WHERE s.id=?""",
                (segment_id,),
            )
            if not row or int(row["job_id"]) != job_id:
                raise LookupError("Segment does not belong to the requested Job")
            reused = row["status"] == "pending" and row["job_status"] == "queued"
            if not reused:
                retry_failed_segment(segment_id)
            return ProductionCommandMutation(
                outcome="ACCEPTED",
                submitted_count=1,
                applied_items=({
                    "job_id": job_id,
                    "segment_id": segment_id,
                    "status": "queued",
                    "reused": reused,
                },),
                operator_message="Đã xếp lại segment lỗi; segment hợp lệ được giữ nguyên.",
                asynchronous_reference={
                    "type": "job",
                    "id": job_id,
                    "status": "queued",
                    "status_url": f"/api/jobs/{job_id}",
                },
            )
        if command_type == "REGENERATE_SEGMENT":
            job_id = int(payload["job_id"])
            segment_id = int(payload["segment_id"])
            segment_scope = db.fetch_one(
                """SELECT jc.job_id
                   FROM segments s
                   JOIN job_chapters jc ON jc.id=s.job_chapter_id
                   WHERE s.id=?""",
                (segment_id,),
            )
            if not segment_scope or int(segment_scope["job_id"]) != job_id:
                raise LookupError("Segment does not belong to the requested Job")
            existing = db.fetch_one(
                """SELECT sa.id AS attempt_id,sa.attempt_number,sa.duration_ms
                   FROM segment_attempts sa
                   WHERE sa.segment_id=? AND sa.status='candidate'
                   ORDER BY sa.attempt_number DESC LIMIT 1""",
                (segment_id,),
            )
            reused = existing is not None
            result = (
                {
                    "attempt_id": int(existing["attempt_id"]),
                    "attempt_number": int(existing["attempt_number"]),
                    "duration_ms": int(existing["duration_ms"]),
                }
                if existing
                else regenerate_segment(segment_id)
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({
                    "job_id": job_id,
                    "segment_id": segment_id,
                    "attempt_id": result.get("attempt_id"),
                    "attempt_number": result.get("attempt_number"),
                    "duration_ms": result.get("duration_ms"),
                    "reused": reused,
                },),
                operator_message="Đã tạo candidate mới để nghe kiểm tra.",
            )
        if command_type == "CREATE_AUDIO_REPAIR_BLOCK":
            job_id = int(payload["job_id"])
            result = create_repair_block(
                job_id,
                {
                    "first_segment_id": int(payload["first_segment_id"]),
                    "last_segment_id": int(payload["last_segment_id"]),
                },
            )
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({
                    "job_id": job_id,
                    "repair_block_id": result.get("id"),
                    "job_chapter_id": result.get("job_chapter_id"),
                    "candidate_duration_ms": result.get("candidate_duration_ms"),
                },),
                operator_message="Đã tạo repair-block candidate để nghe kiểm tra.",
            )
        if command_type in {
            "ACCEPT_AUDIO_REPAIR_BLOCK",
            "REJECT_AUDIO_REPAIR_BLOCK",
        }:
            job_id = int(payload["job_id"])
            repair_block_id = int(payload["repair_block_id"])
            row = db.fetch_one(
                "SELECT job_id,status,job_chapter_id FROM audio_repair_blocks WHERE id=?",
                (repair_block_id,),
            )
            if not row or int(row["job_id"]) != job_id:
                raise LookupError("Repair block does not belong to the requested Job")
            accepting = command_type == "ACCEPT_AUDIO_REPAIR_BLOCK"
            terminal_status = "accepted" if accepting else "rejected"
            reused = str(row["status"]) == terminal_status
            result = (
                {
                    "repair_block": {
                        "job_chapter_id": int(row["job_chapter_id"]),
                    },
                    "new_artifact_id": None,
                }
                if reused
                else (
                    accept_repair_block(repair_block_id)
                    if accepting
                    else reject_repair_block(repair_block_id)
                )
            )
            repair = result.get("repair_block") or result
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({
                    "job_id": job_id,
                    "repair_block_id": repair_block_id,
                    "job_chapter_id": repair.get("job_chapter_id"),
                    "status": terminal_status,
                    "new_artifact_id": result.get("new_artifact_id"),
                    "reused": reused,
                },),
                operator_message=(
                    "Đã chấp nhận repair block và cập nhật artifact."
                    if accepting
                    else "Đã loại repair-block candidate."
                ),
            )
        if command_type in {
            "ACCEPT_SEGMENT_CANDIDATE",
            "REJECT_SEGMENT_CANDIDATE",
        }:
            job_id = int(payload["job_id"])
            segment_id = int(payload["segment_id"])
            attempt_id = int(payload["attempt_id"])
            row = db.fetch_one(
                """SELECT sa.status,jc.job_id
                   FROM segment_attempts sa
                   JOIN segments s ON s.id=sa.segment_id
                   JOIN job_chapters jc ON jc.id=s.job_chapter_id
                   WHERE sa.id=? AND sa.segment_id=?""",
                (attempt_id, segment_id),
            )
            if not row or int(row["job_id"]) != job_id:
                raise LookupError("Candidate does not belong to the requested Job")
            accepting = command_type == "ACCEPT_SEGMENT_CANDIDATE"
            terminal_status = "active" if accepting else "rejected"
            reused = str(row["status"]) == terminal_status
            if not reused:
                if accepting:
                    accept_candidate(segment_id, {"attempt_id": attempt_id})
                else:
                    reject_candidate(segment_id, {"attempt_id": attempt_id})
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({
                    "job_id": job_id,
                    "segment_id": segment_id,
                    "attempt_id": attempt_id,
                    "status": terminal_status,
                    "reused": reused,
                },),
                operator_message=(
                    "Đã chấp nhận candidate và cập nhật artifact."
                    if accepting
                    else "Đã loại candidate; audio hiện tại được giữ nguyên."
                ),
            )
        if command_type in {"HUMAN_QA_ACCEPT", "HUMAN_QA_NEEDS_FIXES"}:
            chapter_id = int(payload["chapter_id"])
            status = (
                "approved"
                if command_type == "HUMAN_QA_ACCEPT"
                else "needs_fixes"
            )
            result = set_human_approval(
                chapter_id,
                HumanApprovalRequest(
                    status=status,
                    notes=payload.get("notes"),
                    qa_feedback=payload.get("qa_feedback") or {},
                ),
            )
            artifact_id = result.get("human_approval", {}).get("artifact_id")
            chapter_number = result.get("chapter", {}).get("chapter_number") or chapter_id
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({
                    "chapter_id": chapter_id,
                    "artifact_id": artifact_id,
                    "qa_status": status,
                    "reused": bool(result.get("idempotent_reused")),
                },),
                operator_message=(
                    f"Đã ghi Chấp nhận cho Chương {chapter_number}."
                    if status == "approved"
                    else f"Đã ghi Cần sửa cho Chương {chapter_number}."
                ),
            )
        raise ProductionCommandError("Unsupported Production command type")

    return execute


def _production_command_from_body(command_body: Any) -> ProductionCommandRequest:
    if isinstance(command_body, str):
        try:
            command_body = json.loads(command_body)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                400,
                {
                    "code": "PRODUCTION_COMMAND_BODY_INVALID",
                    "message": "Production command body must be a JSON object.",
                },
            ) from exc
    if not isinstance(command_body, dict):
        raise HTTPException(
            400,
            {
                "code": "PRODUCTION_COMMAND_BODY_INVALID",
                "message": "Production command body must be a JSON object.",
            },
        )
    try:
        return ProductionCommandRequest.model_validate(command_body)
    except ValidationError as exc:
        raise HTTPException(
            400,
            {
                "code": "PRODUCTION_COMMAND_CONTRACT_INVALID",
                "message": "Production command request is incomplete or invalid.",
                "errors": exc.errors(),
            },
        ) from exc


@app.post("/api/production/commands")
@_serialized_production_mutation
def execute_production_command(
    request: Request,
    command_body: Any = Body(...),
) -> dict[str, Any]:
    command = _production_command_from_body(command_body)
    service = ProductionCommandService(_project_production_command)
    try:
        return service.execute(
            command_type=command.command_type,
            idempotency_key=command.idempotency_key,
            scope=command.scope,
            executor=_production_command_executor(
                command,
                authorization_header=_request_prepare_authorization(request),
            ),
        )
    except HTTPException as exc:
        detail = exc.detail
        message = (
            str(detail.get("message") or detail.get("code"))
            if isinstance(detail, dict)
            else str(detail)
        )
    except ClonePrepareApiError as exc:
        message = str(exc)
    except (
        CastingError,
        ChapterVoiceOverrideError,
        CharacterAssignmentError,
        JobPreparationConflict,
        JobStartConflict,
        LookupError,
        ProductionCommandError,
        RangeInputError,
        RetryConflict,
        SpeakerAssignmentError,
        GeminiSpeakerReviewSuggestionError,
        SpeakerReviewError,
        SpeakerReviewSuggestionError,
        ValueError,
        ValidationError,
        VoiceEligibilityBlocked,
        VoiceCatalogUnavailable,
        VoiceProfileError,
    ) as exc:
        message = str(exc)
    return service.rejected(
        command_type=command.command_type.strip().upper(),
        idempotency_key=command.idempotency_key,
        scope=command.scope,
        message=message or "Thao tác bị từ chối an toàn.",
    )


def _range_input_state(
    *,
    book_id: int,
    from_chapter: int,
    to_chapter: int,
    skip_completed: bool,
) -> dict[str, Any]:
    voice_catalog = _load_voice_catalog()
    return get_range_input_snapshot(
        db,
        store,
        settings,
        book_id=book_id,
        from_chapter=from_chapter,
        to_chapter=to_chapter,
        voice_catalog=voice_catalog,
        custom_voice_context=_build_custom_voice_context(),
        skip_completed=skip_completed,
    )


@app.get("/api/production/range-inputs")
def production_range_inputs(
    book_id: int = Query(..., gt=0),
    from_chapter: int = Query(..., ge=0),
    to_chapter: int = Query(..., ge=0),
    skip_completed: bool = Query(True),
) -> dict[str, Any]:
    try:
        return _range_input_state(
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            skip_completed=skip_completed,
        )
    except VoiceCatalogUnavailable as exc:
        raise _job_http_error(exc) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (RangeInputError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/production/range-inputs/prepare")
@_serialized_production_mutation
def production_prepare_range_inputs(
    request: RangeInputScopeRequest,
) -> dict[str, Any]:
    try:
        voice_catalog = _load_voice_catalog()
        return prepare_range_inputs(
            db,
            store,
            settings,
            book_id=request.book_id,
            from_chapter=request.from_chapter,
            to_chapter=request.to_chapter,
            voice_catalog=voice_catalog,
            allowed_voice_ids=_preset_voice_ids(),
            custom_voice_context=_build_custom_voice_context(),
            skip_completed=request.skip_completed,
        )
    except VoiceCatalogUnavailable as exc:
        raise _job_http_error(exc) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (RangeInputError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/production/range-inputs/speaker-approvals")
@_serialized_production_mutation
def production_approve_range_speaker_drafts(
    request: RangeSpeakerApprovalRequest,
) -> dict[str, Any]:
    try:
        snapshot = _range_input_state(
            book_id=request.book_id,
            from_chapter=request.from_chapter,
            to_chapter=request.to_chapter,
            skip_completed=request.skip_completed,
        )
        result = approve_ready_speaker_drafts(
            db,
            store,
            settings,
            snapshot=snapshot,
            requested=[item.model_dump() for item in request.chapters],
        )
        result["snapshot"] = _range_input_state(
            book_id=request.book_id,
            from_chapter=request.from_chapter,
            to_chapter=request.to_chapter,
            skip_completed=request.skip_completed,
        )
        return result
    except VoiceCatalogUnavailable as exc:
        raise _job_http_error(exc) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (RangeInputError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/production/range-inputs/casting-approvals")
@_serialized_production_mutation
def production_approve_range_casting_plans(
    request: RangeCastingApprovalRequest,
) -> dict[str, Any]:
    try:
        voice_catalog = _load_voice_catalog()
        custom_context = _build_custom_voice_context()
        snapshot = get_range_input_snapshot(
            db,
            store,
            settings,
            book_id=request.book_id,
            from_chapter=request.from_chapter,
            to_chapter=request.to_chapter,
            voice_catalog=voice_catalog,
            custom_voice_context=custom_context,
            skip_completed=request.skip_completed,
        )
        result = approve_ready_casting_plans(
            db,
            store,
            snapshot=snapshot,
            requested=[item.model_dump() for item in request.chapters],
            voice_catalog=voice_catalog,
            allowed_voice_ids=_preset_voice_ids(),
            custom_voice_context=custom_context,
        )
        result["snapshot"] = get_range_input_snapshot(
            db,
            store,
            settings,
            book_id=request.book_id,
            from_chapter=request.from_chapter,
            to_chapter=request.to_chapter,
            voice_catalog=voice_catalog,
            custom_voice_context=custom_context,
            skip_completed=request.skip_completed,
        )
        return result
    except VoiceCatalogUnavailable as exc:
        raise _job_http_error(exc) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (RangeInputError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/production/batch-plan")
def production_batch_plan(
    book_id: int = Query(..., gt=0),
    from_chapter: int = Query(..., ge=0),
    to_chapter: int = Query(..., ge=0),
    target_phase: str = Query(..., min_length=1),
) -> dict[str, Any]:
    try:
        voice_catalog = _load_voice_catalog()
        readiness = get_range_readiness(
            db,
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            voice_catalog=voice_catalog,
            store=store,
        )
        return build_batch_plan(readiness, target_phase=target_phase)
    except VoiceCatalogUnavailable as exc:
        raise _job_http_error(exc) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/books/{book_id}/chapters")
def list_chapters(
    book_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    query: str = "",
    status: str = "",
) -> dict[str, Any]:
    where = ["c.book_id=?"]
    params: list[Any] = [book_id]
    if query.strip():
        where.append("(c.title LIKE ? OR CAST(c.chapter_number AS TEXT)=?)")
        params.extend([f"%{query.strip()}%", query.strip()])
    if status:
        where.append("c.audio_status=?")
        params.append(status)
    clause = " AND ".join(where)
    total = db.fetch_one(f"SELECT COUNT(*) AS count FROM chapters c WHERE {clause}", tuple(params))["count"]
    rows = db.fetch_all(
        f"""SELECT c.id,c.chapter_number,c.title,c.char_count,c.audio_status,c.active_audio_artifact_id,
                   (SELECT COUNT(*) FROM qa_issues q WHERE q.chapter_id=c.id AND q.resolved_at IS NULL) AS qa_count
            FROM chapters c WHERE {clause} ORDER BY c.chapter_number LIMIT ? OFFSET ?""",
        tuple(params + [limit, offset]),
    )
    return {"total": total, "items": annotate_chapter_rows(db, rows)}


@app.get("/api/chapters/{chapter_id}")
def chapter_detail(chapter_id: int) -> dict[str, Any]:
    chapter = db.fetch_one(
        """SELECT c.*,b.title AS book_title FROM chapters c JOIN books b ON b.id=c.book_id WHERE c.id=?""",
        (chapter_id,),
    )
    if not chapter:
        raise HTTPException(404, "Không tìm thấy chương.")
    revisions = db.fetch_all(
        "SELECT * FROM text_revisions WHERE chapter_id=? ORDER BY id DESC", (chapter_id,)
    )
    issues = db.fetch_all(
        "SELECT * FROM qa_issues WHERE chapter_id=? ORDER BY id", (chapter_id,)
    )
    artifact = None
    if chapter["active_audio_artifact_id"]:
        artifact = db.fetch_one(
            "SELECT id,artifact_type,path,size_bytes,duration_ms,status FROM artifacts WHERE id=?",
            (chapter["active_audio_artifact_id"],),
        )
    active_output = get_active_output_bindings(db, [chapter_id]).get(chapter_id, {})
    approval = resolve_authoritative_human_approval(
        db,
        chapter_id,
        active_artifact_id=int(chapter["active_audio_artifact_id"] or 0),
    )
    chapter_data, human_approval = _decorate_human_approval(
        dict(chapter),
        approval,
        active_output,
    )
    revision_data = []
    for row in revisions:
        item = dict(row)
        item["text"] = store.read_text(row["content_path"])
        revision_data.append(item)
    return {
        "chapter": chapter_data,
        "revisions": revision_data,
        "qa_issues": [dict(row) for row in issues],
        "audio_artifact": dict(artifact) if artifact else None,
        "active_output": active_output,
        "human_approval": human_approval,
    }


@app.put("/api/chapters/{chapter_id}/human-approval")
def set_human_approval(chapter_id: int, request: HumanApprovalRequest) -> dict[str, Any]:
    chapter = db.fetch_one(
        "SELECT c.*,b.title AS book_title FROM chapters c JOIN books b ON b.id=c.book_id WHERE c.id=?",
        (chapter_id,),
    )
    if not chapter:
        raise HTTPException(404, "Không tìm thấy chương.")
    chapter_data = dict(chapter)
    snapshot = _active_artifact_snapshot(chapter_data)
    if not snapshot:
        raise HTTPException(400, "Chưa có active audio để chốt hoặc đánh dấu cần sửa.")
    notes = (request.notes or "").strip()
    if request.status == "needs_fixes" and not notes:
        raise HTTPException(
            400,
            {
                "code": "QA_REJECTION_NOTE_REQUIRED",
                "message": "Please describe the issue before marking this audio as needing fixes.",
            },
        )
    existing_approval = _parse_human_approval(chapter_data["human_approval_json"])
    qa_feedback = (
        request.qa_feedback.model_dump(exclude_none=True)
        if request.qa_feedback is not None
        else {}
    )
    if (
        existing_approval
        and existing_approval.get("status") == request.status
        and (existing_approval.get("notes") or "") == notes
        and int(existing_approval.get("artifact_id") or 0)
        == int(snapshot["artifact_id"])
        and dict(existing_approval.get("qa_feedback") or {}) == qa_feedback
    ):
        active_output = get_active_output_bindings(db, [chapter_id]).get(chapter_id, {})
        chapter_view, human_approval = _decorate_human_approval(
            chapter_data, existing_approval, active_output
        )
        return {
            "chapter": chapter_view,
            "human_approval": human_approval,
            "active_output": active_output,
            "idempotent_reused": True,
        }
    recorded_at = utcnow()
    approval = {
        "status": request.status,
        "recorded_at": recorded_at,
        "approved_at": recorded_at if request.status == "approved" else None,
        "notes": notes,
        "artifact_id": snapshot["artifact_id"],
        "job_id": snapshot["job_id"],
        "output_path": snapshot["output_path"],
        "sha256": snapshot["sha256"],
        "duration_ms": snapshot["duration_ms"],
        "qa_feedback": qa_feedback,
    }
    with db.transaction() as connection:
        connection.execute(
            "UPDATE chapters SET human_approval_json=?, updated_at=? WHERE id=?",
            (json.dumps(approval, ensure_ascii=False), recorded_at, chapter_id),
        )
        connection.execute(
            """
            INSERT INTO audit_events(event_code,job_id,chapter_id,details_json,created_at)
            VALUES(?,?,?,?,?)
            """,
            (
                "human_qa_recorded",
                snapshot["job_id"],
                chapter_id,
                json.dumps(
                    {
                        "status": request.status,
                        "notes": notes,
                        "artifact_id": snapshot["artifact_id"],
                        "job_id": snapshot["job_id"],
                        "sha256": snapshot["sha256"],
                        "duration_ms": snapshot["duration_ms"],
                        "qa_feedback": qa_feedback,
                    },
                    ensure_ascii=False,
                ),
                recorded_at,
            ),
        )
    refreshed = db.fetch_one(
        "SELECT c.*,b.title AS book_title FROM chapters c JOIN books b ON b.id=c.book_id WHERE c.id=?",
        (chapter_id,),
    )
    active_output = get_active_output_bindings(db, [chapter_id]).get(chapter_id, {})
    chapter_view, human_approval = _decorate_human_approval(dict(refreshed), approval, active_output)
    return {
        "chapter": chapter_view,
        "human_approval": human_approval,
        "active_output": active_output,
        "idempotent_reused": False,
    }


@app.get("/api/chapters/{chapter_id}/human-approval-history")
def human_approval_history(chapter_id: int) -> dict[str, Any]:
    chapter = db.fetch_one(
        "SELECT id,human_approval_json FROM chapters WHERE id=?",
        (chapter_id,),
    )
    if not chapter:
        raise HTTPException(404, "Chapter not found.")
    rows = db.fetch_all(
        """
        SELECT id,job_id,details_json,created_at
        FROM audit_events
        WHERE chapter_id=? AND event_code='human_qa_recorded'
        ORDER BY id DESC
        """,
        (chapter_id,),
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            details = json.loads(row["details_json"] or "{}")
        except (TypeError, ValueError):
            details = {}
        items.append(
            {
                "id": int(row["id"]),
                "status": details.get("status"),
                "notes": details.get("notes") or "",
                "artifact_id": details.get("artifact_id"),
                "job_id": details.get("job_id") or row["job_id"],
                "sha256": details.get("sha256"),
                "duration_ms": details.get("duration_ms"),
                "qa_feedback": details.get("qa_feedback") or {},
                "recorded_at": row["created_at"],
                "source": "audit",
            }
        )
    current = _parse_human_approval(chapter["human_approval_json"])
    if current and not any(
        item["artifact_id"] == current.get("artifact_id")
        and item["recorded_at"] == current.get("recorded_at")
        for item in items
    ):
        items.append(
            {
                "id": None,
                "status": current.get("status"),
                "notes": current.get("notes") or "",
                "artifact_id": current.get("artifact_id"),
                "job_id": current.get("job_id"),
                "sha256": current.get("sha256"),
                "duration_ms": current.get("duration_ms"),
                "qa_feedback": current.get("qa_feedback") or {},
                "recorded_at": current.get("recorded_at"),
                "source": "legacy_snapshot",
            }
        )
    items.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)
    return {"chapter_id": chapter_id, "items": items, "total": len(items)}


@app.get("/api/chapters/{chapter_id}/revisions")
def chapter_revisions(chapter_id: int) -> dict[str, Any]:
    try:
        return {"chapter_id": chapter_id, "items": list_revision_metadata(db, chapter_id)}
    except TextDiffError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/chapters/{chapter_id}/diff")
def chapter_revision_diff(
    chapter_id: int,
    revision_a: int = Query(..., ge=1),
    revision_b: int = Query(..., ge=1),
) -> dict[str, Any]:
    try:
        return build_revision_diff(db, store, chapter_id, revision_a, revision_b)
    except TextDiffError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/chapters/{chapter_id}/text-revisions/targeted-correction")
def create_targeted_text_correction(
    chapter_id: int,
    request: TargetedTextCorrectionRequest,
) -> dict[str, Any]:
    try:
        return apply_targeted_text_correction(
            db,
            store,
            chapter_id=chapter_id,
            base_revision_id=request.base_revision_id,
            expected_text=request.expected_text,
            replacement_text=request.replacement_text,
            reason=request.reason,
        )
    except TextCorrectionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except TextCorrectionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except TextCorrectionError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/voices")
def list_voices() -> dict[str, Any]:
    try:
        return {"items": tts_service.voices(), "status": tts_service.status}
    except Exception as exc:
        raise HTTPException(503, f"Không tải được VieNeu: {exc}") from exc


@app.get("/api/voice-catalog")
def voice_catalog() -> dict[str, Any]:
    try:
        return _load_voice_catalog().public_payload()
    except VoiceCatalogUnavailable as exc:
        raise _job_http_error(exc) from exc


def _preset_voice_ids() -> set[str]:
    return set(_load_voice_catalog().preset_ids)


@app.get("/api/books/{book_id}/characters")
def book_characters(book_id: int) -> list[dict[str, Any]]:
    return list_characters(db, book_id)


@app.post("/api/books/{book_id}/character-bible/dry-run")
def dry_run_character_bible(
    book_id: int,
    request: CharacterBibleImportRequest = Body(...),
) -> dict[str, Any]:
    try:
        return _character_bible_plan(book_id, request)
    except CharacterBibleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/books/{book_id}/character-bible/apply")
def apply_character_bible(
    book_id: int,
    request: CharacterBibleImportRequest = Body(...),
) -> dict[str, Any]:
    try:
        plan = _character_bible_plan(book_id, request)
        result = apply_character_bible_import(db, plan)
        return {"plan": plan, "result": result}
    except CharacterBibleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/books/{book_id}/characters")
def add_character(book_id: int, request: CharacterCreateRequest) -> dict[str, Any]:
    try:
        voice_id = request.voice_override_id or request.default_voice_id
        if voice_id is not None:
            if is_custom_ref(voice_id):
                ctx = _build_custom_voice_context()
                if ctx is None or not ctx.is_available(voice_id):
                    raise CastingError("Custom voice does not exist or is not usable")
            elif voice_id not in _preset_voice_ids():
                raise CastingError("Preset voice does not exist")
        return create_character(
            db, book_id, request.display_name, voice_id, gender=request.gender
        )
    except CastingError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.patch("/api/characters/{character_id}")
def edit_character(character_id: int, request: CharacterUpdateRequest) -> dict[str, Any]:
    try:
        if request.default_voice_id is not None and request.default_voice_id not in _preset_voice_ids():
            raise CastingError("Preset voice does not exist")
        return update_character(
            db,
            character_id,
            display_name=request.display_name,
            voice_id=request.default_voice_id,
            gender=request.gender,
            role=request.role,
            age_group=request.age_group,
            description=request.description,
            speech_style=request.speech_style,
            visual_notes=request.visual_notes,
            notes=request.notes,
        )
    except CastingError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/books/{book_id}/voice-profile")
def read_book_voice_profile(book_id: int) -> dict[str, Any]:
    if not db.fetch_one("SELECT id FROM books WHERE id=?", (book_id,)):
        raise HTTPException(404, "Book not found")
    profile = get_book_voice_profile(db, book_id)
    if not profile:
        return {"configured": False, "profile": None, "valid": False, "missing_preset_ids": []}
    custom_context = _build_custom_voice_context()
    return {
        "configured": True,
        "profile": profile,
        **profile,
        **profile_validation(profile, _preset_voice_ids(), custom_context),
    }


@app.put("/api/books/{book_id}/voice-profile")
def write_book_voice_profile(book_id: int, request: BookVoiceProfileRequest) -> dict[str, Any]:
    try:
        return set_book_voice_profile(
            db,
            book_id,
            allowed_voice_ids=_preset_voice_ids(),
            custom_voice_context=_build_custom_voice_context(),
            **request.model_dump()
        )
    except VoiceProfileError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.put("/api/characters/{character_id}/voice-override")
def write_character_voice_override(
    character_id: int, request: CharacterOverrideRequest
) -> dict[str, Any]:
    try:
        if request.gender is not None and request.gender not in {"male", "female", "unknown"}:
            raise VoiceProfileError("Character gender is invalid")
        custom_context = _build_custom_voice_context()
        valid_voices = _preset_voice_ids()
        if request.voice_override_id is not None:
            # Check both preset and custom voices
            from .voice_ref import is_custom_ref
            if is_custom_ref(request.voice_override_id):
                # Validate custom voice through context
                from .voice_ref import parse_custom_ref
                try:
                    custom_id = parse_custom_ref(request.voice_override_id)
                    if custom_context is None or custom_context.get(custom_id) is None:
                        raise VoiceProfileError("Character override is not an available custom voice")
                except Exception as e:
                    raise VoiceProfileError(f"Character override custom voice is invalid: {e}") from e
            elif request.voice_override_id not in valid_voices:
                raise VoiceProfileError("Character override is not an available preset voice")
        result = set_character_voice_override(
            db,
            character_id,
            request.voice_override_id,
            allowed_voice_ids=valid_voices,
            custom_voice_context=custom_context,
        )
        if request.gender is not None:
            result = set_character_gender(db, character_id, request.gender)
        return result
    except VoiceProfileError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/books/{book_id}/voice-profile/resolve")
def resolve_voice_preview(book_id: int, request: VoiceResolveRequest) -> dict[str, Any]:
    try:
        profile = get_book_voice_profile(db, book_id)
        if not profile:
            raise VoiceProfileError("Book voice profile not found")
        character = None
        if request.character_id is not None:
            row = db.fetch_one(
                "SELECT * FROM characters WHERE id=? AND book_id=? AND active=1",
                (request.character_id, book_id),
            )
            if not row:
                raise VoiceProfileError("Character not found in this book")
            character = dict(row)
            if request.gender is not None:
                if request.gender not in {"male", "female", "unknown"}:
                    raise VoiceProfileError("Character gender is invalid")
                character["gender"] = request.gender
        
        # Build custom voice context for resolution
        custom_context = _build_custom_voice_context()
        
        # Validate preview override (preset or custom)
        if request.voice_override_id is not None:
            from .voice_ref import is_custom_ref, parse_custom_ref
            if is_custom_ref(request.voice_override_id):
                try:
                    custom_id = parse_custom_ref(request.voice_override_id)
                    if custom_context is None or custom_context.get(custom_id) is None:
                        raise VoiceProfileError("Preview override is not an available custom voice")
                except Exception as e:
                    raise VoiceProfileError(f"Preview override custom voice is invalid: {e}") from e
            elif request.voice_override_id not in _preset_voice_ids():
                raise VoiceProfileError("Preview override is not an available preset voice")
        
        preview_override = (
            request.voice_override_id
            if request.voice_override_id is not None
            else (None if request.use_character_override else "")
        )
        result = resolve_voice(
            speaker_type=request.speaker_type,
            book_voice_profile=profile,
            character=character,
            inferred_gender=request.inferred_gender,
            optional_override=preview_override,
            custom_voice_context=custom_context,
        )
        return {**result, "resolved_voice": result["voice"]}
    except VoiceProfileError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/characters/{character_id}")
def remove_character(character_id: int) -> dict[str, bool]:
    try:
        deactivate_character(db, character_id)
        return {"ok": True}
    except CastingError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/chapters/{chapter_id}/casting")
def chapter_casting(chapter_id: int) -> dict[str, Any]:
    try:
        return casting_context(
            db, store, chapter_id, _preset_voice_ids(), custom_voice_context=_build_custom_voice_context()
        )
    except CastingError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/chapters/{chapter_id}/casting/draft")
def save_casting_draft(chapter_id: int, request: CastingDraftRequest) -> dict[str, Any]:
    try:
        return create_casting_draft(
            db,
            store,
            chapter_id=chapter_id,
            text_revision_id=request.text_revision_id,
            narrator_voice_id=request.narrator_voice_id,
            assignments=[item.model_dump() for item in request.assignments],
            allowed_voice_ids=_preset_voice_ids(),
            maximum=settings.tts_max_chars,
            custom_voice_context=_build_custom_voice_context(),
        )
    except CastingError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/chapters/{chapter_id}/speaker-assignment/draft")
def create_speaker_assignment_draft(
    chapter_id: int, request: SpeakerAssignmentDraftRequest
) -> dict[str, Any]:
    try:
        return generate_speaker_assignment_draft(
            db,
            store,
            settings,
            chapter_id=chapter_id,
            mode=request.mode,
            utterance_ids=request.utterance_ids,
            force_refresh=request.force_refresh,
        )
    except SpeakerAssignmentError as exc:
        raise HTTPException(400, str(exc)) from exc
    except GeminiSpeakerAssignmentError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/chapters/{chapter_id}/speaker-assignment/drafts/{draft_id}")
def read_speaker_assignment_draft(chapter_id: int, draft_id: int) -> dict[str, Any]:
    try:
        return get_speaker_review_draft(
            db, store, settings, chapter_id=chapter_id, draft_id=draft_id
        )
    except (SpeakerAssignmentError, SpeakerReviewError, OSError) as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/chapters/{chapter_id}/speaker-assignment/drafts")
def read_speaker_assignment_drafts(chapter_id: int) -> dict[str, Any]:
    try:
        return list_speaker_review_drafts(db, store, settings, chapter_id=chapter_id)
    except SpeakerReviewError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.put("/api/chapters/{chapter_id}/speaker-assignment/drafts/{draft_id}/reviews/{target_id}")
def review_speaker_assignment_target(
    chapter_id: int,
    draft_id: int,
    target_id: str,
    request: SpeakerAssignmentRowReviewRequest,
) -> dict[str, Any]:
    try:
        if request.decision == "MARK_NARRATOR":
            speaker_type = "narrator"
            character_id = None
            decision_source = "narrator"
        elif request.decision == "KEEP_UNKNOWN":
            speaker_type = "unknown"
            character_id = None
            decision_source = "unknown"
        else:
            speaker_type = "character"
            character_id = request.character_id
            decision_source = "manual_character"
        return review_speaker_assignment_row(
            db,
            store,
            settings,
            chapter_id=chapter_id,
            draft_id=draft_id,
            target_id=target_id,
            speaker_type=speaker_type,
            character_id=character_id,
            decision_source=decision_source,
            operator_note=request.operator_note,
        )
    except SpeakerReviewNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except SpeakerReviewConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (SpeakerReviewError, SpeakerAssignmentError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/chapters/{chapter_id}/speaker-assignment/drafts/{draft_id}/approve-only")
def approve_speaker_assignment_draft_without_casting(
    chapter_id: int, draft_id: int
) -> dict[str, Any]:
    try:
        return approve_speaker_assignment_draft_only(
            db,
            store,
            settings,
            chapter_id=chapter_id,
            draft_id=draft_id,
        )
    except SpeakerReviewNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except SpeakerReviewConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (SpeakerReviewError, SpeakerAssignmentError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/chapters/{chapter_id}/speaker-assignment/drafts/{draft_id}/approve")
def approve_speaker_assignment_review(
    chapter_id: int, draft_id: int, request: SpeakerReviewApprovalRequest
) -> dict[str, Any]:
    try:
        return approve_speaker_review(
            db,
            store,
            settings,
            chapter_id=chapter_id,
            draft_id=draft_id,
            base_casting_plan_revision_id=request.base_casting_plan_revision_id,
            expected_draft_fingerprint=request.expected_draft_fingerprint,
            expected_text_revision_id=request.expected_text_revision_id,
            decisions=[item.model_dump() for item in request.decisions],
            idempotency_key=request.idempotency_key,
            allowed_voice_ids=_preset_voice_ids(),
            custom_voice_context=_build_custom_voice_context(),
        )
    except SpeakerReviewConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (SpeakerReviewError, CastingError, SpeakerAssignmentError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/chapters/{chapter_id}/speaker-review/casting-plan-draft")
def create_speaker_review_casting_plan_draft(
    chapter_id: int, request: SpeakerReviewCastingPlanDraftRequest
) -> dict[str, Any]:
    try:
        return create_casting_plan_draft_from_speaker_review(
            db,
            store,
            settings,
            chapter_id=chapter_id,
            draft_id=request.speaker_draft_id,
            base_casting_plan_revision_id=request.base_casting_plan_revision_id,
            expected_draft_fingerprint=request.expected_draft_fingerprint,
            expected_text_revision_id=request.expected_text_revision_id,
            decisions=[item.model_dump() for item in request.decisions],
            idempotency_key=request.idempotency_key,
            operator_note=request.operator_note,
            allowed_voice_ids=_preset_voice_ids(),
            custom_voice_context=_build_custom_voice_context(),
        )
    except SpeakerReviewNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except SpeakerReviewConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (SpeakerReviewError, CastingError, SpeakerAssignmentError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/casting/{casting_plan_id}/approve")
def approve_casting(casting_plan_id: int) -> dict[str, Any]:
    try:
        candidate = get_plan(db, store, casting_plan_id, include_text=True)
        voice_catalog = _load_voice_catalog()
        require_casting_plan_eligible(
            candidate["plan"],
            voice_catalog,
            chapter_id=int(candidate["chapter_id"]),
        )
        result = approve_plan(db, store, casting_plan_id)
        validate_approved_plan(
            db,
            store,
            casting_plan_id,
            set(voice_catalog.preset_ids),
            custom_voice_context=_build_custom_voice_context(),
        )
        return result
    except (VoiceCatalogUnavailable, VoiceEligibilityBlocked) as exc:
        raise _job_http_error(exc) from exc
    except CastingError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/casting/{casting_plan_id}")
def read_casting_plan(casting_plan_id: int) -> dict[str, Any]:
    try:
        result = get_plan(db, store, casting_plan_id, include_text=True)
        validate_approved_plan(
            db,
            store,
            casting_plan_id,
            _preset_voice_ids(),
            custom_voice_context=_build_custom_voice_context(),
        )
        return result
    except CastingError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() else 400
        raise HTTPException(status, message) from exc


@app.post("/api/voice-previews")
def create_voice_preview(request: VoicePreviewRequest) -> dict[str, Any]:
    # Import custom voice exceptions for error handling
    from .custom_voice import CustomVoiceRevisionNotFoundError, CustomVoiceRepository
    from .synthesis_snapshot import StorageResolutionError
    from .voice_ref import is_custom_ref, resolve_custom_ref, CustomVoiceContext

    # XOR validation: exactly one selector required
    preset_provided = request.voice_id is not None
    custom_provided = request.custom_voice_revision_id is not None

    if not preset_provided and not custom_provided:
        raise HTTPException(400, "Must provide either voice_id or custom_voice_revision_id")
    if preset_provided and custom_provided:
        raise HTTPException(400, "Cannot provide both voice_id and custom_voice_revision_id")

    # Validate preview_text is only used with custom voices
    if request.preview_text is not None and preset_provided:
        raise HTTPException(400, "preview_text can only be used with custom_voice_revision_id")

    try:
        if preset_provided:
            # Check if voice_id is a custom logical reference (e.g., "custom:25")
            if is_custom_ref(request.voice_id):
                # Resolve logical custom voice reference to preferred revision
                ctx = CustomVoiceContext.from_repository(custom_voice_repo)
                resolved = resolve_custom_ref(request.voice_id, ctx, repository=custom_voice_repo)
                revision_id = resolved["custom_voice_revision_id"]

                # Use custom path with resolved revision
                result = voice_previews.create_custom(
                    revision_id,
                    preview_text=request.preview_text
                )
                result["audio_url"] = f"/api/voice-previews/{result['cache_key']}/file"
                return result
            else:
                # Preset path (unchanged behavior)
                valid_voices = {item["id"] for item in tts_service.voices()}
                if request.voice_id not in valid_voices:
                    raise ValueError(f"Giọng '{request.voice_id}' không tồn tại trong VieNeu.")
                result = voice_previews.create(request.voice_id)
                result["audio_url"] = f"/api/voice-previews/{result['cache_key']}/file"
                return result
        else:
            # Custom path with explicit revision ID and optional preview_text
            result = voice_previews.create_custom(
                request.custom_voice_revision_id,
                preview_text=request.preview_text
            )
            result["audio_url"] = f"/api/voice-previews/{result['cache_key']}/file"
            return result
    except CustomVoiceRevisionNotFoundError:
        raise HTTPException(404, "Custom voice revision not found")
    except StorageResolutionError:
        raise HTTPException(404, "Custom voice reference audio is unavailable")
    except ValueError as exc:
        # Metadata/transcript/duration validation errors
        exc_str = str(exc).lower()
        if "revision" in exc_str or "transcript" in exc_str or "audio" in exc_str:
            raise HTTPException(400, "Invalid custom voice revision metadata")
        if "duration" in exc_str or "preview" in exc_str:
            raise HTTPException(400, "Voice preview validation failed")
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(503, "Voice preview generation failed") from exc


@app.get("/api/voice-previews/{cache_key}/file")
def voice_preview_file(cache_key: str):
    try:
        path = voice_previews.audio_path(cache_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, media_type="audio/wav", filename=path.name)


@app.get("/api/jobs/preview")
def preview_job(book_id: int, from_chapter: int, to_chapter: int) -> dict[str, Any]:
    if from_chapter > to_chapter:
        raise HTTPException(400, "Khoảng chương không hợp lệ.")
    row = db.fetch_one(
        """SELECT COUNT(*) AS total,
            SUM(CASE WHEN active_audio_artifact_id IS NOT NULL THEN 1 ELSE 0 END) AS completed,
            SUM(char_count) AS chars
            FROM chapters WHERE book_id=? AND chapter_number BETWEEN ? AND ?""",
        (book_id, from_chapter, to_chapter),
    )
    if not row or not row["total"]:
        raise HTTPException(404, "Không có chương trong khoảng này.")
    chars = int(row["chars"] or 0)
    estimated_audio_minutes = round(chars / 750, 1)
    return {
        "total": int(row["total"]),
        "completed": int(row["completed"] or 0),
        "pending": int(row["total"] - (row["completed"] or 0)),
        "characters": chars,
        "estimated_audio_minutes": estimated_audio_minutes,
        "estimated_processing_minutes": round(estimated_audio_minutes * 1.1, 1),
    }


def _legacy_validated_job_payload(request: JobRequest) -> dict[str, Any]:
    payload = request.model_dump()
    payload["voice_name"] = unicodedata.normalize("NFC", payload["voice_name"]).strip()

    voice_name = payload["voice_name"]
    if is_custom_ref(voice_name):
        ctx = CustomVoiceContext.from_repository(custom_voice_repo)
        try:
            resolve_custom_ref(voice_name, ctx, repository=custom_voice_repo)
        except Exception as exc:
            raise ValueError(f"Giọng '{voice_name}' không khả dụng: {str(exc)}") from exc
    else:
        valid_voices = _preset_voice_ids()
        if voice_name not in valid_voices:
            raise ValueError(f"Giọng '{voice_name}' không tồn tại trong VieNeu.")

    if payload.get("casting_plan_id") is not None:
        validate_approved_plan(
            db,
            store,
            int(payload["casting_plan_id"]),
            _preset_voice_ids(),
            custom_voice_context=_build_custom_voice_context(),
        )
    return payload


def _validated_job_payload(request: JobRequest) -> dict[str, Any]:
    payload = request.model_dump()
    payload["voice_name"] = unicodedata.normalize("NFC", payload["voice_name"]).strip()
    voice_catalog = _load_voice_catalog()
    issue = inspect_voice_ref(
        payload["voice_name"],
        voice_catalog,
        chapter_id=None,
        chapter_number=(
            payload["from_chapter"]
            if payload["from_chapter"] == payload["to_chapter"]
            else None
        ),
        role="narrator",
    )
    if issue:
        raise VoiceEligibilityBlocked((issue,))
    payload["voice_catalog"] = voice_catalog
    return payload


@app.post("/api/jobs/prepare")
@_serialized_production_mutation
def prepare_job_route(request: JobRequest) -> dict[str, Any]:
    if prepare_runtime_integration.runtime_mode == PRODUCTION:
        raise HTTPException(409, {"code": "BATCH_PREPARE_API_REQUIRED"})
    if request.repair_mode != "off" and not settings.gemini_key():
        raise HTTPException(400, "Chưa có GEMINI_API_KEY hoặc gemini_api_key.txt.")
    try:
        payload = _validated_job_payload(request)
        return prepare_job(db, settings, store=store, **payload)
    except Exception as exc:
        raise _job_http_error(exc) from exc


@app.post("/api/jobs")
@_serialized_production_mutation
def submit_job(request: JobRequest) -> dict[str, Any]:
    if prepare_runtime_integration.runtime_mode == PRODUCTION:
        raise HTTPException(409, {"code": "START_RENDER_UNAVAILABLE"})
    if request.repair_mode != "off" and not settings.gemini_key():
        raise HTTPException(400, "Chưa có GEMINI_API_KEY hoặc gemini_api_key.txt.")
    try:
        payload = _validated_job_payload(request)
        result = create_job(db, settings, store=store, **payload)
        worker.wake()
        return result
        payload = request.model_dump()
        payload["voice_name"] = unicodedata.normalize("NFC", payload["voice_name"]).strip()

        # Validate voice reference (preset or custom logical reference)
        voice_name = payload["voice_name"]
        if is_custom_ref(voice_name):
            # Validate custom logical reference
            ctx = CustomVoiceContext.from_repository(custom_voice_repo)
            try:
                # This will raise if voice is inactive, missing, or has no preferred revision
                resolve_custom_ref(voice_name, ctx, repository=custom_voice_repo)
            except Exception as exc:
                raise ValueError(f"Giọng '{voice_name}' không khả dụng: {str(exc)}")
        else:
            # Validate preset voice
            valid_voices = _preset_voice_ids()
            if voice_name not in valid_voices:
                raise ValueError(f"Giọng '{voice_name}' không tồn tại trong VieNeu.")

        if payload.get("casting_plan_id") is not None:
            validate_approved_plan(
                db,
                store,
                int(payload["casting_plan_id"]),
                _preset_voice_ids(),
                custom_voice_context=_build_custom_voice_context(),
            )
        result = create_job(db, settings, store=store, **payload)
        worker.wake()
        return result
    except Exception as exc:
        raise _job_http_error(exc) from exc


@app.get("/api/jobs")
def list_jobs(limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """SELECT j.*,b.title AS book_title,
            (SELECT COUNT(*) FROM job_chapters jc WHERE jc.job_id=j.id AND jc.status='completed') AS actual_completed,
            (SELECT COUNT(*) FROM job_chapters jc WHERE jc.job_id=j.id AND jc.status IN ('failed','needs_review')) AS actual_failed,
            (SELECT COUNT(*) FROM segments s JOIN job_chapters jc ON jc.id=s.job_chapter_id WHERE jc.job_id=j.id) AS total_segments,
            (SELECT COUNT(*) FROM segments s JOIN job_chapters jc ON jc.id=s.job_chapter_id WHERE jc.job_id=j.id AND s.status='verified') AS completed_segments,
            (SELECT COUNT(*) FROM segments s JOIN job_chapters jc ON jc.id=s.job_chapter_id WHERE jc.job_id=j.id AND s.status IN ('failed','interrupted')) AS failed_segments,
            (SELECT COUNT(*) FROM segments s JOIN job_chapters jc ON jc.id=s.job_chapter_id WHERE jc.job_id=j.id AND s.status='pending') AS pending_segments
            FROM jobs j JOIN books b ON b.id=j.book_id ORDER BY j.id DESC LIMIT ?""",
        (limit,),
    )
    return annotate_job_rows(db, rows)


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: int) -> dict[str, Any]:
    job = db.fetch_one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job:
        raise HTTPException(404, "Không tìm thấy job.")
    chapters = db.fetch_all(
        """SELECT jc.*,c.chapter_number,c.title,
            (SELECT COUNT(*) FROM segments s WHERE s.job_chapter_id=jc.id) AS total_segments,
            (SELECT COUNT(*) FROM segments s WHERE s.job_chapter_id=jc.id AND s.status='verified') AS completed_segments,
            (SELECT COUNT(*) FROM segments s WHERE s.job_chapter_id=jc.id AND s.status IN ('failed','interrupted')) AS failed_segments,
            (SELECT COUNT(*) FROM segments s WHERE s.job_chapter_id=jc.id AND s.status='pending') AS pending_segments
            FROM job_chapters jc JOIN chapters c ON c.id=jc.chapter_id
            WHERE jc.job_id=? ORDER BY jc.sequence""",
        (job_id,),
    )
    job_row = annotate_job_rows(db, [dict(job)])[0]
    active_bindings = get_active_output_bindings(db, [row["chapter_id"] for row in chapters])
    chapter_rows: list[dict[str, Any]] = []
    for row in chapters:
        item = dict(row)
        binding = active_bindings.get(int(row["chapter_id"]), {})
        item["is_active_output"] = (
            binding.get("active_output_job_id") == int(job_id)
            and binding.get("active_output_job_chapter_id") == int(row["id"])
        )
        item["is_historical_output"] = bool(
            binding.get("active_output_artifact_id") and not item["is_active_output"]
        )
        item["active_output_artifact_id"] = binding.get("active_output_artifact_id")
        item["active_output_casting_plan_revision"] = binding.get("active_output_casting_plan_revision")
        chapter_rows.append(item)
    return {"job": job_row, "chapters": chapter_rows}


@app.post("/api/jobs/{job_id}/start")
@_serialized_production_mutation
def start_job(job_id: int) -> dict[str, Any]:
    if (
        prepare_runtime_integration.runtime_mode == PRODUCTION
        and not getattr(
            prepare_runtime_integration,
            "production_render_enabled",
            False,
        )
    ):
        raise HTTPException(409, {"code": "START_RENDER_UNAVAILABLE"})
    try:
        result = start_prepared_job(
            db,
            settings,
            job_id=job_id,
            voice_catalog=_load_voice_catalog(),
            store=store,
        )
    except Exception as exc:
        raise _job_http_error(exc) from exc
    worker.wake()
    return result


def _diagnostic_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DiagnosticNotFound):
        return HTTPException(404, str(exc))
    if isinstance(exc, RetryConflict):
        return HTTPException(409, str(exc))
    return HTTPException(400, str(exc))


@app.get("/api/diagnostics/jobs/{job_id}")
def job_diagnostics(job_id: int) -> dict[str, Any]:
    try:
        return get_job_diagnostics(db, job_id)
    except (DiagnosticNotFound, RetryConflict) as exc:
        raise _diagnostic_error(exc) from exc


@app.get("/api/diagnostics/job-chapters/{job_chapter_id}")
def job_chapter_diagnostics(job_chapter_id: int) -> dict[str, Any]:
    try:
        return get_job_chapter_diagnostics(db, store, job_chapter_id)
    except (DiagnosticNotFound, RetryConflict) as exc:
        raise _diagnostic_error(exc) from exc


@app.get("/api/diagnostics/segments/{segment_id}")
def segment_diagnostics(segment_id: int) -> dict[str, Any]:
    try:
        return get_segment_diagnostics(db, store, segment_id)
    except (DiagnosticNotFound, RetryConflict) as exc:
        raise _diagnostic_error(exc) from exc


@app.post("/api/job-chapters/{job_chapter_id}/retry")
@_serialized_production_mutation
def retry_chapter(job_chapter_id: int) -> dict[str, Any]:
    try:
        result = retry_job_chapter(db, job_chapter_id)
    except (DiagnosticNotFound, RetryConflict) as exc:
        raise _diagnostic_error(exc) from exc
    worker.wake()
    return {"ok": True, **result}


@app.post("/api/segments/{segment_id}/retry")
@_serialized_production_mutation
def retry_failed_segment(segment_id: int) -> dict[str, Any]:
    try:
        result = retry_segment(db, segment_id)
    except (DiagnosticNotFound, RetryConflict) as exc:
        raise _diagnostic_error(exc) from exc
    worker.wake()
    return {"ok": True, **result}


@app.post("/api/segments/{segment_id}/regenerate")
@_serialized_production_mutation
def regenerate_segment(segment_id: int) -> dict[str, Any]:
    """Generate candidate synthesis for verified segment."""
    from .segment_regeneration import RegenerationError, regenerate_verified_segment
    try:
        result = regenerate_verified_segment(db, store, tts_service, settings, segment_id)
        return {"ok": True, **result}
    except RegenerationError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs/{job_id}/repair-blocks")
@_serialized_production_mutation
def create_repair_block(job_id: int, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Generate a candidate audio repair block for adjacent verified segments."""
    from .audio_repair_blocks import AudioRepairBlockError, create_audio_repair_block_candidate
    first_segment_id = body.get("first_segment_id")
    last_segment_id = body.get("last_segment_id")
    if not first_segment_id or not last_segment_id:
        raise HTTPException(400, "first_segment_id and last_segment_id required")
    try:
        return create_audio_repair_block_candidate(
            db,
            store,
            tts_service,
            settings,
            job_id=job_id,
            first_segment_id=int(first_segment_id),
            last_segment_id=int(last_segment_id),
        )
    except AudioRepairBlockError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/job-chapters/{job_chapter_id}/repair-blocks")
def get_repair_blocks(job_chapter_id: int) -> dict[str, Any]:
    """List audio repair blocks for a JobChapter."""
    from .audio_repair_blocks import AudioRepairBlockError, list_audio_repair_blocks
    try:
        return list_audio_repair_blocks(db, job_chapter_id)
    except AudioRepairBlockError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/audio-repair-blocks/{repair_block_id}/reject")
@_serialized_production_mutation
def reject_repair_block(repair_block_id: int) -> dict[str, Any]:
    """Reject a candidate audio repair block without modifying active audio."""
    from .audio_repair_blocks import AudioRepairBlockError, reject_audio_repair_block_candidate
    try:
        return reject_audio_repair_block_candidate(db, repair_block_id)
    except AudioRepairBlockError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/audio-repair-blocks/{repair_block_id}/accept")
@_serialized_production_mutation
def accept_repair_block(repair_block_id: int) -> dict[str, Any]:
    """Accept a repair block and reassemble the same job with the candidate overlay."""
    from .audio_repair_blocks import AudioRepairBlockError, accept_audio_repair_block_candidate
    try:
        return accept_audio_repair_block_candidate(db, store, settings, repair_block_id)
    except AudioRepairBlockError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/audio-repair-blocks/{repair_block_id}/audio")
def get_repair_block_audio(repair_block_id: int) -> FileResponse:
    """Serve candidate audio for an audio repair block."""
    repair_block = db.fetch_one("SELECT * FROM audio_repair_blocks WHERE id=?", (repair_block_id,))
    if not repair_block:
        raise HTTPException(404, "Repair block not found")
    path = Path(repair_block["candidate_wav_path"])
    if not path.exists():
        raise HTTPException(404, "Repair block audio file not found")
    return FileResponse(path, media_type="audio/wav", filename=f"audio_repair_block_{repair_block_id}.wav")


@app.get("/api/audio-repair-blocks/{repair_block_id}/active-audio")
def get_repair_block_active_audio(repair_block_id: int) -> FileResponse:
    """Serve preview-only active range audio for repair-block A/B review."""
    from .audio_repair_blocks import AudioRepairBlockError, build_active_audio_preview

    try:
        path = build_active_audio_preview(db, settings, repair_block_id)
    except AudioRepairBlockError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not path.exists():
        raise HTTPException(404, "Active repair block preview not found")
    return FileResponse(path, media_type="audio/wav", filename=f"audio_repair_block_{repair_block_id}_active.wav")


@app.post("/api/segments/{segment_id}/accept-candidate")
@_serialized_production_mutation
def accept_candidate(segment_id: int, body: dict[str, int] = Body(...)) -> dict[str, Any]:
    """Accept candidate and rebuild chapter artifacts."""
    from .segment_regeneration import RegenerationError, accept_segment_candidate
    attempt_id = body.get("attempt_id")
    if not attempt_id:
        raise HTTPException(400, "attempt_id required")
    try:
        result = accept_segment_candidate(db, store, settings, segment_id, attempt_id)
        return {"ok": True, **result}
    except RegenerationError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/segments/{segment_id}/reject-candidate")
@_serialized_production_mutation
def reject_candidate(segment_id: int, body: dict[str, int] = Body(...)) -> dict[str, Any]:
    """Reject candidate and keep active segment unchanged."""
    from .segment_regeneration import RegenerationError, reject_segment_candidate
    attempt_id = body.get("attempt_id")
    if not attempt_id:
        raise HTTPException(400, "attempt_id required")
    try:
        result = reject_segment_candidate(db, segment_id, attempt_id)
        return {"ok": True, **result}
    except RegenerationError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/segments/{segment_id}/attempts")
def get_segment_attempts(segment_id: int) -> dict[str, Any]:
    """List all attempts for a segment."""
    from .segment_regeneration import RegenerationError, list_segment_attempts
    try:
        return list_segment_attempts(db, segment_id)
    except RegenerationError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/segments/{segment_id}/audio")
def get_segment_audio(segment_id: int) -> FileResponse:
    """Serve audio for current active segment."""
    segment = db.fetch_one("SELECT * FROM segments WHERE id=?", (segment_id,))
    if not segment:
        raise HTTPException(404, "Segment not found")

    if not segment["wav_path"]:
        raise HTTPException(404, "Segment has no audio")

    path = Path(segment["wav_path"])
    if not path.exists():
        raise HTTPException(404, "Audio file not found")

    return FileResponse(path, media_type="audio/wav", filename=f"segment_{segment_id}.wav")


@app.get("/api/segment-attempts/{attempt_id}/audio")
def get_attempt_audio(attempt_id: int) -> FileResponse:
    """Serve audio for a specific attempt (safe audio serving)."""
    attempt = db.fetch_one("SELECT * FROM segment_attempts WHERE id=?", (attempt_id,))
    if not attempt:
        raise HTTPException(404, "Attempt not found")

    path = Path(attempt["wav_path"])
    if not path.exists():
        raise HTTPException(404, "Audio file not found")

    return FileResponse(path, media_type="audio/wav", filename=f"attempt_{attempt_id}.wav")


@app.post("/api/jobs/{job_id}/{action}")
@_serialized_production_mutation
def job_action(job_id: int, action: str) -> dict[str, Any]:
    job = db.fetch_one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job:
        raise HTTPException(404, "Không tìm thấy job.")
    action_key = {
        "pause": "can_pause",
        "resume": "can_resume",
        "cancel": "can_cancel",
        "retry": "can_retry",
    }.get(action)
    if not action_key:
        raise HTTPException(400, "Invalid job action.")
    job_view = annotate_job_rows(db, [dict(job)])[0]
    if not job_view["actions"][action_key]:
        raise HTTPException(
            409,
            {
                "code": "JOB_ACTION_NOT_AVAILABLE",
                "message": f"Action {action} is not available for Job {job_id}.",
            },
        )
    now = utcnow()
    with db.connect() as connection:
        if action == "pause":
            connection.execute("UPDATE jobs SET pause_requested=1,updated_at=? WHERE id=?", (now, job_id))
        elif action == "resume":
            connection.execute(
                "UPDATE jobs SET pause_requested=0,cancel_requested=0,status='queued',updated_at=? WHERE id=?",
                (now, job_id),
            )
        elif action == "cancel":
            connection.execute("UPDATE jobs SET cancel_requested=1,updated_at=? WHERE id=?", (now, job_id))
            if job["status"] in {"prepared", "scheduled"}:
                connection.execute("UPDATE jobs SET status='cancelled',finished_at=? WHERE id=?", (now, job_id))
                connection.execute(
                    "UPDATE job_chapters SET status='cancelled',finished_at=? WHERE job_id=?",
                    (now, job_id),
                )
        elif action == "retry":
            connection.execute(
                "UPDATE job_chapters SET status='pending',error_message=NULL,finished_at=NULL WHERE job_id=? AND status IN ('failed','needs_review','interrupted')",
                (job_id,),
            )
            connection.execute(
                "UPDATE repair_blocks SET status='pending',attempt_count=0,error_message=NULL WHERE job_chapter_id IN (SELECT id FROM job_chapters WHERE job_id=?) AND status='failed'",
                (job_id,),
            )
            connection.execute(
                "UPDATE segments SET status='pending',attempt_count=0,error_message=NULL WHERE job_chapter_id IN (SELECT id FROM job_chapters WHERE job_id=?) AND status IN ('failed','pending','interrupted','running')",
                (job_id,),
            )
            connection.execute(
                "UPDATE jobs SET status='queued',pause_requested=0,cancel_requested=0,error_message=NULL,finished_at=NULL,updated_at=? WHERE id=?",
                (now, job_id),
            )
        else:
            raise HTTPException(400, "Hành động không hợp lệ.")
    db.audit(f"job_{action}_requested", job_id=job_id)
    worker.wake()
    return {"ok": True, "action": action}


@app.get("/api/artifacts/{artifact_id}/file")
def artifact_file(artifact_id: int):
    row = db.fetch_one(
        """
        SELECT a.*, c.book_id, c.chapter_number
        FROM artifacts a
        JOIN chapters c ON c.id=a.chapter_id
        WHERE a.id=? AND a.deleted_at IS NULL
        """,
        (artifact_id,),
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy artifact.")
    path = Path(row["path"])
    if not path.exists():
        raise HTTPException(404, "File artifact không còn tồn tại.")
    suffix = path.suffix.lower() or ".bin"
    download_name = (
        f"book-{int(row['book_id'])}-chapter-{int(row['chapter_number']):04d}"
        f"-artifact-{artifact_id}{suffix}"
    )
    return FileResponse(path, filename=download_name)


@app.post("/api/artifacts/{artifact_id}/video-export")
def artifact_video_export(artifact_id: int) -> dict[str, Any]:
    try:
        return create_video_export(db, settings, artifact_id)
    except VideoExportError as exc:
        status = 404 if exc.code in {"ARTIFACT_NOT_FOUND", "EXPORT_NOT_FOUND"} else 409
        raise HTTPException(status, {"code": exc.code, "message": str(exc)}) from exc


@app.get("/api/video-exports/{export_id}/file")
def video_export_file(export_id: str):
    try:
        path, manifest = load_video_export_file(db, settings, export_id)
    except VideoExportError as exc:
        status = 404 if exc.code == "EXPORT_NOT_FOUND" else 409
        raise HTTPException(status, {"code": exc.code, "message": str(exc)}) from exc
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=Path(str(manifest["path"])).name,
    )


def _last_cleanup_result() -> dict[str, Any] | None:
    report_root = settings.data_dir / "cleanup_reports"
    reports = sorted(report_root.glob("storage-cleanup-*.json"), reverse=True)
    for path in reports:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if payload.get("mode") != "execute":
            continue
        return {
            "executed_at": payload.get("executed_at"),
            "reclaimed_bytes": int(payload.get("reclaimed_bytes") or 0),
            "deleted_count": len(payload.get("deleted") or []),
        }
    return None


def _storage_report_payload(*, mode: str) -> dict[str, Any]:
    try:
        report = build_storage_report(
            settings.root,
            include_largest=False,
            live_runtime=True,
        )
    except (StorageCleanupError, OSError, ValueError) as exc:
        raise HTTPException(
            409,
            {"code": "STORAGE_REPORT_BLOCKED", "message": str(exc)},
        ) from exc
    report["mode"] = mode
    report["last_cleanup_result"] = _last_cleanup_result()
    report["cleanup_confirmation"] = STORAGE_CLEANUP_CONFIRMATION
    return report


@app.get("/api/storage/report")
def storage_report() -> dict[str, Any]:
    return _storage_report_payload(mode="report")


@app.post("/api/storage/dry-run")
def storage_dry_run() -> dict[str, Any]:
    return _storage_report_payload(mode="dry_run")


@app.post("/api/storage/cleanup")
@_serialized_production_mutation
def storage_cleanup(request: StorageCleanupRequest) -> dict[str, Any]:
    try:
        result = execute_cleanup(
            settings.root,
            confirmation=request.confirmation,
            allow_running_runtime=True,
        )
    except StorageCleanupError as exc:
        raise HTTPException(
            409,
            {"code": "STORAGE_CLEANUP_BLOCKED", "message": str(exc)},
        ) from exc
    return {
        "mode": result["mode"],
        "executed_at": result["executed_at"],
        "reclaimed_bytes": result["reclaimed_bytes"],
        "deleted": result["deleted"],
        "storage_after_bytes": result["storage_after_bytes"],
    }


def _signal_supervised_restart() -> None:
    try:
        os.kill(os.getpid(), signal.SIGINT)
    except (OSError, ValueError):
        os._exit(75)


@app.post("/api/runtime/restart")
def restart_runtime(request: RuntimeRestartRequest) -> dict[str, Any]:
    signal_value = os.environ.get("STORY_AUDIO_RESTART_SIGNAL", "").strip()
    if os.environ.get("STORY_AUDIO_SUPERVISED") != "1" or not signal_value:
        raise HTTPException(
            409,
            {
                "code": "SUPERVISED_RESTART_UNAVAILABLE",
                "message": "Restart is available only from the durable launcher.",
            },
        )
    signal_path = Path(signal_value).resolve(strict=False)
    runtime_root = (settings.data_dir / "runtime").resolve(strict=False)
    try:
        signal_path.relative_to(runtime_root)
    except ValueError as exc:
        raise HTTPException(
            409,
            {
                "code": "RESTART_SIGNAL_PATH_UNSAFE",
                "message": "The restart signal path is outside managed runtime storage.",
            },
        ) from exc
    signal_path.parent.mkdir(parents=True, exist_ok=True)
    signal_path.write_text("restart\n", encoding="ascii")
    threading.Timer(0.75, _signal_supervised_restart).start()
    return {"ok": True, "state": "restarting"}


@app.post("/api/maintenance/cleanup")
def cleanup_segments() -> dict[str, int]:
    return worker.cleanup_expired_segments()


@app.post("/api/maintenance/preview-cache")
def cleanup_preview_cache() -> dict[str, int]:
    return voice_previews.cleanup()


# Custom Voice API Endpoints

@app.post("/api/custom-voices")
def create_custom_voice(
    display_name: str = Body(..., min_length=1, max_length=120),
    description: str | None = Body(None),
) -> dict[str, Any]:
    return create_custom_voice_handler(custom_voice_repo, display_name, description)


@app.get("/api/custom-voices")
def list_custom_voices(active_only: bool = Query(False)) -> list[dict[str, Any]]:
    return list_custom_voices_handler(custom_voice_repo, active_only)


@app.get("/api/custom-voices/{voice_id}")
def get_custom_voice(voice_id: int) -> dict[str, Any]:
    return get_custom_voice_handler(custom_voice_repo, voice_id)


@app.patch("/api/custom-voices/{voice_id}/deactivate")
def deactivate_custom_voice(voice_id: int) -> dict[str, Any]:
    return deactivate_custom_voice_handler(custom_voice_repo, voice_id)


@app.patch("/api/custom-voices/{voice_id}/reactivate")
def reactivate_custom_voice(voice_id: int) -> dict[str, Any]:
    return reactivate_custom_voice_handler(custom_voice_repo, voice_id)


@app.post("/api/custom-voices/{voice_id}/revisions")
async def create_custom_voice_revision(
    voice_id: int,
    audio: UploadFile = File(...),
    transcript: str = Form(...),
) -> dict[str, Any]:
    return create_custom_voice_revision_handler(custom_voice_repo, voice_id, audio, transcript)


@app.get("/api/custom-voices/{voice_id}/revisions")
def list_custom_voice_revisions(voice_id: int) -> list[dict[str, Any]]:
    return list_custom_voice_revisions_handler(custom_voice_repo, voice_id)


@app.get("/api/custom-voice-revisions/{revision_id}")
def get_custom_voice_revision(revision_id: int) -> dict[str, Any]:
    return get_custom_voice_revision_handler(custom_voice_repo, revision_id)


@app.patch("/api/custom-voices/{voice_id}/preferred-revision")
def set_preferred_synthesis_revision(
    voice_id: int,
    revision_id: int | None = Body(None, embed=True),
) -> dict[str, Any]:
    """Set or clear the preferred synthesis revision for a custom voice."""
    return set_preferred_synthesis_revision_handler(custom_voice_repo, voice_id, revision_id)


@app.get("/api/custom-voice-revisions/{revision_id}/audio")
def get_custom_voice_revision_audio(revision_id: int):
    """Serve the reference audio file for a custom voice revision."""
    from .custom_voice import CustomVoiceRevisionNotFoundError
    from .files import sha256_file

    try:
        revision = custom_voice_repo.get_revision(revision_id)
    except CustomVoiceRevisionNotFoundError:
        raise HTTPException(404, "Custom voice revision not found")

    # Resolve audio path
    try:
        audio_path = store.absolute(revision.audio_storage_key)
    except ValueError:
        raise HTTPException(404, "Reference audio path is invalid")

    if not audio_path.exists() or not audio_path.is_file():
        raise HTTPException(404, "Reference audio file not found")

    # Verify SHA-256 integrity before serving
    computed_sha = sha256_file(audio_path)
    if computed_sha != revision.audio_sha256:
        raise HTTPException(409, "Reference audio integrity check failed")

    # Determine content type from audio format
    content_type = "audio/wav" if revision.audio_format == "wav" else "audio/mpeg"

    return FileResponse(
        audio_path,
        media_type=content_type,
        filename=f"revision_{revision_id}.{revision.audio_format}"
    )


UI_DIR = settings.root / "ui"
app.mount("/assets", StaticFiles(directory=UI_DIR), name="assets")


@app.get("/", include_in_schema=False)
def index():
    response = FileResponse(UI_DIR / "index.html")
    runtime_operator_session.apply_cookie(response)
    return response
