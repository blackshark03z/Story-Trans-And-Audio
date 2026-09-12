"""Compile and execute one artifact-bound chapter repair instruction."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import Settings
from .db import Database, utcnow
from .files import sha256_file
from .machine_audio_repair import (
    SUPPORTED_REPAIRS,
    MachineAudioRepairError,
    render_machine_repairs,
)
from .storage import ContentStore
from .synthesis_snapshot import load_segment_synthesis_input


class ChapterRepairInstructionError(RuntimeError):
    pass


def _timeline_items(db: Database, artifact: dict[str, Any]) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """SELECT path,sha256 FROM artifacts
           WHERE chapter_id=? AND job_chapter_id=? AND artifact_type='segment_timeline_json'
             AND deleted_at IS NULL ORDER BY id DESC""",
        (int(artifact["chapter_id"]), int(artifact["job_chapter_id"])),
    )
    final_dir = Path(str(artifact["path"])).resolve(strict=False).parent
    candidates = [row for row in rows if Path(str(row["path"])).resolve(strict=False).parent == final_dir]
    if len(candidates) != 1:
        raise ChapterRepairInstructionError("Không xác định được timeline đúng của Artifact nguồn.")
    path = Path(str(candidates[0]["path"])).resolve(strict=False)
    if not path.is_file() or sha256_file(path) != str(candidates[0]["sha256"] or ""):
        raise ChapterRepairInstructionError("Timeline nguồn không còn khớp SHA đã xác minh.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChapterRepairInstructionError("Không đọc được timeline nguồn.") from exc
    items = payload.get("items")
    if int(payload.get("chapter_id") or 0) != int(artifact["chapter_id"]) or not isinstance(items, list):
        raise ChapterRepairInstructionError("Timeline nguồn không khớp chương.")
    return [dict(item) for item in items]


def _verified_source_segment(
    db: Database,
    artifact: dict[str, Any],
    marker: dict[str, Any],
    timeline: list[dict[str, Any]],
) -> dict[str, Any]:
    segment_id = int(marker.get("segment_id") or 0)
    if not segment_id:
        if marker.get("timestamp_seconds") is None:
            raise ChapterRepairInstructionError("Vị trí sửa chưa có thời điểm nghe hoặc segment đã ghim.")
        timestamp_ms = round(float(marker["timestamp_seconds"]) * 1000)
        matches = [
            item
            for item in timeline
            if int(item.get("start_ms") or 0) <= timestamp_ms < int(item.get("end_ms") or 0)
        ]
        if len(matches) != 1:
            raise ChapterRepairInstructionError("Không ánh xạ được vị trí nghe vào đúng một segment.")
        sequence = int(matches[0].get("index") or 0)
        row = db.fetch_one(
            "SELECT * FROM segments WHERE job_chapter_id=? AND segment_index=?",
            (int(artifact["job_chapter_id"]), sequence),
        )
    else:
        row = db.fetch_one(
            "SELECT * FROM segments WHERE id=? AND job_chapter_id=?",
            (segment_id, int(artifact["job_chapter_id"])),
        )
    if not row or row["status"] != "verified" or not row["wav_path"]:
        raise ChapterRepairInstructionError("Vị trí sửa không còn trỏ tới segment đã xác minh.")
    segment = dict(row)
    source_path = Path(str(segment["wav_path"])).resolve(strict=False)
    actual_sha = str(segment["audio_sha256"] or "")
    bound_sha = str(marker.get("segment_audio_sha256") or actual_sha)
    if bound_sha != actual_sha or not source_path.is_file() or sha256_file(source_path) != actual_sha:
        raise ChapterRepairInstructionError("File segment nguồn không còn khớp SHA đã xác minh.")
    return segment


def _source_artifact(
    db: Database,
    chapter_id: int,
    artifact_id: int,
    *,
    require_media_binding: bool = True,
) -> dict[str, Any]:
    row = db.fetch_one(
        """SELECT a.*,c.active_audio_artifact_id
           FROM artifacts a JOIN chapters c ON c.id=a.chapter_id
           WHERE a.id=? AND a.chapter_id=? AND a.deleted_at IS NULL""",
        (artifact_id, chapter_id),
    )
    if not row or int(row["active_audio_artifact_id"] or 0) != int(artifact_id):
        raise ChapterRepairInstructionError(
            "Artifact nguồn không còn là audio hiện tại của chương."
        )
    if require_media_binding and not row["job_chapter_id"]:
        raise ChapterRepairInstructionError("Artifact nguồn không có JobChapter để đối chiếu segment.")
    path = Path(str(row["path"] or "")).resolve(strict=False)
    if require_media_binding and (
        not path.is_file() or sha256_file(path) != str(row["sha256"] or "")
    ):
        raise ChapterRepairInstructionError("File Artifact nguồn không còn khớp SHA đã xác minh.")
    return dict(row)


def compile_chapter_repair_instruction(
    db: Database,
    *,
    chapter_id: int,
    artifact_id: int,
    markers: list[dict[str, Any]],
    repeated_words: bool,
    global_speed_target: float | None,
    local_pacing_adjustment_required: bool,
) -> dict[str, Any]:
    """Bind reviewed markers to verified source segments without mutating media."""

    has_machine_actions = bool(
        markers or repeated_words or global_speed_target is not None or local_pacing_adjustment_required
    )
    artifact = _source_artifact(
        db,
        chapter_id,
        artifact_id,
        require_media_binding=has_machine_actions,
    )
    timeline = _timeline_items(db, artifact) if has_machine_actions else []
    actions: dict[tuple[int, str, str], dict[str, Any]] = {}
    repeated_word_locations = 0
    local_pace_locations = 0
    local_tempo_segments: set[int] = set()
    local_tempo_by_segment: dict[int, float] = {}
    for marker in markers:
        kind = str(marker.get("repair_kind") or "").strip()
        if kind and kind not in SUPPORTED_REPAIRS:
            raise ChapterRepairInstructionError(f"Phép sửa không được hỗ trợ: {kind}.")
        segment = _verified_source_segment(db, artifact, marker, timeline)
        segment_id = int(segment["id"])
        bound_sha = str(segment["audio_sha256"])
        issue = str(marker.get("issue") or "")
        risk_kind = str(marker.get("risk_kind") or "")
        pacing_only = (
            not kind
            and issue in {"too_slow", "too_fast"}
            and marker.get("local_pace") is not None
        )
        action_kind = "offline" if kind else "resynthesize"
        action_value = kind or "same_text_same_voice"
        if issue == "repeated_words":
            repeated_word_locations += 1
            action_kind, action_value = "resynthesize", "same_text_same_voice"
        local_pace = marker.get("local_pace")
        if local_pace is not None and abs(float(local_pace) - 1.0) >= 0.01:
            pace_value = float(local_pace)
            existing_pace = local_tempo_by_segment.get(segment_id)
            if existing_pace is not None and abs(existing_pace - pace_value) >= 0.001:
                raise ChapterRepairInstructionError(
                    "Một segment không thể có hai tốc độ sửa khác nhau."
                )
            local_tempo_by_segment[segment_id] = pace_value
            local_pace_locations += 1
            local_tempo_segments.add(segment_id)
            tempo_key = (segment_id, "tempo", f"{pace_value:.3f}")
            actions[tempo_key] = {
                "segment_id": segment_id,
                "segment_index": int(segment["segment_index"]),
                "segment_audio_sha256": bound_sha,
                "text_sha256": str(segment["text_sha256"]),
                "resolved_voice_id": str(segment["resolved_voice_id"] or ""),
                "action_kind": "tempo",
                "tempo": pace_value,
                "repair_kind": None,
                "machine_finding_key": str(marker.get("machine_finding_key") or "") or None,
                "timestamp_seconds": marker.get("timestamp_seconds"),
            }
        if not pacing_only:
            key = (segment_id, action_kind, action_value)
            actions[key] = {
                "segment_id": segment_id,
                "segment_index": int(segment["segment_index"]),
                "segment_audio_sha256": bound_sha,
                "text_sha256": str(segment["text_sha256"]),
                "resolved_voice_id": str(segment["resolved_voice_id"] or ""),
                "action_kind": action_kind,
                "repair_kind": kind or None,
                "risk_kind": risk_kind or None,
                "machine_finding_key": str(marker.get("machine_finding_key") or "") or None,
                "timestamp_seconds": marker.get("timestamp_seconds"),
            }

    if global_speed_target is not None and abs(float(global_speed_target) - 1.0) >= 0.01:
        for segment_row in db.fetch_all(
            "SELECT * FROM segments WHERE job_chapter_id=? ORDER BY segment_index",
            (int(artifact["job_chapter_id"]),),
        ):
            segment = dict(segment_row)
            marker = {"segment_id": int(segment["id"]), "segment_audio_sha256": segment["audio_sha256"]}
            segment = _verified_source_segment(db, artifact, marker, timeline)
            if int(segment["id"]) in local_tempo_segments:
                continue
            key = (int(segment["id"]), "tempo", f"{float(global_speed_target):.3f}")
            actions[key] = {
                "segment_id": int(segment["id"]),
                "segment_index": int(segment["segment_index"]),
                "segment_audio_sha256": str(segment["audio_sha256"]),
                "text_sha256": str(segment["text_sha256"]),
                "resolved_voice_id": str(segment["resolved_voice_id"] or ""),
                "action_kind": "tempo",
                "tempo": float(global_speed_target),
                "repair_kind": None,
                "scope": "global",
            }

    blockers = []
    if repeated_words and not repeated_word_locations:
        blockers.append("repeated_words_location_required")
    if local_pacing_adjustment_required and not local_pace_locations:
        blockers.append("local_pace_marker_required")
    if not actions:
        blockers.append("no_executable_repairs")
    ordered = sorted(
        actions.values(),
        key=lambda item: (
            item["segment_index"],
            item["action_kind"],
            str(item.get("repair_kind") or item.get("tempo") or ""),
        ),
    )
    requires_tts = any(item["action_kind"] == "resynthesize" for item in ordered)
    return {
        "source_artifact_sha256": str(artifact["sha256"]),
        "source_job_chapter_id": int(artifact["job_chapter_id"] or 0),
        "execution_mode": (
            "hybrid_segment_batch" if requires_tts else "offline_segment_batch"
        ) if not blockers else "blocked",
        "execution_ready": not blockers,
        "execution_blockers": blockers,
        "machine_actions": ordered,
        "machine_action_count": len(ordered),
        "resynthesis_segment_count": len(
            {item["segment_id"] for item in ordered if item["action_kind"] == "resynthesize"}
        ),
        "provider_call_required": requires_tts,
    }


def _tempo_audio(source: Path, destination: Path, tempo: float) -> dict[str, Any]:
    if not 0.5 <= tempo <= 2.0 or abs(tempo - 1.0) < 0.01:
        raise ChapterRepairInstructionError("Tốc độ sửa phải khác 1.0 và nằm trong khoảng 0.5-2.0.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af", f"atempo={tempo:.4f}", "-c:a", "pcm_s16le", str(destination)],
            capture_output=True,
            text=True,
            check=True,
        )
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(destination)],
            capture_output=True,
            text=True,
            check=True,
        )
        duration_ms = round(float(probe.stdout.strip()) * 1000)
        if duration_ms <= 0 or sha256_file(destination) == sha256_file(source):
            raise ChapterRepairInstructionError("Điều chỉnh tốc độ không tạo ra audio hợp lệ.")
        return {"audio_sha256": sha256_file(destination), "duration_ms": duration_ms}
    except (FileNotFoundError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        destination.unlink(missing_ok=True)
        raise ChapterRepairInstructionError("Không áp dụng được tốc độ đã duyệt.") from exc


def materialize_offline_repair_segments(
    db: Database,
    config: Settings,
    *,
    chapter_id: int,
    instruction: dict[str, Any],
    target_segments: list[dict[str, Any]],
    target_dir: Path,
    store: ContentStore | None = None,
    tts: Any | None = None,
) -> list[dict[str, Any]]:
    """Materialize all replacement segments from one frozen instruction."""

    if instruction.get("execution_mode") not in {"offline_segment_batch", "hybrid_segment_batch"} or not instruction.get("execution_ready"):
        reasons = ", ".join(instruction.get("execution_blockers") or ["instruction_not_ready"])
        raise ChapterRepairInstructionError(f"Bản sửa chưa có bộ thực thi an toàn: {reasons}.")
    artifact_id = int(instruction.get("replacement_for_artifact_id") or 0)
    artifact = _source_artifact(db, chapter_id, artifact_id)
    if str(artifact["sha256"] or "") != str(instruction.get("source_artifact_sha256") or ""):
        raise ChapterRepairInstructionError("Artifact nguồn đã thay đổi sau PREPARE.")
    source_job_chapter_id = int(instruction.get("source_job_chapter_id") or 0)
    if source_job_chapter_id != int(artifact["job_chapter_id"]):
        raise ChapterRepairInstructionError("JobChapter nguồn đã thay đổi sau PREPARE.")

    source_rows = [
        dict(row)
        for row in db.fetch_all(
            "SELECT * FROM segments WHERE job_chapter_id=? ORDER BY segment_index",
            (source_job_chapter_id,),
        )
    ]
    targets = sorted(target_segments, key=lambda row: int(row["segment_index"]))
    if len(source_rows) != len(targets) or not source_rows:
        raise ChapterRepairInstructionError("Cấu trúc segment replacement không còn khớp Artifact nguồn.")

    actions_by_index: dict[int, list[dict[str, Any]]] = {}
    expected_action_count = 0
    for action in instruction.get("machine_actions") or []:
        index = int(action.get("segment_index") or 0)
        actions_by_index.setdefault(index, []).append(dict(action))
        expected_action_count += 1

    written: list[Path] = []
    temporary_paths: set[Path] = set()
    evidence: list[dict[str, Any]] = []
    try:
        for position, (source, target) in enumerate(zip(source_rows, targets)):
            source_index = int(source["segment_index"])
            if (
                source_index != int(target["segment_index"])
                or str(source["text_sha256"]) != str(target["text_sha256"])
                or str(source["resolved_voice_id"] or "") != str(target["resolved_voice_id"] or "")
            ):
                raise ChapterRepairInstructionError(
                    "Text, thứ tự hoặc giọng segment replacement không còn khớp nguồn."
                )
            source_path = Path(str(source["wav_path"] or "")).resolve(strict=False)
            source_sha = str(source["audio_sha256"] or "")
            if source["status"] != "verified" or not source_path.is_file() or sha256_file(source_path) != source_sha:
                raise ChapterRepairInstructionError("Segment nguồn không còn là WAV đã xác minh.")
            segment_actions = actions_by_index.get(source_index, [])
            for expected in segment_actions:
                if int(expected.get("segment_id") or 0) != int(source["id"]) or str(
                    expected.get("segment_audio_sha256") or ""
                ) != source_sha:
                    raise ChapterRepairInstructionError("Binding phép sửa không còn khớp segment nguồn.")

            target_path = target_dir / f"{int(target['segment_index']):06d}.wav"
            offline_kinds = [str(item["repair_kind"]) for item in segment_actions if item.get("action_kind") == "offline"]
            tempos = [float(item["tempo"]) for item in segment_actions if item.get("action_kind") == "tempo"]
            resynthesize = any(item.get("action_kind") == "resynthesize" for item in segment_actions)
            stage_path = source_path
            temporary_stages: list[Path] = []
            if resynthesize:
                if store is None or tts is None:
                    raise ChapterRepairInstructionError("Bản sửa cần TTS nhưng worker không có synthesis dependency.")
                target_dir.mkdir(parents=True, exist_ok=True)
                stage_path = target_dir / f".{int(target['segment_index']):06d}.resynth.wav"
                temporary_paths.add(stage_path)
                synth_input = load_segment_synthesis_input(
                    target,
                    store,
                    is_final_segment=position == len(targets) - 1,
                )
                with db.connect() as connection:
                    connection.execute(
                        "UPDATE segments SET status='running',attempt_count=attempt_count+1,error_message=NULL WHERE id=?",
                        (int(target["id"]),),
                    )
                try:
                    tts.synthesize(synth_input=synth_input, output_path=stage_path)
                except Exception as exc:
                    raise ChapterRepairInstructionError(
                        f"Không tái tạo được segment {source_index}."
                    ) from exc
                if not stage_path.is_file() or sha256_file(stage_path) == source_sha:
                    raise ChapterRepairInstructionError("Tái tạo segment không tạo ra audio mới hợp lệ.")
                temporary_stages.append(stage_path)
                evidence.append({"segment_index": source_index, "action_kind": "resynthesize"})
            if offline_kinds:
                offline_destination = target_path if not tempos else target_dir / f".{int(target['segment_index']):06d}.offline.wav"
                if offline_destination != target_path:
                    temporary_paths.add(offline_destination)
                stage_row = {**source, "wav_path": str(stage_path), "audio_sha256": sha256_file(stage_path)}
                try:
                    result = render_machine_repairs(
                        db, row=stage_row, repair_kinds=offline_kinds, destination=offline_destination
                    )
                except MachineAudioRepairError as exc:
                    raise ChapterRepairInstructionError(str(exc)) from exc
                evidence.extend(
                    {"segment_index": source_index, "action_kind": "offline", **comparison}
                    for comparison in result["comparisons"]
                )
                if offline_destination != target_path:
                    temporary_stages.append(offline_destination)
                stage_path = offline_destination
            for tempo_index, tempo in enumerate(tempos):
                tempo_destination = target_path if tempo_index == len(tempos) - 1 else target_dir / f".{int(target['segment_index']):06d}.tempo{tempo_index}.wav"
                if tempo_destination != target_path:
                    temporary_paths.add(tempo_destination)
                _tempo_audio(stage_path, tempo_destination, tempo)
                if stage_path != source_path and stage_path != target_path:
                    stage_path.unlink(missing_ok=True)
                stage_path = tempo_destination
                if tempo_destination != target_path:
                    temporary_stages.append(tempo_destination)
                evidence.append({"segment_index": source_index, "action_kind": "tempo", "tempo": tempo})
            if segment_actions:
                if stage_path != target_path:
                    shutil.copy2(stage_path, target_path)
                digest = sha256_file(target_path)
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(target_path)],
                    capture_output=True, text=True, check=True,
                )
                duration_ms = round(float(probe.stdout.strip()) * 1000)
                for path in temporary_stages:
                    if path != target_path:
                        path.unlink(missing_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
                digest = sha256_file(target_path)
                duration_ms = int(source["duration_ms"])
            written.append(target_path)
            with db.connect() as connection:
                connection.execute(
                    """UPDATE segments SET status='verified',wav_path=?,audio_sha256=?,duration_ms=?,
                       verified_at=?,error_message=NULL WHERE id=?""",
                    (str(target_path), digest, duration_ms, utcnow(), int(target["id"])),
                )
        if len(evidence) != expected_action_count:
            raise ChapterRepairInstructionError("Không thực thi đủ mọi phép sửa đã ghim.")
    except Exception:
        for path in {*written, *temporary_paths, *(target_dir / f"{int(row['segment_index']):06d}.wav" for row in targets)}:
            path.unlink(missing_ok=True)
        with db.connect() as connection:
            for target in targets:
                connection.execute(
                    """UPDATE segments SET status='pending',wav_path=NULL,audio_sha256=NULL,
                       duration_ms=NULL,verified_at=NULL WHERE id=?""",
                    (int(target["id"]),),
                )
        raise
    return [
        dict(row)
        for row in db.fetch_all(
            "SELECT * FROM segments WHERE job_chapter_id=? ORDER BY segment_index",
            (int(targets[0]["job_chapter_id"]),),
        )
    ]
