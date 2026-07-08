from __future__ import annotations

import argparse
import html
import json
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from .audio_qa import AUDIO_QA_SCHEMA
from .config import canonical_production_db_path
from .files import atomic_write_bytes, sha256_file, sha256_text


LISTENING_PACKAGE_VERSION = "listening-checklist/v1"
LISTENING_REVIEW_SCHEMA = "story-audio-listening-review/v1"
MANIFEST_SCHEMA = "story-audio-production-manifest/v1"

EXIT_SUCCESS = 0
EXIT_INVALID_ARGUMENTS = 2
EXIT_INPUT_MISMATCH = 3
EXIT_RUNTIME_ROOT_MISMATCH = 4
EXIT_ARTIFACT_INTEGRITY_FAILURE = 5
EXIT_OUTPUT_CONFLICT = 6
EXIT_INTERNAL_ERROR = 7

_LIVE_ROOT = canonical_production_db_path().resolve().parent
_DEFAULT_MAX_RISK_ITEMS = 20


class ListeningChecklistError(RuntimeError):
    exit_code = EXIT_INPUT_MISMATCH
    status = "input_mismatch"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class ChecklistArgumentError(ListeningChecklistError):
    exit_code = EXIT_INVALID_ARGUMENTS
    status = "invalid_arguments"


class ChecklistInputMismatchError(ListeningChecklistError):
    exit_code = EXIT_INPUT_MISMATCH
    status = "input_mismatch"


class ChecklistRuntimeMismatchError(ListeningChecklistError):
    exit_code = EXIT_RUNTIME_ROOT_MISMATCH
    status = "runtime_root_mismatch"


class ChecklistArtifactIntegrityError(ListeningChecklistError):
    exit_code = EXIT_ARTIFACT_INTEGRITY_FAILURE
    status = "artifact_integrity_failure"


class ChecklistOutputConflictError(ListeningChecklistError):
    exit_code = EXIT_OUTPUT_CONFLICT
    status = "conflicting_existing_package"


class ChecklistInternalError(ListeningChecklistError):
    exit_code = EXIT_INTERNAL_ERROR
    status = "internal_error"


@dataclass(frozen=True)
class ChecklistOptions:
    max_risk_items: int = _DEFAULT_MAX_RISK_ITEMS
    title: str | None = None


