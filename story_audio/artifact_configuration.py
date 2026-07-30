"""Read immutable render configuration recorded with an audio artifact."""

from __future__ import annotations

import json
from typing import Any

from .db import Database


def _object(value: object) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _provenance(utterance: dict[str, Any]) -> str:
    source = str(utterance.get("resolution_source") or "").strip()
    return {
        "narrator": "book_narrator_snapshot",
        "character": "casting_plan_snapshot",
        "book_male": "book_default_snapshot",
        "book_female": "book_default_snapshot",
        "chapter_override": "chapter_override_snapshot",
        "range_override": "range_override_snapshot",
        "unknown": "pinned_fallback_snapshot",
    }.get(source, source or "pinned_snapshot")


def artifact_configuration_summary(db: Database, artifact_id: int) -> dict[str, Any] | None:
    """Return render inputs from snapshots, never from mutable current settings."""
    row = db.fetch_one(
        """
        SELECT a.id AS artifact_id, a.chapter_id, a.job_chapter_id, a.text_revision_id,
               a.sha256, a.size_bytes, a.duration_ms, a.status AS artifact_status,
               a.created_at AS artifact_created_at,
               c.book_id, c.chapter_number, c.title AS chapter_title,
               c.active_audio_artifact_id, c.human_approval_json,
               b.title AS book_title,
               j.id AS job_id, j.settings_json,
               jc.casting_plan_id, jc.voice_snapshot_json,
               cp.plan_revision AS casting_plan_revision
        FROM artifacts a
        JOIN chapters c ON c.id=a.chapter_id
        JOIN books b ON b.id=c.book_id
        JOIN job_chapters jc ON jc.id=a.job_chapter_id
        JOIN jobs j ON j.id=jc.job_id
        LEFT JOIN casting_plans cp ON cp.id=jc.casting_plan_id
        WHERE a.id=? AND a.deleted_at IS NULL
        """,
        (artifact_id,),
    )
    if row is None:
        return None

    snapshot = _object(row["voice_snapshot_json"])
    settings = _object(row["settings_json"])
    character_labels = snapshot.get("character_labels")
    character_labels = character_labels if isinstance(character_labels, dict) else {}
    tts_settings = snapshot.get("tts_settings")
    tts_settings = tts_settings if isinstance(tts_settings, dict) else {}
    actors: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw_utterance in snapshot.get("utterances") or []:
        if not isinstance(raw_utterance, dict):
            continue
        voice_id = str(raw_utterance.get("resolved_voice_id") or "").strip()
        if not voice_id:
            continue
        role = str(raw_utterance.get("role") or "unknown")
        character_id = raw_utterance.get("character_id")
        actor_key = "narrator" if role == "narrator" else f"character:{character_id}" if character_id else role
        provenance = _provenance(raw_utterance)
        key = (actor_key, voice_id, provenance)
        entry = actors.setdefault(
            key,
            {
                "actor_key": actor_key,
                "label": "Narrator" if actor_key == "narrator" else str(character_labels.get(str(character_id)) or f"Nhân vật/nhóm #{character_id}") if character_id else "Người nói chưa định danh",
                "role": role,
                "character_id": character_id,
                "voice_id": voice_id,
                "provenance": provenance,
                "segment_count": 0,
            },
        )
        entry["segment_count"] += 1

    counts = db.fetch_one(
        """SELECT COUNT(*) AS segment_count,
                  COALESCE(SUM(CASE WHEN status='verified' THEN 1 ELSE 0 END),0) AS verified_segment_count,
                  COALESCE(SUM(attempt_count),0) AS attempt_count
           FROM segments WHERE job_chapter_id=?""",
        (row["job_chapter_id"],),
    )
    approval = _object(row["human_approval_json"])
    qa_status = "pending"
    if int(approval.get("artifact_id") or 0) == int(row["artifact_id"]):
        qa_status = str(approval.get("status") or "pending")
    engine = str(snapshot.get("engine_version") or settings.get("engine_version") or "unknown")
    mode = str(tts_settings.get("tts_mode") or settings.get("tts_mode") or "unknown")
    ordered_actors = sorted(actors.values(), key=lambda item: (item["actor_key"] != "narrator", item["label"], item["voice_id"]))
    return {
        "schema": "story-audio-artifact-configuration/v1",
        "artifact": {
            "id": int(row["artifact_id"]),
            "status": row["artifact_status"],
            "active": int(row["active_audio_artifact_id"] or 0) == int(row["artifact_id"]),
            "created_at": row["artifact_created_at"],
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
            "duration_ms": row["duration_ms"],
            "human_qa_status": qa_status,
        },
        "book": {"id": int(row["book_id"]), "title": row["book_title"]},
        "chapter": {"id": int(row["chapter_id"]), "number": int(row["chapter_number"]), "title": row["chapter_title"]},
        "job": {"id": int(row["job_id"]), "job_chapter_id": int(row["job_chapter_id"])},
        "source_revision_id": row["text_revision_id"],
        "casting_plan": {"id": row["casting_plan_id"], "revision": row["casting_plan_revision"]},
        "provider": {"engine": engine, "mode": mode},
        "actors": ordered_actors,
        "synthesis": {
            "segment_count": int(counts["segment_count"] or 0),
            "verified_segment_count": int(counts["verified_segment_count"] or 0),
            "attempt_count": int(counts["attempt_count"] or 0),
            "retry_count": max(0, int(counts["attempt_count"] or 0) - int(counts["segment_count"] or 0)),
        },
    }
