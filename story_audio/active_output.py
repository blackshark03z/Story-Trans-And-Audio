from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from .db import Database


def _placeholders(count: int) -> str:
    return ",".join("?" for _ in range(count))


def get_active_output_bindings(
    db: Database, chapter_ids: Iterable[int]
) -> dict[int, dict[str, Any]]:
    chapter_id_list = [int(chapter_id) for chapter_id in chapter_ids]
    if not chapter_id_list:
        return {}
    rows = db.fetch_all(
        f"""
        SELECT c.id AS chapter_id,
               c.active_audio_artifact_id,
               a.id AS artifact_id,
               a.job_chapter_id,
               a.artifact_type,
               jc.job_id AS active_job_id,
               jc.status AS active_job_chapter_status,
               jc.casting_plan_id AS active_casting_plan_id,
               cp.plan_revision AS active_casting_plan_revision
        FROM chapters c
        LEFT JOIN artifacts a
               ON a.id = c.active_audio_artifact_id AND a.deleted_at IS NULL
        LEFT JOIN job_chapters jc ON jc.id = a.job_chapter_id
        LEFT JOIN casting_plans cp ON cp.id = jc.casting_plan_id
        WHERE c.id IN ({_placeholders(len(chapter_id_list))})
        """,
        tuple(chapter_id_list),
    )
    bindings: dict[int, dict[str, Any]] = {}
    for row in rows:
        artifact_id = row["artifact_id"]
        job_id = row["active_job_id"]
        job_chapter_id = row["job_chapter_id"]
        bindings[int(row["chapter_id"])] = {
            "chapter_id": int(row["chapter_id"]),
            "active_audio_artifact_id": int(row["active_audio_artifact_id"]) if row["active_audio_artifact_id"] else None,
            "active_output_artifact_id": int(artifact_id) if artifact_id else None,
            "active_output_job_id": int(job_id) if job_id else None,
            "active_output_job_chapter_id": int(job_chapter_id) if job_chapter_id else None,
            "active_output_job_chapter_status": row["active_job_chapter_status"],
            "active_output_casting_plan_id": int(row["active_casting_plan_id"]) if row["active_casting_plan_id"] else None,
            "active_output_casting_plan_revision": int(row["active_casting_plan_revision"]) if row["active_casting_plan_revision"] else None,
            "active_output_artifact_type": row["artifact_type"],
            "has_active_audio": bool(artifact_id),
            "active_output_has_trustworthy_binding": bool(artifact_id and job_id and job_chapter_id),
            "active_output_source": "artifact_binding" if artifact_id else None,
        }
    return bindings


def annotate_chapter_rows(
    db: Database, rows: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    chapter_rows = [dict(row) for row in rows]
    bindings = get_active_output_bindings(db, [row["id"] for row in chapter_rows])
    for row in chapter_rows:
        row.update(bindings.get(int(row["id"]), {
            "chapter_id": int(row["id"]),
            "active_output_artifact_id": None,
            "active_output_job_id": None,
            "active_output_job_chapter_id": None,
            "active_output_job_chapter_status": None,
            "active_output_casting_plan_id": None,
            "active_output_casting_plan_revision": None,
            "active_output_artifact_type": None,
            "has_active_audio": False,
            "active_output_has_trustworthy_binding": False,
            "active_output_source": None,
        }))
    return chapter_rows


def annotate_job_rows(
    db: Database, rows: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    job_rows = [dict(row) for row in rows]
    job_ids = [int(row["id"]) for row in job_rows]
    if not job_ids:
        return job_rows
    active_rows = db.fetch_all(
        f"""
        SELECT jc.job_id,
               c.id AS chapter_id,
               c.chapter_number,
               c.title AS chapter_title,
               c.active_audio_artifact_id,
               a.id AS artifact_id,
               jc.id AS job_chapter_id,
               jc.casting_plan_id,
               cp.plan_revision AS casting_plan_revision
        FROM chapters c
        JOIN artifacts a
             ON a.id = c.active_audio_artifact_id AND a.deleted_at IS NULL
        JOIN job_chapters jc ON jc.id = a.job_chapter_id
        LEFT JOIN casting_plans cp ON cp.id = jc.casting_plan_id
        WHERE jc.job_id IN ({_placeholders(len(job_ids))})
        ORDER BY jc.job_id, c.chapter_number
        """,
        tuple(job_ids),
    )
    by_job: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in active_rows:
        by_job[int(row["job_id"])].append({
            "chapter_id": int(row["chapter_id"]),
            "chapter_number": int(row["chapter_number"]),
            "chapter_title": row["chapter_title"],
            "active_audio_artifact_id": int(row["active_audio_artifact_id"]) if row["active_audio_artifact_id"] else None,
            "active_output_artifact_id": int(row["artifact_id"]) if row["artifact_id"] else None,
            "active_output_job_chapter_id": int(row["job_chapter_id"]),
            "active_output_casting_plan_id": int(row["casting_plan_id"]) if row["casting_plan_id"] else None,
            "active_output_casting_plan_revision": int(row["casting_plan_revision"]) if row["casting_plan_revision"] else None,
        })
    for row in job_rows:
        active_chapters = by_job.get(int(row["id"]), [])
        row["active_output_chapters"] = active_chapters
        row["active_output_chapter_count"] = len(active_chapters)
        row["is_active_output"] = bool(active_chapters)
        row["is_historical_output"] = row.get("status") in {"completed", "completed_with_errors"} and not active_chapters
    return job_rows
