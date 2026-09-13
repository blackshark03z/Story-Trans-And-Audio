"""Deterministic offline repair candidates for exact current audio segments."""

from __future__ import annotations

import json
import statistics
import subprocess
from pathlib import Path
from typing import Any

from .audio_qa import QaThresholds, analyze_audio_file
from .config import Settings
from .db import Database, utcnow
from .files import sha256_file
from .storage import ContentStore


SUPPORTED_REPAIRS = {
    "trim_leading_silence",
    "trim_trailing_silence",
    "reduce_peak",
    "normalize_loudness",
}
REPAIR_ORDER = (
    "trim_leading_silence",
    "trim_trailing_silence",
    "reduce_peak",
    "normalize_loudness",
)


class MachineAudioRepairError(RuntimeError):
    pass


def _inside(path: Path, root: Path) -> bool:
    resolved = path.resolve(strict=False)
    parent = root.resolve(strict=False)
    return resolved == parent or parent in resolved.parents


def _duration_ms(path: Path) -> int:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(round(float(result.stdout.strip()) * 1000))


def _context(db: Database, artifact_id: int, artifact_sha256: str, segment_id: int) -> dict[str, Any]:
    row = db.fetch_one(
        """SELECT s.*, jc.job_id, jc.chapter_id, c.active_audio_artifact_id,
                  a.sha256 AS artifact_sha256, j.status AS job_status
           FROM segments s
           JOIN job_chapters jc ON jc.id=s.job_chapter_id
           JOIN chapters c ON c.id=jc.chapter_id
           JOIN artifacts a ON a.id=c.active_audio_artifact_id AND a.job_chapter_id=jc.id
           JOIN jobs j ON j.id=jc.job_id
           WHERE s.id=? AND a.id=? AND a.deleted_at IS NULL""",
        (segment_id, artifact_id),
    )
    if not row or str(row["artifact_sha256"] or "") != str(artifact_sha256 or ""):
        raise MachineAudioRepairError("Audio hoặc segment đã thay đổi. Hãy tải lại kết quả máy trước khi sửa.")
    if row["status"] != "verified" or not row["wav_path"]:
        raise MachineAudioRepairError("Segment hiện tại không có WAV đã xác minh để tạo bản sửa thử.")
    if row["job_status"] in {"running", "repairing", "synthesizing", "assembling"}:
        raise MachineAudioRepairError("Job đang chạy; hãy chờ hoàn tất trước khi sửa audio hiện tại.")
    source = Path(str(row["wav_path"])).resolve()
    if not source.is_file() or sha256_file(source) != str(row["audio_sha256"] or ""):
        raise MachineAudioRepairError("WAV segment không còn khớp binding đã xác minh.")
    return dict(row)


def _loudness_target(db: Database, row: dict[str, Any]) -> float:
    peers = db.fetch_all(
        """SELECT wav_path,audio_sha256 FROM segments
           WHERE job_chapter_id=? AND resolved_voice_id=? AND status='verified' AND wav_path IS NOT NULL""",
        (row["job_chapter_id"], row["resolved_voice_id"]),
    )
    values: list[float] = []
    for peer in peers:
        path = Path(str(peer["wav_path"])).resolve()
        if not path.is_file() or sha256_file(path) != str(peer["audio_sha256"] or ""):
            continue
        value = analyze_audio_file(path, thresholds=QaThresholds()).get("mean_volume_dbfs")
        if value is not None:
            values.append(float(value))
    return float(statistics.median(values)) if len(values) >= 2 else -18.0


def _trailing_silence_target(db: Database, row: dict[str, Any]) -> int:
    values: list[int] = []
    peers = db.fetch_all(
        "SELECT wav_path,audio_sha256 FROM segments WHERE job_chapter_id=? AND status='verified' AND wav_path IS NOT NULL",
        (row["job_chapter_id"],),
    )
    for peer in peers:
        path = Path(str(peer["wav_path"])).resolve()
        if not path.is_file() or sha256_file(path) != str(peer["audio_sha256"] or ""):
            continue
        value = analyze_audio_file(path, thresholds=QaThresholds()).get("trailing_silence_ms")
        if value is not None:
            values.append(int(value))
    baseline = int(round(statistics.median(values))) if values else 250
    return max(200, min(300, baseline))


