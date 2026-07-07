from __future__ import annotations

import json
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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
from .active_output import annotate_chapter_rows, annotate_job_rows, get_active_output_bindings
from .custom_voice import CustomVoiceRepository
from .custom_voice_api import (
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
from .db import Database, utcnow
from .diagnostics import (
    DiagnosticNotFound,
    RetryConflict,
    get_job_chapter_diagnostics,
    get_job_diagnostics,
    get_segment_diagnostics,
    retry_job_chapter,
    retry_segment,
)
from .epub import import_epub
from .gemini import GeminiSpeakerAssignmentError
from .pipeline import PipelineWorker, create_job
from .storage import ContentStore
from .speaker_assignment import (
    SpeakerAssignmentError,
    generate_speaker_assignment_draft,
    get_speaker_assignment_draft,
)
from .speaker_review import (
    SpeakerReviewConflict,
    SpeakerReviewError,
    approve_speaker_review,
    get_speaker_review_draft,
    list_speaker_review_drafts,
)
from .tts import tts_service
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
from .voice_ref import CustomVoiceContext, is_custom_ref, resolve_custom_ref


settings.ensure_dirs()
db = Database(settings.db_path)
store = ContentStore(settings)
custom_voice_repo = CustomVoiceRepository(db, store)
worker = PipelineWorker(db, store, tts_service, settings)
voice_previews = VoicePreviewService(
    tts_service, settings, custom_voice_repo=custom_voice_repo, store=store
)


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


class VoicePreviewRequest(BaseModel):
    voice_id: str | None = Field(default=None, min_length=1, max_length=200)
    custom_voice_revision_id: int | None = Field(default=None, gt=0)
    preview_text: str | None = Field(default=None, max_length=500)


class CharacterCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    default_voice_id: str | None = Field(default=None, max_length=200)
    voice_override_id: str | None = Field(default=None, max_length=200)
    gender: str | None = None


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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.initialize()
    worker.start()
    yield
    worker.stop()


app = FastAPI(title="Story Audio", version="0.1.0", lifespan=lifespan)


def as_dict(row) -> dict[str, Any]:
    return dict(row) if row is not None else {}


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
    }


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
    revision_data = []
    for row in revisions:
        item = dict(row)
        item["text"] = store.read_text(row["content_path"])
        revision_data.append(item)
    return {
        "chapter": dict(chapter),
        "revisions": revision_data,
        "qa_issues": [dict(row) for row in issues],
        "audio_artifact": dict(artifact) if artifact else None,
        "active_output": active_output,
    }


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


@app.get("/api/voices")
def list_voices() -> dict[str, Any]:
    try:
        return {"items": tts_service.voices(), "status": tts_service.status}
    except Exception as exc:
        raise HTTPException(503, f"Không tải được VieNeu: {exc}") from exc


def _preset_voice_ids() -> set[str]:
    return {item["id"] for item in tts_service.voices()}


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
        if voice_id is not None and voice_id not in _preset_voice_ids():
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
    return {
        "configured": True,
        "profile": profile,
        **profile,
        **profile_validation(profile, _preset_voice_ids()),
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


@app.post("/api/casting/{casting_plan_id}/approve")
def approve_casting(casting_plan_id: int) -> dict[str, Any]:
    try:
        result = approve_plan(db, store, casting_plan_id)
        validate_approved_plan(
            db, store, casting_plan_id, _preset_voice_ids(), custom_voice_context=_build_custom_voice_context()
        )
        return result
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


@app.post("/api/jobs")
def submit_job(request: JobRequest) -> dict[str, Any]:
    if request.repair_mode != "off" and not settings.gemini_key():
        raise HTTPException(400, "Chưa có GEMINI_API_KEY hoặc gemini_api_key.txt.")
    try:
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
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/jobs")
def list_jobs(limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """SELECT j.*,b.title AS book_title,
            (SELECT COUNT(*) FROM job_chapters jc WHERE jc.job_id=j.id AND jc.status='completed') AS actual_completed,
            (SELECT COUNT(*) FROM job_chapters jc WHERE jc.job_id=j.id AND jc.status IN ('failed','needs_review')) AS actual_failed,
            (SELECT COUNT(*) FROM segments s JOIN job_chapters jc ON jc.id=s.job_chapter_id WHERE jc.job_id=j.id) AS total_segments,
            (SELECT COUNT(*) FROM segments s JOIN job_chapters jc ON jc.id=s.job_chapter_id WHERE jc.job_id=j.id AND s.status='verified') AS completed_segments
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
            (SELECT COUNT(*) FROM segments s WHERE s.job_chapter_id=jc.id AND s.status='verified') AS completed_segments
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
def retry_chapter(job_chapter_id: int) -> dict[str, Any]:
    try:
        result = retry_job_chapter(db, job_chapter_id)
    except (DiagnosticNotFound, RetryConflict) as exc:
        raise _diagnostic_error(exc) from exc
    worker.wake()
    return {"ok": True, **result}


@app.post("/api/segments/{segment_id}/retry")
def retry_failed_segment(segment_id: int) -> dict[str, Any]:
    try:
        result = retry_segment(db, segment_id)
    except (DiagnosticNotFound, RetryConflict) as exc:
        raise _diagnostic_error(exc) from exc
    worker.wake()
    return {"ok": True, **result}


@app.post("/api/segments/{segment_id}/regenerate")
def regenerate_segment(segment_id: int) -> dict[str, Any]:
    """Generate candidate synthesis for verified segment."""
    from .segment_regeneration import RegenerationError, regenerate_verified_segment
    try:
        result = regenerate_verified_segment(db, store, tts_service, settings, segment_id)
        return {"ok": True, **result}
    except RegenerationError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/segments/{segment_id}/accept-candidate")
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
def job_action(job_id: int, action: str) -> dict[str, Any]:
    job = db.fetch_one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job:
        raise HTTPException(404, "Không tìm thấy job.")
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
            if job["status"] == "scheduled":
                connection.execute("UPDATE jobs SET status='cancelled',finished_at=? WHERE id=?", (now, job_id))
                connection.execute(
                    "UPDATE job_chapters SET status='cancelled',finished_at=? WHERE job_id=?",
                    (now, job_id),
                )
        elif action == "retry":
            connection.execute(
                "UPDATE job_chapters SET status='pending',error_message=NULL,finished_at=NULL WHERE job_id=? AND status IN ('failed','needs_review')",
                (job_id,),
            )
            connection.execute(
                "UPDATE repair_blocks SET status='pending',attempt_count=0,error_message=NULL WHERE job_chapter_id IN (SELECT id FROM job_chapters WHERE job_id=?) AND status='failed'",
                (job_id,),
            )
            connection.execute(
                "UPDATE segments SET status='pending',attempt_count=0,error_message=NULL WHERE job_chapter_id IN (SELECT id FROM job_chapters WHERE job_id=?) AND status IN ('failed','pending')",
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
    row = db.fetch_one("SELECT * FROM artifacts WHERE id=? AND deleted_at IS NULL", (artifact_id,))
    if not row:
        raise HTTPException(404, "Không tìm thấy artifact.")
    path = Path(row["path"])
    if not path.exists():
        raise HTTPException(404, "File artifact không còn tồn tại.")
    return FileResponse(path, filename=path.name)


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
    return FileResponse(UI_DIR / "index.html")
