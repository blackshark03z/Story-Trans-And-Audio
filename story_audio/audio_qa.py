from __future__ import annotations

import argparse
from contextlib import closing
import json
import math
import sqlite3
import statistics
import subprocess
import sys
import time
import wave
from array import array
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import canonical_production_db_path
from .files import atomic_write_bytes, sha256_file, sha256_text


AUDIO_QA_SCHEMA = "story-audio-audio-qa/v1"
MANIFEST_SCHEMA = "story-audio-production-manifest/v1"
IMPLEMENTATION_VERSION = "audio-qa-core/v1"

EXIT_SUCCESS = 0
EXIT_INVALID_ARGUMENTS = 2
EXIT_MANIFEST_INVALID = 3
EXIT_RUNTIME_ROOT_MISMATCH = 4
EXIT_ARTIFACT_INTEGRITY_FAILURE = 5
EXIT_FFMPEG_UNAVAILABLE = 6
EXIT_ANALYSIS_FAILURE = 7
EXIT_REPORT_CONFLICT = 8
EXIT_INTERNAL_ERROR = 9

_LIVE_ROOT = canonical_production_db_path().resolve().parent


class AudioQaError(RuntimeError):
    exit_code = EXIT_ANALYSIS_FAILURE
    status = "analysis_failure"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class QaArgumentError(AudioQaError):
    exit_code = EXIT_INVALID_ARGUMENTS
    status = "invalid_arguments"


class QaManifestError(AudioQaError):
    exit_code = EXIT_MANIFEST_INVALID
    status = "manifest_invalid"


class QaRuntimeMismatchError(AudioQaError):
    exit_code = EXIT_RUNTIME_ROOT_MISMATCH
    status = "runtime_root_mismatch"


class QaArtifactIntegrityError(AudioQaError):
    exit_code = EXIT_ARTIFACT_INTEGRITY_FAILURE
    status = "artifact_integrity_failure"


class QaFfmpegUnavailableError(AudioQaError):
    exit_code = EXIT_FFMPEG_UNAVAILABLE
    status = "ffmpeg_unavailable"


class QaReportConflictError(AudioQaError):
    exit_code = EXIT_REPORT_CONFLICT
    status = "conflicting_existing_report"


class QaInternalError(AudioQaError):
    exit_code = EXIT_INTERNAL_ERROR
    status = "internal_error"


@dataclass(frozen=True)
class QaThresholds:
    silence_threshold_dbfs: float = -40.0
    silence_min_span_ms: int = 80
    near_clip_dbfs: float = -0.2
    long_leading_silence_ms: int = 250
    long_trailing_silence_ms: int = 300
    trailing_silence_excess_ms: int = 80
    long_internal_silence_ms: int = 400
    adjacent_loudness_jump_db: float = 6.0
    loudness_outlier_db: float = 4.0
    duration_mad_multiplier: float = 3.0
    duration_floor_ms: int = 1500
    speech_rate_mad_multiplier: float = 3.0
    speech_rate_floor_cps: float = 6.0
    speech_rate_ceiling_cps: float = 30.0
    min_voice_group_for_outlier_stats: int = 4
    very_short_segment_ms: int = 750
    very_long_segment_ms: int = 12000
    shortlist_max_segments: int = 25
    analysis_timeout_seconds: int = 60


@dataclass(frozen=True)
class SignalMetrics:
    duration_ms: int
    sample_rate: int
    channels: int
    sample_format: str
    sample_width_bits: int
    frame_count: int
    mean_volume_dbfs: float | None
    max_peak_dbfs: float | None
    peak_reaches_full_scale: bool
    sample_count: int
    hard_clipping_sample_count: int
    hard_clipping_sample_ratio: float
    longest_full_scale_run_samples: int
    near_clipping_sample_count: int
    near_clipping_sample_ratio: float
    leading_silence_ms: int
    trailing_silence_ms: int
    longest_internal_silence_ms: int
    total_internal_silence_ms: int
    total_silence_ms: int
    silence_span_count: int
    silence_spans: list[dict[str, int]]


def _canonical_json(value: Any, *, ensure_ascii: bool = False) -> str:
    return json.dumps(value, ensure_ascii=ensure_ascii, sort_keys=True, separators=(",", ":"))


def _utc_iso_from_epoch(epoch_seconds: float) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


def _dbfs_from_amplitude(amplitude: float, scale: float) -> float | None:
    if amplitude <= 0 or scale <= 0:
        return None
    return 20.0 * math.log10(amplitude / scale)


def _round_db(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 3)


