from __future__ import annotations

import json
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .casting import (
    CastingError,
    approve_plan,
    casting_context,
    create_casting_draft,
    create_character,
    deactivate_character,
    list_characters,
    update_character,
    validate_approved_plan,
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
from .pipeline import PipelineWorker, create_job
from .storage import ContentStore
from .tts import tts_service
from .text_diff import TextDiffError, build_revision_diff, list_revision_metadata
from .voice_preview import VoicePreviewService


settings.ensure_dirs()
db = Database(settings.db_path)
store = ContentStore(settings)
worker = PipelineWorker(db, store, tts_service, settings)
voice_previews = VoicePreviewService(tts_service, settings)


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
    voice_id: str = Field(min_length=1, max_length=200)


class CharacterCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    default_voice_id: str = Field(min_length=1, max_length=200)


class CharacterUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    default_voice_id: str | None = Field(default=None, min_length=1, max_length=200)


class CastingAssignment(BaseModel):
    utterance_id: str
    role: str
    character_id: int | None = None


class CastingDraftRequest(BaseModel):
    text_revision_id: int
    narrator_voice_id: str
    assignments: list[CastingAssignment] = Field(default_factory=list)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.initialize()
    worker.start()
    yield
    worker.stop()


app = FastAPI(title="Story Audio", version="0.1.0", lifespan=lifespan)


def as_dict(row) -> dict[str, Any]:
    return dict(row) if row is not None else {}


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
    return {"total": total, "items": [dict(row) for row in rows]}


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


@app.post("/api/books/{book_id}/characters")
def add_character(book_id: int, request: CharacterCreateRequest) -> dict[str, Any]:
    try:
        if request.default_voice_id not in _preset_voice_ids():
            raise CastingError("Preset voice does not exist")
        return create_character(db, book_id, request.display_name, request.default_voice_id)
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
        )
    except CastingError as exc:
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
        return casting_context(db, store, chapter_id)
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
        )
    except CastingError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/casting/{casting_plan_id}/approve")
def approve_casting(casting_plan_id: int) -> dict[str, Any]:
    try:
        result = approve_plan(db, store, casting_plan_id)
        validate_approved_plan(db, store, casting_plan_id, _preset_voice_ids())
        return result
    except CastingError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/voice-previews")
def create_voice_preview(request: VoicePreviewRequest) -> dict[str, Any]:
    try:
        valid_voices = {item["id"] for item in tts_service.voices()}
        if request.voice_id not in valid_voices:
            raise ValueError(f"Giọng '{request.voice_id}' không tồn tại trong VieNeu.")
        result = voice_previews.create(request.voice_id)
        result["audio_url"] = f"/api/voice-previews/{result['cache_key']}/file"
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Không tạo được voice preview: {exc}") from exc


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
        valid_voices = _preset_voice_ids()
        if payload["voice_name"] not in valid_voices:
            raise ValueError(f"Giọng '{payload['voice_name']}' không tồn tại trong VieNeu.")
        if payload.get("casting_plan_id") is not None:
            validate_approved_plan(db, store, int(payload["casting_plan_id"]), valid_voices)
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
    return [dict(row) for row in rows]


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
    return {"job": dict(job), "chapters": [dict(row) for row in chapters]}


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


UI_DIR = settings.root / "ui"
app.mount("/assets", StaticFiles(directory=UI_DIR), name="assets")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(UI_DIR / "index.html")