def _metric(kind: str, metrics: dict[str, Any], target: float | None = None) -> tuple[str, float, str]:
    if kind == "trim_leading_silence":
        value = float(metrics.get("leading_silence_ms") or 0)
        return "Khoảng lặng đầu", value, "ms"
    if kind == "trim_trailing_silence":
        value = float(metrics.get("trailing_silence_ms") or 0)
        return "Khoảng lặng cuối", value, "ms"
    if kind == "reduce_peak":
        value = float(metrics.get("hard_clipping_sample_count") or 0)
        return "Mẫu clipping", value, "mẫu"
    value = float(metrics.get("mean_volume_dbfs") or -120.0)
    return "Độ lệch âm lượng", abs(value - float(target or -18.0)), "dB"


def render_machine_repairs(
    db: Database,
    *,
    row: dict[str, Any],
    repair_kinds: list[str] | tuple[str, ...],
    destination: Path,
) -> dict[str, Any]:
    """Apply compatible offline transforms once and prove every target improves."""

    kinds = [kind for kind in REPAIR_ORDER if kind in set(repair_kinds)]
    unknown = sorted(set(repair_kinds) - SUPPORTED_REPAIRS)
    if unknown or not kinds:
        raise MachineAudioRepairError(
            "Yêu cầu sửa chứa phép xử lý chưa được hỗ trợ."
            if unknown
            else "Không có phép sửa offline hợp lệ."
        )
    source = Path(str(row["wav_path"])).resolve()
    if not source.is_file() or sha256_file(source) != str(row.get("audio_sha256") or ""):
        raise MachineAudioRepairError("WAV segment không còn khớp binding đã xác minh.")

    before = analyze_audio_file(source, thresholds=QaThresholds())
    duration_ms = int(before.get("duration_ms") or row.get("duration_ms") or 0)
    start_seconds: float | None = None
    end_seconds: float | None = None
    filters: list[str] = []
    targets: dict[str, float | None] = {}

    if "trim_leading_silence" in kinds:
        remove_ms = max(0, int(before.get("leading_silence_ms") or 0) - 250)
        if remove_ms <= 0:
            raise MachineAudioRepairError("Khoảng lặng đầu không còn vượt ngưỡng sửa.")
        start_seconds = remove_ms / 1000
        targets["trim_leading_silence"] = None
    if "trim_trailing_silence" in kinds:
        target_ms = _trailing_silence_target(db, row)
        remove_ms = max(0, int(before.get("trailing_silence_ms") or 0) - target_ms)
        if remove_ms <= 0:
            raise MachineAudioRepairError("Khoảng lặng cuối không còn vượt ngưỡng sửa.")
        end_seconds = max(0.05, (duration_ms - remove_ms) / 1000)
        targets["trim_trailing_silence"] = None
    if start_seconds is not None or end_seconds is not None:
        trim = "atrim="
        if start_seconds is not None:
            trim += f"start={start_seconds:.3f}"
        if end_seconds is not None:
            trim += (":" if start_seconds is not None else "") + f"end={end_seconds:.3f}"
        filters.extend([trim, "asetpts=PTS-STARTPTS"])
    if "reduce_peak" in kinds:
        if int(before.get("hard_clipping_sample_count") or 0) <= 0:
            raise MachineAudioRepairError("Đoạn này không còn mẫu clipping để sửa.")
        filters.extend(["volume=-1.0dB", "alimiter=limit=0.95"])
        targets["reduce_peak"] = None
    if "normalize_loudness" in kinds:
        target = _loudness_target(db, row)
        current = float(before.get("mean_volume_dbfs") or -120.0)
        gain = max(-6.0, min(6.0, target - current))
        if abs(gain) < 0.5:
            raise MachineAudioRepairError("Âm lượng đoạn này không còn lệch đủ để sửa.")
        filters.extend([f"volume={gain:.2f}dB", "alimiter=limit=0.95"])
        targets["normalize_loudness"] = target

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-i", str(source),
                "-af", ",".join(filters), "-c:a", "pcm_s16le", str(destination),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        digest = sha256_file(destination)
        if digest == str(row.get("audio_sha256") or ""):
            raise MachineAudioRepairError("Phép sửa không tạo ra thay đổi đo được.")
        after = analyze_audio_file(destination, thresholds=QaThresholds())
        comparisons = []
        for kind in kinds:
            label, before_value, unit = _metric(kind, before, targets.get(kind))
            _, after_value, _ = _metric(kind, after, targets.get(kind))
            if after_value >= before_value:
                raise MachineAudioRepairError(
                    f"Bản sửa không cải thiện chỉ số {label.lower()} nên đã bị loại."
                )
            comparisons.append(
                {
                    "repair_kind": kind,
                    "label": label,
                    "before": round(before_value, 1),
                    "after": round(after_value, 1),
                    "unit": unit,
                    "improved": True,
                }
            )
        return {
            "audio_sha256": digest,
            "duration_ms": _duration_ms(destination),
            "comparisons": comparisons,
        }
    except MachineAudioRepairError:
        destination.unlink(missing_ok=True)
        raise
    except FileNotFoundError as exc:
        destination.unlink(missing_ok=True)
        raise MachineAudioRepairError("Không tìm thấy công cụ xử lý audio offline trên máy này.") from exc
    except subprocess.CalledProcessError as exc:
        destination.unlink(missing_ok=True)
        raise MachineAudioRepairError("Không tạo được audio đã sửa; audio hiện tại vẫn được giữ nguyên.") from exc
    except (OSError, ValueError) as exc:
        destination.unlink(missing_ok=True)
        raise MachineAudioRepairError("Không xác minh được audio đã sửa; audio hiện tại vẫn được giữ nguyên.") from exc


