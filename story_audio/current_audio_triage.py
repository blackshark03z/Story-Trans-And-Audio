"""Read-only, current-artifact listening triage for the Audio workspace."""

from __future__ import annotations

import json
import sqlite3
import statistics
from contextlib import closing
from pathlib import Path
from typing import Any

from .audio_qa import QaThresholds, analyze_audio_file
from .files import sha256_file, sha256_text


class CurrentAudioTriageError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _readonly_connection(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def _current_binding(db_path: Path, artifact_id: int) -> dict[str, Any]:
    with closing(_readonly_connection(db_path)) as connection:
        current = connection.execute(
            """
            SELECT c.id AS chapter_id, c.active_audio_artifact_id,
                   a.id AS artifact_id, a.job_chapter_id, a.path, a.sha256,
                   a.artifact_type, a.duration_ms
            FROM chapters c JOIN artifacts a ON a.id=c.active_audio_artifact_id
            WHERE a.id=? AND a.deleted_at IS NULL
            """,
            (artifact_id,),
        ).fetchone()
        if current is not None:
            return dict(current)
        existing = connection.execute("SELECT id FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
    if existing is None:
        raise CurrentAudioTriageError("MISSING_ARTIFACT", "Không tìm thấy audio đã chọn.")
    raise CurrentAudioTriageError("STALE_ARTIFACT", "Audio đã chọn không còn là bản hiện tại.")


def _verified_file(row: dict[str, Any], *, label: str) -> Path:
    raw_path = str(row.get("path") or "")
    if not raw_path:
        raise CurrentAudioTriageError("BLOCKED_BINDING", f"{label} không có đường dẫn đã pin.")
    path = Path(raw_path).resolve()
    if not path.exists() or not path.is_file():
        raise CurrentAudioTriageError("BLOCKED_INTEGRITY", f"Không tìm thấy {label} đã pin.")
    expected = str(row.get("sha256") or "")
    if not expected or sha256_file(path) != expected:
        raise CurrentAudioTriageError("BLOCKED_INTEGRITY", f"SHA-256 của {label} không khớp bản hiện tại.")
    return path


def _supporting_artifacts(db_path: Path, binding: dict[str, Any], final_path: Path) -> dict[str, dict[str, Any]]:
    job_chapter_id = binding.get("job_chapter_id")
    if not job_chapter_id:
        raise CurrentAudioTriageError("BLOCKED_BINDING", "Audio hiện tại không có binding Job/chương để kiểm tra.")
    with closing(_readonly_connection(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT id, artifact_type, path, sha256, duration_ms
            FROM artifacts
            WHERE chapter_id=? AND job_chapter_id=? AND deleted_at IS NULL
              AND artifact_type IN ('chapter_master_wav','segment_timeline_json')
            ORDER BY id DESC
            """,
            (binding["chapter_id"], job_chapter_id),
        ).fetchall()
    selected: dict[str, dict[str, Any]] = {}
    for artifact_type in ("chapter_master_wav", "segment_timeline_json"):
        candidates = [dict(row) for row in rows if row["artifact_type"] == artifact_type]
        same_render = [row for row in candidates if Path(str(row["path"])).resolve().parent == final_path.parent]
        if len(same_render) == 1:
            selected[artifact_type] = same_render[0]
        elif len(candidates) == 1:
            selected[artifact_type] = candidates[0]
        else:
            raise CurrentAudioTriageError("BLOCKED_BINDING", f"Không xác định được {artifact_type} đúng với audio hiện tại.")
    return selected


def _timeline_and_segments(db_path: Path, binding: dict[str, Any], timeline_path: Path) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    try:
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CurrentAudioTriageError("BLOCKED_INTEGRITY", "Không đọc được timeline đã pin.") from exc
    items = timeline.get("items")
    if not isinstance(items, list) or not items:
        raise CurrentAudioTriageError("BLOCKED_TIMELINE", "Timeline đã pin không có phân đoạn hợp lệ.")
    if int(timeline.get("chapter_id") or 0) != int(binding["chapter_id"]):
        raise CurrentAudioTriageError("BLOCKED_TIMELINE", "Timeline không khớp chương của audio hiện tại.")
    with closing(_readonly_connection(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT id, segment_index, wav_path, audio_sha256, duration_ms,
                   speaker_role, resolved_voice_id, text_sha256
            FROM segments WHERE job_chapter_id=? ORDER BY segment_index
            """,
            (binding["job_chapter_id"],),
        ).fetchall()
    segments = {int(row["segment_index"]): dict(row) for row in rows}
    if not segments:
        raise CurrentAudioTriageError("BLOCKED_TIMELINE", "Không có segment binding cho audio hiện tại.")
    normalized: list[dict[str, Any]] = []
    for item in items:
        try:
            sequence = int(item["index"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CurrentAudioTriageError("BLOCKED_TIMELINE", "Timeline có sequence không hợp lệ.") from exc
        segment = segments.get(sequence)
        if segment is None:
            raise CurrentAudioTriageError("BLOCKED_TIMELINE", "Timeline không khớp segment binding hiện tại.")
        if item.get("segment_sha256") and str(item["segment_sha256"]) != str(segment.get("audio_sha256") or ""):
            raise CurrentAudioTriageError("BLOCKED_TIMELINE", "SHA segment trong timeline không khớp binding.")
        if item.get("voice_id") and str(item["voice_id"]) != str(segment.get("resolved_voice_id") or ""):
            raise CurrentAudioTriageError("BLOCKED_TIMELINE", "Giọng trong timeline không khớp binding.")
        if item.get("text") is not None and segment.get("text_sha256"):
            if sha256_text(str(item["text"])) != str(segment["text_sha256"]):
                raise CurrentAudioTriageError("BLOCKED_TIMELINE", "Nội dung trong timeline không khớp binding.")
        normalized.append({**item, "sequence": sequence})
    return normalized, segments


def _shortlist_item(
    item: dict[str, Any],
    *,
    label: str,
    reason: str,
    priority: str,
    segment: dict[str, Any] | None = None,
    risk_kind: str | None = None,
    repair_kind: str | None = None,
) -> dict[str, Any]:
    result = {
        "timestamp_ms": max(0, int(item.get("start_ms") or 0)),
        "end_ms": max(0, int(item.get("end_ms") or item.get("start_ms") or 0)),
        "label": label,
        "reason": reason,
        "priority": priority,
        "sequence": int(item["sequence"]),
        "segment_id": int(segment["id"]) if segment and segment.get("id") else None,
        "segment_audio_sha256": str(segment.get("audio_sha256") or "") if segment else None,
        "speaker": item.get("speaker_role") or None,
        "voice": item.get("voice_id") or None,
        "text": item.get("text") or None,
    }
    if risk_kind:
        result["risk_kind"] = risk_kind
    if repair_kind:
        result["repair"] = {
            "supported": True,
            "kind": repair_kind,
            "label": "Có thể sửa tự động",
            "effect": "Điểm này có tham số sửa xác định và sẽ được gom cùng các điểm đã chọn trong một yêu cầu sửa cho chương.",
        }
    elif risk_kind:
        result["repair"] = {
            "supported": False,
            "kind": None,
            "label": "Cần Human QA",
            "effect": "Máy chưa có cách tự sửa đáng tin cậy; điểm này vẫn được gom vào cùng yêu cầu sửa để người dùng rà soát.",
        }
    return result


_PRIORITY_ORDER = {"hard_clipping": 0, "technical_risk": 1, "voice_sample": 2, "boundary": 3}
_MAX_RISK_POINTS = 8
_MAX_SHORTLIST_POINTS = 12


def _merge_shortlist(items: list[dict[str, Any]], candidate: dict[str, Any], *, maximum: int) -> None:
    """Keep one seek point per sequence/timestamp, retaining the higher priority reason."""

    identity = (candidate.get("sequence"), candidate.get("timestamp_ms"))
    for index, existing in enumerate(items):
        if (existing.get("sequence"), existing.get("timestamp_ms")) != identity:
            continue
        candidate_priority = _PRIORITY_ORDER.get(str(candidate.get("priority")), 99)
        existing_priority = _PRIORITY_ORDER.get(str(existing.get("priority")), 99)
        candidate_is_actionable = bool((candidate.get("repair") or {}).get("supported"))
        existing_is_actionable = bool((existing.get("repair") or {}).get("supported"))
        if candidate_priority < existing_priority or (
            candidate_priority == existing_priority and candidate_is_actionable and not existing_is_actionable
        ):
            items[index] = candidate
        return
    if len(items) < maximum:
        items.append(candidate)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return float(ordered[index])


def _machine_assessment(
    *,
    segment_count: int,
    analyzed_segment_count: int,
    risk_counts: dict[str, int],
    shortlist_count: int,
) -> dict[str, Any]:
    """Build an explainable rule-based technical score, never a Human-QA verdict."""

    penalty = min(60, risk_counts.get("hard_clipping", 0) * 40)
    penalty += min(24, risk_counts.get("near_clipping", 0) * 8)
    penalty += min(20, risk_counts.get("silence", 0) * 5)
    penalty += min(16, risk_counts.get("pacing", 0) * 4)
    penalty += min(18, risk_counts.get("loudness", 0) * 6)
    technical_score = max(0, min(100, 100 - penalty))
    coverage_percent = round((analyzed_segment_count / segment_count) * 100) if segment_count else 0
    confidence = "high" if coverage_percent == 100 else "medium" if coverage_percent >= 60 else "limited"
    if shortlist_count:
        next_action = f"Nghe {shortlist_count} điểm được ưu tiên, chọn hoặc bỏ điểm, rồi tạo một yêu cầu sửa cho cả chương."
    elif coverage_percent == 100:
        next_action = "Nghe kiểm tra các mẫu đại diện rồi chọn Chấp nhận hoặc Cần sửa."
    else:
        next_action = "Máy chỉ kiểm tra được final và phần dữ liệu còn giữ; hãy nghe kỹ hơn trước khi quyết định."
    return {
        "technical_score": technical_score,
        "coverage_percent": coverage_percent,
        "confidence": confidence,
        "method": "rule_based_technical_v1",
        "risk_counts": risk_counts,
        "next_action": next_action,
        "capabilities": {
            "technical": "scored",
            "source_binding": "verified",
            "spoken_content": "not_scored",
            "acoustic_voice_match": "not_scored",
            "naturalness": "not_scored",
        },
        "limitations": [
            "Điểm này chỉ phản ánh kỹ thuật và độ đầy đủ của phép kiểm tra.",
            "Máy chưa chấm độ đúng của lời đọc, độ giống giọng hoặc độ tự nhiên.",
            "Human QA vẫn là quyết định cuối cùng.",
        ],
    }


def analyze_current_audio(db_path: Path, artifact_id: int) -> dict[str, Any]:
    """Return a non-persistent, exact-current listening shortlist."""

    binding = _current_binding(Path(db_path), int(artifact_id))
    final_path = _verified_file(binding, label="audio hiện tại")
    support = _supporting_artifacts(Path(db_path), binding, final_path)
    master_path = _verified_file(support["chapter_master_wav"], label="master WAV")
    timeline_path = _verified_file(support["segment_timeline_json"], label="timeline")
    timeline, segments = _timeline_and_segments(Path(db_path), binding, timeline_path)
    thresholds = QaThresholds()
    try:
        final_metrics = analyze_audio_file(final_path, thresholds=thresholds)
    except Exception as exc:
        raise CurrentAudioTriageError("BLOCKED_DECODE", "Không thể xác minh decode của audio hiện tại.") from exc

    risk_points: list[dict[str, Any]] = []
    risk_counts = {"hard_clipping": 0, "near_clipping": 0, "silence": 0, "pacing": 0, "loudness": 0}
    risks_found = bool(final_metrics.get("hard_clipping_sample_count"))
    if risks_found:
        risk_counts["hard_clipping"] += 1
        first_segment = segments[int(timeline[0]["sequence"])]
        _merge_shortlist(risk_points, _shortlist_item(timeline[0], label="Kiểm tra clipping", reason="Final audio có mẫu chạm full scale.", priority="hard_clipping", segment=first_segment, risk_kind="hard_clipping", repair_kind="reduce_peak"), maximum=10_000_000)

    missing_segment_wavs = 0
    analyzed_segments: list[tuple[dict[str, Any], dict[str, Any]]] = []
    realized_voices: set[str] = set()
    representative_by_voice: dict[str, dict[str, Any]] = {}
    for item in timeline:
        segment = segments[int(item["sequence"])]
        voice = str(item.get("voice_id") or segment.get("resolved_voice_id") or "")
        if voice:
            realized_voices.add(voice)
            representative_by_voice.setdefault(voice, item)
        wav_path = Path(str(segment.get("wav_path") or "")).resolve() if segment.get("wav_path") else None
        if wav_path is None or not wav_path.exists():
            missing_segment_wavs += 1
            continue
        if not segment.get("audio_sha256") or sha256_file(wav_path) != str(segment["audio_sha256"]):
            raise CurrentAudioTriageError("BLOCKED_INTEGRITY", "SHA của segment không khớp binding.")
        try:
            metrics = analyze_audio_file(wav_path, thresholds=thresholds)
        except Exception as exc:
            raise CurrentAudioTriageError("BLOCKED_DECODE", "Không thể decode một segment đã pin.") from exc
        analyzed_segments.append((item, metrics))

    trailing_values = [float(metrics.get("trailing_silence_ms") or 0) for _, metrics in analyzed_segments]
    trailing_median = float(statistics.median(trailing_values)) if trailing_values else 0.0
    trailing_p95 = _percentile(trailing_values, 0.95)
    voice_cps: dict[str, list[float]] = {}
    voice_loudness: dict[str, list[float]] = {}
    for item, metrics in analyzed_segments:
        voice = str(item.get("voice_id") or "")
        duration_ms = int(metrics.get("duration_ms") or item.get("duration_ms") or 0)
        text = str(item.get("text") or "")
        if voice and duration_ms > 0 and text:
            voice_cps.setdefault(voice, []).append(len(text) / (duration_ms / 1000.0))
        if voice and metrics.get("mean_volume_dbfs") is not None:
            voice_loudness.setdefault(voice, []).append(float(metrics["mean_volume_dbfs"]))

    previous_loudness: float | None = None
    for item, metrics in analyzed_segments:
        segment = segments[int(item["sequence"])]
        voice = str(item.get("voice_id") or "")
        flags: list[tuple[str, str, str, str, str | None]] = []
        if metrics.get("hard_clipping_sample_count"):
            flags.append(("hard_clipping", "Clipping", "Segment có mẫu chạm full scale.", "hard_clipping", "reduce_peak"))
        if metrics.get("near_clipping_sample_count"):
            flags.append(("near_clipping", "Mức âm sát ngưỡng", "Segment có mẫu âm sát full scale.", "technical_risk", None))
        longest_internal = int(metrics.get("longest_internal_silence_ms") or 0)
        if longest_internal >= max(1200, thresholds.long_internal_silence_ms * 3):
            flags.append(("silence", "Khoảng lặng bất thường", f"Có khoảng lặng bên trong dài {longest_internal} ms.", "technical_risk", None))
        leading = int(metrics.get("leading_silence_ms") or 0)
        if leading >= max(800, thresholds.long_leading_silence_ms * 3):
            flags.append(("silence", "Mở đầu chậm", f"Segment bắt đầu bằng {leading} ms im lặng.", "technical_risk", "trim_leading_silence"))
        trailing = int(metrics.get("trailing_silence_ms") or 0)
        trailing_is_outlier = trailing >= max(1200, int(trailing_median + thresholds.trailing_silence_excess_ms)) or (
            trailing > trailing_p95 and trailing >= thresholds.long_trailing_silence_ms
        )
        if trailing_is_outlier:
            flags.append(("silence", "Khoảng nghỉ dài", f"Khoảng nghỉ cuối segment dài {trailing} ms, khác nền chung của chương.", "technical_risk", "trim_trailing_silence"))
        duration_ms = int(metrics.get("duration_ms") or item.get("duration_ms") or 0)
        text = str(item.get("text") or "")
        cps = len(text) / (duration_ms / 1000.0) if duration_ms > 0 and text else None
        if cps is not None and (cps < thresholds.speech_rate_floor_cps or cps > thresholds.speech_rate_ceiling_cps):
            flags.append(("pacing", "Nhịp đọc khác biệt", f"Mật độ lời đọc {cps:.1f} ký tự/giây nằm ngoài dải kiểm tra.", "technical_risk", None))
        elif cps is not None and len(voice_cps.get(voice, [])) >= thresholds.min_voice_group_for_outlier_stats:
            group_cps = voice_cps[voice]
            median_cps = float(statistics.median(group_cps))
            mad_cps = float(statistics.median(abs(value - median_cps) for value in group_cps))
            if abs(cps - median_cps) > max(2.0, thresholds.speech_rate_mad_multiplier * mad_cps):
                flags.append(("pacing", "Nhịp đọc khác biệt", "Nhịp đoạn này khác đáng kể so với các đoạn cùng giọng.", "technical_risk", None))
        loudness = float(metrics["mean_volume_dbfs"]) if metrics.get("mean_volume_dbfs") is not None else None
        group = voice_loudness.get(voice, [])
        loudness_repair_supported = False
        if loudness is not None and len(group) >= thresholds.min_voice_group_for_outlier_stats:
            voice_median = float(statistics.median(group))
            if abs(loudness - voice_median) > thresholds.loudness_outlier_db:
                flags.append(("loudness", "Âm lượng không đều", "Mức âm khác đáng kể so với các đoạn cùng giọng.", "technical_risk", "normalize_loudness"))
                loudness_repair_supported = True
        if loudness is not None and previous_loudness is not None and abs(loudness - previous_loudness) > thresholds.adjacent_loudness_jump_db:
            flags.append(("loudness", "Âm lượng chuyển đột ngột", "Mức âm thay đổi mạnh so với đoạn ngay trước.", "technical_risk", "normalize_loudness" if loudness_repair_supported else None))
        if loudness is not None:
            previous_loudness = loudness
        for risk_kind, label, reason, priority, repair_kind in flags:
            risks_found = True
            risk_counts[risk_kind] += 1
            _merge_shortlist(risk_points, _shortlist_item(item, label=label, reason=reason, priority=priority, segment=segment, risk_kind=risk_kind, repair_kind=repair_kind), maximum=10_000_000)

    shortlist: list[dict[str, Any]] = []
    mandatory_count = min(_MAX_SHORTLIST_POINTS, len(realized_voices) + 2)
    risk_budget = min(_MAX_RISK_POINTS, max(0, _MAX_SHORTLIST_POINTS - mandatory_count))
    risk_points.sort(key=lambda point: (_PRIORITY_ORDER[str(point["priority"])], int(point["sequence"]), int(point["timestamp_ms"])))
    for point in risk_points:
        if len(shortlist) >= risk_budget:
            break
        _merge_shortlist(shortlist, point, maximum=risk_budget)
    for voice in sorted(realized_voices):
        sample = representative_by_voice[voice]
        _merge_shortlist(shortlist, _shortlist_item(sample, label="Mẫu giọng", reason="Một đoạn đại diện của giọng đã xuất hiện.", priority="voice_sample", segment=segments[int(sample["sequence"])]), maximum=_MAX_SHORTLIST_POINTS)
    _merge_shortlist(shortlist, _shortlist_item(timeline[0], label="Mở đầu", reason="Kiểm tra đoạn mở đầu.", priority="boundary", segment=segments[int(timeline[0]["sequence"])]), maximum=_MAX_SHORTLIST_POINTS)
    _merge_shortlist(shortlist, _shortlist_item(timeline[-1], label="Kết thúc", reason="Kiểm tra đoạn kết thúc.", priority="boundary", segment=segments[int(timeline[-1]["sequence"])]), maximum=_MAX_SHORTLIST_POINTS)

    mode = "degraded" if missing_segment_wavs else "full"
    state = "degraded" if missing_segment_wavs else "attention" if risks_found else "clear"
    assessment = _machine_assessment(
        segment_count=len(timeline),
        analyzed_segment_count=len(analyzed_segments),
        risk_counts=risk_counts,
        shortlist_count=len(shortlist),
    )
    final_binding = _current_binding(Path(db_path), int(artifact_id))
    if (
        str(final_binding.get("sha256") or "") != str(binding.get("sha256") or "")
        or int(final_binding.get("job_chapter_id") or 0) != int(binding.get("job_chapter_id") or 0)
    ):
        raise CurrentAudioTriageError("STALE_ARTIFACT", "Audio đã thay đổi trong khi máy đang kiểm tra.")
    return {
        "state": state,
        "mode": mode,
        "artifact": {"id": int(binding["artifact_id"]), "sha256": binding["sha256"]},
        "shortlist": shortlist,
        "summary": {
            "segment_count": len(timeline),
            "analyzed_segment_wavs": len(analyzed_segments),
            "missing_segment_wavs": missing_segment_wavs,
            "risk_detected": risks_found,
            "risk_count": sum(risk_counts.values()),
            "realized_voice_count": len(realized_voices),
        },
        "assessment": assessment,
        "human_qa": "required",
        "mutation_performed": False,
    }
