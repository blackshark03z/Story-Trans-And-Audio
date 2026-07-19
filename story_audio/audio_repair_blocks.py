from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

from .config import Settings
from .db import Database, utcnow
from .files import sha256_file, sha256_text
from .storage import ContentStore
from .synthesis_snapshot import load_segment_synthesis_input
from .tts import TtsService


class AudioRepairBlockError(RuntimeError):
    """Base error for adjacent-segment audio repair blocks."""


class AudioRepairBlockValidationError(AudioRepairBlockError):
    """Raised when a repair block cannot be created safely."""


def _load_text_revision_text(store: ContentStore, text_revision: dict[str, Any]) -> str:
    text = store.read_text(text_revision["content_path"])
    actual = sha256_text(text)
    if actual != text_revision["content_sha256"]:
        raise AudioRepairBlockValidationError("Text Revision content hash mismatch")
    return text


def _rows_to_dict(rows: list[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _load_segments_for_range(db: Database, first_segment_id: int, last_segment_id: int) -> list[dict[str, Any]]:
    first = db.fetch_one(
        """SELECT s.*, jc.job_id, jc.chapter_id, jc.text_revision_id,
                  jc.casting_plan_id, jc.casting_plan_sha256,
                  j.status AS job_status, c.chapter_number, b.title AS book_title
           FROM segments s
           JOIN job_chapters jc ON jc.id = s.job_chapter_id
           JOIN jobs j ON j.id = jc.job_id
           JOIN chapters c ON c.id = jc.chapter_id
           JOIN books b ON b.id = c.book_id
           WHERE s.id = ?""",
        (first_segment_id,),
    )
    last = db.fetch_one("SELECT * FROM segments WHERE id=?", (last_segment_id,))
    if not first or not last:
        raise AudioRepairBlockValidationError("Repair block segment not found")
    if first["job_chapter_id"] != last["job_chapter_id"]:
        raise AudioRepairBlockValidationError("Repair block segments must be in the same JobChapter")
    if int(first["segment_index"]) > int(last["segment_index"]):
        raise AudioRepairBlockValidationError("first_segment_id must not come after last_segment_id")
    rows = db.fetch_all(
        """SELECT s.*, jc.job_id, jc.chapter_id, jc.text_revision_id,
                  jc.casting_plan_id, jc.casting_plan_sha256,
                  j.status AS job_status, c.chapter_number, b.title AS book_title
           FROM segments s
           JOIN job_chapters jc ON jc.id = s.job_chapter_id
           JOIN jobs j ON j.id = jc.job_id
           JOIN chapters c ON c.id = jc.chapter_id
           JOIN books b ON b.id = c.book_id
           WHERE s.job_chapter_id=? AND s.segment_index BETWEEN ? AND ?
           ORDER BY s.segment_index""",
        (first["job_chapter_id"], first["segment_index"], last["segment_index"]),
    )
    segments = _rows_to_dict(rows)
    expected = int(last["segment_index"]) - int(first["segment_index"]) + 1
    if expected < 2:
        raise AudioRepairBlockValidationError("Repair block must cover at least two adjacent segments")
    if len(segments) != expected:
        raise AudioRepairBlockValidationError("Repair block range has missing segment indexes")
    if segments[0]["id"] != first_segment_id or segments[-1]["id"] != last_segment_id:
        raise AudioRepairBlockValidationError("Repair block range boundary mismatch")
    return segments


def _validate_common_snapshot(segments: list[dict[str, Any]]) -> None:
    base = segments[0]
    if base["job_status"] in ("running", "repairing", "synthesizing", "assembling"):
        raise AudioRepairBlockValidationError(f"Cannot create repair block while job is {base['job_status']}")
    fields = [
        "job_chapter_id",
        "text_revision_id",
        "casting_plan_id",
        "casting_plan_sha256",
        "speaker_role",
        "character_id",
        "resolved_voice_id",
        "effective_voice_ref",
        "custom_voice_revision_id",
        "voice_source_type",
        "voice_provider",
        "voice_model",
        "logical_voice_ref",
        "voice_resolution_reason",
        "reference_audio_sha256",
        "reference_audio_storage_key",
        "reference_transcript",
        "reference_transcript_sha256",
        "synthesis_settings_json",
        "voice_snapshot_version",
    ]
    for segment in segments:
        if segment["status"] != "verified":
            raise AudioRepairBlockValidationError("Repair block segments must all be verified")
        if not segment["wav_path"]:
            raise AudioRepairBlockValidationError("Repair block segments must have active WAV paths")
        if int(segment["utterance_sequence"]) != int(base["utterance_sequence"]) + (int(segment["segment_index"]) - int(base["segment_index"])):
            raise AudioRepairBlockValidationError("Repair block segment sequences must be consecutive")
        for field in fields:
            if segment[field] != base[field]:
                raise AudioRepairBlockValidationError(f"Repair block segments differ in {field}")


def _plan_utterance_offsets(
    db: Database,
    store: ContentStore,
    casting_plan_id: int,
    expected_plan_sha256: str,
    expected_text_revision_id: int,
    sequences: list[int],
) -> dict[int, dict[str, Any]]:
    plan = db.fetch_one("SELECT * FROM casting_plans WHERE id=?", (casting_plan_id,))
    if not plan:
        raise AudioRepairBlockValidationError("Repair block Casting Plan not found")
    if plan["status"] != "approved":
        raise AudioRepairBlockValidationError("Repair block requires an approved Casting Plan")
    if plan["plan_sha256"] != expected_plan_sha256:
        raise AudioRepairBlockValidationError("Repair block Casting Plan hash does not match JobChapter pin")
    if int(plan["text_revision_id"]) != int(expected_text_revision_id):
        raise AudioRepairBlockValidationError("Repair block Casting Plan Text Revision does not match JobChapter pin")
    payload = json.loads(store.read_text(plan["content_path"]))
    by_sequence: dict[int, dict[str, Any]] = {}
    for utterance in payload.get("utterances") or []:
        sequence = int(utterance.get("sequence") or 0)
        if sequence in sequences:
            by_sequence[sequence] = utterance
    missing = [seq for seq in sequences if seq not in by_sequence]
    if missing:
        raise AudioRepairBlockValidationError(f"Repair block missing utterance offsets: {missing}")
    return by_sequence


def _repair_identity(
    db: Database,
    store: ContentStore,
    first_segment_id: int,
    last_segment_id: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    segments = _load_segments_for_range(db, first_segment_id, last_segment_id)
    _validate_common_snapshot(segments)
    first = segments[0]
    job_chapter = db.fetch_one("SELECT * FROM job_chapters WHERE id=?", (first["job_chapter_id"],))
    if not job_chapter:
        raise AudioRepairBlockValidationError("Repair block JobChapter not found")
    pinned_casting_plan_id = first["casting_plan_id"] or job_chapter["casting_plan_id"]
    pinned_casting_plan_sha256 = first["casting_plan_sha256"] or job_chapter["casting_plan_sha256"]
    if not pinned_casting_plan_id:
        raise AudioRepairBlockValidationError("Repair block requires a pinned Casting Plan")
    sequences = [int(segment["utterance_sequence"]) for segment in segments]
    offsets = _plan_utterance_offsets(
        db,
        store,
        int(pinned_casting_plan_id),
        pinned_casting_plan_sha256,
        int(first["text_revision_id"]),
        sequences,
    )
    source_start = int(offsets[sequences[0]]["start_offset"])
    source_end = int(offsets[sequences[-1]]["end_offset"])
    if source_start >= source_end:
        raise AudioRepairBlockValidationError("Repair block source offsets are invalid")
    text_revision = db.fetch_one("SELECT * FROM text_revisions WHERE id=?", (first["text_revision_id"],))
    if not text_revision:
        raise AudioRepairBlockValidationError("Repair block Text Revision not found")
    revision_text = _load_text_revision_text(store, dict(text_revision))
    source_text = revision_text[source_start:source_end]
    if not source_text.strip():
        raise AudioRepairBlockValidationError("Repair block source span is empty")
    expected = " ".join(store.read_text(segment["text_path"]).strip() for segment in segments)
    if source_text.strip() != expected.strip():
        raise AudioRepairBlockValidationError("Repair block source span does not match covered segment texts")
    identity = {
        "job_id": int(first["job_id"]),
        "job_chapter_id": int(first["job_chapter_id"]),
        "chapter_id": int(first["chapter_id"]),
        "chapter_number": int(first["chapter_number"]),
        "text_revision_id": int(first["text_revision_id"]),
        "casting_plan_id": int(pinned_casting_plan_id),
        "casting_plan_sha256": pinned_casting_plan_sha256,
        "covered_segment_ids": [int(segment["id"]) for segment in segments],
        "first_segment_id": int(segments[0]["id"]),
        "last_segment_id": int(segments[-1]["id"]),
        "first_sequence": sequences[0],
        "last_sequence": sequences[-1],
        "source_start_offset": source_start,
        "source_end_offset": source_end,
        "source_text": source_text,
        "source_text_sha256": sha256_text(source_text),
        "speaker_role": first["speaker_role"] or "narrator",
        "character_id": first["character_id"],
        "resolved_voice_id": first["resolved_voice_id"],
        "effective_voice_ref": first["effective_voice_ref"],
        "custom_voice_revision_id": first["custom_voice_revision_id"],
        "voice_source_type": first["voice_source_type"],
        "voice_provider": first["voice_provider"],
        "voice_model": first["voice_model"],
        "logical_voice_ref": first["logical_voice_ref"],
        "voice_resolution_reason": first["voice_resolution_reason"],
        "reference_audio_sha256": first["reference_audio_sha256"],
        "reference_audio_storage_key": first["reference_audio_storage_key"],
        "reference_transcript": first["reference_transcript"],
        "reference_transcript_sha256": first["reference_transcript_sha256"],
        "synthesis_settings_json": first["synthesis_settings_json"],
        "synthesis_hash": sha256_text(json.dumps({
            "repair_block": "audio-repair-block-v1",
            "job_chapter_id": int(first["job_chapter_id"]),
            "segment_ids": [int(segment["id"]) for segment in segments],
            "source_text_sha256": sha256_text(source_text),
            "effective_voice_ref": first["effective_voice_ref"],
            "settings": json.loads(first["synthesis_settings_json"]),
        }, sort_keys=True, ensure_ascii=False)),
    }
    return segments, identity


def _candidate_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["covered_segment_ids"] = json.loads(data.pop("covered_segment_ids_json"))
    return data


def create_audio_repair_block_candidate(
    db: Database,
    store: ContentStore,
    tts: TtsService,
    config: Settings,
    *,
    job_id: int,
    first_segment_id: int,
    last_segment_id: int,
) -> dict[str, Any]:
    segments, identity = _repair_identity(db, store, first_segment_id, last_segment_id)
    if identity["job_id"] != int(job_id):
        raise AudioRepairBlockValidationError("Repair block job_id does not match covered segments")
    existing = db.fetch_one(
        """SELECT * FROM audio_repair_blocks
           WHERE job_chapter_id=? AND first_segment_id=? AND last_segment_id=?
             AND source_text_sha256=? AND effective_voice_ref=? AND status='candidate'""",
        (
            identity["job_chapter_id"],
            identity["first_segment_id"],
            identity["last_segment_id"],
            identity["source_text_sha256"],
            identity["effective_voice_ref"],
        ),
    )
    if existing:
        return {"ok": True, "reused": True, **_candidate_dict(existing)}

    first = dict(segments[0])
    total_segments = int(db.fetch_one(
        "SELECT COUNT(*) as count FROM segments WHERE job_chapter_id=?",
        (identity["job_chapter_id"],),
    )["count"])
    is_final = int(segments[-1]["segment_index"]) == total_segments
    synth_input = replace(
        load_segment_synthesis_input(first, store, is_final_segment=is_final),
        text=identity["source_text"],
        text_sha256=identity["source_text_sha256"],
        segment_index=int(first["segment_index"]),
    )

    work_dir = config.work_dir / f"job_{identity['job_id']}" / f"chapter_{identity['chapter_number']:04d}" / "repair_blocks"
    work_dir.mkdir(parents=True, exist_ok=True)
    next_number = int(db.fetch_one(
        "SELECT COUNT(*) as count FROM audio_repair_blocks WHERE job_chapter_id=?",
        (identity["job_chapter_id"],),
    )["count"]) + 1
    candidate_path = work_dir / f"repair_block_{identity['first_segment_id']}_{identity['last_segment_id']}_candidate_{next_number:04d}.wav"

    try:
        duration_ms, _sample_rate = tts.synthesize(synth_input=synth_input, output_path=candidate_path)
        audio_hash = sha256_file(candidate_path)
    except Exception as exc:
        candidate_path.unlink(missing_ok=True)
        raise AudioRepairBlockError(f"Repair block synthesis failed: {exc}") from exc

    now = utcnow()
    with db.connect() as conn:
        cursor = conn.execute(
            """INSERT INTO audio_repair_blocks(
                job_id, job_chapter_id, chapter_id, text_revision_id, casting_plan_id,
                casting_plan_sha256, first_segment_id, last_segment_id,
                covered_segment_ids_json, first_sequence, last_sequence,
                source_start_offset, source_end_offset, source_text, source_text_sha256,
                speaker_role, character_id, resolved_voice_id, effective_voice_ref,
                custom_voice_revision_id, voice_source_type, voice_provider, voice_model,
                logical_voice_ref, voice_resolution_reason, reference_audio_sha256,
                reference_audio_storage_key, reference_transcript, reference_transcript_sha256,
                synthesis_settings_json, synthesis_hash, status, candidate_wav_path,
                candidate_audio_sha256, candidate_duration_ms, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                identity["job_id"], identity["job_chapter_id"], identity["chapter_id"],
                identity["text_revision_id"], identity["casting_plan_id"],
                identity["casting_plan_sha256"], identity["first_segment_id"],
                identity["last_segment_id"], json.dumps(identity["covered_segment_ids"]),
                identity["first_sequence"], identity["last_sequence"],
                identity["source_start_offset"], identity["source_end_offset"],
                identity["source_text"], identity["source_text_sha256"],
                identity["speaker_role"], identity["character_id"],
                identity["resolved_voice_id"], identity["effective_voice_ref"],
                identity["custom_voice_revision_id"], identity["voice_source_type"],
                identity["voice_provider"], identity["voice_model"],
                identity["logical_voice_ref"], identity["voice_resolution_reason"],
                identity["reference_audio_sha256"], identity["reference_audio_storage_key"],
                identity["reference_transcript"], identity["reference_transcript_sha256"],
                identity["synthesis_settings_json"], identity["synthesis_hash"], "candidate",
                str(candidate_path), audio_hash, duration_ms, now,
            ),
        )
        block_id = cursor.lastrowid
    db.audit(
        "audio_repair_block_candidate_generated",
        job_id=identity["job_id"],
        chapter_id=identity["chapter_id"],
        details={
            "repair_block_id": block_id,
            "covered_segment_ids": identity["covered_segment_ids"],
            "duration_ms": duration_ms,
        },
    )
    row = db.fetch_one("SELECT * FROM audio_repair_blocks WHERE id=?", (block_id,))
    return {"ok": True, "reused": False, **_candidate_dict(row)}


def list_audio_repair_blocks(db: Database, job_chapter_id: int) -> dict[str, Any]:
    rows = db.fetch_all(
        "SELECT * FROM audio_repair_blocks WHERE job_chapter_id=? ORDER BY id DESC",
        (job_chapter_id,),
    )
    return {"job_chapter_id": job_chapter_id, "repair_blocks": [_candidate_dict(row) for row in rows]}


def reject_audio_repair_block_candidate(db: Database, repair_block_id: int) -> dict[str, Any]:
    row = db.fetch_one(
        """SELECT rb.*, c.chapter_number
           FROM audio_repair_blocks rb
           JOIN chapters c ON c.id = rb.chapter_id
           WHERE rb.id=?""",
        (repair_block_id,),
    )
    if not row:
        raise AudioRepairBlockValidationError("Repair block not found")
    if row["status"] != "candidate":
        raise AudioRepairBlockValidationError(f"Repair block status is '{row['status']}', expected 'candidate'")
    now = utcnow()
    with db.connect() as conn:
        conn.execute(
            "UPDATE audio_repair_blocks SET status='rejected', rejected_at=? WHERE id=?",
            (now, repair_block_id),
        )
    db.audit(
        "audio_repair_block_candidate_rejected",
        job_id=row["job_id"],
        chapter_id=row["chapter_id"],
        details={"repair_block_id": repair_block_id},
    )
    updated = db.fetch_one("SELECT * FROM audio_repair_blocks WHERE id=?", (repair_block_id,))
    return {"ok": True, **_candidate_dict(updated)}


def build_active_audio_preview(
    db: Database,
    config: Settings,
    repair_block_id: int,
) -> Path:
    """Build a preview-only WAV of the currently active covered segment range."""

    row = db.fetch_one(
        """SELECT rb.*, c.chapter_number
           FROM audio_repair_blocks rb
           JOIN chapters c ON c.id = rb.chapter_id
           WHERE rb.id=?""",
        (repair_block_id,),
    )
    if not row:
        raise AudioRepairBlockValidationError("Repair block not found")

    segment_ids = json.loads(row["covered_segment_ids_json"])
    if not segment_ids:
        raise AudioRepairBlockValidationError("Repair block has no covered segments")

    placeholders = ",".join("?" for _ in segment_ids)
    segments = db.fetch_all(
        f"""SELECT id, segment_index, wav_path
            FROM segments
            WHERE id IN ({placeholders})
            ORDER BY segment_index""",
        tuple(segment_ids),
    )
    if len(segments) != len(segment_ids):
        raise AudioRepairBlockValidationError("Repair block covered segment missing")

    wav_paths = [Path(segment["wav_path"]) for segment in segments]
    missing = [path for path in wav_paths if not path.exists()]
    if missing:
        raise AudioRepairBlockValidationError(f"Active segment audio missing: {missing[0]}")

    preview_dir = (
        config.work_dir
        / f"job_{int(row['job_id'])}"
        / f"chapter_{int(row['chapter_number']):04d}"
        / "repair_blocks"
    )
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / f"repair_block_{repair_block_id}_active_preview.wav"
    concat_list = preview_dir / f"repair_block_{repair_block_id}_active_concat.txt"

    newest_source_mtime = max(path.stat().st_mtime for path in wav_paths)
    if preview_path.exists() and preview_path.stat().st_mtime >= newest_source_mtime:
        return preview_path

    concat_lines = []
    for path in wav_paths:
        escaped = str(path).replace("'", "'\\''")
        concat_lines.append(f"file '{escaped}'")
    concat_list.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

    temp_path = preview_path.with_suffix(".tmp.wav")
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c",
        "copy",
        str(temp_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        temp_path.replace(preview_path)
    except (OSError, subprocess.CalledProcessError) as exc:
        temp_path.unlink(missing_ok=True)
        detail = getattr(exc, "stderr", "") or str(exc)
        raise AudioRepairBlockValidationError(
            f"Active repair-block preview failed: {detail}"
        ) from exc

    return preview_path