def _repair_kind_from_path(path: Path) -> str | None:
    name = path.stem
    for kind in SUPPORTED_REPAIRS:
        if f"_{kind}_" in name:
            return kind
    return None


def _candidate_response(
    db: Database,
    *,
    artifact_id: int,
    artifact_sha256: str,
    row: dict[str, Any],
    attempt: Any,
    repair_kind: str,
    restored: bool = False,
) -> dict[str, Any]:
    source = Path(str(row["wav_path"])).resolve()
    candidate_path = Path(str(attempt["wav_path"])).resolve()
    if not candidate_path.is_file() or sha256_file(candidate_path) != str(attempt["audio_sha256"] or ""):
        raise MachineAudioRepairError("Bản sửa thử không còn khớp file đã xác minh. Hãy bỏ bản này và tạo lại.")
    target = _loudness_target(db, row) if repair_kind == "normalize_loudness" else None
    before = analyze_audio_file(source, thresholds=QaThresholds())
    after = analyze_audio_file(candidate_path, thresholds=QaThresholds())
    label, before_value, unit = _metric(repair_kind, before, target)
    _, after_value, _ = _metric(repair_kind, after, target)
    return {
        "artifact": {"id": artifact_id, "sha256": artifact_sha256},
        "segment_id": int(row["id"]),
        "repair_kind": repair_kind,
        "attempt_id": int(attempt["id"]),
        "candidate_audio_sha256": str(attempt["audio_sha256"]),
        "duration_ms": int(attempt["duration_ms"]),
        "comparison": {
            "label": label,
            "before": round(before_value, 1),
            "after": round(after_value, 1),
            "unit": unit,
            "improved": after_value < before_value,
        },
        "current_audio_url": f"/api/segments/{int(row['id'])}/audio",
        "candidate_audio_url": f"/api/segment-attempts/{int(attempt['id'])}/audio",
        "current_audio_changed": False,
        "mutation_performed": False,
        "restored": restored,
        "next_action": "Nghe hai bản rồi chọn Dùng bản sửa hoặc Giữ bản hiện tại.",
    }


