from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

from .config import Settings
from .db import Database, utcnow
from .files import atomic_write_json, safe_slug, sha256_file, sha256_text
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


def _ffprobe_duration_ms(path: Path) -> int:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    duration = float(result.stdout.strip())
    if duration <= 0:
        raise AudioRepairBlockValidationError(f"Invalid audio duration: {path}")
    return int(round(duration * 1000))


def _run_command(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr or exc.stdout or str(exc)
        raise AudioRepairBlockError(detail) from exc


def _repair_block_with_context(db: Database, repair_block_id: int) -> dict[str, Any]:
    row = db.fetch_one(
        """SELECT rb.*, c.chapter_number, c.book_id, b.title AS book_title,
                  j.status AS job_status, j.voice_name, j.output_format, j.settings_json,
                  jc.status AS job_chapter_status, jc.artifact_id AS job_chapter_artifact_id,
                  jc.voice_snapshot_json
           FROM audio_repair_blocks rb
           JOIN jobs j ON j.id=rb.job_id
           JOIN job_chapters jc ON jc.id=rb.job_chapter_id
           JOIN chapters c ON c.id=rb.chapter_id
           JOIN books b ON b.id=c.book_id
           WHERE rb.id=?""",
        (repair_block_id,),
    )
    if not row:
        raise AudioRepairBlockValidationError("Repair block not found")
    return dict(row)


def _reassemble_chapter_with_repair_block(
    db: Database,
    store: ContentStore,
    config: Settings,
    repair_block: dict[str, Any],
) -> dict[str, Any]:
    job_id = int(repair_block["job_id"])
    job_chapter_id = int(repair_block["job_chapter_id"])
    chapter_id = int(repair_block["chapter_id"])
    output_format = str(repair_block["output_format"])
    candidate_path = Path(repair_block["candidate_wav_path"])
    first_segment_id = int(repair_block["first_segment_id"])
    last_segment_id = int(repair_block["last_segment_id"])
    covered_segment_ids = set(json.loads(repair_block["covered_segment_ids_json"]))

    segments = db.fetch_all(
        """SELECT s.*, ch.display_name AS character_name
           FROM segments s
           LEFT JOIN characters ch ON ch.id=s.character_id
           WHERE s.job_chapter_id=?
           ORDER BY s.segment_index""",
        (job_chapter_id,),
    )
    if not segments:
        raise AudioRepairBlockValidationError("Repair block chapter has no segments")

    segment_wavs: list[dict[str, Any]] = []
    skipped_ids: set[int] = set()
    for segment in segments:
        segment_id = int(segment["id"])
        if segment_id in skipped_ids:
            continue
        if segment_id == first_segment_id:
            expected_ids: list[int] = []
            for covered in segments:
                covered_id = int(covered["id"])
                if covered_id in covered_segment_ids:
                    if covered["status"] != "verified":
                        raise AudioRepairBlockValidationError("Covered repair-block segment is not verified")
                    expected_ids.append(covered_id)
            if expected_ids != json.loads(repair_block["covered_segment_ids_json"]):
                raise AudioRepairBlockValidationError("Repair block covered segment order mismatch")
            segment_wavs.append(
                {
                    "path": candidate_path,
                    "duration_ms": int(repair_block["candidate_duration_ms"]),
                    "segment": segment,
                    "repair_block": repair_block,
                    "covered_segment_ids": expected_ids,
                }
            )
            skipped_ids.update(expected_ids)
            skipped_ids.remove(first_segment_id)
            continue
        if segment_id in covered_segment_ids:
            raise AudioRepairBlockValidationError("Repair block range did not start at first segment")
        if segment["status"] != "verified" or not segment["wav_path"]:
            raise AudioRepairBlockValidationError(f"Segment {segment_id} is not verified")
        segment_wavs.append(
            {
                "path": Path(segment["wav_path"]),
                "duration_ms": int(segment["duration_ms"]),
                "segment": segment,
                "repair_block": None,
                "covered_segment_ids": [segment_id],
            }
        )

    temp_dir = (
        config.work_dir
        / f"job_{job_id}"
        / f"chapter_{int(repair_block['chapter_number']):04d}"
        / "repair_blocks"
        / f"accept_repair_block_{int(repair_block['id'])}"
    )
    temp_dir.mkdir(parents=True, exist_ok=True)
    concat_path = temp_dir / "concat.txt"
    concat_path.write_text(
        "\n".join(
            f"file '{str(item['path'].resolve()).replace(chr(92), '/')}'"
            for item in segment_wavs
        )
        + "\n",
        encoding="utf-8",
    )

    master_temp = temp_dir / "chapter_master.wav"
    master_partial = temp_dir / "chapter_master.partial.wav"
    _run_command(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", str(concat_path), "-c:a", "pcm_s16le", str(master_partial),
        ]
    )
    master_duration_ms = _ffprobe_duration_ms(master_partial)
    master_partial.replace(master_temp)

    voice_snapshot = json.loads(repair_block["voice_snapshot_json"] or "{}")
    utterance_metadata = {
        int(item["sequence"]): item
        for item in voice_snapshot.get("utterances", [])
        if item.get("sequence") is not None
    }
    cursor_ms = 0
    timeline_items = []
    repair_region: dict[str, Any] | None = None
    for item in segment_wavs:
        segment = item["segment"]
        duration_ms = int(item["duration_ms"])
        repair = item["repair_block"]
        resolution = (
            utterance_metadata.get(int(segment["utterance_sequence"]))
            if segment["utterance_sequence"] is not None else None
        )
        timeline_item = {
            "index": int(segment["segment_index"]),
            "text": repair["source_text"] if repair else store.read_text(segment["text_path"]),
            "start_ms": cursor_ms,
            "end_ms": cursor_ms + duration_ms,
            "duration_ms": duration_ms,
            "segment_sha256": repair["candidate_audio_sha256"] if repair else segment["audio_sha256"],
            "utterance_sequence": segment["utterance_sequence"],
            "speaker_role": segment["speaker_role"] or "narrator",
            "character_id": segment["character_id"],
            "character_name": segment["character_name"],
            "voice_id": segment["resolved_voice_id"] or repair_block["voice_name"],
            "resolution_source": resolution.get("resolution_source") if resolution else None,
            "resolved_gender": resolution.get("resolved_gender") if resolution else None,
            "needs_review": bool(resolution.get("needs_review")) if resolution else False,
            "voice_profile_id": resolution.get("voice_profile_id") if resolution else None,
            "voice_profile_version": resolution.get("voice_profile_version") if resolution else None,
            "synthesis_hash": repair["synthesis_hash"] if repair else segment["synthesis_hash"],
        }
        if repair:
            timeline_item.update(
                {
                    "repair_block_id": int(repair["id"]),
                    "covered_segment_ids": item["covered_segment_ids"],
                    "first_sequence": int(repair["first_sequence"]),
                    "last_sequence": int(repair["last_sequence"]),
                    "source_start_offset": int(repair["source_start_offset"]),
                    "source_end_offset": int(repair["source_end_offset"]),
                }
            )
            repair_region = {
                "start_ms": cursor_ms,
                "end_ms": cursor_ms + duration_ms,
                "covered_segment_ids": item["covered_segment_ids"],
                "repair_block_id": int(repair["id"]),
            }
        timeline_items.append(timeline_item)
        cursor_ms += duration_ms

    timeline_temp = temp_dir / "segment_timeline.json"
    atomic_write_json(
        timeline_temp,
        {
            "schema_version": 2,
            "chapter_id": chapter_id,
            "text_revision_id": int(repair_block["text_revision_id"]),
            "sample_rate": config.tts_sample_rate,
            "duration_ms": master_duration_ms,
            "repair_blocks": [repair_region] if repair_region else [],
            "items": timeline_items,
        },
    )

    final_temp = temp_dir / f"chapter.{output_format}"
    final_partial = temp_dir / f"chapter.partial.{output_format}"
    codec = ["-c:a", "aac", "-b:a", "128k"] if output_format == "m4a" else ["-c:a", "libmp3lame", "-b:a", "128k"]
    _run_command(["ffmpeg", "-y", "-v", "error", "-i", str(master_temp), *codec, str(final_partial)])
    final_duration_ms = _ffprobe_duration_ms(final_partial)
    if abs(final_duration_ms - master_duration_ms) > 750:
        raise AudioRepairBlockError(
            f"Audio export duration mismatch: master={master_duration_ms}ms final={final_duration_ms}ms"
        )
    final_partial.replace(final_temp)

    output_dir = (
        config.output_dir
        / f"{int(repair_block['book_id'])}-{safe_slug(str(repair_block['book_title']), 'book')}"
        / f"chapter_{int(repair_block['chapter_number']):04d}"
        / f"job_{job_id}"
    )
    previous_renders = int(db.fetch_one(
        "SELECT COUNT(*) AS count FROM artifacts WHERE job_chapter_id=? AND artifact_type='chapter_master_wav'",
        (job_chapter_id,),
    )["count"])
    render_dir = output_dir / f"render_{previous_renders + 1:04d}"
    render_dir.mkdir(parents=True, exist_ok=False)
    master_final = render_dir / "chapter_master.wav"
    timeline_final = render_dir / "segment_timeline.json"
    final_path = render_dir / f"chapter.{output_format}"
    shutil.copy2(master_temp, master_final)
    shutil.copy2(timeline_temp, timeline_final)
    shutil.copy2(final_temp, final_path)

    settings = json.loads(repair_block["settings_json"])
    synthesis_hash = sha256_text(json.dumps({
        "text_revision_id": int(repair_block["text_revision_id"]),
        "voice": repair_block["voice_name"],
        "casting_plan_sha256": repair_block["casting_plan_sha256"],
        "repair_block_id": int(repair_block["id"]),
        "repair_block_candidate_sha256": repair_block["candidate_audio_sha256"],
        "settings": settings,
    }, sort_keys=True, ensure_ascii=False))
    export_hash = sha256_text(json.dumps({"format": output_format, "bitrate": "128k"}, sort_keys=True))

    return {
        "render_dir": render_dir,
        "master_path": master_final,
        "timeline_path": timeline_final,
        "final_path": final_path,
        "master_duration_ms": master_duration_ms,
        "final_duration_ms": final_duration_ms,
        "synthesis_hash": synthesis_hash,
        "export_hash": export_hash,
        "repair_region": repair_region,
    }