def _round_float(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _ensure_absolute_path(label: str, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise QaArgumentError(f"{label} must be an absolute path")
    return path.resolve()


def _path_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _relative_to_root(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def _open_readonly_db(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def _stderr(message: str, *, stream: Any) -> None:
    print(message, file=stream, flush=True)


def _run_completed_command(command: list[str], *, timeout_seconds: int) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise QaFfmpegUnavailableError(
            "Required FFmpeg binary is missing",
            details={"command": command[0]},
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise QaFfmpegUnavailableError(
            "FFmpeg command timed out",
            details={"command": command[0], "timeout_seconds": timeout_seconds},
        ) from exc


def _pcm_integer_codec_supported(codec_name: str | None) -> bool:
    return str(codec_name or "") in {"pcm_u8", "pcm_s16le", "pcm_s24le", "pcm_s32le"}


def _quantile(values: Iterable[float], percentile: float) -> float | None:
    materialized = sorted(float(value) for value in values)
    if not materialized:
        return None
    if len(materialized) == 1:
        return materialized[0]
    rank = (len(materialized) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return materialized[lower]
    weight = rank - lower
    return materialized[lower] + (materialized[upper] - materialized[lower]) * weight


def _build_numeric_summary(values: Iterable[float]) -> dict[str, float | int | None]:
    materialized = [float(value) for value in values]
    if not materialized:
        return {
            "count": 0,
            "median": None,
            "mean": None,
            "p90": None,
            "p95": None,
            "min": None,
            "max": None,
        }
    return {
        "count": len(materialized),
        "median": _round_float(_median(materialized)),
        "mean": _round_float(_mean(materialized)),
        "p90": _round_float(_quantile(materialized, 0.90)),
        "p95": _round_float(_quantile(materialized, 0.95)),
        "min": _round_float(min(materialized)),
        "max": _round_float(max(materialized)),
    }


def _check_binary_available(binary: str, *, timeout_seconds: int) -> None:
    completed = _run_completed_command([binary, "-version"], timeout_seconds=timeout_seconds)
    if completed.returncode != 0:
        raise QaFfmpegUnavailableError(
            "Required FFmpeg binary is not callable",
            details={
                "command": binary,
                "returncode": completed.returncode,
                "stderr": completed.stderr.decode("utf-8", errors="replace").strip(),
            },
        )


def _ffprobe_audio_metadata(path: Path, *, ffprobe_path: str, timeout_seconds: int) -> dict[str, Any]:
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    completed = _run_completed_command(command, timeout_seconds=timeout_seconds)
    if completed.returncode != 0:
        raise QaArtifactIntegrityError(
            "ffprobe could not inspect audio artifact",
            details={
                "path": str(path),
                "returncode": completed.returncode,
                "stderr": completed.stderr.decode("utf-8", errors="replace").strip(),
            },
        )
    try:
        payload = json.loads(completed.stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise QaArtifactIntegrityError("ffprobe returned invalid JSON", details={"path": str(path)}) from exc
    streams = payload.get("streams") or []
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not isinstance(audio_stream, dict):
        raise QaArtifactIntegrityError("Audio artifact has no audio stream", details={"path": str(path)})
    format_info = payload.get("format") or {}
    return {
        "codec_name": audio_stream.get("codec_name"),
        "codec_long_name": audio_stream.get("codec_long_name"),
        "sample_format": audio_stream.get("sample_fmt"),
        "sample_rate": int(audio_stream.get("sample_rate") or 0),
        "channels": int(audio_stream.get("channels") or 0),
        "bits_per_sample": int(audio_stream.get("bits_per_sample") or audio_stream.get("bits_per_raw_sample") or 0),
        "duration_seconds": float(format_info.get("duration") or audio_stream.get("duration") or 0.0),
        "format_name": format_info.get("format_name"),
        "bit_rate": int(format_info.get("bit_rate") or 0) if str(format_info.get("bit_rate") or "").isdigit() else None,
    }


def _parse_pcm_chunk(
    chunk: bytes,
    *,
    channels: int,
    max_amplitude: int,
    positive_full_scale_sample: int,
    negative_full_scale_sample: int,
    silence_amplitude: int,
    near_clip_amplitude: int,
    state: dict[str, Any],
) -> None:
    samples = array("h")
    samples.frombytes(chunk)
    if sys.byteorder != "little":
        samples.byteswap()
    state["sample_count"] += len(samples)
    frame_start = state["frame_count"]
    for offset in range(0, len(samples), channels):
        frame_max = 0
        for channel_index in range(channels):
            sample = int(samples[offset + channel_index])
            amplitude = abs(sample)
            if amplitude > frame_max:
                frame_max = amplitude
            state["sum_squares"] += amplitude * amplitude
            is_full_scale = sample == positive_full_scale_sample or sample == negative_full_scale_sample
            if is_full_scale:
                state["hard_clipping_sample_count"] += 1
                state["current_full_scale_run_samples"] += 1
                if state["current_full_scale_run_samples"] > state["longest_full_scale_run_samples"]:
                    state["longest_full_scale_run_samples"] = state["current_full_scale_run_samples"]
            elif amplitude >= near_clip_amplitude:
                state["near_clipping_sample_count"] += 1
                state["current_full_scale_run_samples"] = 0
            else:
                state["current_full_scale_run_samples"] = 0
        frame_index = state["frame_count"]
        if frame_max <= silence_amplitude:
            if state["current_silence_start_frame"] is None:
                state["current_silence_start_frame"] = frame_index
        else:
            if state["current_silence_start_frame"] is not None:
                state["silence_spans_frames"].append(
                    (state["current_silence_start_frame"], frame_index)
                )
                state["current_silence_start_frame"] = None
        if frame_max > state["peak_amplitude"]:
            state["peak_amplitude"] = frame_max
        state["frame_count"] += 1
    if state["frame_count"] < frame_start:
        raise QaInternalError("PCM analysis overflowed frame counter")


def _decode_pcm_sample(sample_bytes: bytes, *, sample_width: int) -> int:
    if sample_width == 1:
        return int(sample_bytes[0]) - 128
    if sample_width == 2:
        return int.from_bytes(sample_bytes, byteorder="little", signed=True)
    if sample_width == 3:
        value = int.from_bytes(sample_bytes, byteorder="little", signed=False)
        if value & 0x800000:
            value -= 0x1000000
        return value
    if sample_width == 4:
        return int.from_bytes(sample_bytes, byteorder="little", signed=True)
    raise QaArtifactIntegrityError(
        "Unsupported integer PCM sample width",
        details={"sample_width_bytes": sample_width},
    )


def _pcm_scale(width_bytes: int) -> int:
    return 1 << ((width_bytes * 8) - 1)


def _positive_full_scale_sample(width_bytes: int) -> int:
    if width_bytes == 1:
        return 127
    return _pcm_scale(width_bytes) - 1


def _negative_full_scale_sample(width_bytes: int) -> int:
    return -_pcm_scale(width_bytes)


def _parse_generic_pcm_chunk(
    chunk: bytes,
    *,
    channels: int,
    sample_width: int,
    silence_amplitude: int,
    near_clip_amplitude: int,
    state: dict[str, Any],
) -> None:
    frame_bytes = channels * sample_width
    if len(chunk) % frame_bytes != 0:
        raise QaArtifactIntegrityError(
            "PCM byte stream is not aligned to frame size",
            details={"channels": channels, "sample_width_bytes": sample_width, "pcm_bytes": len(chunk)},
        )
    max_amplitude = _pcm_scale(sample_width) - 1
    positive_full_scale = _positive_full_scale_sample(sample_width)
    negative_full_scale = _negative_full_scale_sample(sample_width)
    for frame_offset in range(0, len(chunk), frame_bytes):
        frame = chunk[frame_offset:frame_offset + frame_bytes]
        frame_max = 0
        for channel_index in range(channels):
            start = channel_index * sample_width
            sample = _decode_pcm_sample(frame[start:start + sample_width], sample_width=sample_width)
            amplitude = abs(sample)
            if amplitude > frame_max:
                frame_max = amplitude
            state["sum_squares"] += amplitude * amplitude
            state["sample_count"] += 1
            is_full_scale = sample == positive_full_scale or sample == negative_full_scale
            if is_full_scale:
                state["hard_clipping_sample_count"] += 1
                state["current_full_scale_run_samples"] += 1
                if state["current_full_scale_run_samples"] > state["longest_full_scale_run_samples"]:
                    state["longest_full_scale_run_samples"] = state["current_full_scale_run_samples"]
            elif amplitude >= near_clip_amplitude:
                state["near_clipping_sample_count"] += 1
                state["current_full_scale_run_samples"] = 0
            else:
                state["current_full_scale_run_samples"] = 0
        frame_index = state["frame_count"]
        if frame_max <= silence_amplitude:
            if state["current_silence_start_frame"] is None:
                state["current_silence_start_frame"] = frame_index
        else:
            if state["current_silence_start_frame"] is not None:
                state["silence_spans_frames"].append((state["current_silence_start_frame"], frame_index))
                state["current_silence_start_frame"] = None
        if frame_max > state["peak_amplitude"]:
            state["peak_amplitude"] = frame_max
        state["frame_count"] += 1


def _finalize_signal_metrics(
    *,
    state: dict[str, Any],
    sample_rate: int,
    channels: int,
    sample_format: str,
    sample_width_bits: int,
    min_silence_span_ms: int,
) -> SignalMetrics:
    if state["current_silence_start_frame"] is not None:
        state["silence_spans_frames"].append((state["current_silence_start_frame"], state["frame_count"]))
        state["current_silence_start_frame"] = None
    scale = float(2 ** (sample_width_bits - 1))
    rms = math.sqrt(state["sum_squares"] / state["sample_count"]) if state["sample_count"] else 0.0
    min_frames = max(1, round(sample_rate * (min_silence_span_ms / 1000.0))) if sample_rate else 1
    silence_spans = []
    for start_frame, end_frame in state["silence_spans_frames"]:
        if (end_frame - start_frame) < min_frames:
            continue
        start_ms = round((start_frame / sample_rate) * 1000)
        end_ms = round((end_frame / sample_rate) * 1000)
        silence_spans.append(
            {
                "start_ms": int(start_ms),
                "end_ms": int(end_ms),
                "duration_ms": int(max(0, end_ms - start_ms)),
            }
        )
    leading = silence_spans[0]["duration_ms"] if silence_spans and silence_spans[0]["start_ms"] == 0 else 0
    trailing = silence_spans[-1]["duration_ms"] if silence_spans and silence_spans[-1]["end_ms"] >= round((state["frame_count"] / sample_rate) * 1000) else 0
    internal_spans = silence_spans[1:-1] if leading and trailing else (
        silence_spans[1:] if leading else silence_spans[:-1] if trailing else silence_spans
    )
    total_silence_ms = sum(span["duration_ms"] for span in silence_spans)
    total_internal_silence_ms = sum(span["duration_ms"] for span in internal_spans)
    longest_internal_silence_ms = max((span["duration_ms"] for span in internal_spans), default=0)
    duration_ms = round((state["frame_count"] / sample_rate) * 1000) if sample_rate else 0
    return SignalMetrics(
        duration_ms=int(duration_ms),
        sample_rate=sample_rate,
        channels=channels,
        sample_format=sample_format,
        sample_width_bits=sample_width_bits,
        frame_count=state["frame_count"],
        mean_volume_dbfs=_round_db(_dbfs_from_amplitude(rms, scale)),
        max_peak_dbfs=_round_db(_dbfs_from_amplitude(float(state["peak_amplitude"]), scale)),
        peak_reaches_full_scale=bool(state["hard_clipping_sample_count"] > 0),
        sample_count=int(state["sample_count"]),
        hard_clipping_sample_count=int(state["hard_clipping_sample_count"]),
        hard_clipping_sample_ratio=_round_float(
            (state["hard_clipping_sample_count"] / state["sample_count"]) if state["sample_count"] else 0.0
        ) or 0.0,
        longest_full_scale_run_samples=int(state["longest_full_scale_run_samples"]),
        near_clipping_sample_count=int(state["near_clipping_sample_count"]),
        near_clipping_sample_ratio=_round_float(
            (state["near_clipping_sample_count"] / state["sample_count"]) if state["sample_count"] else 0.0
        ) or 0.0,
        leading_silence_ms=int(leading),
        trailing_silence_ms=int(trailing),
        longest_internal_silence_ms=int(longest_internal_silence_ms),
        total_internal_silence_ms=int(total_internal_silence_ms),
        total_silence_ms=int(total_silence_ms),
        silence_span_count=len(silence_spans),
        silence_spans=silence_spans,
    )


def _analyze_wave_signal(path: Path, *, thresholds: QaThresholds) -> SignalMetrics:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_rate = handle.getframerate()
        sample_width = handle.getsampwidth()
        if sample_width not in {1, 2, 3, 4}:
            raise QaArtifactIntegrityError(
                "Unsupported integer PCM WAV sample width",
                details={"path": str(path), "sample_width_bytes": sample_width},
            )
        state = {
            "sample_count": 0,
            "sum_squares": 0,
            "peak_amplitude": 0,
            "hard_clipping_sample_count": 0,
            "near_clipping_sample_count": 0,
            "current_full_scale_run_samples": 0,
            "longest_full_scale_run_samples": 0,
            "frame_count": 0,
            "current_silence_start_frame": None,
            "silence_spans_frames": [],
        }
        scale = _pcm_scale(sample_width)
        silence_amplitude = math.ceil(scale * (10 ** (thresholds.silence_threshold_dbfs / 20.0)))
        near_clip_amplitude = math.floor(scale * (10 ** (thresholds.near_clip_dbfs / 20.0)))
        while True:
            frames = handle.readframes(4096)
            if not frames:
                break
            if sample_width == 2:
                _parse_pcm_chunk(
                    frames,
                    channels=channels,
                    max_amplitude=scale - 1,
                    positive_full_scale_sample=_positive_full_scale_sample(sample_width),
                    negative_full_scale_sample=_negative_full_scale_sample(sample_width),
                    silence_amplitude=silence_amplitude,
                    near_clip_amplitude=near_clip_amplitude,
                    state=state,
                )
            else:
                _parse_generic_pcm_chunk(
                    frames,
                    channels=channels,
                    sample_width=sample_width,
                    silence_amplitude=silence_amplitude,
                    near_clip_amplitude=near_clip_amplitude,
                    state=state,
                )
    return _finalize_signal_metrics(
        state=state,
        sample_rate=sample_rate,
        channels=channels,
        sample_format={1: "pcm_u8", 2: "pcm_s16le", 3: "pcm_s24le", 4: "pcm_s32le"}[sample_width],
        sample_width_bits=sample_width * 8,
        min_silence_span_ms=thresholds.silence_min_span_ms,
    )


def _analyze_via_ffmpeg(
    path: Path,
    *,
    ffmpeg_path: str,
    ffprobe_metadata: dict[str, Any],
    thresholds: QaThresholds,
    timeout_seconds: int,
) -> SignalMetrics:
    channels = int(ffprobe_metadata.get("channels") or 0)
    sample_rate = int(ffprobe_metadata.get("sample_rate") or 0)
    if channels <= 0 or sample_rate <= 0:
        raise QaArtifactIntegrityError(
            "ffprobe metadata is missing sample rate or channels",
            details={"path": str(path), "metadata": ffprobe_metadata},
        )
    command = [
        ffmpeg_path,
        "-v",
        "error",
        "-i",
        str(path),
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-",
    ]
    completed = _run_completed_command(command, timeout_seconds=timeout_seconds)
    if completed.returncode != 0:
        raise QaArtifactIntegrityError(
            "ffmpeg could not decode audio artifact",
            details={
                "path": str(path),
                "returncode": completed.returncode,
                "stderr": completed.stderr.decode("utf-8", errors="replace").strip(),
            },
        )
    raw = completed.stdout
    frame_bytes = channels * 2
    if len(raw) % frame_bytes != 0:
        raise QaArtifactIntegrityError(
            "Decoded PCM length is not aligned to frame size",
            details={"path": str(path), "channels": channels, "pcm_bytes": len(raw)},
        )
    state = {
        "sample_count": 0,
        "sum_squares": 0,
        "peak_amplitude": 0,
        "hard_clipping_sample_count": 0,
        "near_clipping_sample_count": 0,
        "current_full_scale_run_samples": 0,
        "longest_full_scale_run_samples": 0,
        "frame_count": 0,
        "current_silence_start_frame": None,
        "silence_spans_frames": [],
    }
    silence_amplitude = math.ceil((2 ** 15) * (10 ** (thresholds.silence_threshold_dbfs / 20.0)))
    near_clip_amplitude = math.floor((2 ** 15) * (10 ** (thresholds.near_clip_dbfs / 20.0)))
    chunk_size = frame_bytes * 4096
    for index in range(0, len(raw), chunk_size):
        _parse_pcm_chunk(
            raw[index:index + chunk_size],
            channels=channels,
            max_amplitude=(2 ** 15) - 1,
            positive_full_scale_sample=(2 ** 15) - 1,
            negative_full_scale_sample=-(2 ** 15),
            silence_amplitude=silence_amplitude,
            near_clip_amplitude=near_clip_amplitude,
            state=state,
        )
    return _finalize_signal_metrics(
        state=state,
        sample_rate=sample_rate,
        channels=channels,
        sample_format="pcm_s16le",
        sample_width_bits=16,
        min_silence_span_ms=thresholds.silence_min_span_ms,
    )


def _analyze_audio_file(
    path: Path,
    *,
    ffmpeg_path: str,
    ffprobe_path: str,
    thresholds: QaThresholds,
    timeout_seconds: int,
) -> dict[str, Any]:
    metadata = _ffprobe_audio_metadata(path, ffprobe_path=ffprobe_path, timeout_seconds=timeout_seconds)
    codec_name = str(metadata.get("codec_name") or "")
    if path.suffix.lower() == ".wav" and codec_name.startswith("pcm_") and not _pcm_integer_codec_supported(codec_name):
        raise QaArtifactIntegrityError(
            "Unsupported PCM WAV codec for objective analysis",
            details={"path": str(path), "codec_name": codec_name},
        )
    if path.suffix.lower() == ".wav" and _pcm_integer_codec_supported(codec_name):
        signal = _analyze_wave_signal(path, thresholds=thresholds)
    else:
        signal = _analyze_via_ffmpeg(
            path,
            ffmpeg_path=ffmpeg_path,
            ffprobe_metadata=metadata,
            thresholds=thresholds,
            timeout_seconds=timeout_seconds,
        )
    return {
        "codec_name": metadata.get("codec_name"),
        "codec_long_name": metadata.get("codec_long_name"),
        "format_name": metadata.get("format_name"),
        "sample_format": metadata.get("sample_format") or signal.sample_format,
        "sample_rate": signal.sample_rate,
        "channels": signal.channels,
        "bits_per_sample": metadata.get("bits_per_sample") or signal.sample_width_bits,
        "duration_seconds": _round_float(float(metadata.get("duration_seconds") or 0.0)),
        "duration_ms": signal.duration_ms,
        "bit_rate": metadata.get("bit_rate"),
        "mean_volume_dbfs": signal.mean_volume_dbfs,
        "max_peak_dbfs": signal.max_peak_dbfs,
        "peak_reaches_full_scale": signal.peak_reaches_full_scale,
        "sample_count": signal.sample_count,
        "hard_clipping_sample_count": signal.hard_clipping_sample_count,
        "hard_clipping_sample_ratio": signal.hard_clipping_sample_ratio,
        "longest_full_scale_run_samples": signal.longest_full_scale_run_samples,
        "near_clipping_sample_count": signal.near_clipping_sample_count,
        "near_clipping_sample_ratio": signal.near_clipping_sample_ratio,
        "leading_silence_ms": signal.leading_silence_ms,
        "trailing_silence_ms": signal.trailing_silence_ms,
        "longest_internal_silence_ms": signal.longest_internal_silence_ms,
        "total_internal_silence_ms": signal.total_internal_silence_ms,
        "total_silence_ms": signal.total_silence_ms,
        "silence_span_count": signal.silence_span_count,
        "silence_spans": signal.silence_spans,
    }


def _load_json(path: Path, *, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise QaManifestError(f"{label} file does not exist", details={"path": str(path)}) from exc
    except json.JSONDecodeError as exc:
        raise QaManifestError(f"{label} file is not valid JSON", details={"path": str(path)}) from exc


def _validate_manifest_structure(manifest: dict[str, Any]) -> None:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise QaManifestError(
            "Manifest schema is not supported",
            details={"expected": MANIFEST_SCHEMA, "actual": manifest.get("schema")},
        )
    for key in ("identity", "immutable_bindings", "terminal_state", "artifacts", "segment_integrity_summary"):
        if key not in manifest:
            raise QaManifestError("Manifest is missing required key", details={"key": key})
    if not isinstance(manifest["artifacts"], list) or not manifest["artifacts"]:
        raise QaManifestError("Manifest artifacts list is missing or empty")


def _select_manifest_artifact(manifest: dict[str, Any], artifact_type: str) -> dict[str, Any]:
    matches = [item for item in manifest["artifacts"] if item.get("artifact_type") == artifact_type]
    if len(matches) != 1:
        raise QaManifestError(
            "Manifest does not contain exactly one required artifact",
            details={"artifact_type": artifact_type, "count": len(matches)},
        )
    return matches[0]


def _verify_manifest_artifact(item: dict[str, Any], *, data_root: Path) -> dict[str, Any]:
    path = _ensure_absolute_path("manifest artifact path", item["absolute_local_path"])
    if not _path_within_root(path, data_root):
        raise QaRuntimeMismatchError(
            "Manifest artifact path escapes isolated data root",
            details={"path": str(path), "data_root": str(data_root)},
        )
    if not path.exists():
        raise QaArtifactIntegrityError("Manifest artifact file is missing", details={"path": str(path)})
    computed = sha256_file(path)
    expected_hashes = {item.get("stored_sha256"), item.get("computed_sha256")}
    expected_hashes.discard(None)
    if computed not in expected_hashes:
        raise QaArtifactIntegrityError(
            "Manifest artifact hash does not match source file",
            details={"path": str(path), "computed_sha256": computed, "expected_hashes": sorted(expected_hashes)},
        )
    relative = _relative_to_root(path, data_root)
    if relative != item.get("path_relative_to_data_root"):
        raise QaArtifactIntegrityError(
            "Manifest artifact relative path drifted",
            details={
                "path": str(path),
                "expected_relative": item.get("path_relative_to_data_root"),
                "actual_relative": relative,
            },
        )
    return {
        "artifact_id": int(item["artifact_id"]),
        "artifact_type": str(item["artifact_type"]),
        "status": item.get("status"),
        "absolute_local_path": str(path),
        "path_relative_to_data_root": relative,
        "sha256": computed,
        "size_bytes": path.stat().st_size,
        "mtime_epoch_seconds": path.stat().st_mtime,
        "duration_ms": _coerce_int(item.get("duration_ms")),
        "mime_type": item.get("mime_type"),
    }


def _load_segment_rows(db_path: Path, job_chapter_id: int) -> list[dict[str, Any]]:
    with closing(_open_readonly_db(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT id, job_chapter_id, segment_index, utterance_sequence, speaker_role,
                   character_id, resolved_voice_id, synthesis_hash, text_path, text_sha256,
                   wav_path, audio_sha256, duration_ms, status
            FROM segments
            WHERE job_chapter_id = ?
            ORDER BY segment_index
            """,
            (job_chapter_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _verify_readonly_runtime_identity(
    manifest: dict[str, Any],
    *,
    allow_canonical_production: bool = False,
) -> tuple[Path, Path]:
    identity = manifest["identity"]
    data_root = _ensure_absolute_path("manifest identity data_root", identity["data_root"])
    db_path = _ensure_absolute_path("manifest identity db_path", identity["db_path"])
    if data_root == _LIVE_ROOT or db_path == canonical_production_db_path().resolve():
        if not allow_canonical_production:
            raise QaRuntimeMismatchError(
                "Refusing canonical live root in audio QA without explicit canonical approval"
            )
    if not db_path.exists():
        raise QaRuntimeMismatchError("Manifest database path does not exist", details={"db_path": str(db_path)})
    if not data_root.exists():
        raise QaRuntimeMismatchError("Manifest data root does not exist", details={"data_root": str(data_root)})
    if not _path_within_root(db_path, data_root):
        raise QaRuntimeMismatchError(
            "Manifest database path is not inside isolated data root",
            details={"data_root": str(data_root), "db_path": str(db_path)},
        )
    return data_root, db_path


def _median(values: Iterable[float]) -> float | None:
    materialized = [float(value) for value in values]
    if not materialized:
        return None
    return float(statistics.median(materialized))


def _mean(values: Iterable[float]) -> float | None:
    materialized = [float(value) for value in values]
    if not materialized:
        return None
    return float(statistics.mean(materialized))


def _mad(values: Iterable[float], *, center: float | None = None) -> float:
    materialized = [float(value) for value in values]
    if not materialized:
        return 0.0
    midpoint = float(center) if center is not None else float(statistics.median(materialized))
    deviations = [abs(value - midpoint) for value in materialized]
    return float(statistics.median(deviations))


def _build_voice_aggregates(segment_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in segment_results:
        voice_id = str(result.get("resolved_voice_id") or "")
        grouped.setdefault(voice_id, []).append(result)
    aggregates = []
    for voice_id in sorted(grouped):
        values = grouped[voice_id]
        mean_volumes = [item["mean_volume_dbfs"] for item in values if item["mean_volume_dbfs"] is not None]
        chars_per_second = [item["chars_per_second"] for item in values if item["chars_per_second"] is not None]
        trailing_silence = [item["trailing_silence_ms"] for item in values if item["trailing_silence_ms"] is not None]
        enough_voice_samples = len(values) >= 4
        aggregates.append(
            {
                "voice_id": voice_id,
                "voice_name": None,
                "segment_count": len(values),
                "total_duration_ms": sum(int(item["duration_ms"] or 0) for item in values),
                "median_mean_volume_dbfs": _round_db(_median(mean_volumes)),
                "mean_mean_volume_dbfs": _round_db(_mean(mean_volumes)),
                "min_mean_volume_dbfs": _round_db(min(mean_volumes) if mean_volumes else None),
                "max_mean_volume_dbfs": _round_db(max(mean_volumes) if mean_volumes else None),
                "median_chars_per_second": _round_float(_median(chars_per_second)),
                "median_trailing_silence_ms": _round_float(_median(trailing_silence)),
                "trailing_silence_distribution": _build_numeric_summary(trailing_silence),
                "clipping_segment_count": sum(
                    1 for item in values if int(item["hard_clipping_sample_count"] or 0) > 0 or int(item["near_clipping_sample_count"] or 0) > 0
                ),
                "silence_outlier_count": sum(
                    1 for item in values if int(item["longest_internal_silence_ms"] or 0) > 0 or int(item["leading_silence_ms"] or 0) > 0 or int(item["trailing_silence_ms"] or 0) > 0
                ),
                "robust_outlier_sample_size_met": enough_voice_samples,
                "limitations": [] if enough_voice_samples else ["voice_sample_size_below_robust_outlier_threshold"],
            }
        )
    return aggregates


def _build_segment_result(
    *,
    sequence: int,
    segment_row: dict[str, Any],
    timeline_item: dict[str, Any],
    wav_path: Path | None,
    data_root: Path,
    artifact_issue: str | None,
    metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    text = timeline_item.get("text")
    character_count = len(text) if isinstance(text, str) else None
    duration_ms = metrics["duration_ms"] if metrics is not None else _coerce_int(segment_row.get("duration_ms"))
    chars_per_second = None
    if character_count is not None and duration_ms and duration_ms > 0:
        chars_per_second = round(character_count / (duration_ms / 1000.0), 6)
    file_relative = _relative_to_root(wav_path, data_root) if wav_path else None
    source_limitations = []
    if duration_ms in (None, 0):
        source_limitations.append("duration_missing_or_zero")
    if character_count in (None, 0):
        source_limitations.append("character_count_missing_or_zero")
    return {
        "segment_id": int(segment_row["id"]),
        "sequence": sequence,
        "utterance_id": None,
        "utterance_sequence": _coerce_int(timeline_item.get("utterance_sequence")),
        "text": text if isinstance(text, str) else None,
        "text_sha256": sha256_text(text) if isinstance(text, str) else segment_row.get("text_sha256"),
        "speaker_role": timeline_item.get("speaker_role") or segment_row.get("speaker_role"),
        "character_id": timeline_item.get("character_id"),
        "character_name": timeline_item.get("character_name"),
        "resolved_voice_id": timeline_item.get("voice_id") or segment_row.get("resolved_voice_id"),
        "resolved_voice_name": None,
        "resolution_source": timeline_item.get("resolution_source"),
        "resolved_gender": timeline_item.get("resolved_gender"),
        "needs_review": bool(timeline_item.get("needs_review")),
        "voice_profile_id": _coerce_int(timeline_item.get("voice_profile_id")),
        "voice_profile_version": _coerce_int(timeline_item.get("voice_profile_version")),
        "chapter_start_ms": _coerce_int(timeline_item.get("start_ms")),
        "chapter_end_ms": _coerce_int(timeline_item.get("end_ms")),
        "timeline_duration_ms": _coerce_int(timeline_item.get("duration_ms")),
        "duration_ms": duration_ms,
        "character_count": character_count,
        "chars_per_second": chars_per_second,
        "mean_volume_dbfs": metrics.get("mean_volume_dbfs") if metrics else None,
        "max_peak_dbfs": metrics.get("max_peak_dbfs") if metrics else None,
        "peak_reaches_full_scale": bool(metrics.get("peak_reaches_full_scale")) if metrics else False,
        "sample_count": int(metrics.get("sample_count") or 0) if metrics else 0,
        "hard_clipping_sample_count": int(metrics.get("hard_clipping_sample_count") or 0) if metrics else 0,
        "hard_clipping_sample_ratio": metrics.get("hard_clipping_sample_ratio") if metrics else 0.0,
        "longest_full_scale_run_samples": int(metrics.get("longest_full_scale_run_samples") or 0) if metrics else 0,
        "near_clipping_sample_count": int(metrics.get("near_clipping_sample_count") or 0) if metrics else 0,
        "near_clipping_sample_ratio": metrics.get("near_clipping_sample_ratio") if metrics else 0.0,
        "leading_silence_ms": int(metrics.get("leading_silence_ms") or 0) if metrics else 0,
        "trailing_silence_ms": int(metrics.get("trailing_silence_ms") or 0) if metrics else 0,
        "longest_internal_silence_ms": int(metrics.get("longest_internal_silence_ms") or 0) if metrics else 0,
        "total_internal_silence_ms": int(metrics.get("total_internal_silence_ms") or 0) if metrics else 0,
        "segment_file_relative_to_data_root": file_relative,
        "segment_file_absolute_path": str(wav_path) if wav_path else None,
        "segment_audio_sha256": metrics.get("sha256") if metrics else segment_row.get("audio_sha256"),
        "artifact_issue": artifact_issue,
        "source_limitations": source_limitations,
    }


def _flag_segment_risks(
    segment_results: list[dict[str, Any]],
    *,
    thresholds: QaThresholds,
    voice_aggregates: list[dict[str, Any]],
) -> None:
    duration_values = [float(item["duration_ms"]) for item in segment_results if item["duration_ms"] is not None]
    duration_median = _median(duration_values)
    duration_mad = _mad(duration_values, center=duration_median)
    chapter_trailing_values = [float(item["trailing_silence_ms"]) for item in segment_results if item["trailing_silence_ms"] is not None]
    chapter_trailing_median = _median(chapter_trailing_values) or 0.0
    chapter_trailing_p95 = _quantile(chapter_trailing_values, 0.95) or 0.0

    voice_baselines = {item["voice_id"]: item for item in voice_aggregates}
    voice_rate_medians: dict[str, float] = {}
    voice_rate_mads: dict[str, float] = {}
    voice_loudness_medians: dict[str, float] = {}
    voice_trailing_medians: dict[str, float] = {}
    voice_sample_counts: dict[str, int] = {}
    for voice_id in voice_baselines:
        values = [float(result["chars_per_second"]) for result in segment_results if result.get("resolved_voice_id") == voice_id and result["chars_per_second"] is not None]
        loudness_values = [float(result["mean_volume_dbfs"]) for result in segment_results if result.get("resolved_voice_id") == voice_id and result["mean_volume_dbfs"] is not None]
        trailing_values = [float(result["trailing_silence_ms"]) for result in segment_results if result.get("resolved_voice_id") == voice_id and result["trailing_silence_ms"] is not None]
        voice_sample_counts[voice_id] = sum(1 for result in segment_results if result.get("resolved_voice_id") == voice_id)
        if values:
            voice_rate_medians[voice_id] = float(statistics.median(values))
            voice_rate_mads[voice_id] = _mad(values, center=voice_rate_medians[voice_id])
        if loudness_values:
            voice_loudness_medians[voice_id] = float(statistics.median(loudness_values))
        if trailing_values:
            voice_trailing_medians[voice_id] = float(statistics.median(trailing_values))

    for index, result in enumerate(segment_results):
        flags: list[str] = []
        reasons: list[str] = []
        if result["artifact_issue"]:
            flags.append("missing_metadata")
            reasons.append(f"artifact_issue={result['artifact_issue']}")
        if result["hard_clipping_sample_count"] > 0:
            flags.append("hard_clipping")
            reasons.append(
                "hard_clipping_samples="
                f"{result['hard_clipping_sample_count']} ratio={result['hard_clipping_sample_ratio']} "
                f"longest_full_scale_run_samples={result['longest_full_scale_run_samples']}"
            )
        if result["near_clipping_sample_count"] > 0:
            flags.append("near_clipping")
            reasons.append(
                f"near_clipping_samples={result['near_clipping_sample_count']} ratio={result['near_clipping_sample_ratio']}"
            )
        if result["leading_silence_ms"] >= thresholds.long_leading_silence_ms:
            flags.append("long_leading_silence")
            reasons.append(f"leading_silence_ms={result['leading_silence_ms']}")
        voice_id = str(result.get("resolved_voice_id") or "")
        voice_median_trailing = voice_trailing_medians.get(voice_id)
        voice_has_robust_sample = voice_sample_counts.get(voice_id, 0) >= thresholds.min_voice_group_for_outlier_stats
        chapter_excess = max(0.0, float(result["trailing_silence_ms"]) - chapter_trailing_median)
        voice_excess = max(0.0, float(result["trailing_silence_ms"]) - voice_median_trailing) if voice_median_trailing is not None else None
        result["trailing_silence_context"] = {
            "chapter_median_ms": _round_float(chapter_trailing_median),
            "chapter_p95_ms": _round_float(chapter_trailing_p95),
            "voice_median_ms": _round_float(voice_median_trailing),
            "chapter_excess_ms": _round_float(chapter_excess),
            "voice_excess_ms": _round_float(voice_excess),
            "absolute_threshold_ms": thresholds.long_trailing_silence_ms,
            "excess_threshold_ms": thresholds.trailing_silence_excess_ms,
            "voice_sample_size": voice_sample_counts.get(voice_id, 0),
            "voice_robust_sample_size_met": voice_has_robust_sample,
            "measured_above_absolute_threshold": bool(result["trailing_silence_ms"] >= thresholds.long_trailing_silence_ms),
        }
        trailing_risk = (
            result["trailing_silence_ms"] >= thresholds.long_trailing_silence_ms
            and (
                chapter_excess >= thresholds.trailing_silence_excess_ms
                or (voice_has_robust_sample and voice_excess is not None and voice_excess >= thresholds.trailing_silence_excess_ms)
                or float(result["trailing_silence_ms"]) > chapter_trailing_p95
            )
        )
        if trailing_risk:
            flags.append("long_trailing_silence")
            reasons.append(
                "trailing_silence_ms="
                f"{result['trailing_silence_ms']} chapter_median_ms={_round_float(chapter_trailing_median)} "
                f"chapter_excess_ms={_round_float(chapter_excess)} voice_median_ms={_round_float(voice_median_trailing)} "
                f"voice_excess_ms={_round_float(voice_excess)}"
            )
        if result["longest_internal_silence_ms"] >= thresholds.long_internal_silence_ms:
            flags.append("long_internal_silence")
            reasons.append(f"longest_internal_silence_ms={result['longest_internal_silence_ms']}")
        if result["duration_ms"] is not None and duration_median is not None:
            delta = abs(float(result["duration_ms"]) - duration_median)
            duration_threshold = max(float(thresholds.duration_floor_ms), thresholds.duration_mad_multiplier * duration_mad)
            if delta > duration_threshold:
                flags.append("duration_outlier")
                reasons.append(f"duration_ms={result['duration_ms']} median_ms={round(duration_median, 3)}")
        if result["duration_ms"] is not None and result["duration_ms"] <= thresholds.very_short_segment_ms:
            flags.append("very_short_segment")
            reasons.append(f"duration_ms={result['duration_ms']}")
        if result["duration_ms"] is not None and result["duration_ms"] >= thresholds.very_long_segment_ms:
            flags.append("very_long_segment")
            reasons.append(f"duration_ms={result['duration_ms']}")
        if result["chars_per_second"] is not None and voice_id in voice_rate_medians:
            cps = float(result["chars_per_second"])
            median_cps = voice_rate_medians[voice_id]
            mad_cps = voice_rate_mads.get(voice_id, 0.0)
            if cps < thresholds.speech_rate_floor_cps or cps > thresholds.speech_rate_ceiling_cps:
                flags.append("speech_rate_outlier")
                reasons.append(f"chars_per_second={round(cps, 3)}")
            elif voice_sample_counts.get(voice_id, 0) >= thresholds.min_voice_group_for_outlier_stats and abs(cps - median_cps) > max(2.0, thresholds.speech_rate_mad_multiplier * mad_cps):
                flags.append("speech_rate_outlier")
                reasons.append(f"chars_per_second={round(cps, 3)} voice_median={round(median_cps, 3)}")
        if result["mean_volume_dbfs"] is not None and voice_id in voice_loudness_medians:
            loudness = float(result["mean_volume_dbfs"])
            voice_median = voice_loudness_medians[voice_id]
            if voice_sample_counts.get(voice_id, 0) >= thresholds.min_voice_group_for_outlier_stats and abs(loudness - voice_median) > thresholds.loudness_outlier_db:
                flags.append("loudness_outlier")
                reasons.append(f"mean_volume_dbfs={round(loudness, 3)} voice_median_dbfs={round(voice_median, 3)}")
        previous = segment_results[index - 1] if index > 0 else None
        if previous and previous["mean_volume_dbfs"] is not None and result["mean_volume_dbfs"] is not None:
            jump = abs(float(result["mean_volume_dbfs"]) - float(previous["mean_volume_dbfs"]))
            if jump > thresholds.adjacent_loudness_jump_db:
                flags.append("adjacent_loudness_jump")
                reasons.append(f"adjacent_jump_db={round(jump, 3)} previous_sequence={previous['sequence']}")
        if any(result.get(field) in (None, "") for field in ("speaker_role", "resolved_voice_id", "segment_file_relative_to_data_root")):
            flags.append("missing_metadata")
            reasons.append("required_metadata_missing")
        if voice_sample_counts.get(voice_id, 0) < thresholds.min_voice_group_for_outlier_stats:
            result["source_limitations"].append("voice_sample_size_below_robust_outlier_threshold")
        score = (
            (100 if "hard_clipping" in flags else 0)
            + (100 if result["artifact_issue"] else 0)
            + (40 if "near_clipping" in flags else 0)
            + (30 if "loudness_outlier" in flags else 0)
            + (20 if "adjacent_loudness_jump" in flags else 0)
            + (15 if "long_internal_silence" in flags else 0)
            + (10 if "long_leading_silence" in flags else 0)
            + (10 if "long_trailing_silence" in flags else 0)
            + (10 if "duration_outlier" in flags else 0)
            + (10 if "speech_rate_outlier" in flags else 0)
            + (5 if "very_short_segment" in flags else 0)
            + (5 if "very_long_segment" in flags else 0)
            + (5 if "missing_metadata" in flags else 0)
        )
        result["risk_flags"] = sorted(set(flags))
        result["risk_reasons"] = reasons
        result["risk_score"] = score


def _top_risky_segments(segment_results: list[dict[str, Any]], *, max_segments: int) -> list[dict[str, Any]]:
    ordered = sorted(
        (item for item in segment_results if int(item.get("risk_score") or 0) > 0),
        key=lambda item: (-int(item["risk_score"]), int(item["sequence"]), int(item["segment_id"])),
    )
    seen: set[int] = set()
    selected = []
    for item in ordered:
        if item["segment_id"] in seen:
            continue
        selected.append(
            {
                "segment_id": item["segment_id"],
                "sequence": item["sequence"],
                "voice_id": item.get("resolved_voice_id"),
                "character_name": item.get("character_name"),
                "risk_score": item["risk_score"],
                "risk_flags": item["risk_flags"],
                "selection_reason": "; ".join(item["risk_reasons"]) or "risk_score>0",
            }
        )
        seen.add(item["segment_id"])
        if len(selected) >= max_segments:
            break
    return selected


def _representative_segments_by_voice(segment_results: list[dict[str, Any]], voice_aggregates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = []
    for aggregate in sorted(voice_aggregates, key=lambda item: str(item["voice_id"])):
        voice_id = str(aggregate["voice_id"])
        candidates = [item for item in segment_results if str(item.get("resolved_voice_id") or "") == voice_id]
        if not candidates:
            continue
        median_loudness = aggregate.get("median_mean_volume_dbfs")
        median_cps = aggregate.get("median_chars_per_second")
        best = min(
            candidates,
            key=lambda item: (
                abs((item["mean_volume_dbfs"] or median_loudness or 0.0) - (median_loudness or item["mean_volume_dbfs"] or 0.0)),
                abs((item["chars_per_second"] or median_cps or 0.0) - (median_cps or item["chars_per_second"] or 0.0)),
                int(item["sequence"]),
            ),
        )
        selected.append(
            {
                "voice_id": voice_id,
                "segment_id": best["segment_id"],
                "sequence": best["sequence"],
                "character_name": best.get("character_name"),
                "selection_reason": "closest_to_voice_medians",
            }
        )
    return selected


def _build_report_payload(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    data_root: Path,
    db_path: Path,
    threshold_values: QaThresholds,
    manifest_artifacts: dict[str, dict[str, Any]],
    chapter_metrics: dict[str, Any],
    voice_aggregates: list[dict[str, Any]],
    segment_results: list[dict[str, Any]],
    integrity: dict[str, Any],
) -> dict[str, Any]:
    risk_counts: dict[str, int] = {}
    for result in segment_results:
        result["source_limitations"] = sorted(set(result.get("source_limitations", [])))
        for flag in result.get("risk_flags", []):
            risk_counts[flag] = risk_counts.get(flag, 0) + 1
    trailing_values = [float(item["trailing_silence_ms"]) for item in segment_results if item["trailing_silence_ms"] is not None]
    leading_values = [float(item["leading_silence_ms"]) for item in segment_results if item["leading_silence_ms"] is not None]
    internal_values = [float(item["longest_internal_silence_ms"]) for item in segment_results if item["longest_internal_silence_ms"] is not None]
    input_mtimes = [manifest_path.stat().st_mtime]
    input_mtimes.extend(item["mtime_epoch_seconds"] for item in manifest_artifacts.values())
    input_mtimes.extend(
        Path(result["segment_file_absolute_path"]).stat().st_mtime
        for result in segment_results
        if result.get("segment_file_absolute_path") and Path(result["segment_file_absolute_path"]).exists()
    )
    generated_at = _utc_iso_from_epoch(max(input_mtimes))
    report = {
        "schema": AUDIO_QA_SCHEMA,
        "identity": {
            "source_manifest_path": str(manifest_path),
            "source_manifest_sha256": sha256_file(manifest_path),
            "source_manifest_schema": manifest.get("schema"),
            "data_root": str(data_root),
            "data_root_fingerprint": manifest["identity"].get("data_root_fingerprint"),
            "db_path": str(db_path),
            "db_identity": manifest["identity"].get("db_identity"),
            "book_id": manifest["identity"].get("book_id"),
            "book_title": manifest["identity"].get("book_title"),
            "chapter_id": manifest["identity"].get("chapter_id"),
            "chapter_number": manifest["identity"].get("chapter_number"),
            "chapter_title": manifest["identity"].get("chapter_title"),
            "job_id": manifest["identity"].get("job_id"),
            "job_chapter_id": manifest["identity"].get("job_chapter_id"),
            "text_revision_id": manifest["immutable_bindings"].get("text_revision_id"),
            "text_revision_content_sha256": manifest["immutable_bindings"].get("text_revision_content_sha256"),
            "casting_plan_id": manifest["immutable_bindings"].get("casting_plan_id"),
            "casting_plan_revision": manifest["immutable_bindings"].get("casting_plan_revision"),
            "casting_plan_sha256": manifest["immutable_bindings"].get("casting_plan_sha256"),
            "generated_at": generated_at,
            "implementation_version": IMPLEMENTATION_VERSION,
        },
        "thresholds": asdict(threshold_values),
        "chapter_metrics": chapter_metrics,
        "voice_aggregates": voice_aggregates,
        "segment_results": segment_results,
        "risk_summary": {
            "counts_by_type": dict(sorted(risk_counts.items())),
            "top_risk_segments": _top_risky_segments(
                segment_results,
                max_segments=threshold_values.shortlist_max_segments,
            ),
            "representative_segments_by_voice": _representative_segments_by_voice(segment_results, voice_aggregates),
            "all_hard_clipped_segments": [
                {
                    "segment_id": item["segment_id"],
                    "sequence": item["sequence"],
                    "hard_clipping_sample_count": item["hard_clipping_sample_count"],
                    "hard_clipping_sample_ratio": item["hard_clipping_sample_ratio"],
                    "longest_full_scale_run_samples": item["longest_full_scale_run_samples"],
                }
                for item in segment_results
                if int(item.get("hard_clipping_sample_count") or 0) > 0
            ],
            "all_missing_or_corrupt_segments": [
                {
                    "segment_id": item["segment_id"],
                    "sequence": item["sequence"],
                    "artifact_issue": item["artifact_issue"],
                }
                for item in segment_results
                if item.get("artifact_issue")
            ],
            "silence_distribution": {
                "trailing_silence_ms": {
                    **_build_numeric_summary(trailing_values),
                    "count_above_absolute_threshold": sum(
                        1 for value in trailing_values if value >= threshold_values.long_trailing_silence_ms
                    ),
                    "count_materially_above_chapter_median": sum(
                        1 for item in segment_results
                        if float(item["trailing_silence_ms"]) >= threshold_values.long_trailing_silence_ms
                        and float(item.get("trailing_silence_context", {}).get("chapter_excess_ms") or 0.0) >= threshold_values.trailing_silence_excess_ms
                    ),
                },
                "leading_silence_ms": _build_numeric_summary(leading_values),
                "internal_silence_ms": _build_numeric_summary(internal_values),
            },
            "limitation_notes": [
                "Objective heuristics only; no naturalness or pronunciation judgment.",
                "No automatic regenerate, accept, or reject action is performed.",
            ],
        },
        "integrity": integrity,
        "human_boundary": {
            "human_review_required": True,
            "notes": [
                "Objective metrics cannot validate pronunciation, acting, or speaker correctness by ear.",
                "Any candidate action remains an operator decision outside this report.",
            ],
        },
        "mutation_performed": False,
    }
    return report


def _default_output_path(manifest: dict[str, Any], *, data_root: Path) -> Path:
    job_id = int(manifest["identity"]["job_id"])
    chapter_number = int(manifest["identity"]["chapter_number"])
    return (data_root / "qa" / f"job_{job_id}_chapter_{chapter_number}_audio_qa.json").resolve()


def _write_report(report: dict[str, Any], *, target: Path) -> dict[str, Any]:
    payload_bytes = (_canonical_json(report, ensure_ascii=False) + "\n").encode("utf-8")
    if target.exists():
        existing_bytes = target.read_bytes()
        try:
            existing_value = json.loads(existing_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise QaReportConflictError("Existing report is not valid UTF-8 JSON", details={"path": str(target)}) from exc
        if existing_value == report:
            return {
                "path": str(target),
                "sha256": sha256_file(target),
                "size_bytes": target.stat().st_size,
                "reused_existing": True,
            }
        raise QaReportConflictError("Conflicting report already exists", details={"path": str(target)})
    atomic_write_bytes(target, payload_bytes)
    reread = json.loads(target.read_text(encoding="utf-8"))
    if reread != report:
        raise QaInternalError("Report failed logical reread equality", details={"path": str(target)})
    return {
        "path": str(target),
        "sha256": sha256_file(target),
        "size_bytes": target.stat().st_size,
        "reused_existing": False,
    }


def generate_audio_qa_report(
    manifest_path: Path,
    *,
    output_path: Path | None = None,
    ffmpeg_path: str = "ffmpeg",
    ffprobe_path: str = "ffprobe",
    thresholds: QaThresholds | None = None,
    allow_canonical_production: bool = False,
) -> dict[str, Any]:
    manifest_path = _ensure_absolute_path("--manifest", manifest_path)
    if not manifest_path.exists():
        raise QaArgumentError("--manifest path does not exist", details={"path": str(manifest_path)})
    thresholds = thresholds or QaThresholds()
    _check_binary_available(ffmpeg_path, timeout_seconds=thresholds.analysis_timeout_seconds)
    _check_binary_available(ffprobe_path, timeout_seconds=thresholds.analysis_timeout_seconds)

    manifest = _load_json(manifest_path, label="manifest")
    if not isinstance(manifest, dict):
        raise QaManifestError("Manifest root must be a JSON object")
    _validate_manifest_structure(manifest)
    data_root, db_path = _verify_readonly_runtime_identity(
        manifest,
        allow_canonical_production=allow_canonical_production,
    )

    manifest_artifacts = {
        "chapter_master_wav": _verify_manifest_artifact(
            _select_manifest_artifact(manifest, "chapter_master_wav"),
            data_root=data_root,
        ),
        "segment_timeline_json": _verify_manifest_artifact(
            _select_manifest_artifact(manifest, "segment_timeline_json"),
            data_root=data_root,
        ),
    }
    final_artifact_entry = next(
        (
            item
            for item in manifest["artifacts"]
            if str(item.get("artifact_type")) in {"chapter_m4a", "chapter_mp3", "chapter_final_m4a", "chapter_final_mp3"}
        ),
        None,
    )
    if final_artifact_entry is None:
        raise QaManifestError("Manifest is missing final chapter artifact")
    manifest_artifacts["chapter_final"] = _verify_manifest_artifact(final_artifact_entry, data_root=data_root)

    timeline_path = Path(manifest_artifacts["segment_timeline_json"]["absolute_local_path"])
    timeline = _load_json(timeline_path, label="segment timeline")
    items = timeline.get("items")
    if not isinstance(items, list):
        raise QaManifestError("Timeline items must be a JSON list", details={"path": str(timeline_path)})
    if int(timeline.get("chapter_id") or 0) != int(manifest["identity"]["chapter_id"]):
        raise QaManifestError(
            "Timeline chapter_id does not match manifest identity",
            details={"timeline_chapter_id": timeline.get("chapter_id"), "manifest_chapter_id": manifest["identity"]["chapter_id"]},
        )
    if int(timeline.get("text_revision_id") or 0) != int(manifest["immutable_bindings"]["text_revision_id"]):
        raise QaManifestError(
            "Timeline text_revision_id does not match manifest bindings",
            details={
                "timeline_text_revision_id": timeline.get("text_revision_id"),
                "manifest_text_revision_id": manifest["immutable_bindings"]["text_revision_id"],
            },
        )

    segment_rows = _load_segment_rows(db_path, int(manifest["identity"]["job_chapter_id"]))
    if len(segment_rows) != len(items):
        raise QaManifestError(
            "Timeline entry count does not match read-only segment rows",
            details={"timeline_entries": len(items), "segment_rows": len(segment_rows)},
        )

    sequence_map = {int(row["segment_index"]): row for row in segment_rows}
    segment_results = []
    analysis_failures = []
    for item in items:
        sequence = int(item["index"])
        segment_row = sequence_map.get(sequence)
        if segment_row is None:
            raise QaManifestError("Timeline references missing segment row", details={"sequence": sequence})
        if item.get("segment_sha256") and str(item.get("segment_sha256")) != str(segment_row.get("audio_sha256")):
            raise QaManifestError(
                "Timeline segment hash does not match persisted segment hash",
                details={"sequence": sequence, "timeline_segment_sha256": item.get("segment_sha256"), "segment_audio_sha256": segment_row.get("audio_sha256")},
            )
        if item.get("text") is not None and sha256_text(str(item["text"])) != str(segment_row.get("text_sha256")):
            raise QaManifestError(
                "Timeline text does not match persisted segment text hash",
                details={"sequence": sequence},
            )
        if item.get("utterance_sequence") is not None and int(item["utterance_sequence"]) != int(segment_row.get("utterance_sequence") or 0):
            raise QaManifestError(
                "Timeline utterance sequence does not match persisted segment binding",
                details={"sequence": sequence},
            )
        if item.get("speaker_role") and str(item["speaker_role"]) != str(segment_row.get("speaker_role") or ""):
            raise QaManifestError(
                "Timeline speaker role does not match persisted segment binding",
                details={"sequence": sequence},
            )
        if item.get("voice_id") and str(item["voice_id"]) != str(segment_row.get("resolved_voice_id") or ""):
            raise QaManifestError(
                "Timeline voice_id does not match persisted segment binding",
                details={"sequence": sequence},
            )
        wav_path = Path(segment_row["wav_path"]).resolve() if segment_row.get("wav_path") else None
        artifact_issue = None
        metrics = None
        if wav_path is None:
            artifact_issue = "missing_wav_path"
        elif not _path_within_root(wav_path, data_root):
            artifact_issue = "wav_path_outside_data_root"
        elif not wav_path.exists():
            artifact_issue = "missing_segment_file"
        else:
            computed = sha256_file(wav_path)
            if computed != segment_row.get("audio_sha256"):
                artifact_issue = "segment_hash_mismatch"
            else:
                try:
                    metrics = _analyze_audio_file(
                        wav_path,
                        ffmpeg_path=ffmpeg_path,
                        ffprobe_path=ffprobe_path,
                        thresholds=thresholds,
                        timeout_seconds=thresholds.analysis_timeout_seconds,
                    )
                except AudioQaError as exc:
                    artifact_issue = "analysis_failure"
                    analysis_failures.append({"sequence": sequence, "segment_id": int(segment_row["id"]), "error": str(exc)})
                else:
                    metrics["sha256"] = computed
        result = _build_segment_result(
            sequence=sequence,
            segment_row=segment_row,
            timeline_item=item,
            wav_path=wav_path,
            data_root=data_root,
            artifact_issue=artifact_issue,
            metrics=metrics,
        )
        segment_results.append(result)

    chapter_master_path = Path(manifest_artifacts["chapter_master_wav"]["absolute_local_path"])
    chapter_final_path = Path(manifest_artifacts["chapter_final"]["absolute_local_path"])
    master_metrics = _analyze_audio_file(
        chapter_master_path,
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_path,
        thresholds=thresholds,
        timeout_seconds=thresholds.analysis_timeout_seconds,
    )
    final_metrics = _analyze_audio_file(
        chapter_final_path,
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_path,
        thresholds=thresholds,
        timeout_seconds=thresholds.analysis_timeout_seconds,
    )

    voice_aggregates = _build_voice_aggregates(segment_results)
    _flag_segment_risks(segment_results, thresholds=thresholds, voice_aggregates=voice_aggregates)

    integrity = {
        "manifest_sha256_verified": True,
        "artifact_hash_verification": {
            key: {
                "path": value["absolute_local_path"],
                "sha256": value["sha256"],
                "size_bytes": value["size_bytes"],
            }
            for key, value in sorted(manifest_artifacts.items())
        },
        "segment_artifact_issues": [
            {
                "segment_id": item["segment_id"],
                "sequence": item["sequence"],
                "artifact_issue": item["artifact_issue"],
            }
            for item in segment_results
            if item["artifact_issue"]
        ],
        "ffmpeg_failures": analysis_failures,
        "metric_completeness": {
            "segment_total": len(segment_results),
            "segment_metrics_complete": sum(1 for item in segment_results if not item["artifact_issue"]),
            "segment_metrics_missing": sum(1 for item in segment_results if item["artifact_issue"]),
        },
    }

    chapter_metrics = {
        "segment_count": len(segment_results),
        "timeline_duration_ms": _coerce_int(timeline.get("duration_ms")),
        "timeline_sample_rate": _coerce_int(timeline.get("sample_rate")),
        "segment_duration_total_ms": sum(int(item["duration_ms"] or 0) for item in segment_results if item["duration_ms"] is not None),
        "segment_silence_distribution": {
            "leading_silence_ms": _build_numeric_summary(item["leading_silence_ms"] for item in segment_results),
            "trailing_silence_ms": _build_numeric_summary(item["trailing_silence_ms"] for item in segment_results),
            "internal_silence_ms": _build_numeric_summary(item["longest_internal_silence_ms"] for item in segment_results),
        },
        "master_artifact": {
            **manifest_artifacts["chapter_master_wav"],
            **master_metrics,
        },
        "final_artifact": {
            **manifest_artifacts["chapter_final"],
            **final_metrics,
        },
        "format_consistency": {
            "master_sample_rate": master_metrics["sample_rate"],
            "final_sample_rate": final_metrics["sample_rate"],
            "master_channels": master_metrics["channels"],
            "final_channels": final_metrics["channels"],
            "master_duration_ms": master_metrics["duration_ms"],
            "final_duration_ms": final_metrics["duration_ms"],
            "duration_difference_ms": abs(int(master_metrics["duration_ms"]) - int(final_metrics["duration_ms"])),
        },
    }

    report = _build_report_payload(
        manifest_path=manifest_path,
        manifest=manifest,
        data_root=data_root,
        db_path=db_path,
        threshold_values=thresholds,
        manifest_artifacts=manifest_artifacts,
        chapter_metrics=chapter_metrics,
        voice_aggregates=voice_aggregates,
        segment_results=segment_results,
        integrity=integrity,
    )
    target = _ensure_absolute_path("--output", output_path) if output_path is not None else _default_output_path(manifest, data_root=data_root)
    if not _path_within_root(target, data_root):
        raise QaRuntimeMismatchError("Report output path must stay inside isolated data root", details={"path": str(target)})
    write_result = _write_report(report, target=target)
    status = "success" if not integrity["segment_artifact_issues"] and not integrity["ffmpeg_failures"] else "artifact_integrity_failure"
    exit_code = EXIT_SUCCESS if status == "success" else EXIT_ARTIFACT_INTEGRITY_FAILURE
    return {
        "status": status,
        "exit_code": exit_code,
        "report_path": write_result["path"],
        "report_sha256": write_result["sha256"],
        "reused_existing": write_result["reused_existing"],
        "report": report,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline objective audio QA for production manifests")
    parser.add_argument("--manifest", required=True, help="Absolute path to a story-audio-production-manifest/v1 file")
    parser.add_argument("--output", help="Absolute output path for the deterministic QA JSON")
    parser.add_argument("--ffmpeg-path", default="ffmpeg", help="FFmpeg binary path")
    parser.add_argument("--ffprobe-path", default="ffprobe", help="FFprobe binary path")
    parser.add_argument("--allow-canonical-production", action="store_true")
    return parser


def main(argv: list[str] | None = None, *, stdout: Any = None, stderr: Any = None) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    try:
        args = build_arg_parser().parse_args(argv)
        started = time.perf_counter()
        result = generate_audio_qa_report(
            Path(args.manifest),
            output_path=Path(args.output) if args.output else None,
            ffmpeg_path=str(args.ffmpeg_path),
            ffprobe_path=str(args.ffprobe_path),
            allow_canonical_production=bool(args.allow_canonical_production),
        )
        payload = {
            "status": result["status"],
            "exit_code": result["exit_code"],
            "report_path": result["report_path"],
            "report_sha256": result["report_sha256"],
            "reused_existing": result["reused_existing"],
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "segment_count": len(result["report"]["segment_results"]),
            "voice_count": len(result["report"]["voice_aggregates"]),
            "human_review_required": True,
            "mutation_performed": False,
        }
        print(_canonical_json(payload), file=stdout)
        return int(result["exit_code"])
    except AudioQaError as exc:
        _stderr(str(exc), stream=stderr)
        payload = {
            "status": exc.status,
            "exit_code": exc.exit_code,
            "message": str(exc),
            "details": exc.details,
            "mutation_performed": False,
        }
        print(_canonical_json(payload), file=stdout)
        return int(exc.exit_code)
    except SystemExit:
        raise
    except Exception as exc:
        _stderr(f"internal error: {exc}", stream=stderr)
        payload = {
            "status": QaInternalError.status,
            "exit_code": QaInternalError.exit_code,
            "message": "Unhandled internal error while building audio QA report",
            "details": {"exception_type": type(exc).__name__},
            "mutation_performed": False,
        }
        print(_canonical_json(payload), file=stdout)
        return QaInternalError.exit_code