def _canonical_json(value: Any, *, ensure_ascii: bool = False) -> str:
    return json.dumps(value, ensure_ascii=ensure_ascii, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ChecklistArgumentError(f"{label} path does not exist", details={"path": str(path)}) from exc
    except json.JSONDecodeError as exc:
        raise ChecklistInputMismatchError(f"{label} is not valid UTF-8 JSON", details={"path": str(path)}) from exc
    if not isinstance(payload, dict):
        raise ChecklistInputMismatchError(f"{label} root must be a JSON object", details={"path": str(path)})
    return payload


def _ensure_absolute_path(label: str, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ChecklistArgumentError(f"{label} must be an absolute path")
    return path.resolve()


def _path_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_relative_to_root(path: Path, root: Path) -> PurePosixPath:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ChecklistRuntimeMismatchError(
            "Path escapes isolated data root",
            details={"path": str(path), "data_root": str(root)},
        ) from exc
    return PurePosixPath(relative.as_posix())


def _reject_symlink_component(path: Path, root: Path) -> None:
    current = path
    root_resolved = root.resolve()
    while True:
        if current.exists() and current.is_symlink():
            raise ChecklistArtifactIntegrityError("Path must not be a symlink", details={"path": str(path)})
        if current.resolve() == root_resolved:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent


def _validate_local_file(
    path: Path,
    *,
    expected_sha256: str | None,
    data_root: Path,
    label: str,
) -> dict[str, Any]:
    if not path.exists():
        raise ChecklistArtifactIntegrityError(f"{label} file is missing", details={"path": str(path)})
    if not path.is_file():
        raise ChecklistArtifactIntegrityError(f"{label} path is not a file", details={"path": str(path)})
    if not _path_within_root(path, data_root):
        raise ChecklistRuntimeMismatchError(
            f"{label} path escapes isolated data root",
            details={"path": str(path), "data_root": str(data_root)},
        )
    _reject_symlink_component(path, data_root)
    computed_sha256 = sha256_file(path)
    if expected_sha256 and computed_sha256 != expected_sha256:
        raise ChecklistArtifactIntegrityError(
            f"{label} hash mismatch",
            details={"path": str(path), "expected_sha256": expected_sha256, "computed_sha256": computed_sha256},
        )
    stat = path.stat()
    return {
        "path": path,
        "sha256": computed_sha256,
        "size_bytes": stat.st_size,
        "mtime_epoch_seconds": stat.st_mtime,
    }


def _resolve_relative_url(package_dir: Path, target: Path, *, data_root: Path) -> str:
    if not _path_within_root(package_dir, data_root):
        raise ChecklistRuntimeMismatchError(
            "Package directory escapes isolated data root",
            details={"package_dir": str(package_dir), "data_root": str(data_root)},
        )
    target_relative = _safe_relative_to_root(target, data_root)
    package_relative = _safe_relative_to_root(package_dir, data_root)
    package_parts = list(package_relative.parts)
    target_parts = list(target_relative.parts)
    common = 0
    for left, right in zip(package_parts, target_parts):
        if left != right:
            break
        common += 1
    upward = [".."] * (len(package_parts) - common)
    remainder = target_parts[common:]
    relative_parts = upward + remainder
    encoded = []
    for part in relative_parts:
        if part in {"", "."}:
            continue
        if part == "..":
            encoded.append("..")
            continue
        encoded.append(quote(part))
    return "/".join(encoded) or "."


def _html_escape(value: Any) -> str:
    return html.escape("--" if value is None else str(value), quote=True)


def _json_script(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _selection_reason_for_hard_clip(segment: dict[str, Any]) -> str:
    return (
        f"hard_clipping_samples={int(segment.get('hard_clipping_sample_count') or 0)} "
        f"ratio={segment.get('hard_clipping_sample_ratio') or 0.0} "
        f"longest_full_scale_run_samples={int(segment.get('longest_full_scale_run_samples') or 0)}"
    )


def _selection_reason_for_integrity(segment: dict[str, Any]) -> str:
    return f"artifact_issue={segment.get('artifact_issue') or 'unknown'}"


def _segment_key(segment: dict[str, Any]) -> tuple[int, int]:
    segment_id = int(segment.get("segment_id") or 0)
    sequence = int(segment.get("sequence") or 0)
    return (segment_id, sequence)


def _rendered_voice_summary(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    distribution = manifest.get("immutable_bindings", {}).get("speaker_voice_distribution") or []
    return [dict(item) for item in distribution if isinstance(item, dict)]


def _deterministic_package_identity(
    *,
    manifest_sha256: str,
    qa_report_sha256: str,
    options: ChecklistOptions,
) -> str:
    return sha256_text(
        _canonical_json(
            {
                "schema": LISTENING_PACKAGE_VERSION,
                "manifest_sha256": manifest_sha256,
                "qa_report_sha256": qa_report_sha256,
                "max_risk_items": int(options.max_risk_items),
                "title": options.title,
            },
            ensure_ascii=False,
        )
    )


def _default_output_path(manifest: dict[str, Any], *, data_root: Path) -> Path:
    identity = manifest["identity"]
    return (
        data_root
        / "listening"
        / f"job_{int(identity['job_id'])}_chapter_{int(identity['chapter_number'])}"
        / "index.html"
    ).resolve()


def _validate_manifest_schema(manifest: dict[str, Any]) -> None:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ChecklistInputMismatchError(
            "Manifest schema is invalid",
            details={"expected": MANIFEST_SCHEMA, "actual": manifest.get("schema")},
        )


def _validate_qa_schema(report: dict[str, Any]) -> None:
    if report.get("schema") != AUDIO_QA_SCHEMA:
        raise ChecklistInputMismatchError(
            "QA report schema is invalid",
            details={"expected": AUDIO_QA_SCHEMA, "actual": report.get("schema")},
        )


def _validate_manifest_report_identity(
    manifest: dict[str, Any],
    report: dict[str, Any],
    *,
    manifest_path: Path,
    qa_report_path: Path,
    manifest_sha256: str,
    qa_report_sha256: str,
    allow_canonical_production: bool = False,
) -> tuple[Path, Path]:
    manifest_identity = manifest.get("identity") or {}
    report_identity = report.get("identity") or {}
    data_root = _ensure_absolute_path("manifest identity.data_root", str(manifest_identity.get("data_root")))
    qa_data_root = _ensure_absolute_path("qa identity.data_root", str(report_identity.get("data_root")))
    if data_root != qa_data_root:
        raise ChecklistInputMismatchError(
            "Manifest and QA report data roots do not match",
            details={"manifest_data_root": str(data_root), "qa_data_root": str(qa_data_root)},
        )
    manifest_db_path = _ensure_absolute_path("manifest identity.db_path", str(manifest_identity.get("db_path"))).resolve()
    if data_root == _LIVE_ROOT and not allow_canonical_production:
        raise ChecklistRuntimeMismatchError("Refusing canonical live data root without explicit canonical approval")
    if manifest_db_path == canonical_production_db_path().resolve() and not allow_canonical_production:
        raise ChecklistRuntimeMismatchError("Refusing canonical live database path without explicit canonical approval")
    if report_identity.get("source_manifest_schema") != MANIFEST_SCHEMA:
        raise ChecklistInputMismatchError(
            "QA report references an unexpected manifest schema",
            details={"actual": report_identity.get("source_manifest_schema")},
        )
    if _ensure_absolute_path("qa identity.source_manifest_path", str(report_identity.get("source_manifest_path"))) != manifest_path.resolve():
        raise ChecklistInputMismatchError(
            "QA report references a different source manifest path",
            details={"expected": str(manifest_path.resolve()), "actual": report_identity.get("source_manifest_path")},
        )
    if str(report_identity.get("source_manifest_sha256") or "") != manifest_sha256:
        raise ChecklistInputMismatchError(
            "QA report source manifest hash does not match the provided manifest",
            details={"expected": manifest_sha256, "actual": report_identity.get("source_manifest_sha256")},
        )
    identity_fields = (
        "book_id",
        "chapter_id",
        "chapter_number",
        "job_id",
        "job_chapter_id",
        "text_revision_id",
        "casting_plan_id",
        "casting_plan_revision",
        "casting_plan_sha256",
        "text_revision_content_sha256",
    )
    for field in identity_fields:
        manifest_value = (
            manifest_identity.get(field)
            if field in manifest_identity
            else (manifest.get("immutable_bindings") or {}).get(field)
        )
        report_value = report_identity.get(field)
        if manifest_value != report_value:
            raise ChecklistInputMismatchError(
                f"Manifest and QA report disagree on {field}",
                details={"field": field, "manifest": manifest_value, "qa_report": report_value},
            )
    if qa_report_sha256 != sha256_file(qa_report_path):
        raise ChecklistArtifactIntegrityError("QA report hash verification drifted", details={"path": str(qa_report_path)})
    return data_root, qa_data_root


def _artifact_by_type(manifest: dict[str, Any], artifact_type: str) -> dict[str, Any]:
    for artifact in manifest.get("artifacts", []):
        if str(artifact.get("artifact_type")) == artifact_type:
            return artifact
    raise ChecklistInputMismatchError("Manifest artifact is missing", details={"artifact_type": artifact_type})


def _final_artifact(manifest: dict[str, Any]) -> dict[str, Any]:
    for artifact in manifest.get("artifacts", []):
        if str(artifact.get("artifact_type")) in {"chapter_m4a", "chapter_mp3", "chapter_final_m4a", "chapter_final_mp3"}:
            return artifact
    raise ChecklistInputMismatchError("Manifest final chapter artifact is missing")


def _compare_artifact_contract(
    manifest_artifact: dict[str, Any],
    qa_artifact: dict[str, Any],
    *,
    artifact_type: str,
) -> None:
    if str(qa_artifact.get("artifact_type")) != artifact_type:
        raise ChecklistInputMismatchError(
            "QA report artifact type mismatch",
            details={"expected": artifact_type, "actual": qa_artifact.get("artifact_type")},
        )
    fields = ("absolute_local_path", "path_relative_to_data_root", "sha256")
    for field in fields:
        manifest_value = manifest_artifact.get("absolute_local_path") if field == "absolute_local_path" else (
            manifest_artifact.get("path_relative_to_data_root") if field == "path_relative_to_data_root" else (
                manifest_artifact.get("computed_sha256") if field == "sha256" else manifest_artifact.get(field)
            )
        )
        qa_value = qa_artifact.get(field)
        if manifest_value != qa_value:
            raise ChecklistInputMismatchError(
                "Manifest and QA artifact contracts do not match",
                details={"artifact_type": artifact_type, "field": field, "manifest": manifest_value, "qa_report": qa_value},
            )


def _segment_maps(
    manifest: dict[str, Any],
    report: dict[str, Any],
    timeline: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    timeline_items = timeline.get("items")
    if not isinstance(timeline_items, list):
        raise ChecklistInputMismatchError("Timeline items must be a list")
    segments = report.get("segment_results")
    if not isinstance(segments, list):
        raise ChecklistInputMismatchError("QA segment_results must be a list")
    if len(timeline_items) != len(segments):
        raise ChecklistInputMismatchError(
            "Timeline and QA segment counts do not match",
            details={"timeline_count": len(timeline_items), "qa_count": len(segments)},
        )
    manifest_summary = manifest.get("segment_integrity_summary") or {}
    expected_count = int(manifest_summary.get("segment_count") or len(timeline_items))
    if expected_count != len(segments):
        raise ChecklistInputMismatchError(
            "Manifest segment count does not match QA report",
            details={"manifest_count": expected_count, "qa_count": len(segments)},
        )
    timeline_by_sequence: dict[int, dict[str, Any]] = {}
    qa_by_sequence: dict[int, dict[str, Any]] = {}
    qa_by_segment_id: dict[int, dict[str, Any]] = {}
    ordered_segments: list[dict[str, Any]] = []
    for timeline_item, qa_segment in zip(timeline_items, segments):
        sequence = int(timeline_item.get("index") or 0)
        if sequence != int(qa_segment.get("sequence") or 0):
            raise ChecklistInputMismatchError(
                "Timeline sequence does not match QA sequence",
                details={"timeline_sequence": sequence, "qa_sequence": qa_segment.get("sequence")},
            )
        if qa_segment.get("text") != timeline_item.get("text"):
            raise ChecklistInputMismatchError(
                "Timeline text does not match QA text",
                details={"sequence": sequence},
            )
        if int(qa_segment.get("chapter_start_ms") or 0) != int(timeline_item.get("start_ms") or 0):
            raise ChecklistInputMismatchError("Timeline start_ms does not match QA segment", details={"sequence": sequence})
        if int(qa_segment.get("chapter_end_ms") or 0) != int(timeline_item.get("end_ms") or 0):
            raise ChecklistInputMismatchError("Timeline end_ms does not match QA segment", details={"sequence": sequence})
        if qa_segment.get("speaker_role") != timeline_item.get("speaker_role"):
            raise ChecklistInputMismatchError("Timeline speaker_role does not match QA segment", details={"sequence": sequence})
        if qa_segment.get("character_name") != timeline_item.get("character_name"):
            raise ChecklistInputMismatchError("Timeline character_name does not match QA segment", details={"sequence": sequence})
        if qa_segment.get("resolved_voice_id") != timeline_item.get("voice_id"):
            raise ChecklistInputMismatchError("Timeline voice_id does not match QA segment", details={"sequence": sequence})
        if qa_segment.get("segment_audio_sha256") != timeline_item.get("segment_sha256"):
            raise ChecklistInputMismatchError("Timeline segment hash does not match QA segment", details={"sequence": sequence})
        timeline_by_sequence[sequence] = dict(timeline_item)
        qa_by_sequence[sequence] = dict(qa_segment)
        if qa_segment.get("segment_id") is not None:
            qa_by_segment_id[int(qa_segment["segment_id"])] = dict(qa_segment)
        ordered_segments.append(dict(qa_segment))
    return ordered_segments, timeline_by_sequence, qa_by_sequence, qa_by_segment_id


def _validate_segment_audio_files(segments: list[dict[str, Any]], *, data_root: Path) -> None:
    for segment in segments:
        audio_path = _ensure_absolute_path("segment audio path", str(segment.get("segment_file_absolute_path")))
        _validate_local_file(
            audio_path,
            expected_sha256=str(segment.get("segment_audio_sha256") or ""),
            data_root=data_root,
            label=f"Segment {segment.get('sequence')}",
        )
        relative_path = str(segment.get("segment_file_relative_to_data_root") or "")
        actual_relative = _safe_relative_to_root(audio_path, data_root).as_posix()
        if relative_path != actual_relative:
            raise ChecklistInputMismatchError(
                "Segment relative audio path does not match actual path",
                details={"sequence": segment.get("sequence"), "expected": relative_path, "actual": actual_relative},
            )


def _selection_entry(
    segment: dict[str, Any],
    *,
    category: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "segment_key": _segment_key(segment),
        "segment_id": segment.get("segment_id"),
        "sequence": segment.get("sequence"),
        "category": category,
        "reason": reason,
    }


def _ordered_unique_selection(
    segments: list[dict[str, Any]],
    report: dict[str, Any],
    *,
    max_risk_items: int,
) -> list[dict[str, Any]]:
    by_segment_id = {
        int(segment["segment_id"]): segment
        for segment in segments
        if segment.get("segment_id") is not None
    }
    by_sequence = {int(segment["sequence"]): segment for segment in segments}

    entries: list[dict[str, Any]] = []
    for item in report["risk_summary"].get("all_missing_or_corrupt_segments", []):
        segment = by_segment_id.get(int(item.get("segment_id") or 0)) or by_sequence.get(int(item.get("sequence") or 0))
        if segment is None:
            raise ChecklistInputMismatchError("Integrity selection references missing segment", details=item)
        entries.append(_selection_entry(segment, category="integrity_failure", reason=_selection_reason_for_integrity(segment)))

    for item in report["risk_summary"].get("all_hard_clipped_segments", []):
        segment = by_segment_id.get(int(item.get("segment_id") or 0)) or by_sequence.get(int(item.get("sequence") or 0))
        if segment is None:
            raise ChecklistInputMismatchError("Hard-clipping selection references missing segment", details=item)
        entries.append(_selection_entry(segment, category="hard_clipping", reason=_selection_reason_for_hard_clip(segment)))

    ordinary_risks = []
    for item in report["risk_summary"].get("top_risk_segments", []):
        segment = by_segment_id.get(int(item.get("segment_id") or 0)) or by_sequence.get(int(item.get("sequence") or 0))
        if segment is None:
            raise ChecklistInputMismatchError("Top-risk selection references missing segment", details=item)
        ordinary_risks.append(
            _selection_entry(
                segment,
                category="top_risk",
                reason=str(item.get("selection_reason") or "; ".join(segment.get("risk_reasons") or []) or "top_risk"),
            )
        )
    ordinary_risks.sort(
        key=lambda item: (
            -float(by_sequence[int(item["sequence"])]["risk_score"] or 0),
            int(item["sequence"]),
            int(item["segment_id"] or 0),
        )
    )
    entries.extend(ordinary_risks[: max(0, int(max_risk_items))])

    representative_seen: set[str] = set()
    representative_items = sorted(
        (dict(item) for item in report["risk_summary"].get("representative_segments_by_voice", [])),
        key=lambda item: (
            str(item.get("voice_id") or ""),
            int(item.get("sequence") or 0),
            int(item.get("segment_id") or 0),
        ),
    )
    for item in representative_items:
        voice_id = str(item.get("voice_id") or "")
        representative_seen.add(voice_id)
        segment = by_segment_id.get(int(item.get("segment_id") or 0)) or by_sequence.get(int(item.get("sequence") or 0))
        if segment is None:
            raise ChecklistInputMismatchError("Representative selection references missing segment", details=item)
        entries.append(
            _selection_entry(
                segment,
                category="representative_sample",
                reason=str(item.get("selection_reason") or "representative_sample"),
            )
        )
    for voice_id in sorted({str(segment.get("resolved_voice_id") or "") for segment in segments}):
        if voice_id in representative_seen:
            continue
        voice_segments = sorted(
            (segment for segment in segments if str(segment.get("resolved_voice_id") or "") == voice_id),
            key=lambda segment: (int(segment.get("sequence") or 0), int(segment.get("segment_id") or 0)),
        )
        if voice_segments:
            entries.append(
                _selection_entry(
                    voice_segments[0],
                    category="representative_sample",
                    reason="fallback_representative_for_realized_voice",
                )
            )

    if segments:
        entries.append(_selection_entry(segments[0], category="first_segment", reason="first_sequence_coverage"))
        entries.append(_selection_entry(segments[-1], category="last_segment", reason="last_sequence_coverage"))

    deduped: dict[tuple[int, int], dict[str, Any]] = {}
    ordered_keys: list[tuple[int, int]] = []
    for entry in entries:
        key = tuple(entry["segment_key"])
        if key not in deduped:
            deduped[key] = {
                "segment": by_segment_id.get(int(entry["segment_id"] or 0)) or by_sequence[int(entry["sequence"])],
                "selection_categories": [],
                "selection_reasons": [],
            }
            ordered_keys.append(key)
        if entry["category"] not in deduped[key]["selection_categories"]:
            deduped[key]["selection_categories"].append(entry["category"])
        if entry["reason"] not in deduped[key]["selection_reasons"]:
            deduped[key]["selection_reasons"].append(entry["reason"])
    return [
        {
            **deduped[key]["segment"],
            "selection_categories": deduped[key]["selection_categories"],
            "selection_reasons": deduped[key]["selection_reasons"],
        }
        for key in ordered_keys
    ]
def _review_controls(segment: dict[str, Any]) -> str:
    segment_id = int(segment.get("segment_id") or 0)
    name = f"decision-{segment_id}"
    control_id = f"segment-{segment_id}"
    return f"""
      <fieldset class="review-controls">
        <legend>Operator review</legend>
        <div class="decision-row" role="radiogroup" aria-label="Review decision for segment {segment_id}">
          <label><input type="radio" name="{_html_escape(name)}" value="pass"> Pass</label>
          <label><input type="radio" name="{_html_escape(name)}" value="needs_attention"> Needs attention</label>
          <label><input type="radio" name="{_html_escape(name)}" value="regenerate_suggested"> Regenerate suggested</label>
          <label><input type="radio" name="{_html_escape(name)}" value="skipped"> Skipped</label>
        </div>
        <div class="issue-grid">
          <label><input type="checkbox" data-issue="pronunciation"> pronunciation issue</label>
          <label><input type="checkbox" data-issue="wrong_speaker_or_voice"> wrong speaker/voice</label>
          <label><input type="checkbox" data-issue="pacing"> pacing issue</label>
          <label><input type="checkbox" data-issue="silence"> silence issue</label>
          <label><input type="checkbox" data-issue="clipping_or_distortion"> clipping/distortion</label>
          <label><input type="checkbox" data-issue="emotional_delivery"> emotional delivery issue</label>
        </div>
        <label class="notes-label" for="{_html_escape(control_id)}-note">Notes</label>
        <textarea id="{_html_escape(control_id)}-note" data-note rows="3"></textarea>
      </fieldset>
    """


def _render_segment_card(segment: dict[str, Any], *, audio_url: str) -> str:
    segment_id = int(segment.get("segment_id") or 0)
    sequence = int(segment.get("sequence") or 0)
    risk_flags = segment.get("risk_flags") or []
    risk_reasons = segment.get("risk_reasons") or []
    selection_categories = segment.get("selection_categories") or []
    selection_reasons = segment.get("selection_reasons") or []
    all_reasons = selection_reasons + [reason for reason in risk_reasons if reason not in selection_reasons]
    search_blob = " ".join(
        str(value or "")
        for value in (
            sequence,
            segment_id,
            segment.get("speaker_role"),
            segment.get("character_name"),
            segment.get("resolved_voice_id"),
            segment.get("text"),
        )
    ).lower()
    category_blob = " ".join(selection_categories + risk_flags).lower()
    return f"""
    <article
      class="segment-card"
      id="segment-card-{segment_id or sequence}"
      data-segment-id="{segment_id}"
      data-sequence="{sequence}"
      data-search="{_html_escape(search_blob)}"
      data-risk-flags="{_html_escape(' '.join(risk_flags).lower())}"
      data-selection-categories="{_html_escape(category_blob)}"
      data-default-state="unreviewed"
    >
      <header class="segment-card-header">
        <div>
          <h3>Sequence {sequence} - Segment {segment_id or "--"}</h3>
          <p class="identity-line">
            <span>Speaker role: {_html_escape(segment.get("speaker_role"))}</span>
            <span>Character: {_html_escape(segment.get("character_name"))}</span>
            <span>Voice: {_html_escape(segment.get("resolved_voice_id"))}</span>
          </p>
          <p class="identity-line">
            <span>Chapter time: {_html_escape(segment.get("chapter_start_ms"))}-{_html_escape(segment.get("chapter_end_ms"))} ms</span>
            <span>Duration: {_html_escape(segment.get("duration_ms"))} ms</span>
            <span>Speech rate: {_html_escape(segment.get("chars_per_second"))}</span>
          </p>
        </div>
        <div class="selection-tags" aria-label="Selection reasons">
          {"".join(f'<span class=\"tag\">{_html_escape(item)}</span>' for item in selection_categories)}
        </div>
      </header>
      <details open>
        <summary>Text</summary>
        <p class="segment-text">{_html_escape(segment.get("text"))}</p>
      </details>
      <div class="audio-row">
        <audio controls preload="none" src="{_html_escape(audio_url)}"></audio>
        <div class="jump-controls">
          <button type="button" class="jump-button" data-jump-target="master-audio" data-jump-ms="{int(segment.get('chapter_start_ms') or 0)}">Jump master</button>
          <button type="button" class="jump-button" data-jump-target="final-audio" data-jump-ms="{int(segment.get('chapter_start_ms') or 0)}">Jump final</button>
        </div>
      </div>
      <details>
        <summary>Objective metrics</summary>
        <dl class="metric-grid">
          <div><dt>Mean volume</dt><dd>{_html_escape(segment.get("mean_volume_dbfs"))}</dd></div>
          <div><dt>Max peak</dt><dd>{_html_escape(segment.get("max_peak_dbfs"))}</dd></div>
          <div><dt>Hard clipping samples</dt><dd>{_html_escape(segment.get("hard_clipping_sample_count"))}</dd></div>
          <div><dt>Hard clipping ratio</dt><dd>{_html_escape(segment.get("hard_clipping_sample_ratio"))}</dd></div>
          <div><dt>Longest full-scale run</dt><dd>{_html_escape(segment.get("longest_full_scale_run_samples"))}</dd></div>
          <div><dt>Near clipping samples</dt><dd>{_html_escape(segment.get("near_clipping_sample_count"))}</dd></div>
          <div><dt>Near clipping ratio</dt><dd>{_html_escape(segment.get("near_clipping_sample_ratio"))}</dd></div>
          <div><dt>Leading silence</dt><dd>{_html_escape(segment.get("leading_silence_ms"))} ms</dd></div>
          <div><dt>Trailing silence</dt><dd>{_html_escape(segment.get("trailing_silence_ms"))} ms</dd></div>
          <div><dt>Longest internal silence</dt><dd>{_html_escape(segment.get("longest_internal_silence_ms"))} ms</dd></div>
        </dl>
      </details>
      <details>
        <summary>Selection and risk reasons</summary>
        <ul class="reason-list">
          {"".join(f'<li>{_html_escape(reason)}</li>' for reason in all_reasons)}
        </ul>
      </details>
      <details>
        <summary>Risk flags and limitations</summary>
        <p><strong>Risk flags:</strong> {_html_escape(", ".join(risk_flags) if risk_flags else "--")}</p>
        <p><strong>Artifact issue:</strong> {_html_escape(segment.get("artifact_issue"))}</p>
        <p><strong>Limitations:</strong> {_html_escape(", ".join(segment.get("source_limitations") or []) if segment.get("source_limitations") else "--")}</p>
      </details>
      {_review_controls(segment)}
    </article>
    """


def _render_html(
    *,
    manifest: dict[str, Any],
    report: dict[str, Any],
    manifest_sha256: str,
    qa_report_sha256: str,
    package_identity: str,
    selected_segments: list[dict[str, Any]],
    package_dir: Path,
    data_root: Path,
    output_path: Path,
    options: ChecklistOptions,
) -> str:
    identity = manifest["identity"]
    bindings = manifest["immutable_bindings"]
    chapter_metrics = report["chapter_metrics"]
    risk_summary = report["risk_summary"]
    realized_voices = _rendered_voice_summary(manifest)
    master_url = _resolve_relative_url(package_dir, Path(chapter_metrics["master_artifact"]["absolute_local_path"]), data_root=data_root)
    final_url = _resolve_relative_url(package_dir, Path(chapter_metrics["final_artifact"]["absolute_local_path"]), data_root=data_root)
    cards_html = []
    for segment in selected_segments:
        audio_url = _resolve_relative_url(package_dir, Path(segment["segment_file_absolute_path"]), data_root=data_root)
        cards_html.append(_render_segment_card(segment, audio_url=audio_url))
    page_title = options.title or f"Listening Checklist - Job {int(identity['job_id'])} Chapter {int(identity['chapter_number'])}"
    bootstrap = {
        "package_identity": package_identity,
        "review_schema": LISTENING_REVIEW_SCHEMA,
        "manifest_sha256": manifest_sha256,
        "qa_report_sha256": qa_report_sha256,
        "job_id": int(identity["job_id"]),
        "chapter_id": int(identity["chapter_id"]),
        "chapter_number": int(identity["chapter_number"]),
        "text_revision_id": int(bindings["text_revision_id"]),
        "casting_plan_id": int(bindings["casting_plan_id"]),
        "casting_plan_revision": int(bindings["casting_plan_revision"]),
        "selected_segments": [
            {
                "segment_id": int(segment.get("segment_id") or 0),
                "sequence": int(segment.get("sequence") or 0),
                "selection_reasons": segment.get("selection_reasons") or [],
            }
            for segment in selected_segments
        ],
    }
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_html_escape(page_title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #0f1419;
      --surface: #182028;
      --surface-2: #202b35;
      --text: #f3f7fb;
      --muted: #b9c7d6;
      --accent: #68b0ff;
      --border: #314252;
      --danger: #ff8c82;
      --warn: #ffd36b;
      --ok: #86d39b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    main {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
    h1, h2, h3 {{ margin: 0 0 8px; }}
    p, li, dd, dt, summary, label, button, input, select, textarea {{ font-size: 14px; }}
    .warning {{ color: var(--warn); font-weight: 700; }}
    .section {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
    }}
    .header-grid, .overview-grid, .progress-grid, .filter-grid, .metric-grid {{
      display: grid;
      gap: 12px;
    }}
    .header-grid {{ grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
    .overview-grid {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }}
    .progress-grid {{ grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }}
    .filter-grid {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); align-items: end; }}
    .metric-grid {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }}
    .metric-grid div {{
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
    }}
    .metric-grid dt {{ color: var(--muted); }}
    .metric-grid dd {{ margin: 4px 0 0; font-weight: 700; }}
    .audio-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
      margin: 12px 0;
    }}
    audio {{ width: 100%; }}
    .jump-controls {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .segment-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
    }}
    .segment-card[hidden] {{ display: none; }}
    .segment-card-header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      flex-wrap: wrap;
    }}
    .identity-line {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      color: var(--muted);
      margin: 4px 0;
    }}
    .tag {{
      display: inline-block;
      padding: 4px 8px;
      border: 1px solid var(--border);
      border-radius: 999px;
      margin: 0 4px 4px 0;
      color: var(--accent);
      background: transparent;
    }}
    .reason-list {{
      padding-left: 20px;
      margin: 8px 0 0;
    }}
    .review-controls {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      margin-top: 12px;
    }}
    .decision-row, .issue-grid {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }}
    .notes-label {{ display: block; margin-bottom: 6px; }}
    textarea, input[type="search"], select {{
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #0b1015;
      color: var(--text);
      padding: 8px;
    }}
    button {{
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--surface-2);
      color: var(--text);
      padding: 8px 10px;
      cursor: pointer;
    }}
    button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible, summary:focus-visible {{
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }}
    .summary-count {{ font-size: 24px; font-weight: 700; }}
    .summary-label {{ color: var(--muted); }}
    .section-actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .chapter-audio-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }}
    .small-mono {{ font-family: Consolas, monospace; word-break: break-all; }}
    @media (max-width: 720px) {{
      .audio-row {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="section">
      <h1>{_html_escape(page_title)}</h1>
      <p class="warning">Metrics are review aids, not a final quality decision.</p>
      <div class="header-grid">
        <div><strong>Book</strong><div>{_html_escape(identity.get("book_title"))}</div></div>
        <div><strong>Chapter</strong><div>{_html_escape(identity.get("chapter_number"))} - {_html_escape(identity.get("chapter_title"))}</div></div>
        <div><strong>Job ID</strong><div>{_html_escape(identity.get("job_id"))}</div></div>
        <div><strong>Text Revision</strong><div>{_html_escape(bindings.get("text_revision_id"))} - <span class="small-mono">{_html_escape(bindings.get("text_revision_content_sha256"))}</span></div></div>
        <div><strong>Casting Plan</strong><div>{_html_escape(bindings.get("casting_plan_id"))} rev {_html_escape(bindings.get("casting_plan_revision"))} - <span class="small-mono">{_html_escape(bindings.get("casting_plan_sha256"))}</span></div></div>
        <div><strong>Package version</strong><div>{_html_escape(LISTENING_PACKAGE_VERSION)}</div></div>
        <div><strong>Package identity</strong><div class="small-mono">{_html_escape(package_identity)}</div></div>
        <div><strong>Production manifest SHA-256</strong><div class="small-mono">{_html_escape(manifest_sha256)}</div></div>
        <div><strong>QA report SHA-256</strong><div class="small-mono">{_html_escape(qa_report_sha256)}</div></div>
      </div>
    </section>

    <section class="section">
      <h2>Chapter Overview</h2>
      <div class="overview-grid">
        <div><strong>Chapter duration</strong><div>{_html_escape(chapter_metrics['final_artifact'].get('duration_ms'))} ms</div></div>
        <div><strong>Total segments</strong><div>{_html_escape(chapter_metrics.get('segment_count'))}</div></div>
        <div><strong>Realized voices</strong><div>{_html_escape(len(realized_voices))}</div></div>
        <div><strong>Master mean / peak</strong><div>{_html_escape(chapter_metrics['master_artifact'].get('mean_volume_dbfs'))} / {_html_escape(chapter_metrics['master_artifact'].get('max_peak_dbfs'))}</div></div>
        <div><strong>Final mean / peak</strong><div>{_html_escape(chapter_metrics['final_artifact'].get('mean_volume_dbfs'))} / {_html_escape(chapter_metrics['final_artifact'].get('max_peak_dbfs'))}</div></div>
        <div><strong>Hard clipping segments</strong><div>{_html_escape(len(risk_summary.get('all_hard_clipped_segments') or []))}</div></div>
      </div>
      <div class="chapter-audio-grid">
        <div>
          <h3>Chapter master WAV</h3>
          <audio id="master-audio" controls preload="none" src="{_html_escape(master_url)}"></audio>
          <p class="small-mono">{_html_escape(chapter_metrics['master_artifact'].get('sha256'))}</p>
        </div>
        <div>
          <h3>Final output</h3>
          <audio id="final-audio" controls preload="none" src="{_html_escape(final_url)}"></audio>
          <p class="small-mono">{_html_escape(chapter_metrics['final_artifact'].get('sha256'))}</p>
        </div>
      </div>
      <details>
        <summary>Risk-count summary</summary>
        <ul class="reason-list">
          {"".join(f"<li>{_html_escape(key)}: {_html_escape(value)}</li>" for key, value in sorted((risk_summary.get('counts_by_type') or {}).items()))}
        </ul>
      </details>
      <details>
        <summary>Realized voices</summary>
        <ul class="reason-list">
          {"".join(f'<li>{_html_escape(item.get("speaker_role"))}: {_html_escape(item.get("voice_id"))} - {_html_escape(item.get("segment_count"))} segments</li>' for item in realized_voices)}
        </ul>
      </details>
    </section>

    <section class="section">
      <h2>Review Progress</h2>
      <div class="progress-grid" id="review-progress">
        <div><div class="summary-count" id="count-unreviewed">0</div><div class="summary-label">not reviewed</div></div>
        <div><div class="summary-count" id="count-pass">0</div><div class="summary-label">pass</div></div>
        <div><div class="summary-count" id="count-needs-attention">0</div><div class="summary-label">needs attention</div></div>
        <div><div class="summary-count" id="count-regenerate-suggested">0</div><div class="summary-label">regenerate suggested</div></div>
        <div><div class="summary-count" id="count-skipped">0</div><div class="summary-label">skipped</div></div>
      </div>
      <div class="section-actions">
        <button type="button" id="reset-local-review">Reset local review</button>
        <button type="button" id="export-review-json">Export review JSON</button>
      </div>
    </section>

    <section class="section">
      <h2>Filters</h2>
      <div class="filter-grid">
        <label>
          Queue filter
          <select id="queue-filter">
            <option value="all">all</option>
            <option value="unreviewed">unreviewed</option>
            <option value="hard_clipping">hard clipping</option>
            <option value="silence">silence</option>
            <option value="loudness">loudness</option>
            <option value="representative_sample">representative samples</option>
          </select>
        </label>
        <label>
          Decision filter
          <select id="decision-filter">
            <option value="all">all decisions</option>
            <option value="unreviewed">unreviewed</option>
            <option value="pass">pass</option>
            <option value="needs_attention">needs attention</option>
            <option value="regenerate_suggested">regenerate suggested</option>
            <option value="skipped">skipped</option>
          </select>
        </label>
        <label>
          Search
          <input id="segment-search" type="search" placeholder="sequence, speaker, voice, or text">
        </label>
      </div>
    </section>

    <section class="section">
      <h2>Priority Review Queue</h2>
      <p>{_html_escape(len(selected_segments))} selected entries. Hard-clipping and integrity issues are always included; ordinary ranked risks are capped by the configured maximum.</p>
      {"".join(cards_html)}
    </section>
  </main>

  <script id="package-bootstrap" type="application/json">{_json_script(bootstrap)}</script>
  <script>
    (() => {{
      "use strict";
      const bootstrap = JSON.parse(document.getElementById("package-bootstrap").textContent);
      const storageKey = "story-audio-listening-review:" + bootstrap.package_identity;
      const cards = Array.from(document.querySelectorAll(".segment-card"));
      function loadState() {{
        try {{
          const raw = window.localStorage.getItem(storageKey);
          return raw ? JSON.parse(raw) : {{}};
        }} catch (_error) {{
          return {{}};
        }}
      }}

      function saveState(state) {{
        window.localStorage.setItem(storageKey, JSON.stringify(state));
      }}

      function defaultSegmentState() {{
        return {{
          decision: "unreviewed",
          issues: {{}},
          note: "",
        }};
      }}

      function readCardState(card) {{
        const segmentId = String(card.dataset.segmentId || "");
        const checked = card.querySelector('input[type="radio"]:checked');
        const state = {{
          decision: checked ? checked.value : "unreviewed",
          issues: {{}},
          note: card.querySelector("[data-note]").value || "",
        }};
        card.querySelectorAll("input[data-issue]").forEach((input) => {{
          state.issues[input.dataset.issue] = Boolean(input.checked);
        }});
        return [segmentId, state];
      }}

      function writeCardState(card, state) {{
        const merged = Object.assign(defaultSegmentState(), state || {{}});
        card.querySelectorAll('input[type="radio"]').forEach((input) => {{
          input.checked = input.value === merged.decision && merged.decision !== "unreviewed";
        }});
        card.querySelectorAll("input[data-issue]").forEach((input) => {{
          input.checked = Boolean((merged.issues || {{}})[input.dataset.issue]);
        }});
        card.querySelector("[data-note]").value = merged.note || "";
        card.dataset.reviewDecision = merged.decision;
      }}

      function updateProgress(state) {{
        const counts = {{
          unreviewed: 0,
          pass: 0,
          needs_attention: 0,
          regenerate_suggested: 0,
          skipped: 0,
        }};
        cards.forEach((card) => {{
          const segmentId = String(card.dataset.segmentId || "");
          const cardState = state[segmentId] || defaultSegmentState();
          const decision = cardState.decision || "unreviewed";
          counts[decision] = (counts[decision] || 0) + 1;
        }});
        document.getElementById("count-unreviewed").textContent = String(counts.unreviewed);
        document.getElementById("count-pass").textContent = String(counts.pass);
        document.getElementById("count-needs-attention").textContent = String(counts.needs_attention);
        document.getElementById("count-regenerate-suggested").textContent = String(counts.regenerate_suggested);
        document.getElementById("count-skipped").textContent = String(counts.skipped);
      }}

      function saveAllState() {{
        const nextState = {{}};
        cards.forEach((card) => {{
          const [segmentId, cardState] = readCardState(card);
          nextState[segmentId] = cardState;
        }});
        saveState(nextState);
        updateProgress(nextState);
        applyFilters(nextState);
      }}

      function matchesQueueFilter(card, queueFilter) {{
        if (queueFilter === "all") {{
          return true;
        }}
        if (queueFilter === "unreviewed") {{
          return (card.dataset.reviewDecision || "unreviewed") === "unreviewed";
        }}
        if (queueFilter === "representative_sample") {{
          return (card.dataset.selectionCategories || "").includes("representative_sample");
        }}
        return (card.dataset.riskFlags || "").includes(queueFilter) || (card.dataset.selectionCategories || "").includes(queueFilter);
      }}

      function matchesDecisionFilter(card, decisionFilter) {{
        if (decisionFilter === "all") {{
          return true;
        }}
        return (card.dataset.reviewDecision || "unreviewed") === decisionFilter;
      }}

      function matchesSearch(card, query) {{
        if (!query) {{
          return true;
        }}
        return (card.dataset.search || "").includes(query);
      }}

      function applyFilters(state) {{
        const queueFilter = document.getElementById("queue-filter").value;
        const decisionFilter = document.getElementById("decision-filter").value;
        const search = document.getElementById("segment-search").value.trim().toLowerCase();
        cards.forEach((card) => {{
          const segmentId = String(card.dataset.segmentId || "");
          const cardState = state[segmentId] || defaultSegmentState();
          card.dataset.reviewDecision = cardState.decision || "unreviewed";
          const visible = matchesQueueFilter(card, queueFilter) && matchesDecisionFilter(card, decisionFilter) && matchesSearch(card, search);
          card.hidden = !visible;
        }});
      }}

      function exportReviewJson() {{
        const state = loadState();
        const selected = bootstrap.selected_segments.map((segment) => {{
          const segmentId = String(segment.segment_id || 0);
          const cardState = state[segmentId] || defaultSegmentState();
          return {{
            segment_id: segment.segment_id || null,
            sequence: segment.sequence || null,
            decision: cardState.decision || "unreviewed",
            issues: Object.assign({{}}, cardState.issues || {{}}),
            note: cardState.note || "",
            selection_reasons: segment.selection_reasons || [],
          }};
        }});
        const summary_counts = {{
          unreviewed: 0,
          pass: 0,
          needs_attention: 0,
          regenerate_suggested: 0,
          skipped: 0,
        }};
        selected.forEach((item) => {{
          const key = item.decision || "unreviewed";
          summary_counts[key] = (summary_counts[key] || 0) + 1;
        }});
        const payload = {{
          schema: bootstrap.review_schema,
          package_identity: bootstrap.package_identity,
          production_manifest_sha256: bootstrap.manifest_sha256,
          qa_report_sha256: bootstrap.qa_report_sha256,
          job_id: bootstrap.job_id,
          chapter_id: bootstrap.chapter_id,
          chapter_number: bootstrap.chapter_number,
          text_revision_id: bootstrap.text_revision_id,
          casting_plan_id: bootstrap.casting_plan_id,
          casting_plan_revision: bootstrap.casting_plan_revision,
          exported_at: new Date().toISOString(),
          summary_counts,
          segments: selected,
        }};
        const blob = new Blob([JSON.stringify(payload, null, 2) + "\\n"], {{ type: "application/json" }});
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `listening_review_job_${{bootstrap.job_id}}_chapter_${{bootstrap.chapter_number}}.json`;
        link.click();
        URL.revokeObjectURL(url);
      }}

      function resetReviewState() {{
        window.localStorage.removeItem(storageKey);
        const state = {{}};
        cards.forEach((card) => writeCardState(card, defaultSegmentState()));
        updateProgress(state);
        applyFilters(state);
      }}

      function jumpAudio(event) {{
        const button = event.target.closest(".jump-button");
        if (!button) {{
          return;
        }}
        const audio = document.getElementById(button.dataset.jumpTarget || "");
        if (!(audio instanceof HTMLMediaElement)) {{
          return;
        }}
        const ms = Number(button.dataset.jumpMs || "0");
        audio.currentTime = Math.max(0, ms / 1000);
        audio.focus();
      }}

      const initialState = loadState();
      cards.forEach((card) => {{
        const segmentId = String(card.dataset.segmentId || "");
        writeCardState(card, initialState[segmentId] || defaultSegmentState());
        card.addEventListener("change", saveAllState);
        card.querySelector("[data-note]").addEventListener("input", saveAllState);
      }});
      document.getElementById("queue-filter").addEventListener("change", () => applyFilters(loadState()));
      document.getElementById("decision-filter").addEventListener("change", () => applyFilters(loadState()));
      document.getElementById("segment-search").addEventListener("input", () => applyFilters(loadState()));
      document.getElementById("reset-local-review").addEventListener("click", resetReviewState);
      document.getElementById("export-review-json").addEventListener("click", exportReviewJson);
      document.addEventListener("click", jumpAudio);
      updateProgress(initialState);
      applyFilters(initialState);
    }})();
  </script>
</body>
</html>
"""


def _write_html_package(
    html_text: str,
    *,
    target: Path,
) -> dict[str, Any]:
    payload_bytes = html_text.encode("utf-8")
    package_dir = target.parent
    if package_dir.exists():
        unknown_files = [
            path.name
            for path in package_dir.iterdir()
            if path.name != target.name
        ]
        if unknown_files:
            raise ChecklistOutputConflictError(
                "Listening package directory contains unexpected existing files",
                details={"path": str(package_dir), "unknown_files": sorted(unknown_files)},
            )
    if target.exists():
        existing_bytes = target.read_bytes()
        if existing_bytes == payload_bytes:
            return {
                "path": str(target),
                "sha256": sha256_file(target),
                "size_bytes": target.stat().st_size,
                "reused_existing": True,
            }
        raise ChecklistOutputConflictError("Conflicting listening checklist already exists", details={"path": str(target)})
    atomic_write_bytes(target, payload_bytes)
    if target.read_bytes() != payload_bytes:
        raise ChecklistInternalError("Listening checklist reread bytes do not match", details={"path": str(target)})
    return {
        "path": str(target),
        "sha256": sha256_file(target),
        "size_bytes": target.stat().st_size,
        "reused_existing": False,
    }


def build_listening_checklist(
    manifest_path: Path,
    qa_report_path: Path,
    *,
    output_path: Path | None = None,
    options: ChecklistOptions | None = None,
    allow_canonical_production: bool = False,
) -> dict[str, Any]:
    manifest_path = _ensure_absolute_path("--manifest", manifest_path)
    qa_report_path = _ensure_absolute_path("--qa-report", qa_report_path)
    if not manifest_path.exists():
        raise ChecklistArgumentError("--manifest path does not exist", details={"path": str(manifest_path)})
    if not qa_report_path.exists():
        raise ChecklistArgumentError("--qa-report path does not exist", details={"path": str(qa_report_path)})
    options = options or ChecklistOptions()
    if int(options.max_risk_items) < 0:
        raise ChecklistArgumentError("--max-risk-items must be >= 0")
    manifest = _load_json(manifest_path, label="manifest")
    report = _load_json(qa_report_path, label="qa report")
    _validate_manifest_schema(manifest)
    _validate_qa_schema(report)
    manifest_sha256 = sha256_file(manifest_path)
    qa_report_sha256 = sha256_file(qa_report_path)
    data_root, _qa_data_root = _validate_manifest_report_identity(
        manifest,
        report,
        manifest_path=manifest_path,
        qa_report_path=qa_report_path,
        manifest_sha256=manifest_sha256,
        qa_report_sha256=qa_report_sha256,
        allow_canonical_production=allow_canonical_production,
    )
    master_artifact = _artifact_by_type(manifest, "chapter_master_wav")
    timeline_artifact = _artifact_by_type(manifest, "segment_timeline_json")
    final_artifact = _final_artifact(manifest)
    master_file = _validate_local_file(
        _ensure_absolute_path("master artifact", str(master_artifact["absolute_local_path"])),
        expected_sha256=str(master_artifact.get("computed_sha256") or master_artifact.get("stored_sha256") or ""),
        data_root=data_root,
        label="Chapter master",
    )
    timeline_file = _validate_local_file(
        _ensure_absolute_path("timeline artifact", str(timeline_artifact["absolute_local_path"])),
        expected_sha256=str(timeline_artifact.get("computed_sha256") or timeline_artifact.get("stored_sha256") or ""),
        data_root=data_root,
        label="Timeline",
    )
    final_file = _validate_local_file(
        _ensure_absolute_path("final artifact", str(final_artifact["absolute_local_path"])),
        expected_sha256=str(final_artifact.get("computed_sha256") or final_artifact.get("stored_sha256") or ""),
        data_root=data_root,
        label="Final chapter artifact",
    )
    _compare_artifact_contract(master_artifact, report["chapter_metrics"]["master_artifact"], artifact_type="chapter_master_wav")
    _compare_artifact_contract(final_artifact, report["chapter_metrics"]["final_artifact"], artifact_type=str(final_artifact["artifact_type"]))
    timeline = _load_json(Path(timeline_file["path"]), label="timeline")
    ordered_segments, timeline_by_sequence, _qa_by_sequence, _qa_by_segment_id = _segment_maps(manifest, report, timeline)
    _validate_segment_audio_files(ordered_segments, data_root=data_root)
    package_identity = _deterministic_package_identity(
        manifest_sha256=manifest_sha256,
        qa_report_sha256=qa_report_sha256,
        options=options,
    )
    target = _ensure_absolute_path("--output", output_path) if output_path is not None else _default_output_path(manifest, data_root=data_root)
    if not _path_within_root(target, data_root):
        raise ChecklistRuntimeMismatchError("Listening checklist output must stay inside isolated data root", details={"path": str(target)})
    selected_segments = _ordered_unique_selection(
        ordered_segments,
        report,
        max_risk_items=int(options.max_risk_items),
    )
    html_text = _render_html(
        manifest=manifest,
        report=report,
        manifest_sha256=manifest_sha256,
        qa_report_sha256=qa_report_sha256,
        package_identity=package_identity,
        selected_segments=selected_segments,
        package_dir=target.parent,
        data_root=data_root,
        output_path=target,
        options=options,
    )
    write_result = _write_html_package(html_text, target=target)
    return {
        "status": "success",
        "exit_code": EXIT_SUCCESS,
        "package_path": write_result["path"],
        "package_sha256": write_result["sha256"],
        "package_size_bytes": write_result["size_bytes"],
        "package_identity": package_identity,
        "reused_existing": write_result["reused_existing"],
        "selected_segment_count": len(selected_segments),
        "hard_clipping_count": len(report["risk_summary"].get("all_hard_clipped_segments") or []),
        "integrity_failure_count": len(report["risk_summary"].get("all_missing_or_corrupt_segments") or []),
        "report": {
            "manifest_sha256": manifest_sha256,
            "qa_report_sha256": qa_report_sha256,
            "selected_segments": selected_segments,
            "timeline_items": timeline_by_sequence,
            "master_sha256": master_file["sha256"],
            "timeline_sha256": timeline_file["sha256"],
            "final_sha256": final_file["sha256"],
        },
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a deterministic local listening checklist HTML package")
    parser.add_argument("--manifest", required=True, help="Absolute path to a story-audio-production-manifest/v1 file")
    parser.add_argument("--qa-report", required=True, help="Absolute path to a story-audio-audio-qa/v1 file")
    parser.add_argument("--output", help="Absolute HTML output path inside the isolated data root")
    parser.add_argument("--max-risk-items", type=int, default=_DEFAULT_MAX_RISK_ITEMS, help="Maximum ordinary ranked risks to include")
    parser.add_argument("--title", help="Optional deterministic page title override")
    parser.add_argument("--allow-canonical-production", action="store_true")
    return parser


def main(argv: list[str] | None = None, *, stdout: Any = None, stderr: Any = None) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    try:
        args = build_arg_parser().parse_args(argv)
        result = build_listening_checklist(
            Path(args.manifest),
            Path(args.qa_report),
            output_path=Path(args.output) if args.output else None,
            options=ChecklistOptions(max_risk_items=int(args.max_risk_items), title=args.title),
            allow_canonical_production=bool(args.allow_canonical_production),
        )
        payload = {
            "status": result["status"],
            "exit_code": result["exit_code"],
            "package_path": result["package_path"],
            "package_sha256": result["package_sha256"],
            "package_size_bytes": result["package_size_bytes"],
            "package_identity": result["package_identity"],
            "reused_existing": result["reused_existing"],
            "selected_segment_count": result["selected_segment_count"],
            "hard_clipping_count": result["hard_clipping_count"],
            "integrity_failure_count": result["integrity_failure_count"],
            "mutation_performed": False,
        }
        print(_canonical_json(payload, ensure_ascii=False), file=stdout)
        return EXIT_SUCCESS
    except ListeningChecklistError as exc:
        print(str(exc), file=stderr, flush=True)
        payload = {
            "status": exc.status,
            "exit_code": exc.exit_code,
            "message": str(exc),
            "details": exc.details,
            "mutation_performed": False,
        }
        print(_canonical_json(payload, ensure_ascii=False), file=stdout)
        return int(exc.exit_code)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"internal error: {exc}", file=stderr, flush=True)
        payload = {
            "status": ChecklistInternalError.status,
            "exit_code": ChecklistInternalError.exit_code,
            "message": "Unhandled internal error while building listening checklist",
            "details": {"exception_type": type(exc).__name__},
            "mutation_performed": False,
        }
        print(_canonical_json(payload, ensure_ascii=False), file=stdout)
        return ChecklistInternalError.exit_code
