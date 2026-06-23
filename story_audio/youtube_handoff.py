from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .db import Database
from .files import atomic_write_json, atomic_write_text, safe_slug, sha256_file, sha256_text
from .storage import ContentStore


HANDOFF_SCHEMA = "story-audio-youtube-handoff/v1"
SPEECH_TIMELINE_SCHEMA = "story-audio-speech-timeline/v1"
CHARACTER_SEED_SCHEMA = "story-character-seed/v1"
DURATION_TOLERANCE_MS = 1_000


class HandoffError(RuntimeError):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def probe_duration_ms(path: Path) -> int:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    duration = int(round(float(result.stdout.strip()) * 1000))
    if duration <= 0:
        raise HandoffError("Audio duration must be positive")
    return duration


def _safe_bundle_path(root: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts:
        raise HandoffError(f"Unsafe bundle path: {relative}")
    cursor = root
    for part in value.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise HandoffError(f"Symlink is not allowed in bundle path: {relative}")
    candidate = (root / value).resolve()
    resolved_root = root.resolve()
    if resolved_root not in candidate.parents:
        raise HandoffError(f"Bundle path escapes root: {relative}")
    return candidate


def verify_handoff(bundle: Path) -> dict[str, Any]:
    bundle = bundle.resolve()
    manifest_path = bundle / "handoff.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HandoffError(f"Invalid handoff.json: {type(exc).__name__}") from exc
    if manifest.get("schema") != HANDOFF_SCHEMA:
        raise HandoffError("Unsupported handoff schema")
    files = manifest.get("files")
    artifacts = manifest.get("artifacts")
    if not isinstance(files, dict) or not isinstance(artifacts, dict):
        raise HandoffError("Handoff manifest is missing file metadata")
    required = {"content", "audio", "speech_timeline", "character_seed"}
    if not required <= artifacts.keys():
        raise HandoffError("Handoff manifest is missing required artifacts")
    for relative, metadata in files.items():
        if not isinstance(metadata, dict):
            raise HandoffError("Invalid handoff file metadata")
        path = _safe_bundle_path(bundle, relative)
        if path.is_symlink() or not path.is_file():
            raise HandoffError(f"Missing handoff file: {relative}")
        if path.stat().st_size != int(metadata.get("size", -1)):
            raise HandoffError(f"Size mismatch: {relative}")
        if sha256_file(path) != metadata.get("sha256"):
            raise HandoffError(f"SHA-256 mismatch: {relative}")
    for relative in artifacts.values():
        if relative not in files:
            raise HandoffError(f"Artifact is not hash-pinned: {relative}")
    source = manifest.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("chapter_ids"), list) or len(source["chapter_ids"]) != 1:
        raise HandoffError("Handoff source must identify exactly one chapter")
    if source.get("audio_hash") != files[artifacts["audio"]]["sha256"]:
        raise HandoffError("Source audio hash does not match bundled audio")
    if source.get("speech_timeline_hash") != files[artifacts["speech_timeline"]]["sha256"]:
        raise HandoffError("Source timeline hash does not match bundled timeline")
    if source.get("character_seed_hash") != files[artifacts["character_seed"]]["sha256"]:
        raise HandoffError("Source character seed hash does not match bundled seed")
    try:
        speech = json.loads(_safe_bundle_path(bundle, artifacts["speech_timeline"]).read_text(encoding="utf-8"))
        seed = json.loads(_safe_bundle_path(bundle, artifacts["character_seed"]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HandoffError("Handoff JSON payload is invalid") from exc
    identity = {
        "schema": HANDOFF_SCHEMA,
        "chapter_id": int(source["chapter_ids"][0]),
        "job_id": int(source["job_id"]),
        "text_revision_hash": source["text_revision_hash"],
        "casting_plan_hash": source.get("casting_plan_hash"),
        "audio_hash": source["audio_hash"],
        "speech_timeline_hash": sha256_text(_canonical(speech)),
        "character_seed_hash": sha256_text(_canonical(seed)),
    }
    if manifest.get("identity_hash") != sha256_text(_canonical(identity)):
        raise HandoffError("Handoff identity hash mismatch")
    return manifest


def _resolve_source(db: Database, chapter_id: int, job_id: int | None) -> dict[str, Any]:
    params: list[Any] = [chapter_id]
    job_filter = ""
    if job_id is not None:
        job_filter = " AND j.id=?"
        params.append(job_id)
    row = db.fetch_one(
        f"""SELECT a.*,jc.id AS job_chapter_id,j.id AS job_id,j.voice_name,j.output_format,
                   jc.casting_plan_id,jc.casting_plan_sha256,jc.voice_snapshot_json,
                   c.chapter_number,c.title AS chapter_title,c.book_id,
                   b.title AS book_title,tr.content_path,tr.content_sha256
            FROM artifacts a
            JOIN job_chapters jc ON jc.id=a.job_chapter_id
            JOIN jobs j ON j.id=jc.job_id
            JOIN chapters c ON c.id=a.chapter_id
            JOIN books b ON b.id=c.book_id
            JOIN text_revisions tr ON tr.id=a.text_revision_id
            WHERE a.chapter_id=?{job_filter}
              AND a.artifact_type IN ('chapter_m4a','chapter_mp3','chapter_master_wav')
              AND a.status IN ('active','verified') AND a.deleted_at IS NULL
              AND jc.status='completed'
            ORDER BY (a.status='active') DESC,
                     CASE a.artifact_type WHEN 'chapter_m4a' THEN 1 WHEN 'chapter_mp3' THEN 2 ELSE 3 END,
                     a.id DESC LIMIT 1""",
        tuple(params),
    )
    if not row:
        raise HandoffError("No completed verified audio artifact was found for this chapter/job")
    return dict(row)


def _timeline_artifact(db: Database, source: dict[str, Any]) -> dict[str, Any]:
    row = db.fetch_one(
        """SELECT * FROM artifacts
           WHERE job_chapter_id=? AND text_revision_id=?
             AND artifact_type='segment_timeline_json'
             AND status IN ('active','verified') AND deleted_at IS NULL
           ORDER BY id DESC LIMIT 1""",
        (source["job_chapter_id"], source["text_revision_id"]),
    )
    if not row:
        raise HandoffError("Verified speech timeline artifact is missing")
    return dict(row)


def _verify_source_artifact(row: dict[str, Any], label: str) -> Path:
    path = Path(str(row["path"]))
    if path.is_symlink() or not path.is_file():
        raise HandoffError(f"{label} file is missing")
    if sha256_file(path) != row["sha256"]:
        raise HandoffError(f"{label} artifact hash mismatch")
    return path


def _source_spans(text: str, items: list[dict[str, Any]], snapshot: dict[str, Any] | None) -> list[tuple[int, int, str]]:
    utterances = {
        int(item["sequence"]): item
        for item in (snapshot or {}).get("utterances", [])
        if isinstance(item, dict) and item.get("sequence") is not None
    }
    cursors: dict[int, int] = {}
    chapter_cursor = 0
    spans: list[tuple[int, int, str]] = []
    for position, item in enumerate(items, start=1):
        segment_text = str(item["text"])
        sequence = item.get("utterance_sequence")
        utterance = utterances.get(int(sequence)) if sequence is not None else None
        if utterance:
            base = int(utterance["start_offset"])
            limit = int(utterance["end_offset"])
            cursor = cursors.get(int(sequence), base)
            found = _find_source_span(text, segment_text, cursor, limit)
            start = found[0] if found else -1
            if start < 0:
                raise HandoffError(f"Timeline text does not match casting utterance at item {position}")
            end = found[1]
            cursors[int(sequence)] = end
            utterance_id = str(utterance.get("utterance_id") or f"utt_{int(sequence):04d}")
        else:
            found = _find_source_span(text, segment_text, chapter_cursor, len(text))
            start = found[0] if found else -1
            if start < 0:
                raise HandoffError(f"Timeline text does not match pinned TextRevision at item {position}")
            end = found[1]
            chapter_cursor = end
            utterance_id = f"utt_{position:04d}"
        spans.append((start, end, utterance_id))
    return spans


def _find_source_span(text: str, segment: str, start: int, end: int) -> tuple[int, int] | None:
    exact = text.find(segment, start, end)
    if exact >= 0:
        return exact, exact + len(segment)
    pieces = re.split(r"\s+", segment.strip())
    if not pieces:
        return None
    pattern = re.compile(r"\s+".join(re.escape(piece) for piece in pieces))
    match = pattern.search(text, start, end)
    return (match.start(), match.end()) if match else None


def _build_speech_timeline(
    db: Database,
    source: dict[str, Any],
    timeline: dict[str, Any],
    text: str,
    audio_duration_ms: int,
) -> dict[str, Any]:
    raw_items = timeline.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise HandoffError("Speech timeline has no items")
    snapshot = json.loads(source["voice_snapshot_json"]) if source.get("voice_snapshot_json") else None
    spans = _source_spans(text, raw_items, snapshot)
    segments = {
        int(row["segment_index"]): dict(row)
        for row in db.fetch_all(
            "SELECT id,segment_index FROM segments WHERE job_chapter_id=?",
            (source["job_chapter_id"],),
        )
    }
    items: list[dict[str, Any]] = []
    previous_end = 0
    for position, (raw, span) in enumerate(zip(raw_items, spans), start=1):
        start_ms, end_ms = int(raw["start_ms"]), int(raw["end_ms"])
        if start_ms < 0 or end_ms <= start_ms or start_ms < previous_end:
            raise HandoffError(f"Invalid or overlapping speech timing at item {position}")
        segment = segments.get(int(raw["index"]))
        if not segment:
            raise HandoffError(f"Timeline segment {raw['index']} is missing from checkpoint data")
        role = str(raw.get("speaker_role") or "narrator")
        if role not in {"narrator", "character"}:
            raise HandoffError(f"Unsupported speaker role at item {position}")
        source_start, source_end, utterance_id = span
        items.append(
            {
                "utterance_id": utterance_id,
                "segment_id": int(segment["id"]),
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": str(raw["text"]),
                "speaker_type": role,
                "character_id": raw.get("character_id"),
                "character_name": raw.get("character_name"),
                "voice_id": str(raw.get("voice_id") or source["voice_name"]),
                "source_start": source_start,
                "source_end": source_end,
            }
        )
        previous_end = end_ms
    if abs(previous_end - audio_duration_ms) > DURATION_TOLERANCE_MS:
        raise HandoffError(
            f"Speech timeline duration {previous_end}ms differs from audio {audio_duration_ms}ms"
        )
    return {
        "schema": SPEECH_TIMELINE_SCHEMA,
        "duration_ms": audio_duration_ms,
        "items": items,
    }


def _character_seed(db: Database, source: dict[str, Any], speech: dict[str, Any]) -> dict[str, Any]:
    ids = sorted(
        {int(item["character_id"]) for item in speech["items"] if item.get("character_id") is not None}
    )
    characters: list[dict[str, Any]] = []
    for character_id in ids:
        row = db.fetch_one(
            "SELECT * FROM characters WHERE id=? AND book_id=?",
            (character_id, source["book_id"]),
        )
        if not row:
            raise HandoffError(f"Character {character_id} referenced by timeline is missing")
        characters.append(
            {
                "character_id": str(character_id),
                "canonical_name": str(row["display_name"]),
                "aliases": [],
                "gender": "unknown",
                "role": "unknown",
                "description": "",
                "speech_style": "",
                "voice_id": str(row["default_voice_id"]),
                "visual_notes": None,
            }
        )
    return {"schema": CHARACTER_SEED_SCHEMA, "characters": characters}


def export_chapter_handoff(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    chapter_id: int,
    job_id: int | None = None,
    export_root: Path | None = None,
    overwrite: bool = False,
    duration_probe: Callable[[Path], int] = probe_duration_ms,
) -> dict[str, Any]:
    source = _resolve_source(db, chapter_id, job_id)
    audio_source = _verify_source_artifact(source, "Audio")
    timeline_row = _timeline_artifact(db, source)
    timeline_source = _verify_source_artifact(timeline_row, "Timeline")
    try:
        timeline_payload = json.loads(timeline_source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HandoffError("Speech timeline JSON is invalid") from exc
    text = store.read_text(source["content_path"])
    if sha256_text(text) != source["content_sha256"]:
        raise HandoffError("Pinned TextRevision hash mismatch")
    audio_duration_ms = duration_probe(audio_source)
    if source.get("duration_ms") and abs(int(source["duration_ms"]) - audio_duration_ms) > DURATION_TOLERANCE_MS:
        raise HandoffError("Audio duration differs from verified artifact metadata")
    speech = _build_speech_timeline(db, source, timeline_payload, text, audio_duration_ms)
    seed = _character_seed(db, source, speech)
    identity = {
        "schema": HANDOFF_SCHEMA,
        "chapter_id": int(source["chapter_id"]),
        "job_id": int(source["job_id"]),
        "text_revision_hash": source["content_sha256"],
        "casting_plan_hash": source.get("casting_plan_sha256"),
        "audio_hash": source["sha256"],
        "speech_timeline_hash": sha256_text(_canonical(speech)),
        "character_seed_hash": sha256_text(_canonical(seed)),
    }
    identity_hash = sha256_text(_canonical(identity))
    export_id = (
        f"{safe_slug(str(source['book_title']), 'book')}-chapter-"
        f"{int(source['chapter_number']):04d}-{identity_hash[:12]}"
    )
    root = (export_root or config.youtube_export_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / export_id
    if destination.exists() and not overwrite:
        manifest = verify_handoff(destination)
        if manifest.get("identity_hash") != identity_hash:
            raise HandoffError("Existing export folder has a different source identity")
        return {"path": destination, "manifest": manifest, "reused": True}
    staging = root / f".{export_id}.partial-{uuid.uuid4().hex}"
    previous: Path | None = None
    try:
        (staging / "audio").mkdir(parents=True)
        content_path = staging / "content.md"
        audio_relative = f"audio/narration{audio_source.suffix.lower()}"
        audio_path = staging / audio_relative
        speech_path = staging / "speech_timeline.json"
        seed_path = staging / "character_seed.json"
        content = f"# {source['book_title']} — {source['chapter_title']}\n\n## Narration\n\n{text}\n"
        atomic_write_text(content_path, content)
        shutil.copy2(audio_source, audio_path)
        atomic_write_json(speech_path, speech)
        atomic_write_json(seed_path, seed)
        artifacts = {
            "content": "content.md",
            "audio": audio_relative,
            "speech_timeline": "speech_timeline.json",
            "character_seed": "character_seed.json",
        }
        files = {
            relative: {"size": (staging / relative).stat().st_size, "sha256": sha256_file(staging / relative)}
            for relative in artifacts.values()
        }
        manifest = {
            "schema": HANDOFF_SCHEMA,
            "export_id": export_id,
            "identity_hash": identity_hash,
            "created_at": _utcnow(),
            "source": {
                "book_id": int(source["book_id"]),
                "book_title": str(source["book_title"]),
                "chapter_ids": [int(source["chapter_id"])],
                "chapter_number": int(source["chapter_number"]),
                "chapter_title": str(source["chapter_title"]),
                "job_id": int(source["job_id"]),
                "text_revision_id": int(source["text_revision_id"]),
                "text_revision_hash": source["content_sha256"],
                "casting_plan_id": source.get("casting_plan_id"),
                "casting_plan_hash": source.get("casting_plan_sha256"),
                "audio_artifact_id": int(source["id"]),
                "audio_hash": source["sha256"],
                "speech_timeline_hash": files["speech_timeline.json"]["sha256"],
                "character_seed_hash": files["character_seed.json"]["sha256"],
            },
            "artifacts": artifacts,
            "files": files,
            "summary": {
                "duration_ms": audio_duration_ms,
                "utterance_count": len(speech["items"]),
                "character_count": len(seed["characters"]),
            },
        }
        atomic_write_json(staging / "handoff.json", manifest)
        verify_handoff(staging)
        if destination.exists():
            previous = root / f".{export_id}.previous-{uuid.uuid4().hex}"
            destination.rename(previous)
        staging.rename(destination)
        if previous:
            shutil.rmtree(previous)
        db.audit(
            "youtube_handoff_exported",
            job_id=int(source["job_id"]),
            chapter_id=int(source["chapter_id"]),
            details={"export_id": export_id, "identity_hash": identity_hash},
        )
        return {"path": destination, "manifest": manifest, "reused": False}
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if previous and previous.exists() and not destination.exists():
            previous.rename(destination)
        raise