def get_machine_repair_candidate(
    db: Database,
    config: Settings,
    *,
    artifact_id: int,
    artifact_sha256: str,
) -> dict[str, Any] | None:
    """Restore the one temporary candidate bound to the exact current artifact."""

    attempts = db.fetch_all(
        """SELECT sa.* FROM segment_attempts sa
           JOIN segments s ON s.id=sa.segment_id
           JOIN job_chapters jc ON jc.id=s.job_chapter_id
           JOIN chapters c ON c.id=jc.chapter_id
           WHERE c.active_audio_artifact_id=? AND sa.status='candidate'
           ORDER BY sa.id DESC""",
        (artifact_id,),
    )
    machine_attempts = []
    for attempt in attempts:
        path = Path(str(attempt["wav_path"] or "")).resolve(strict=False)
        if _inside(path, config.work_dir) and "machine_repair" in path.parts:
            machine_attempts.append(attempt)
    if not machine_attempts:
        return None
    if len(machine_attempts) > 1:
        raise MachineAudioRepairError("Audio này có nhiều bản sửa thử chưa xử lý. Hãy giữ hoặc dùng từng bản trước khi tiếp tục.")
    attempt = machine_attempts[0]
    repair_kind = _repair_kind_from_path(Path(str(attempt["wav_path"])))
    if not repair_kind:
        raise MachineAudioRepairError("Không nhận diện được phép sửa của bản thử hiện tại.")
    row = _context(db, artifact_id, artifact_sha256, int(attempt["segment_id"]))
    return _candidate_response(
        db,
        artifact_id=artifact_id,
        artifact_sha256=artifact_sha256,
        row=row,
        attempt=attempt,
        repair_kind=repair_kind,
        restored=True,
    )


def create_machine_repair_candidate(
    db: Database,
    config: Settings,
    *,
    artifact_id: int,
    artifact_sha256: str,
    segment_id: int,
    repair_kind: str,
) -> dict[str, Any]:
    if repair_kind not in SUPPORTED_REPAIRS:
        raise MachineAudioRepairError("Dấu hiệu này chưa có cách tự sửa đáng tin cậy; hãy đưa vào Human QA.")
    row = _context(db, artifact_id, artifact_sha256, segment_id)
    existing = get_machine_repair_candidate(
        db,
        config,
        artifact_id=artifact_id,
        artifact_sha256=artifact_sha256,
    )
    if existing:
        if int(existing["segment_id"]) == segment_id and existing["repair_kind"] == repair_kind:
            return existing
        raise MachineAudioRepairError("Chương này đã có một bản sửa thử chưa xử lý. Hãy mở lại điểm cũ để dùng hoặc giữ bản hiện tại.")
    if db.fetch_one("SELECT id FROM segment_attempts WHERE segment_id=? AND status='candidate'", (segment_id,)):
        raise MachineAudioRepairError("Đoạn này đang có một bản thử từ luồng sửa khác. Hãy xử lý bản đó trước.")

    attempt_number = int(db.fetch_one("SELECT COALESCE(MAX(attempt_number),0) AS value FROM segment_attempts WHERE segment_id=?", (segment_id,))["value"]) + 1
    candidate_dir = config.work_dir / f"job_{row['job_id']}" / f"chapter_{int(row['chapter_id']):04d}" / "machine_repair"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = candidate_dir / f"segment_{segment_id}_{repair_kind}_{attempt_number}.wav"
    try:
        rendered = render_machine_repairs(
            db, row=row, repair_kinds=[repair_kind], destination=candidate_path
        )
        candidate_hash = str(rendered["audio_sha256"])
        duration = int(rendered["duration_ms"])
        with db.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO segment_attempts(segment_id,attempt_number,status,wav_path,audio_sha256,duration_ms,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (segment_id, attempt_number, "candidate", str(candidate_path), candidate_hash, duration, utcnow()),
            )
            attempt_id = int(cursor.lastrowid)
    except MachineAudioRepairError:
        candidate_path.unlink(missing_ok=True)
        raise
    except FileNotFoundError as exc:
        candidate_path.unlink(missing_ok=True)
        raise MachineAudioRepairError("Không tìm thấy công cụ xử lý audio offline trên máy này.") from exc
    except subprocess.CalledProcessError as exc:
        candidate_path.unlink(missing_ok=True)
        raise MachineAudioRepairError("Không tạo được bản sửa thử; bản hiện tại vẫn được giữ nguyên.") from exc
    except (OSError, ValueError) as exc:
        candidate_path.unlink(missing_ok=True)
        raise MachineAudioRepairError("Không xác minh được bản sửa thử; bản hiện tại vẫn được giữ nguyên.") from exc

    attempt = db.fetch_one("SELECT * FROM segment_attempts WHERE id=?", (attempt_id,))
    return _candidate_response(
        db,
        artifact_id=artifact_id,
        artifact_sha256=artifact_sha256,
        row=row,
        attempt=attempt,
        repair_kind=repair_kind,
    )


