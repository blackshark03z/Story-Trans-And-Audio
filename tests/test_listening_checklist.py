from __future__ import annotations

import io
import json
import shutil
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock
from urllib.parse import unquote

from story_audio.audio_qa import AUDIO_QA_SCHEMA
from story_audio.files import atomic_write_bytes, sha256_file, sha256_text
from story_audio.listening_checklist import (
    LISTENING_REVIEW_SCHEMA,
    MANIFEST_SCHEMA,
    ChecklistArgumentError,
    ChecklistArtifactIntegrityError,
    ChecklistInputMismatchError,
    ChecklistOptions,
    ChecklistOutputConflictError,
    ChecklistRuntimeMismatchError,
    _validate_local_file,
    _resolve_relative_url,
    build_listening_checklist,
    main,
)
from tests.base import IsolatedTestCase


class _AudioSrcParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.audio_srcs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "audio":
            return
        mapping = dict(attrs)
        src = mapping.get("src")
        if src:
            self.audio_srcs.append(src)


class ListeningChecklistFixture:
    def __init__(self, case: IsolatedTestCase) -> None:
        self.case = case
        self.data_root = case.config.data_dir.resolve()
        self.output_root = self.data_root / "output" / "book_1" / "chapter_0629" / "job_2" / "render_0001"
        self.work_root = self.data_root / "work" / "job_2" / "chapter_0629" / "segments"
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.master_path = self.output_root / "chapter_master.wav"
        self.timeline_path = self.output_root / "segment_timeline.json"
        self.final_path = self.output_root / "chapter.m4a"
        self.manifest_path = self.data_root / "manifests" / "job_2_chapter_629.json"
        self.qa_report_path = self.data_root / "qa" / "job_2_chapter_629_audio_qa.json"
        self.segment_paths: dict[int, Path] = {}

    def build(self) -> None:
        shutil.rmtree(self.data_root, ignore_errors=True)
        self.case.config.ensure_dirs()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.work_root.mkdir(parents=True, exist_ok=True)
        segment_defs = [
            {
                "sequence": 1,
                "segment_id": 101,
                "text": "Trần Trí nhìn về phía xa.",
                "speaker_role": "narrator",
                "character_name": None,
                "voice_id": "Ngọc Lan",
                "start_ms": 0,
                "end_ms": 1000,
                "duration_ms": 1000,
                "risk_flags": [],
                "risk_reasons": [],
                "risk_score": 0,
                "hard_clipping_sample_count": 0,
                "hard_clipping_sample_ratio": 0.0,
                "longest_full_scale_run_samples": 0,
                "near_clipping_sample_count": 0,
                "near_clipping_sample_ratio": 0.0,
                "mean_volume_dbfs": -16.1,
                "max_peak_dbfs": -1.2,
                "leading_silence_ms": 80,
                "trailing_silence_ms": 320,
                "longest_internal_silence_ms": 0,
                "total_internal_silence_ms": 0,
                "chars_per_second": 22.0,
                "selection_reason": None,
                "resolution_source": "narrator",
            },
            {
                "sequence": 2,
                "segment_id": 102,
                "text": "Ati gằn giọng: \"Ta không lùi bước.\"",
                "speaker_role": "character",
                "character_name": "Ati",
                "voice_id": "Đức Trí",
                "start_ms": 1000,
                "end_ms": 2100,
                "duration_ms": 1100,
                "risk_flags": ["hard_clipping", "near_clipping"],
                "risk_reasons": ["hard_clipping_samples=3 ratio=0.001 longest_full_scale_run_samples=2", "near_clipping_samples=5 ratio=0.002"],
                "risk_score": 140,
                "hard_clipping_sample_count": 3,
                "hard_clipping_sample_ratio": 0.001,
                "longest_full_scale_run_samples": 2,
                "near_clipping_sample_count": 5,
                "near_clipping_sample_ratio": 0.002,
                "mean_volume_dbfs": -18.0,
                "max_peak_dbfs": 0.0,
                "leading_silence_ms": 0,
                "trailing_silence_ms": 410,
                "longest_internal_silence_ms": 0,
                "total_internal_silence_ms": 0,
                "chars_per_second": 16.0,
                "selection_reason": "hard_clipping_samples=3 ratio=0.001 longest_full_scale_run_samples=2; near_clipping_samples=5 ratio=0.002",
                "resolution_source": "book_male",
            },
            {
                "sequence": 3,
                "segment_id": 103,
                "text": "Mỹ Duyên khẽ đáp.",
                "speaker_role": "character",
                "character_name": "Tử Huyền",
                "voice_id": "Mỹ Duyên",
                "start_ms": 2100,
                "end_ms": 3000,
                "duration_ms": 900,
                "risk_flags": ["long_trailing_silence"],
                "risk_reasons": ["trailing_silence_ms=480 chapter_median_ms=350.0 chapter_excess_ms=130.0"],
                "risk_score": 40,
                "hard_clipping_sample_count": 0,
                "hard_clipping_sample_ratio": 0.0,
                "longest_full_scale_run_samples": 0,
                "near_clipping_sample_count": 0,
                "near_clipping_sample_ratio": 0.0,
                "mean_volume_dbfs": -17.5,
                "max_peak_dbfs": -2.5,
                "leading_silence_ms": 0,
                "trailing_silence_ms": 480,
                "longest_internal_silence_ms": 0,
                "total_internal_silence_ms": 0,
                "chars_per_second": 18.0,
                "selection_reason": "trailing_silence_ms=480 chapter_median_ms=350.0 chapter_excess_ms=130.0",
                "resolution_source": "book_female",
            },
            {
                "sequence": 4,
                "segment_id": 104,
                "text": "Kết thúc chương bằng một câu ngắn.",
                "speaker_role": "narrator",
                "character_name": None,
                "voice_id": "Ngọc Lan",
                "start_ms": 3000,
                "end_ms": 4300,
                "duration_ms": 1300,
                "risk_flags": ["adjacent_loudness_jump"],
                "risk_reasons": ["adjacent_jump_db=7.1 previous_sequence=3"],
                "risk_score": 20,
                "hard_clipping_sample_count": 0,
                "hard_clipping_sample_ratio": 0.0,
                "longest_full_scale_run_samples": 0,
                "near_clipping_sample_count": 0,
                "near_clipping_sample_ratio": 0.0,
                "mean_volume_dbfs": -14.0,
                "max_peak_dbfs": -1.0,
                "leading_silence_ms": 0,
                "trailing_silence_ms": 250,
                "longest_internal_silence_ms": 0,
                "total_internal_silence_ms": 0,
                "chars_per_second": 14.0,
                "selection_reason": "adjacent_jump_db=7.1 previous_sequence=3",
                "resolution_source": "narrator",
            },
        ]
        for definition in segment_defs:
            payload = (f"WAV-{definition['sequence']}-" + definition["text"]).encode("utf-8")
            if int(definition["sequence"]) == 3:
                path = self.work_root / "Mỹ Duyên" / f"{definition['sequence']:06d}.wav"
            else:
                path = self.work_root / f"{definition['sequence']:06d}.wav"
            atomic_write_bytes(path, payload)
            definition["segment_path"] = path
            definition["segment_sha256"] = sha256_file(path)
            definition["text_sha256"] = sha256_text(definition["text"])
            self.segment_paths[int(definition["sequence"])] = path
        atomic_write_bytes(self.master_path, b"MASTER-WAV")
        atomic_write_bytes(self.final_path, b"FINAL-M4A")
        master_sha = sha256_file(self.master_path)
        final_sha = sha256_file(self.final_path)
        timeline = {
            "schema_version": 2,
            "chapter_id": 629,
            "text_revision_id": 1258,
            "sample_rate": 48_000,
            "duration_ms": 4300,
            "items": [
                {
                    "index": item["sequence"],
                    "text": item["text"],
                    "start_ms": item["start_ms"],
                    "end_ms": item["end_ms"],
                    "duration_ms": item["duration_ms"],
                    "segment_sha256": item["segment_sha256"],
                    "utterance_sequence": item["sequence"],
                    "speaker_role": item["speaker_role"],
                    "character_id": item["segment_id"] if item["character_name"] else None,
                    "character_name": item["character_name"],
                    "voice_id": item["voice_id"],
                    "resolution_source": item["resolution_source"],
                    "resolved_gender": "unknown",
                    "needs_review": False,
                    "voice_profile_id": 1,
                    "voice_profile_version": 1,
                    "synthesis_hash": f"synth-{item['sequence']}",
                }
                for item in segment_defs
            ],
        }
        self.timeline_path.write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
        timeline_sha = sha256_file(self.timeline_path)
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "identity": {
                "data_root": str(self.data_root),
                "data_root_fingerprint": sha256_text(str(self.data_root).replace("\\", "/")),
                "db_path": str((self.data_root / "app.db").resolve()),
                "db_identity": {"schema_version": 9},
                "book_id": 1,
                "book_title": "Quang Âm Chi Ngoại",
                "chapter_id": 629,
                "chapter_number": 629,
                "chapter_title": "Chương 629",
                "job_id": 2,
                "job_chapter_id": 2,
                "output_format": "m4a",
                "render_generation": "render_0001",
                "repair_mode": "off",
            },
            "immutable_bindings": {
                "book_voice_profile_id": 1,
                "book_voice_profile_version": 1,
                "casting_plan_id": 2,
                "casting_plan_revision": 1,
                "casting_plan_sha256": "c" * 64,
                "character_bible_fingerprint": None,
                "derived_default_voice": "Ngọc Lan",
                "persisted_text_revision_id": 1258,
                "persisted_text_revision_sha256": "a" * 64,
                "speaker_voice_distribution": [
                    {"segment_count": 2, "speaker_role": "narrator", "voice_id": "Ngọc Lan"},
                    {"segment_count": 1, "speaker_role": "character", "voice_id": "Đức Trí"},
                    {"segment_count": 1, "speaker_role": "character", "voice_id": "Mỹ Duyên"},
                ],
                "text_revision_content_sha256": "a" * 64,
                "text_revision_id": 1258,
            },
            "terminal_state": {
                "expected_segments": 4,
                "failed_segments": 0,
                "final_duration_ms": 4300,
                "finished_at": "2026-07-06T00:00:00+00:00",
                "job_chapter_status": "completed",
                "job_status": "completed",
                "pending_segments": 0,
                "retry_recovery_metadata": {"job_chapter_error_message": None, "job_error_message": None},
                "running_segments": 0,
                "started_at": "2026-07-06T00:00:00+00:00",
                "verified_segments": 4,
            },
            "artifacts": [
                {
                    "absolute_local_path": str(self.master_path),
                    "artifact_id": 4,
                    "artifact_type": "chapter_master_wav",
                    "computed_sha256": master_sha,
                    "duration_ms": 4300,
                    "mime_type": "audio/wav",
                    "mtime_epoch_seconds": self.master_path.stat().st_mtime,
                    "path_relative_to_data_root": self.master_path.resolve().relative_to(self.data_root).as_posix(),
                    "size_bytes": self.master_path.stat().st_size,
                    "status": "verified",
                    "stored_sha256": master_sha,
                },
                {
                    "absolute_local_path": str(self.timeline_path),
                    "artifact_id": 5,
                    "artifact_type": "segment_timeline_json",
                    "computed_sha256": timeline_sha,
                    "duration_ms": 4300,
                    "mime_type": "application/json",
                    "mtime_epoch_seconds": self.timeline_path.stat().st_mtime,
                    "path_relative_to_data_root": self.timeline_path.resolve().relative_to(self.data_root).as_posix(),
                    "size_bytes": self.timeline_path.stat().st_size,
                    "status": "verified",
                    "stored_sha256": timeline_sha,
                },
                {
                    "absolute_local_path": str(self.final_path),
                    "artifact_id": 6,
                    "artifact_type": "chapter_m4a",
                    "computed_sha256": final_sha,
                    "duration_ms": 4300,
                    "mime_type": "audio/mp4",
                    "mtime_epoch_seconds": self.final_path.stat().st_mtime,
                    "path_relative_to_data_root": self.final_path.resolve().relative_to(self.data_root).as_posix(),
                    "size_bytes": self.final_path.stat().st_size,
                    "status": "active",
                    "stored_sha256": final_sha,
                },
            ],
            "segment_integrity_summary": {
                "duplicate_sequences": [],
                "duration_total_ms": 4300,
                "hash_mismatches": [],
                "missing_files": [],
                "missing_sequences": [],
                "segment_count": 4,
                "sequence_max": 4,
                "sequence_min": 1,
                "timeline_entry_count": 4,
            },
            "mutation_performed": False,
        }
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        manifest_sha = sha256_file(self.manifest_path)
        report = {
            "schema": AUDIO_QA_SCHEMA,
            "identity": {
                "book_id": 1,
                "book_title": "Quang Âm Chi Ngoại",
                "casting_plan_id": 2,
                "casting_plan_revision": 1,
                "casting_plan_sha256": "c" * 64,
                "chapter_id": 629,
                "chapter_number": 629,
                "chapter_title": "Chương 629",
                "data_root": str(self.data_root),
                "data_root_fingerprint": sha256_text(str(self.data_root).replace("\\", "/")),
                "db_identity": {"schema_version": 9},
                "db_path": str((self.data_root / "app.db").resolve()),
                "generated_at": "2026-07-06T00:00:00+00:00",
                "implementation_version": "audio-qa-core/v1",
                "job_chapter_id": 2,
                "job_id": 2,
                "source_manifest_path": str(self.manifest_path.resolve()),
                "source_manifest_schema": MANIFEST_SCHEMA,
                "source_manifest_sha256": manifest_sha,
                "text_revision_content_sha256": "a" * 64,
                "text_revision_id": 1258,
            },
            "thresholds": {
                "long_trailing_silence_ms": 300,
                "trailing_silence_excess_ms": 80,
                "shortlist_max_segments": 25,
            },
            "chapter_metrics": {
                "segment_count": 4,
                "segment_duration_total_ms": 4300,
                "timeline_duration_ms": 4300,
                "timeline_sample_rate": 48000,
                "segment_silence_distribution": {
                    "leading_silence_ms": {"count": 4, "median": 20.0, "p95": 75.0},
                    "trailing_silence_ms": {"count": 4, "median": 350.0, "p95": 470.0},
                    "internal_silence_ms": {"count": 4, "median": 0.0, "p95": 0.0},
                },
                "master_artifact": {
                    "absolute_local_path": str(self.master_path),
                    "artifact_id": 4,
                    "artifact_type": "chapter_master_wav",
                    "duration_ms": 4300,
                    "path_relative_to_data_root": self.master_path.resolve().relative_to(self.data_root).as_posix(),
                    "sha256": master_sha,
                    "mean_volume_dbfs": -15.0,
                    "max_peak_dbfs": -0.5,
                },
                "final_artifact": {
                    "absolute_local_path": str(self.final_path),
                    "artifact_id": 6,
                    "artifact_type": "chapter_m4a",
                    "duration_ms": 4300,
                    "path_relative_to_data_root": self.final_path.resolve().relative_to(self.data_root).as_posix(),
                    "sha256": final_sha,
                    "mean_volume_dbfs": -15.1,
                    "max_peak_dbfs": -0.4,
                },
                "format_consistency": {
                    "master_duration_ms": 4300,
                    "final_duration_ms": 4300,
                    "duration_difference_ms": 0,
                },
            },
            "voice_aggregates": [
                {
                    "voice_id": "Mỹ Duyên",
                    "voice_name": None,
                    "segment_count": 1,
                    "clipping_segment_count": 0,
                    "limitations": ["voice_sample_size_below_robust_outlier_threshold"],
                    "total_duration_ms": 900,
                    "trailing_silence_distribution": {"count": 1, "median": 480.0},
                    "median_mean_volume_dbfs": -17.5,
                    "mean_mean_volume_dbfs": -17.5,
                    "max_mean_volume_dbfs": -17.5,
                    "min_mean_volume_dbfs": -17.5,
                    "median_chars_per_second": 18.0,
                    "median_trailing_silence_ms": 480.0,
                    "robust_outlier_sample_size_met": False,
                    "silence_outlier_count": 1,
                },
                {
                    "voice_id": "Ngọc Lan",
                    "voice_name": None,
                    "segment_count": 2,
                    "clipping_segment_count": 0,
                    "limitations": ["voice_sample_size_below_robust_outlier_threshold"],
                    "total_duration_ms": 2300,
                    "trailing_silence_distribution": {"count": 2, "median": 285.0},
                    "median_mean_volume_dbfs": -15.0,
                    "mean_mean_volume_dbfs": -15.05,
                    "max_mean_volume_dbfs": -14.0,
                    "min_mean_volume_dbfs": -16.1,
                    "median_chars_per_second": 18.0,
                    "median_trailing_silence_ms": 285.0,
                    "robust_outlier_sample_size_met": False,
                    "silence_outlier_count": 1,
                },
                {
                    "voice_id": "Đức Trí",
                    "voice_name": None,
                    "segment_count": 1,
                    "clipping_segment_count": 1,
                    "limitations": ["voice_sample_size_below_robust_outlier_threshold"],
                    "total_duration_ms": 1100,
                    "trailing_silence_distribution": {"count": 1, "median": 410.0},
                    "median_mean_volume_dbfs": -18.0,
                    "mean_mean_volume_dbfs": -18.0,
                    "max_mean_volume_dbfs": -18.0,
                    "min_mean_volume_dbfs": -18.0,
                    "median_chars_per_second": 16.0,
                    "median_trailing_silence_ms": 410.0,
                    "robust_outlier_sample_size_met": False,
                    "silence_outlier_count": 1,
                },
            ],
            "segment_results": [],
            "risk_summary": {
                "counts_by_type": {
                    "adjacent_loudness_jump": 1,
                    "hard_clipping": 1,
                    "long_trailing_silence": 1,
                    "near_clipping": 1,
                },
                "top_risk_segments": [
                    {
                        "segment_id": 102,
                        "sequence": 2,
                        "voice_id": "Đức Trí",
                        "character_name": "Ati",
                        "risk_score": 140,
                        "risk_flags": ["hard_clipping", "near_clipping"],
                        "selection_reason": "hard_clipping_samples=3 ratio=0.001 longest_full_scale_run_samples=2; near_clipping_samples=5 ratio=0.002",
                    },
                    {
                        "segment_id": 103,
                        "sequence": 3,
                        "voice_id": "Mỹ Duyên",
                        "character_name": "Tử Huyền",
                        "risk_score": 40,
                        "risk_flags": ["long_trailing_silence"],
                        "selection_reason": "trailing_silence_ms=480 chapter_median_ms=350.0 chapter_excess_ms=130.0",
                    },
                ],
                "representative_segments_by_voice": [
                    {"segment_id": 101, "sequence": 1, "voice_id": "Ngọc Lan", "character_name": None, "selection_reason": "closest_to_voice_medians"},
                    {"segment_id": 102, "sequence": 2, "voice_id": "Đức Trí", "character_name": "Ati", "selection_reason": "closest_to_voice_medians"},
                    {"segment_id": 103, "sequence": 3, "voice_id": "Mỹ Duyên", "character_name": "Tử Huyền", "selection_reason": "closest_to_voice_medians"},
                ],
                "all_hard_clipped_segments": [
                    {
                        "segment_id": 102,
                        "sequence": 2,
                        "hard_clipping_sample_count": 3,
                        "hard_clipping_sample_ratio": 0.001,
                        "longest_full_scale_run_samples": 2,
                    }
                ],
                "all_missing_or_corrupt_segments": [],
                "silence_distribution": {
                    "trailing_silence_ms": {
                        "count": 4,
                        "count_above_absolute_threshold": 3,
                        "count_materially_above_chapter_median": 1,
                        "median": 350.0,
                        "p95": 470.0,
                    }
                },
                "limitation_notes": [
                    "Objective heuristics only; no naturalness or pronunciation judgment.",
                    "No automatic regenerate, accept, or reject action is performed.",
                ],
            },
            "integrity": {
                "manifest_sha256_verified": True,
                "artifact_hash_verification": {
                    "chapter_master_wav": {"path": str(self.master_path), "sha256": master_sha, "size_bytes": self.master_path.stat().st_size},
                    "segment_timeline_json": {"path": str(self.timeline_path), "sha256": timeline_sha, "size_bytes": self.timeline_path.stat().st_size},
                    "chapter_final": {"path": str(self.final_path), "sha256": final_sha, "size_bytes": self.final_path.stat().st_size},
                },
                "segment_artifact_issues": [],
                "ffmpeg_failures": [],
                "metric_completeness": {"segment_total": 4, "segment_metrics_complete": 4, "segment_metrics_missing": 0},
            },
            "human_boundary": {
                "human_review_required": True,
                "notes": [
                    "Objective metrics cannot validate pronunciation, acting, or speaker correctness by ear.",
                    "Any candidate action remains an operator decision outside this report.",
                ],
            },
            "mutation_performed": False,
        }
        for definition in segment_defs:
            report["segment_results"].append(
                {
                    "artifact_issue": None,
                    "chapter_end_ms": definition["end_ms"],
                    "chapter_start_ms": definition["start_ms"],
                    "character_count": len(definition["text"]),
                    "character_id": definition["segment_id"] if definition["character_name"] else None,
                    "character_name": definition["character_name"],
                    "chars_per_second": definition["chars_per_second"],
                    "duration_ms": definition["duration_ms"],
                    "hard_clipping_sample_count": definition["hard_clipping_sample_count"],
                    "hard_clipping_sample_ratio": definition["hard_clipping_sample_ratio"],
                    "leading_silence_ms": definition["leading_silence_ms"],
                    "longest_full_scale_run_samples": definition["longest_full_scale_run_samples"],
                    "longest_internal_silence_ms": definition["longest_internal_silence_ms"],
                    "max_peak_dbfs": definition["max_peak_dbfs"],
                    "mean_volume_dbfs": definition["mean_volume_dbfs"],
                    "near_clipping_sample_count": definition["near_clipping_sample_count"],
                    "near_clipping_sample_ratio": definition["near_clipping_sample_ratio"],
                    "needs_review": False,
                    "peak_reaches_full_scale": definition["hard_clipping_sample_count"] > 0,
                    "resolution_source": definition["resolution_source"],
                    "resolved_gender": "unknown",
                    "resolved_voice_id": definition["voice_id"],
                    "resolved_voice_name": None,
                    "risk_flags": definition["risk_flags"],
                    "risk_reasons": definition["risk_reasons"],
                    "risk_score": definition["risk_score"],
                    "sample_count": 1000,
                    "segment_audio_sha256": definition["segment_sha256"],
                    "segment_file_absolute_path": str(definition["segment_path"]),
                    "segment_file_relative_to_data_root": definition["segment_path"].resolve().relative_to(self.data_root).as_posix(),
                    "segment_id": definition["segment_id"],
                    "sequence": definition["sequence"],
                    "source_limitations": [],
                    "speaker_role": definition["speaker_role"],
                    "text": definition["text"],
                    "text_sha256": definition["text_sha256"],
                    "timeline_duration_ms": definition["duration_ms"],
                    "total_internal_silence_ms": definition["total_internal_silence_ms"],
                    "trailing_silence_context": {
                        "absolute_threshold_ms": 300,
                        "chapter_excess_ms": max(0.0, definition["trailing_silence_ms"] - 350.0),
                        "chapter_median_ms": 350.0,
                        "chapter_p95_ms": 470.0,
                        "excess_threshold_ms": 80,
                        "measured_above_absolute_threshold": definition["trailing_silence_ms"] >= 300,
                        "voice_excess_ms": max(0.0, definition["trailing_silence_ms"] - 300.0),
                        "voice_median_ms": 300.0,
                        "voice_robust_sample_size_met": False,
                        "voice_sample_size": 1,
                    },
                    "trailing_silence_ms": definition["trailing_silence_ms"],
                    "utterance_id": None,
                    "utterance_sequence": definition["sequence"],
                    "voice_profile_id": 1,
                    "voice_profile_version": 1,
                }
            )
        self.qa_report_path.parent.mkdir(parents=True, exist_ok=True)
        self.qa_report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")


class ListeningChecklistTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fixture = ListeningChecklistFixture(self)
        self.fixture.build()

    def _build(self, **kwargs):
        return build_listening_checklist(self.fixture.manifest_path.resolve(), self.fixture.qa_report_path.resolve(), **kwargs)

    def test_valid_matching_inputs_build_html(self):
        result = self._build()
        self.assertEqual(result["status"], "success")
        html_path = Path(result["package_path"])
        self.assertTrue(html_path.exists())
        self.assertTrue(result["package_path"].endswith("listening\\job_2_chapter_629\\index.html"))

    def test_relative_manifest_rejected(self):
        with self.assertRaises(ChecklistArgumentError):
            build_listening_checklist(Path("relative.json"), self.fixture.qa_report_path.resolve())

    def test_relative_qa_report_rejected(self):
        with self.assertRaises(ChecklistArgumentError):
            build_listening_checklist(self.fixture.manifest_path.resolve(), Path("relative.json"))

    def test_wrong_schemas_rejected(self):
        manifest = json.loads(self.fixture.manifest_path.read_text(encoding="utf-8"))
        manifest["schema"] = "wrong"
        self.fixture.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(ChecklistInputMismatchError):
            self._build()
        self.fixture.build()
        report = json.loads(self.fixture.qa_report_path.read_text(encoding="utf-8"))
        report["schema"] = "wrong"
        self.fixture.qa_report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(ChecklistInputMismatchError):
            self._build()

    def test_manifest_qa_identity_and_manifest_hash_mismatch_rejected(self):
        report = json.loads(self.fixture.qa_report_path.read_text(encoding="utf-8"))
        report["identity"]["chapter_id"] = 999
        self.fixture.qa_report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(ChecklistInputMismatchError):
            self._build()
        self.fixture.build()
        report = json.loads(self.fixture.qa_report_path.read_text(encoding="utf-8"))
        report["identity"]["source_manifest_sha256"] = "0" * 64
        self.fixture.qa_report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(ChecklistInputMismatchError):
            self._build()

    def test_live_root_rejected(self):
        manifest = json.loads(self.fixture.manifest_path.read_text(encoding="utf-8"))
        report = json.loads(self.fixture.qa_report_path.read_text(encoding="utf-8"))
        live_root = str((Path.cwd() / "data").resolve())
        live_db = str((Path.cwd() / "data" / "app.db").resolve())
        manifest["identity"]["data_root"] = live_root
        manifest["identity"]["db_path"] = live_db
        report["identity"]["data_root"] = live_root
        report["identity"]["db_path"] = live_db
        self.fixture.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        self.fixture.qa_report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(ChecklistRuntimeMismatchError):
            self._build()

    def test_live_root_allowed_only_with_explicit_flag(self):
        manifest = json.loads(self.fixture.manifest_path.read_text(encoding="utf-8"))
        report = json.loads(self.fixture.qa_report_path.read_text(encoding="utf-8"))
        manifest["identity"]["data_root"] = str(self.fixture.data_root)
        manifest["identity"]["db_path"] = str((self.fixture.data_root / "app.db").resolve())
        report["identity"]["data_root"] = str(self.fixture.data_root)
        report["identity"]["db_path"] = str((self.fixture.data_root / "app.db").resolve())
        self.fixture.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        self.fixture.qa_report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        with mock.patch("story_audio.listening_checklist._LIVE_ROOT", self.fixture.data_root), \
             mock.patch("story_audio.listening_checklist.canonical_production_db_path", return_value=(self.fixture.data_root / "app.db").resolve()):
            with self.assertRaises(ChecklistRuntimeMismatchError):
                self._build()
            result = self._build(allow_canonical_production=True)
        self.assertEqual(result["status"], "success")

    def test_missing_chapter_artifact_or_selected_segment_audio_rejected(self):
        self.fixture.final_path.unlink()
        with self.assertRaisesRegex(Exception, "Final chapter artifact"):
            self._build()
        self.fixture.build()
        self.fixture.segment_paths[2].unlink()
        with self.assertRaisesRegex(Exception, "Segment 2"):
            self._build()

    def test_audio_hash_mismatch_rejected(self):
        report = json.loads(self.fixture.qa_report_path.read_text(encoding="utf-8"))
        timeline = json.loads(self.fixture.timeline_path.read_text(encoding="utf-8"))
        report["segment_results"][1]["segment_audio_sha256"] = "0" * 64
        timeline["items"][1]["segment_sha256"] = "0" * 64
        self.fixture.qa_report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        self.fixture.timeline_path.write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(Exception, "hash mismatch"):
            self._build()

    def test_output_path_traversal_and_symlink_escape_rejected(self):
        outside = (self.temp_root / "outside" / "index.html").resolve()
        with self.assertRaises(ChecklistRuntimeMismatchError):
            self._build(output_path=outside)
        symlink_supported = hasattr(Path, "symlink_to")
        if symlink_supported:
            target = self.fixture.work_root / "real.wav"
            atomic_write_bytes(target, b"real")
            symlink = self.fixture.work_root / "symlink.wav"
            try:
                symlink.symlink_to(target)
            except OSError:
                self.skipTest("symlink not permitted")
            report = json.loads(self.fixture.qa_report_path.read_text(encoding="utf-8"))
            report["segment_results"][0]["segment_file_absolute_path"] = str(symlink)
            report["segment_results"][0]["segment_file_relative_to_data_root"] = symlink.relative_to(self.fixture.data_root).as_posix()
            report["segment_results"][0]["segment_audio_sha256"] = sha256_file(target)
            self.fixture.qa_report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(Exception, "symlink"):
                self._build()

    def test_symlink_component_rejected_with_mock_without_windows_privilege(self):
        suspect = self.fixture.work_root / "mock-symlink.wav"
        atomic_write_bytes(suspect, b"mock-audio")
        path_type = type(suspect)

        def fake_is_symlink(path_self):
            return path_self == suspect

        with mock.patch.object(path_type, "is_symlink", autospec=True, side_effect=fake_is_symlink):
            with self.assertRaises(ChecklistArtifactIntegrityError):
                _validate_local_file(
                    suspect,
                    expected_sha256=sha256_file(suspect),
                    data_root=self.fixture.data_root,
                    label="Mock symlink segment",
                )

    def test_unicode_relative_urls_and_required_audio_controls_present(self):
        result = self._build()
        html_text = Path(result["package_path"]).read_text(encoding="utf-8")
        self.assertIn("master-audio", html_text)
        self.assertIn("final-audio", html_text)
        self.assertIn("%E1%BB%B9%20Duy%C3%AAn", html_text)
        self.assertIn("Jump master", html_text)
        self.assertIn("Jump final", html_text)
        encoded = _resolve_relative_url(
            Path(result["package_path"]).parent,
            self.fixture.segment_paths[3],
            data_root=self.fixture.data_root,
        )
        self.assertIn("%E1%BB%B9%20Duy%C3%AAn", encoded)

    def test_deterministic_identity_byte_identical_reuse_and_conflict(self):
        first = self._build()
        second = self._build()
        self.assertFalse(first["reused_existing"])
        self.assertTrue(second["reused_existing"])
        self.assertEqual(first["package_sha256"], second["package_sha256"])
        output_path = Path(first["package_path"])
        output_path.write_text("conflict", encoding="utf-8")
        with self.assertRaises(ChecklistOutputConflictError):
            self._build(output_path=output_path)

    def test_atomic_write_and_no_source_mutation(self):
        before = {
            "manifest": sha256_file(self.fixture.manifest_path),
            "report": sha256_file(self.fixture.qa_report_path),
            "segment": sha256_file(self.fixture.segment_paths[2]),
            "master": sha256_file(self.fixture.master_path),
        }
        self._build()
        after = {
            "manifest": sha256_file(self.fixture.manifest_path),
            "report": sha256_file(self.fixture.qa_report_path),
            "segment": sha256_file(self.fixture.segment_paths[2]),
            "master": sha256_file(self.fixture.master_path),
        }
        self.assertEqual(before, after)
        self.assertEqual(list(self.fixture.data_root.rglob("*.partial")), [])

    def test_selection_includes_hard_clipping_integrity_representatives_and_first_last(self):
        result = self._build(options=ChecklistOptions(max_risk_items=0))
        selected = result["report"]["selected_segments"]
        sequences = [item["sequence"] for item in selected]
        self.assertIn(2, sequences)
        self.assertIn(1, sequences)
        self.assertIn(4, sequences)
        self.assertIn(3, sequences)
        selected_map = {item["sequence"]: item for item in selected}
        self.assertIn("hard_clipping", selected_map[2]["selection_categories"])
        self.assertIn("representative_sample", selected_map[3]["selection_categories"])
        self.assertIn("first_segment", selected_map[1]["selection_categories"])
        self.assertIn("last_segment", selected_map[4]["selection_categories"])

    def test_risk_max_applies_only_to_ordinary_risks_and_dedupe_is_deterministic(self):
        result = self._build(options=ChecklistOptions(max_risk_items=1))
        selected = result["report"]["selected_segments"]
        sequences = [item["sequence"] for item in selected]
        self.assertEqual(sequences.count(2), 1)
        self.assertIn(2, sequences)
        self.assertIn(1, sequences)
        self.assertIn(4, sequences)

    def test_vietnamese_and_malicious_text_escaped_safely(self):
        report = json.loads(self.fixture.qa_report_path.read_text(encoding="utf-8"))
        timeline = json.loads(self.fixture.timeline_path.read_text(encoding="utf-8"))
        manifest = json.loads(self.fixture.manifest_path.read_text(encoding="utf-8"))
        bad = "<script>alert(1)</script> Mỹ Duyên"
        report["segment_results"][0]["text"] = bad
        report["segment_results"][0]["text_sha256"] = sha256_text(bad)
        report["segment_results"][0]["character_name"] = "<b>Trần Trí</b>"
        timeline["items"][0]["text"] = bad
        timeline["items"][0]["character_name"] = "<b>Trần Trí</b>"
        self.fixture.timeline_path.write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
        timeline_sha = sha256_file(self.fixture.timeline_path)
        manifest["artifacts"][1]["computed_sha256"] = timeline_sha
        manifest["artifacts"][1]["stored_sha256"] = timeline_sha
        self.fixture.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        report["identity"]["source_manifest_sha256"] = sha256_file(self.fixture.manifest_path)
        self.fixture.qa_report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        result = self._build()
        html_text = Path(result["package_path"]).read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; Mỹ Duyên", html_text)
        self.assertNotIn("<script>alert(1)</script>", html_text)
        self.assertIn("&lt;b&gt;Trần Trí&lt;/b&gt;", html_text)

    def test_review_controls_filters_reset_export_and_local_storage_present(self):
        result = self._build()
        html_text = Path(result["package_path"]).read_text(encoding="utf-8")
        self.assertIn('id="queue-filter"', html_text)
        self.assertIn('id="decision-filter"', html_text)
        self.assertIn('id="segment-search"', html_text)
        self.assertIn('id="reset-local-review"', html_text)
        self.assertIn('id="export-review-json"', html_text)
        self.assertIn("story-audio-listening-review:", html_text)
        self.assertIn(LISTENING_REVIEW_SCHEMA, html_text)
        self.assertIn("pronunciation issue", html_text)
        self.assertIn("wrong speaker/voice", html_text)
        self.assertIn("pacing issue", html_text)
        self.assertIn("silence issue", html_text)
        self.assertIn("clipping/distortion", html_text)
        self.assertIn("emotional delivery issue", html_text)
        self.assertIn("Pass", html_text)
        self.assertIn("Needs attention", html_text)
        self.assertIn("Regenerate suggested", html_text)
        self.assertIn("Skipped", html_text)

    def test_no_external_urls_fetch_xhr_or_api_mutation_routes(self):
        result = self._build()
        html_text = Path(result["package_path"]).read_text(encoding="utf-8")
        self.assertNotIn("http://", html_text)
        self.assertNotIn("https://", html_text)
        self.assertNotIn("fetch(", html_text)
        self.assertNotIn("XMLHttpRequest", html_text)
        self.assertNotIn("/api/", html_text)
        self.assertNotIn("eval(", html_text)

    def test_output_directory_with_unknown_files_rejected(self):
        output_path = (self.fixture.data_root / "listening" / "job_2_chapter_629" / "index.html").resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        (output_path.parent / "unknown.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(ChecklistOutputConflictError):
            self._build(output_path=output_path)

    def test_html_parses_and_relative_audio_paths_resolve(self):
        result = self._build()
        html_path = Path(result["package_path"])
        parser = _AudioSrcParser()
        parser.feed(html_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(parser.audio_srcs), 6)
        for src in parser.audio_srcs:
            resolved = (html_path.parent / Path(unquote(src.replace("/", "\\")))).resolve()
            self.assertTrue(resolved.exists(), src)

    def test_structured_cli_success_invalid_input_and_internal_error(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = main(
            ["--manifest", str(self.fixture.manifest_path.resolve()), "--qa-report", str(self.fixture.qa_report_path.resolve())],
            stdout=stdout,
            stderr=stderr,
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "success")
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = main(
            ["--manifest", "relative.json", "--qa-report", str(self.fixture.qa_report_path.resolve())],
            stdout=stdout,
            stderr=stderr,
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(payload["status"], "invalid_arguments")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch("story_audio.listening_checklist.build_listening_checklist", side_effect=ValueError("boom")):
            code = main(
                ["--manifest", str(self.fixture.manifest_path.resolve()), "--qa-report", str(self.fixture.qa_report_path.resolve())],
                stdout=stdout,
                stderr=stderr,
            )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 7)
        self.assertEqual(payload["status"], "internal_error")
