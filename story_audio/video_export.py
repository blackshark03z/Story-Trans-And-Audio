from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from .config import Settings
from .db import Database, utcnow
from .files import atomic_write_json, safe_slug, sha256_file, sha256_text


VIDEO_EXPORT_SCHEMA = "story-audio-video-export/v1"
VIDEO_EXPORT_CONFIG: dict[str, Any] = {
    "container": "mp4",
    "video_codec": "libx264",
    "audio_codec": "aac",
    "audio_bitrate": "128k",
    "pixel_format": "yuv420p",
    "width": 1280,
    "height": 720,
    "frame_rate": 1,
    "visual_kind": "deterministic_static_color",
    "visual_color": "0x173b2c",
}


class VideoExportError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _load_active_audio_artifact(db: Database, artifact_id: int) -> dict[str, Any]:
    row = db.fetch_one(
        """
        SELECT a.*,
               c.book_id,
               c.chapter_number,
               c.title AS chapter_title,
               c.active_audio_artifact_id,
               c.human_approval_json,
               b.title AS book_title,
               jc.job_id,
               jc.status AS job_chapter_status
        FROM artifacts a
        JOIN chapters c ON c.id=a.chapter_id
        JOIN books b ON b.id=c.book_id
        LEFT JOIN job_chapters jc ON jc.id=a.job_chapter_id
        WHERE a.id=? AND a.deleted_at IS NULL
        """,
        (artifact_id,),
    )
    if not row:
        raise VideoExportError("ARTIFACT_NOT_FOUND", "Artifact was not found.")
    data = dict(row)
    if int(data.get("active_audio_artifact_id") or 0) != artifact_id:
        raise VideoExportError(
            "ARTIFACT_NOT_ACTIVE",
            "Video export requires the current active audio Artifact.",
        )
    if str(data.get("artifact_type") or "") not in {"chapter_m4a", "chapter_mp3"}:
        raise VideoExportError("UNSUPPORTED_AUDIO_ARTIFACT", "Only final chapter audio can be exported.")
    if str(data.get("job_chapter_status") or "") != "completed":
        raise VideoExportError("ACTIVE_BINDING_INVALID", "The active Artifact is not bound to a completed JobChapter.")
    try:
        approval = json.loads(data.get("human_approval_json") or "{}")
    except (TypeError, ValueError) as exc:
        raise VideoExportError("HUMAN_QA_NOT_ACCEPTED", "Human QA approval is required before video export.") from exc
    if (
        not isinstance(approval, dict)
        or approval.get("status") != "approved"
        or int(approval.get("artifact_id") or 0) != artifact_id
    ):
        raise VideoExportError("HUMAN_QA_NOT_ACCEPTED", "Human QA approval is required before video export.")
    source = Path(str(data["path"])).resolve(strict=False)
    if not source.is_absolute():
        raise VideoExportError("AUDIO_PATH_INVALID", "Audio path is invalid.")
    if not source.is_file():
        raise VideoExportError("AUDIO_FILE_MISSING", "The active audio file is missing.")
    actual_sha = sha256_file(source)
    if actual_sha != str(data["sha256"]):
        raise VideoExportError("AUDIO_HASH_MISMATCH", "The active audio file no longer matches Artifact metadata.")
    data["source_path"] = source
    data["actual_audio_sha256"] = actual_sha
    data["human_approval"] = approval
    return data


def _export_id(artifact: Mapping[str, Any]) -> str:
    config_sha = sha256_text(json.dumps(VIDEO_EXPORT_CONFIG, sort_keys=True, separators=(",", ":")))
    return f"artifact-{int(artifact['id'])}-{str(artifact['sha256'])[:12]}-{config_sha[:12]}"


def _export_paths(config: Settings, artifact: Mapping[str, Any]) -> tuple[str, Path, Path]:
    export_id = _export_id(artifact)
    root = config.output_dir / "video_exports" / f"artifact_{int(artifact['id'])}" / export_id
    stem = (
        f"{safe_slug(str(artifact.get('book_title') or 'book'))}-"
        f"chapter-{int(artifact.get('chapter_number') or 0):04d}-"
        f"artifact-{int(artifact['id'])}-{export_id.rsplit('-', 1)[-1]}"
    )
    return export_id, root / f"{stem}.mp4", root / "manifest.json"