def accept_audio_repair_block_candidate(
    db: Database,
    store: ContentStore,
    config: Settings,
    repair_block_id: int,
) -> dict[str, Any]:
    repair_block = _repair_block_with_context(db, repair_block_id)
    if repair_block["status"] != "candidate":
        raise AudioRepairBlockValidationError(
            f"Repair block status is '{repair_block['status']}', expected 'candidate'"
        )
    if repair_block["job_status"] in ("running", "repairing", "synthesizing", "assembling"):
        raise AudioRepairBlockValidationError(f"Cannot accept repair block while job is {repair_block['job_status']}")
    if repair_block["job_chapter_status"] != "completed":
        raise AudioRepairBlockValidationError("Repair block JobChapter must be completed")
    pending_count = int(db.fetch_one(
        "SELECT COUNT(*) AS count FROM audio_repair_blocks WHERE job_chapter_id=? AND status='candidate'",
        (repair_block["job_chapter_id"],),
    )["count"])
    if pending_count != 1:
        raise AudioRepairBlockValidationError("Repair block acceptance requires exactly one pending candidate")

    candidate_path = Path(repair_block["candidate_wav_path"])
    if not candidate_path.exists():
        raise AudioRepairBlockValidationError(f"Repair block candidate audio missing: {candidate_path}")
    if sha256_file(candidate_path) != repair_block["candidate_audio_sha256"]:
        raise AudioRepairBlockValidationError("Repair block candidate audio hash mismatch")

    rebuild = _reassemble_chapter_with_repair_block(db, store, config, repair_block)

    now = utcnow()
    with db.transaction() as conn:
        current = conn.execute(
            "SELECT status FROM audio_repair_blocks WHERE id=?",
            (repair_block_id,),
        ).fetchone()
        if not current or current["status"] != "candidate":
            raise AudioRepairBlockValidationError("Repair block is no longer a candidate")
        master_cursor = conn.execute(
            """INSERT INTO artifacts(
                chapter_id,job_chapter_id,text_revision_id,artifact_type,synthesis_hash,
                path,sha256,size_bytes,duration_ms,status,created_at,verified_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                repair_block["chapter_id"], repair_block["job_chapter_id"],
                repair_block["text_revision_id"], "chapter_master_wav",
                rebuild["synthesis_hash"], str(rebuild["master_path"]),
                sha256_file(rebuild["master_path"]), rebuild["master_path"].stat().st_size,
                rebuild["master_duration_ms"], "verified", now, now,
            ),
        )
        master_artifact_id = int(master_cursor.lastrowid)
        timeline_cursor = conn.execute(
            """INSERT INTO artifacts(
                chapter_id,job_chapter_id,text_revision_id,artifact_type,synthesis_hash,
                path,sha256,size_bytes,duration_ms,status,created_at,verified_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                repair_block["chapter_id"], repair_block["job_chapter_id"],
                repair_block["text_revision_id"], "segment_timeline_json",
                rebuild["synthesis_hash"], str(rebuild["timeline_path"]),
                sha256_file(rebuild["timeline_path"]), rebuild["timeline_path"].stat().st_size,
                rebuild["master_duration_ms"], "verified", now, now,
            ),
        )
        timeline_artifact_id = int(timeline_cursor.lastrowid)
        output_format = str(repair_block["output_format"])
        final_cursor = conn.execute(
            """INSERT INTO artifacts(
                chapter_id,job_chapter_id,text_revision_id,artifact_type,synthesis_hash,export_hash,
                path,sha256,size_bytes,duration_ms,status,created_at,verified_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                repair_block["chapter_id"], repair_block["job_chapter_id"],
                repair_block["text_revision_id"], f"chapter_{output_format}",
                rebuild["synthesis_hash"], rebuild["export_hash"], str(rebuild["final_path"]),
                sha256_file(rebuild["final_path"]), rebuild["final_path"].stat().st_size,
                rebuild["final_duration_ms"], "active", now, now,
            ),
        )
        final_artifact_id = int(final_cursor.lastrowid)
        conn.execute(
            """UPDATE artifacts SET status='stale'
               WHERE chapter_id=? AND artifact_type IN (?, ?) AND status='active' AND id<>?""",
            (repair_block["chapter_id"], f"chapter_{output_format}", f"chapter_final_{output_format}", final_artifact_id),
        )
        conn.execute(
            "UPDATE audio_repair_blocks SET status='accepted', accepted_at=? WHERE id=?",
            (now, repair_block_id),
        )
        conn.execute(
            "UPDATE chapters SET active_audio_artifact_id=?, audio_status='completed', updated_at=? WHERE id=?",
            (final_artifact_id, now, repair_block["chapter_id"]),
        )
        conn.execute(
            "UPDATE job_chapters SET artifact_id=? WHERE id=?",
            (final_artifact_id, repair_block["job_chapter_id"]),
        )
        conn.execute(
            "INSERT OR IGNORE INTO artifact_dependencies(parent_artifact_id,child_artifact_id) VALUES(?,?)",
            (master_artifact_id, final_artifact_id),
        )
        conn.execute(
            "INSERT OR IGNORE INTO artifact_dependencies(parent_artifact_id,child_artifact_id) VALUES(?,?)",
            (timeline_artifact_id, final_artifact_id),
        )

    db.audit(
        "audio_repair_block_candidate_accepted",
        job_id=repair_block["job_id"],
        chapter_id=repair_block["chapter_id"],
        details={
            "repair_block_id": repair_block_id,
            "new_artifact_id": final_artifact_id,
            "repair_region": rebuild["repair_region"],
        },
    )
    updated = db.fetch_one("SELECT * FROM audio_repair_blocks WHERE id=?", (repair_block_id,))
    return {
        "ok": True,
        "repair_block": _candidate_dict(updated),
        "new_artifact_id": final_artifact_id,
        "master_artifact_id": master_artifact_id,
        "timeline_artifact_id": timeline_artifact_id,
        "final_path": str(rebuild["final_path"]),
        "final_duration_ms": rebuild["final_duration_ms"],
        "repair_region": rebuild["repair_region"],
    }


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
