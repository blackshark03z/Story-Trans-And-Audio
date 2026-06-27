from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import Database, utcnow
from .files import sha256_file
from .storage import ContentStore


class DiagnosticNotFound(LookupError):
    pass


class RetryConflict(RuntimeError):
    pass


ACTIVE_JOB_STATUSES = {"queued", "running", "repairing", "synthesizing", "assembling"}


def _json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _content_path(store: ContentStore, path: str | None) -> Path | None:
    if not path:
        return None
    try:
        return store.absolute(path)
    except ValueError:
        return None


def _preview(path: Path | None, limit: int = 220) -> str:
    if not path:
        return ""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""
    return text if len(text) <= limit else f"{text[:limit].rstrip()}…"


def _file_details(path: str | None, expected_sha256: str | None = None) -> dict[str, Any]:
    file_path = Path(path) if path else None
    exists = bool(file_path and file_path.is_file())
    details: dict[str, Any] = {
        "filename": file_path.name if file_path else None,
        "file_exists": exists,
        "actual_size_bytes": file_path.stat().st_size if exists else None,
    }
    if expected_sha256 is not None:
        details["hash_matches"] = sha256_file(file_path) == expected_sha256 if exists else False
    return details


def get_job_diagnostics(db: Database, job_id: int) -> dict[str, Any]:
    job = db.fetch_one(
        """
        SELECT j.*, b.title AS book_title
        FROM jobs j JOIN books b ON b.id = j.book_id
        WHERE j.id = ?
        """,
        (job_id,),
    )
    if not job:
        raise DiagnosticNotFound(f"Job {job_id} not found")

    chapters = db.fetch_all(
        """
        SELECT jc.id AS job_chapter_id, jc.chapter_id, jc.sequence, jc.status,
               jc.error_message, jc.started_at, jc.finished_at,
               c.chapter_number, c.title,
               (SELECT COUNT(*) FROM repair_blocks rb WHERE rb.job_chapter_id = jc.id) AS repair_total,
               (SELECT COUNT(*) FROM repair_blocks rb WHERE rb.job_chapter_id = jc.id AND rb.status = 'failed') AS repair_failed,
               (SELECT COUNT(*) FROM segments s WHERE s.job_chapter_id = jc.id) AS segment_total,
               (SELECT COUNT(*) FROM segments s WHERE s.job_chapter_id = jc.id AND s.status = 'verified') AS segment_verified,
               (SELECT COUNT(*) FROM segments s WHERE s.job_chapter_id = jc.id AND s.status = 'failed') AS segment_failed,
               (SELECT COUNT(*) FROM artifacts a WHERE a.job_chapter_id = jc.id AND a.status = 'active') AS artifact_active
        FROM job_chapters jc JOIN chapters c ON c.id = jc.chapter_id
        WHERE jc.job_id = ? ORDER BY jc.sequence
        """,
        (job_id,),
    )
    events = [dict(row) for row in db.fetch_all(
        """
        SELECT event_code, details_json, created_at
        FROM audit_events WHERE job_id = ? ORDER BY id DESC LIMIT 30
        """,
        (job_id,),
    )]
    for event in events:
        event["details"] = _json(event.pop("details_json", None), {})

    status_counts: dict[str, int] = {}
    for chapter in chapters:
        status = chapter["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    result = dict(job)
    result["settings"] = _json(result.pop("settings_json", None), {})
    return {
        "job": result,
        "summary": {
            "chapter_total": len(chapters),
            "chapter_status_counts": status_counts,
            "segment_total": sum(row["segment_total"] for row in chapters),
            "segment_verified": sum(row["segment_verified"] for row in chapters),
            "segment_failed": sum(row["segment_failed"] for row in chapters),
            "repair_failed": sum(row["repair_failed"] for row in chapters),
        },
        "chapters": [dict(row) for row in chapters],
        "events": events,
    }


def get_job_chapter_diagnostics(
    db: Database, store: ContentStore, job_chapter_id: int
) -> dict[str, Any]:
    chapter_row = db.fetch_one(
        """
        SELECT jc.id AS job_chapter_id, jc.job_id, jc.chapter_id, jc.sequence,
               jc.status, jc.error_message, jc.started_at, jc.finished_at,
               jc.text_revision_id, c.chapter_number, c.title,
               j.status AS job_status, b.title AS book_title
        FROM job_chapters jc
        JOIN chapters c ON c.id = jc.chapter_id
        JOIN jobs j ON j.id = jc.job_id
        JOIN books b ON b.id = j.book_id
        WHERE jc.id = ?
        """,
        (job_chapter_id,),
    )
    if not chapter_row:
        raise DiagnosticNotFound(f"Job chapter {job_chapter_id} not found")
    chapter = dict(chapter_row)

    repair_blocks = [dict(row) for row in db.fetch_all(
        """
        SELECT id, block_index, status, attempt_count, error_message, model_id,
               prompt_version, source_sha256, lexical_sha256, verified_at,
               source_path, repaired_path
        FROM repair_blocks WHERE job_chapter_id = ? ORDER BY block_index
        """,
        (job_chapter_id,),
    )]
    for block in repair_blocks:
        source_path = _content_path(store, block.pop("source_path", None))
        repaired_path = _content_path(store, block.pop("repaired_path", None))
        block["source_file_exists"] = bool(source_path and source_path.is_file())
        block["repaired_file_exists"] = bool(repaired_path and repaired_path.is_file())

    segments = [dict(row) for row in db.fetch_all(
        """
        SELECT id, segment_index, status, attempt_count, error_message, duration_ms,
               text_sha256, audio_sha256, text_path, wav_path, created_at, verified_at
        FROM segments WHERE job_chapter_id = ? ORDER BY segment_index
        """,
        (job_chapter_id,),
    )]
    for segment in segments:
        text_path = segment.pop("text_path", None)
        wav_path = segment.pop("wav_path", None)
        segment["text_preview"] = _preview(_content_path(store, text_path))
        segment.update(_file_details(wav_path))

    artifacts = [dict(row) for row in db.fetch_all(
        """
        SELECT id, artifact_type, status, sha256, size_bytes, duration_ms,
               created_at, verified_at, path
        FROM artifacts WHERE job_chapter_id = ? ORDER BY id DESC
        """,
        (job_chapter_id,),
    )]
    for artifact in artifacts:
        path = artifact.pop("path", None)
        artifact.update(_file_details(path, artifact["sha256"]))

    revision = None
    if chapter["text_revision_id"]:
        revision_row = db.fetch_one(
            """
            SELECT id, kind, content_sha256, lexical_sha256, char_count,
                   status, processor_version, created_at
            FROM text_revisions WHERE id = ?
            """,
            (chapter["text_revision_id"],),
        )
        revision = dict(revision_row) if revision_row else None

    return {
        "chapter": chapter,
        "text_revision": revision,
        "repair_blocks": repair_blocks,
        "segments": segments,
        "artifacts": artifacts,
    }


def get_segment_diagnostics(db: Database, store: ContentStore, segment_id: int) -> dict[str, Any]:
    segment_row = db.fetch_one(
        """
        SELECT s.*, jc.job_id, jc.status AS job_chapter_status,
               c.chapter_number, c.title AS chapter_title
        FROM segments s
        JOIN job_chapters jc ON jc.id = s.job_chapter_id
        JOIN chapters c ON c.id = jc.chapter_id
        WHERE s.id = ?
        """,
        (segment_id,),
    )
    if not segment_row:
        raise DiagnosticNotFound(f"Segment {segment_id} not found")
    segment = dict(segment_row)
    text_path = segment.pop("text_path", None)
    wav_path = segment.pop("wav_path", None)
    resolved_text_path = _content_path(store, text_path)
    segment["text_preview"] = _preview(resolved_text_path, 500)
    segment["text_file"] = _file_details(
        str(resolved_text_path) if resolved_text_path else None, segment["text_sha256"]
    )
    segment["audio_file"] = _file_details(wav_path, segment["audio_sha256"])
    return segment


def _ensure_job_idle(status: str) -> None:
    if status in ACTIVE_JOB_STATUSES:
        raise RetryConflict("Job is currently active; pause or wait before retrying")


def retry_job_chapter(db: Database, job_chapter_id: int) -> dict[str, int]:
    row = db.fetch_one(
        """
        SELECT jc.status, jc.job_id, j.status AS job_status
        FROM job_chapters jc JOIN jobs j ON j.id = jc.job_id WHERE jc.id = ?
        """,
        (job_chapter_id,),
    )
    if not row:
        raise DiagnosticNotFound(f"Job chapter {job_chapter_id} not found")
    _ensure_job_idle(row["job_status"])
    if row["status"] not in {"failed", "needs_review", "cancelled", "interrupted"}:
        raise RetryConflict(f"Chapter status '{row['status']}' is not retryable")

    now = utcnow()
    with db.transaction() as connection:
        verified = connection.execute(
            "SELECT COUNT(*) FROM segments WHERE job_chapter_id = ? AND status = 'verified'",
            (job_chapter_id,),
        ).fetchone()[0]
        reset_segments = connection.execute(
            """
            UPDATE segments SET status = 'pending', attempt_count = 0,
                   error_message = NULL,
                   wav_path = NULL, audio_sha256 = NULL, duration_ms = NULL, verified_at = NULL
            WHERE job_chapter_id = ? AND status IN ('failed', 'pending', 'interrupted')
            """,
            (job_chapter_id,),
        ).rowcount
        connection.execute(
            """
            UPDATE repair_blocks SET status = 'pending', attempt_count = 0,
                   error_message = NULL
            WHERE job_chapter_id = ? AND status IN ('failed', 'pending')
            """,
            (job_chapter_id,),
        )
        connection.execute(
            """
            UPDATE job_chapters SET status = 'pending', error_message = NULL,
                   finished_at = NULL WHERE id = ?
            """,
            (job_chapter_id,),
        )
        connection.execute(
            """
            UPDATE jobs SET status = 'queued', pause_requested = 0, cancel_requested = 0,
                   error_message = NULL, finished_at = NULL, updated_at = ? WHERE id = ?
            """,
            (now, row["job_id"]),
        )
    db.audit(
        "job_chapter_retry_requested",
        job_id=row["job_id"],
        details={
            "job_chapter_id": job_chapter_id,
            "verified_segments_reused": verified,
            "segments_reset": reset_segments,
        },
    )
    return {"verified_segments_reused": verified, "segments_reset": reset_segments}


def retry_segment(db: Database, segment_id: int) -> dict[str, int]:
    row = db.fetch_one(
        """
        SELECT s.status, s.job_chapter_id, jc.job_id, jc.status AS chapter_status,
               j.status AS job_status
        FROM segments s
        JOIN job_chapters jc ON jc.id = s.job_chapter_id
        JOIN jobs j ON j.id = jc.job_id
        WHERE s.id = ?
        """,
        (segment_id,),
    )
    if not row:
        raise DiagnosticNotFound(f"Segment {segment_id} not found")
    _ensure_job_idle(row["job_status"])
    if row["status"] == "verified":
        raise RetryConflict("Verified segments are immutable and cannot be retried")
    if row["status"] not in {"failed", "interrupted"}:
        raise RetryConflict(f"Segment status '{row['status']}' is not retryable")

    now = utcnow()
    with db.transaction() as connection:
        connection.execute(
            """
            UPDATE segments SET status = 'pending', attempt_count = 0,
                   error_message = NULL,
                   wav_path = NULL, audio_sha256 = NULL, duration_ms = NULL, verified_at = NULL
            WHERE id = ?
            """,
            (segment_id,),
        )
        connection.execute(
            """
            UPDATE job_chapters SET status = 'pending', error_message = NULL,
                   finished_at = NULL WHERE id = ?
            """,
            (row["job_chapter_id"],),
        )
        connection.execute(
            """
            UPDATE jobs SET status = 'queued', pause_requested = 0, cancel_requested = 0,
                   error_message = NULL, finished_at = NULL, updated_at = ? WHERE id = ?
            """,
            (now, row["job_id"]),
        )
    db.audit(
        "segment_retry_requested",
        job_id=row["job_id"],
        details={"segment_id": segment_id, "job_chapter_id": row["job_chapter_id"]},
    )
    return {"segment_id": segment_id}