def _ffprobe(path: Path, *, ffprobe_path: str = "ffprobe") -> dict[str, Any]:
    result = subprocess.run(
        [
            ffprobe_path,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if result.returncode != 0:
        raise VideoExportError("FFPROBE_FAILED", result.stderr.strip() or "ffprobe failed.")
    try:
        return json.loads(result.stdout)
    except ValueError as exc:
        raise VideoExportError("FFPROBE_INVALID_JSON", "ffprobe returned invalid JSON.") from exc


def _duration_ms(probe: Mapping[str, Any]) -> int | None:
    value = (probe.get("format") or {}).get("duration")
    if value in (None, ""):
        return None
    return int(round(float(value) * 1000))


def _validate_manifest(manifest: Mapping[str, Any], output_path: Path) -> bool:
    if manifest.get("schema") != VIDEO_EXPORT_SCHEMA:
        return False
    if not output_path.is_file():
        return False
    if int(manifest.get("size_bytes") or -1) != output_path.stat().st_size:
        return False
    return str(manifest.get("sha256") or "") == sha256_file(output_path)


def inspect_video_export(db: Database, config: Settings, artifact_id: int) -> dict[str, Any] | None:
    try:
        artifact = _load_active_audio_artifact(db, artifact_id)
    except VideoExportError:
        return None
    export_id, output_path, manifest_path = _export_paths(config, artifact)
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if manifest.get("export_id") != export_id:
        return None
    if int(manifest.get("source_artifact_id") or 0) != artifact_id:
        return None
    if manifest.get("source_audio_sha256") != artifact["sha256"]:
        return None
    if not _validate_manifest(manifest, output_path):
        return None
    return {
        "export_id": export_id,
        "source_artifact_id": artifact_id,
        "download_url": f"/api/video-exports/{export_id}/file",
        "sha256": manifest["sha256"],
        "size_bytes": int(manifest["size_bytes"]),
        "duration_ms": manifest.get("duration_ms"),
        "video_codec": manifest.get("video_codec"),
        "audio_codec": manifest.get("audio_codec"),
        "width": manifest.get("width"),
        "height": manifest.get("height"),
        "reused": True,
    }


def create_video_export(
    db: Database,
    config: Settings,
    artifact_id: int,
    *,
    ffmpeg_path: str = "ffmpeg",
    ffprobe_path: str = "ffprobe",
) -> dict[str, Any]:
    artifact = _load_active_audio_artifact(db, artifact_id)
    export_id, output_path, manifest_path = _export_paths(config, artifact)
    existing = inspect_video_export(db, config, artifact_id)
    if existing:
        return existing

    audio_duration = int(artifact["duration_ms"]) if artifact.get("duration_ms") is not None else None
    if audio_duration is None or audio_duration <= 0:
        raise VideoExportError(
            "AUDIO_DURATION_MISSING",
            "The accepted audio duration is required for deterministic video export.",
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_suffix(".partial.mp4")
    partial.unlink(missing_ok=True)
    visual = (
        f"color=c={VIDEO_EXPORT_CONFIG['visual_color']}:"
        f"s={VIDEO_EXPORT_CONFIG['width']}x{VIDEO_EXPORT_CONFIG['height']}:"
        f"r={VIDEO_EXPORT_CONFIG['frame_rate']}"
    )
    command = [
        ffmpeg_path,
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        visual,
        "-i",
        str(artifact["source_path"]),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        str(VIDEO_EXPORT_CONFIG["video_codec"]),
        "-preset",
        "veryfast",
        "-tune",
        "stillimage",
        "-pix_fmt",
        str(VIDEO_EXPORT_CONFIG["pixel_format"]),
        "-c:a",
        str(VIDEO_EXPORT_CONFIG["audio_codec"]),
        "-b:a",
        str(VIDEO_EXPORT_CONFIG["audio_bitrate"]),
        "-movflags",
        "+faststart",
        "-t",
        f"{audio_duration / 1000:.3f}",
        "-shortest",
        str(partial),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=180)
    if result.returncode != 0:
        partial.unlink(missing_ok=True)
        raise VideoExportError("FFMPEG_EXPORT_FAILED", result.stderr.strip() or "ffmpeg export failed.")
    partial.replace(output_path)

    try:
        probe = _ffprobe(output_path, ffprobe_path=ffprobe_path)
        streams = probe.get("streams") or []
        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        if not video_streams:
            raise VideoExportError("VIDEO_STREAM_MISSING", "Exported MP4 has no video stream.")
        if not audio_streams:
            raise VideoExportError("AUDIO_STREAM_MISSING", "Exported MP4 has no audio stream.")
        if (probe.get("format") or {}).get("format_name") and "mp4" not in str(
            (probe.get("format") or {}).get("format_name")
        ):
            raise VideoExportError("MP4_CONTAINER_MISSING", "Exported file is not an MP4 container.")
        duration_ms = _duration_ms(probe)
        duration_delta = abs(duration_ms - audio_duration) if duration_ms is not None else None
        if duration_delta is not None and duration_delta > 1500:
            raise VideoExportError("DURATION_MISMATCH", "Video duration does not match accepted audio duration.")
    except VideoExportError:
        output_path.unlink(missing_ok=True)
        raise

    video = video_streams[0]
    audio = audio_streams[0]
    manifest = {
        "schema": VIDEO_EXPORT_SCHEMA,
        "export_id": export_id,
        "source_artifact_id": int(artifact["id"]),
        "source_audio_sha256": artifact["sha256"],
        "source_audio_duration_ms": audio_duration,
        "source_audio_path": str(artifact["source_path"]),
        "config": dict(VIDEO_EXPORT_CONFIG),
        "path": str(output_path),
        "sha256": sha256_file(output_path),
        "size_bytes": output_path.stat().st_size,
        "duration_ms": duration_ms,
        "duration_delta_ms": duration_delta,
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "created_at": utcnow(),
    }
    atomic_write_json(manifest_path, manifest)
    return {
        "export_id": export_id,
        "source_artifact_id": int(artifact["id"]),
        "download_url": f"/api/video-exports/{export_id}/file",
        "sha256": manifest["sha256"],
        "size_bytes": manifest["size_bytes"],
        "duration_ms": manifest["duration_ms"],
        "duration_delta_ms": manifest["duration_delta_ms"],
        "video_codec": manifest["video_codec"],
        "audio_codec": manifest["audio_codec"],
        "width": manifest["width"],
        "height": manifest["height"],
        "reused": False,
    }


def load_video_export_file(
    db: Database,
    config: Settings,
    export_id: str,
) -> tuple[Path, dict[str, Any]]:
    if not re.fullmatch(r"artifact-\d+-[0-9a-f]{12}-[0-9a-f]{12}", export_id):
        raise VideoExportError("EXPORT_ID_INVALID", "Video export id is invalid.")
    artifact_id = int(export_id.split("-", 2)[1])
    manifest_path = config.output_dir / "video_exports" / f"artifact_{artifact_id}" / export_id / "manifest.json"
    if not manifest_path.is_file():
        raise VideoExportError("EXPORT_NOT_FOUND", "Video export was not found.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VideoExportError("EXPORT_MANIFEST_INVALID", "Video export manifest is invalid.") from exc
    if manifest.get("export_id") != export_id:
        raise VideoExportError("EXPORT_MANIFEST_MISMATCH", "Video export manifest does not match the requested id.")
    artifact = _load_active_audio_artifact(db, artifact_id)
    if _export_id(artifact) != export_id:
        raise VideoExportError(
            "EXPORT_SOURCE_STALE",
            "Video export no longer matches the active accepted audio Artifact.",
        )
    if manifest.get("source_audio_sha256") != artifact["sha256"]:
        raise VideoExportError(
            "EXPORT_SOURCE_STALE",
            "Video export no longer matches the active accepted audio Artifact.",
        )
    output_path = Path(str(manifest.get("path") or "")).resolve(strict=False)
    if not _is_within(output_path, config.output_dir):
        raise VideoExportError("EXPORT_PATH_UNSAFE", "Video export path is outside managed output storage.")
    if not _validate_manifest(manifest, output_path):
        raise VideoExportError("EXPORT_FILE_INVALID", "Video export file is missing or has changed.")
    return output_path, manifest


__all__ = [
    "VIDEO_EXPORT_CONFIG",
    "VIDEO_EXPORT_SCHEMA",
    "VideoExportError",
    "create_video_export",
    "inspect_video_export",
    "load_video_export_file",
]