def discard_machine_repair_candidate(db: Database, config: Settings, *, segment_id: int, attempt_id: int) -> dict[str, Any]:
    row = db.fetch_one(
        "SELECT * FROM segment_attempts WHERE id=? AND segment_id=? AND status='candidate'",
        (attempt_id, segment_id),
    )
    if not row:
        raise MachineAudioRepairError("Bản sửa thử không còn tồn tại hoặc đã được xử lý.")
    path = Path(str(row["wav_path"])).resolve(strict=False)
    if not _inside(path, config.work_dir):
        raise MachineAudioRepairError("Từ chối xóa candidate ngoài thư mục làm việc đã cấu hình.")
    with db.connect() as connection:
        connection.execute("DELETE FROM segment_attempts WHERE id=?", (attempt_id,))
    path.unlink(missing_ok=True)
    return {
        "segment_id": segment_id,
        "attempt_id": attempt_id,
        "status": "discarded",
        "candidate_deleted": True,
        "current_audio_changed": False,
    }


def accept_machine_repair_candidate(
    db: Database,
    store: ContentStore,
    config: Settings,
    *,
    artifact_id: int,
    artifact_sha256: str,
    segment_id: int,
    attempt_id: int,
) -> dict[str, Any]:
    """Promote an exact machine candidate and remove superseded audio history."""

    from .audio_retention import purge_audio_history
    from .segment_regeneration import accept_segment_candidate

    current = _context(db, artifact_id, artifact_sha256, segment_id)
    candidate = db.fetch_one(
        "SELECT * FROM segment_attempts WHERE id=? AND segment_id=? AND status='candidate'",
        (attempt_id, segment_id),
    )
    if not candidate or "machine_repair" not in Path(str(candidate["wav_path"])).parts:
        raise MachineAudioRepairError("Bản sửa thử không còn tồn tại hoặc không thuộc Máy kiểm tra.")
    candidate_path = Path(str(candidate["wav_path"])).resolve()
    if not _inside(candidate_path, config.work_dir) or not candidate_path.is_file():
        raise MachineAudioRepairError("Không xác minh được file bản sửa thử trong thư mục làm việc.")
    if sha256_file(candidate_path) != str(candidate["audio_sha256"] or ""):
        raise MachineAudioRepairError("Bản sửa thử đã thay đổi sau khi được tạo. Hãy bỏ bản này và tạo lại.")
    old_paths = [
        Path(str(row["wav_path"])).resolve(strict=False)
        for row in db.fetch_all("SELECT wav_path FROM segment_attempts WHERE segment_id=?", (segment_id,))
        if row["wav_path"]
    ]
    old_paths.append(Path(str(current["wav_path"])).resolve(strict=False))
    result = accept_segment_candidate(db, store, config, segment_id, attempt_id)
    retention = purge_audio_history(
        db,
        output_root=config.output_dir,
        work_root=config.work_dir,
        chapter_ids=[int(current["chapter_id"])],
    )
    with db.connect() as connection:
        connection.execute("DELETE FROM segment_attempts WHERE segment_id=?", (segment_id,))
        connection.execute(
            "DELETE FROM audit_events WHERE event_code IN ('segment_candidate_generated','segment_candidate_rejected','segment_candidate_accepted') AND chapter_id=?",
            (int(current["chapter_id"]),),
        )
    deleted_attempt_files = 0
    for path in set(old_paths):
        if path == candidate_path or not _inside(path, config.work_dir):
            continue
        if path.is_file():
            path.unlink()
            deleted_attempt_files += 1
    return {
        **result,
        "status": "accepted",
        "human_qa": "pending",
        "retention": retention,
        "deleted_attempt_files": deleted_attempt_files,
        "next_action": "Máy sẽ kiểm tra lại audio chương mới; Human QA vẫn cần quyết định.",
    }
