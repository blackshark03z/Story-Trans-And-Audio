from __future__ import annotations

import io
import json
import shutil
import subprocess
import wave
from array import array
from pathlib import Path
from unittest.mock import patch

from story_audio.audio_qa import (
    AUDIO_QA_SCHEMA,
    MANIFEST_SCHEMA,
    QaArgumentError,
    QaArtifactIntegrityError,
    QaFfmpegUnavailableError,
    QaManifestError,
    QaReportConflictError,
    QaRuntimeMismatchError,
    QaThresholds,
    _analyze_audio_file,
    _analyze_wave_signal,
    _build_segment_result,
    _build_voice_aggregates,
    _top_risky_segments,
    generate_audio_qa_report,
    main,
)
from story_audio.db import Database
from story_audio.files import atomic_write_bytes, sha256_file, sha256_text
from tests.base import IsolatedTestCase


def _write_pcm_wav(
    path: Path,
    *,
    sample_rate: int,
    channels: int,
    samples: list[int],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = array("h")
    for sample in samples:
        for _ in range(channels):
            frames.append(int(sample))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames.tobytes())


def _write_integer_wav(
    path: Path,
    *,
    sample_rate: int,
    channels: int,
    sample_width: int,
    samples: list[int],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = bytearray()
    for sample in samples:
        for _ in range(channels):
            if sample_width == 1:
                payload.append((int(sample) + 128) & 0xFF)
            elif sample_width == 2:
                payload.extend(int(sample).to_bytes(2, byteorder="little", signed=True))
            elif sample_width == 3:
                payload.extend((int(sample) & 0xFFFFFF).to_bytes(3, byteorder="little", signed=False))
            elif sample_width == 4:
                payload.extend(int(sample).to_bytes(4, byteorder="little", signed=True))
            else:
                raise ValueError(sample_width)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sample_width)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(payload))


def _tone_samples(
    *,
    duration_ms: int,
    amplitude: int,
    sample_rate: int = 48_000,
    leading_silence_ms: int = 0,
    trailing_silence_ms: int = 0,
    internal_silence_ms: int = 0,
) -> list[int]:
    def _count(ms: int) -> int:
        return max(1, round(sample_rate * (ms / 1000.0))) if ms > 0 else 0

    tone_count = _count(duration_ms - leading_silence_ms - trailing_silence_ms - internal_silence_ms)
    tone_count = max(1, tone_count)
    payload = [0] * _count(leading_silence_ms)
    first = tone_count // 2
    second = tone_count - first
    payload.extend([amplitude] * first)
    payload.extend([0] * _count(internal_silence_ms))
    payload.extend([amplitude] * second)
    payload.extend([0] * _count(trailing_silence_ms))
    return payload


class AudioQaFixture:
    def __init__(self, case: IsolatedTestCase) -> None:
        self.case = case
        self.config = case.config
        self.job_id = 1
        self.job_chapter_id = 1
        self.book_id = 1
        self.chapter_id = 1
        self.text_revision_id = 1
        self.render_dir = self.config.output_dir / "job_1" / "chapter_0629" / "render_001"
        self.segment_dir = self.config.work_dir / "job_1" / "chapter_0629" / "segments"
        self.render_dir.mkdir(parents=True, exist_ok=True)
        self.segment_dir.mkdir(parents=True, exist_ok=True)
        self.sample_rate = 48_000
        self.segments = [
            {
                "sequence": 1,
                "text": "Xin chao Ati.",
                "character_name": "Ati",
                "speaker_role": "character",
                "voice_id": "duc_tri",
                "character_id": 101,
                "duration_ms": 1000,
                "amplitude": 6000,
                "wav_path": self.segment_dir / "000001.wav",
            },
            {
                "sequence": 2,
                "text": "Nguoi ke chuyen.",
                "character_name": None,
                "speaker_role": "narrator",
                "voice_id": "ngoc_lan",
                "character_id": None,
                "duration_ms": 1100,
                "amplitude": 5000,
                "wav_path": self.segment_dir / "000002.wav",
            },
        ]

    def build(self) -> None:
        shutil.rmtree(self.config.data_dir, ignore_errors=True)
        self.config.ensure_dirs()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        samples_master: list[int] = []
        cursor_ms = 0
        timeline_items = []
        for segment in self.segments:
            if not segment.get("lock_samples"):
                segment["samples"] = _tone_samples(
                    duration_ms=int(segment["duration_ms"]),
                    amplitude=int(segment["amplitude"]),
                    sample_rate=self.sample_rate,
                    leading_silence_ms=int(segment.get("leading_silence_ms", 0)),
                    trailing_silence_ms=int(segment.get("trailing_silence_ms", 0)),
                    internal_silence_ms=int(segment.get("internal_silence_ms", 0)),
                )
            _write_pcm_wav(
                segment["wav_path"],
                sample_rate=self.sample_rate,
                channels=int(segment.get("channels", 1)),
                samples=list(segment["samples"]),
            )
            segment["sha256"] = sha256_file(segment["wav_path"])
            duration_ms = round((len(segment["samples"]) / self.sample_rate) * 1000)
            segment["duration_ms"] = duration_ms
            timeline_items.append(
                {
                    "index": int(segment["sequence"]),
                    "text": segment["text"],
                    "start_ms": int(cursor_ms),
                    "end_ms": int(cursor_ms + duration_ms),
                    "duration_ms": int(duration_ms),
                    "segment_sha256": segment["sha256"],
                    "utterance_sequence": int(segment["sequence"]),
                    "speaker_role": segment["speaker_role"],
                    "character_id": segment["character_id"],
                    "character_name": segment["character_name"],
                    "voice_id": segment["voice_id"],
                    "resolution_source": segment.get("resolution_source"),
                    "resolved_gender": segment.get("resolved_gender"),
                    "needs_review": bool(segment.get("needs_review", False)),
                    "voice_profile_id": 1,
                    "voice_profile_version": 1,
                    "synthesis_hash": f"synth-{segment['sequence']}",
                }
            )
            cursor_ms += duration_ms
            samples_master.extend(list(segment["samples"]))
        self.master_path = self.render_dir / "chapter_master.wav"
        _write_pcm_wav(self.master_path, sample_rate=self.sample_rate, channels=1, samples=samples_master)
        self.timeline_path = self.render_dir / "segment_timeline.json"
        self.timeline_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "chapter_id": self.chapter_id,
                    "text_revision_id": self.text_revision_id,
                    "sample_rate": self.sample_rate,
                    "duration_ms": cursor_ms,
                    "items": timeline_items,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.final_path = self.render_dir / "chapter.m4a"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(self.master_path),
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(self.final_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO books(id,title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,datetime('now'),datetime('now'))",
                (self.book_id, "Test Book", "fixture://book", "b" * 64, 1),
            )
            conn.execute(
                """INSERT INTO chapters(
                    id,book_id,chapter_number,title,char_count,audio_status,created_at,updated_at
                ) VALUES(?,?,?,?,?,'completed',datetime('now'),datetime('now'))""",
                (self.chapter_id, self.book_id, 629, "Chapter 629", sum(len(item["text"]) for item in self.segments)),
            )
            conn.execute(
                """INSERT INTO characters(
                    id,book_id,display_name,default_voice_id,voice_override_id,active,created_at,updated_at
                ) VALUES(?,?,?,?,?,1,datetime('now'),datetime('now'))""",
                (101, self.book_id, "Ati", "duc_tri", None),
            )
            conn.execute(
                """INSERT INTO text_revisions(
                    id,chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,datetime('now'))""",
                (
                    self.text_revision_id,
                    self.chapter_id,
                    "reflowed",
                    "text/fixture.txt",
                    "c" * 64,
                    "c" * 64,
                    sum(len(item["text"]) for item in self.segments),
                    "fixture-v1",
                    "approved",
                ),
            )
            conn.execute(
                """INSERT INTO jobs(
                    id,book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,scheduled_at,created_at,started_at,finished_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'),datetime('now'),datetime('now'),datetime('now'))""",
                (
                    self.job_id,
                    self.book_id,
                    "completed",
                    629,
                    629,
                    "ngoc_lan",
                    "punctuation",
                    "m4a",
                    json.dumps({"engine_version": "fixture"}, ensure_ascii=False),
                ),
            )
            conn.execute(
                """INSERT INTO job_chapters(
                    id,job_id,chapter_id,sequence,status,text_revision_id,artifact_id,error_message,started_at,finished_at
                ) VALUES(?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))""",
                (self.job_chapter_id, self.job_id, self.chapter_id, 1, "completed", self.text_revision_id, 3, None),
            )
            for segment in self.segments:
                conn.execute(
                    """INSERT INTO segments(
                        id,job_chapter_id,segment_index,text_path,text_sha256,status,attempt_count,created_at,verified_at,
                        wav_path,audio_sha256,duration_ms,utterance_sequence,speaker_role,character_id,resolved_voice_id,synthesis_hash
                    ) VALUES(?,?,?,?,?,'verified',1,datetime('now'),datetime('now'),?,?,?,?,?,?,?,?)""",
                    (
                        int(segment["sequence"]),
                        self.job_chapter_id,
                        int(segment["sequence"]),
                        f"text/segment_{segment['sequence']}.txt",
                        sha256_text(segment["text"]),
                        str(segment["wav_path"]),
                        segment["sha256"],
                        int(segment["duration_ms"]),
                        int(segment["sequence"]),
                        segment["speaker_role"],
                        segment["character_id"],
                        segment["voice_id"],
                        f"synth-{segment['sequence']}",
                    ),
                )
            artifacts = [
                (1, "chapter_master_wav", self.master_path, sha256_file(self.master_path), self.master_path.stat().st_size, cursor_ms),
                (2, "segment_timeline_json", self.timeline_path, sha256_file(self.timeline_path), self.timeline_path.stat().st_size, cursor_ms),
                (3, "chapter_m4a", self.final_path, sha256_file(self.final_path), self.final_path.stat().st_size, cursor_ms),
            ]
            for artifact_id, artifact_type, path, digest, size_bytes, duration_ms in artifacts:
                conn.execute(
                    """INSERT INTO artifacts(
                        id,chapter_id,job_chapter_id,text_revision_id,artifact_type,path,sha256,size_bytes,
                        duration_ms,status,created_at,verified_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,'active',datetime('now'),datetime('now'))""",
                    (
                        artifact_id,
                        self.chapter_id,
                        self.job_chapter_id,
                        self.text_revision_id,
                        artifact_type,
                        str(path),
                        digest,
                        size_bytes,
                        duration_ms,
                    ),
                )
            conn.execute(
                "UPDATE chapters SET active_text_revision_id=?, active_audio_artifact_id=? WHERE id=?",
                (self.text_revision_id, 3, self.chapter_id),
            )
        self.manifest_path = self.config.data_dir / "manifests" / "job_1_chapter_629.json"
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "identity": {
                "data_root": str(self.config.data_dir.resolve()),
                "data_root_fingerprint": sha256_text(str(self.config.data_dir.resolve()).replace("\\", "/")),
                "db_path": str(self.config.db_path.resolve()),
                "db_identity": {"schema_version": self.db.schema_version()},
                "book_id": self.book_id,
                "book_title": "Test Book",
                "chapter_id": self.chapter_id,
                "chapter_number": 629,
                "chapter_title": "Chapter 629",
                "job_id": self.job_id,
                "job_chapter_id": self.job_chapter_id,
                "output_format": "m4a",
                "repair_mode": "punctuation",
                "render_generation": "render_001",
            },
            "immutable_bindings": {
                "text_revision_id": self.text_revision_id,
                "text_revision_content_sha256": "c" * 64,
                "casting_plan_id": 1,
                "casting_plan_revision": 1,
                "casting_plan_sha256": "d" * 64,
            },
            "terminal_state": {
                "job_status": "completed",
                "job_chapter_status": "completed",
                "started_at": "2026-01-01T00:00:00+00:00",
                "finished_at": "2026-01-01T00:05:00+00:00",
                "expected_segments": len(self.segments),
                "verified_segments": len(self.segments),
                "failed_segments": 0,
                "pending_segments": 0,
                "running_segments": 0,
                "final_duration_ms": cursor_ms,
                "retry_recovery_metadata": {
                    "job_error_message": None,
                    "job_chapter_error_message": None,
                },
            },
            "artifacts": [],
            "segment_integrity_summary": {
                "segment_count": len(self.segments),
                "sequence_min": 1,
                "sequence_max": len(self.segments),
                "missing_sequences": [],
                "duplicate_sequences": [],
                "missing_files": [],
                "hash_mismatches": [],
                "duration_total_ms": cursor_ms,
                "timeline_entry_count": len(self.segments),
            },
            "mutation_performed": False,
        }
        for artifact_id, artifact_type, path, digest, size_bytes, duration_ms in artifacts:
            manifest["artifacts"].append(
                {
                    "artifact_id": artifact_id,
                    "artifact_type": artifact_type,
                    "status": "active",
                    "path_relative_to_data_root": path.resolve().relative_to(self.config.data_dir.resolve()).as_posix(),
                    "absolute_local_path": str(path.resolve()),
                    "size_bytes": size_bytes,
                    "stored_sha256": digest,
                    "computed_sha256": digest,
                    "mtime_epoch_seconds": path.stat().st_mtime,
                    "mime_type": "audio/wav" if artifact_type == "chapter_master_wav" else "application/json" if artifact_type == "segment_timeline_json" else "audio/mp4",
                    "duration_ms": duration_ms,
                }
            )
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


class AudioQaTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            self.skipTest("ffmpeg/ffprobe are required for audio QA tests")
        self.fixture = AudioQaFixture(self)
        self.fixture.build()

    def _generate(self, **kwargs):
        return generate_audio_qa_report(self.fixture.manifest_path.resolve(), **kwargs)

    def test_valid_manifest_accepted(self):
        result = self._generate()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["report"]["schema"], AUDIO_QA_SCHEMA)

    def test_relative_manifest_path_rejected(self):
        with self.assertRaises(QaArgumentError):
            generate_audio_qa_report(Path("relative.json"))

    def test_wrong_schema_rejected(self):
        payload = json.loads(self.fixture.manifest_path.read_text(encoding="utf-8"))
        payload["schema"] = "wrong"
        self.fixture.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(QaManifestError):
            self._generate()

    def test_canonical_live_root_rejected(self):
        payload = json.loads(self.fixture.manifest_path.read_text(encoding="utf-8"))
        payload["identity"]["data_root"] = str((Path.cwd() / "data").resolve())
        payload["identity"]["db_path"] = str((Path.cwd() / "data" / "app.db").resolve())
        self.fixture.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(QaRuntimeMismatchError):
            self._generate()

    def test_artifact_hash_mismatch_rejected(self):
        payload = json.loads(self.fixture.manifest_path.read_text(encoding="utf-8"))
        payload["artifacts"][0]["computed_sha256"] = "0" * 64
        payload["artifacts"][0]["stored_sha256"] = "0" * 64
        self.fixture.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(QaArtifactIntegrityError):
            self._generate()

    def test_missing_master_artifact_rejected(self):
        self.fixture.master_path.unlink()
        with self.assertRaises(QaArtifactIntegrityError):
            self._generate()

    def test_missing_segment_file_is_flagged(self):
        self.fixture.segments[0]["wav_path"].unlink()
        result = self._generate()
        self.assertEqual(result["status"], "artifact_integrity_failure")
        flagged = [item for item in result["report"]["segment_results"] if item["artifact_issue"]]
        self.assertEqual(flagged[0]["artifact_issue"], "missing_segment_file")

    def test_mono_wav_metrics_and_sample_rate_and_duration_reporting(self):
        result = self._generate()
        segment = result["report"]["segment_results"][0]
        self.assertEqual(segment["duration_ms"], self.fixture.segments[0]["duration_ms"])
        self.assertEqual(result["report"]["chapter_metrics"]["master_artifact"]["sample_rate"], 48_000)
        self.assertEqual(result["report"]["chapter_metrics"]["master_artifact"]["channels"], 1)

    def test_stereo_input_handling(self):
        self.fixture.segments[0]["channels"] = 2
        self.fixture.build()
        result = self._generate()
        segment = result["report"]["segment_results"][0]
        self.assertIsNotNone(segment["mean_volume_dbfs"])

    def test_supported_sample_widths_are_analyzed(self):
        base = self.temp_root / "widths"
        files = [
            (base / "u8.wav", 1, [0, 127, -128, 64]),
            (base / "s24.wav", 3, [0, 1_000_000, -1_000_000, 2_000_000]),
            (base / "s32.wav", 4, [0, 100_000_000, -100_000_000, 200_000_000]),
        ]
        for path, sample_width, samples in files:
            _write_integer_wav(path, sample_rate=48_000, channels=1, sample_width=sample_width, samples=samples)
            metrics = _analyze_wave_signal(path, thresholds=QaThresholds())
            self.assertEqual(metrics.sample_width_bits, sample_width * 8)
            self.assertGreater(metrics.sample_count, 0)

    def test_unsupported_pcm_codec_rejected_clearly(self):
        with patch(
            "story_audio.audio_qa._ffprobe_audio_metadata",
            return_value={
                "codec_name": "pcm_f32le",
                "codec_long_name": "PCM 32-bit floating point",
                "sample_format": "flt",
                "sample_rate": 48_000,
                "channels": 1,
                "bits_per_sample": 32,
                "duration_seconds": 1.0,
                "format_name": "wav",
                "bit_rate": None,
            },
        ):
            with self.assertRaises(QaArtifactIntegrityError):
                _analyze_audio_file(
                    self.fixture.master_path,
                    ffmpeg_path="ffmpeg",
                    ffprobe_path="ffprobe",
                    thresholds=QaThresholds(),
                    timeout_seconds=10,
                )

    def test_hard_clipping_detected(self):
        self.fixture.segments[0]["samples"] = [32767] * 4_800
        self.fixture.segments[0]["lock_samples"] = True
        self.fixture.build()
        result = self._generate()
        segment = result["report"]["segment_results"][0]
        self.assertIn("hard_clipping", segment["risk_flags"])
        self.assertTrue(segment["peak_reaches_full_scale"])
        self.assertEqual(segment["longest_full_scale_run_samples"], 4_800)

    def test_near_clipping_detected(self):
        self.fixture.segments[0]["samples"] = [32500] * 4_800
        self.fixture.segments[0]["lock_samples"] = True
        self.fixture.build()
        result = self._generate()
        segment = result["report"]["segment_results"][0]
        self.assertIn("near_clipping", segment["risk_flags"])

    def test_leading_trailing_and_internal_silence_detected(self):
        self.fixture.segments[0]["duration_ms"] = 2000
        self.fixture.segments[0]["leading_silence_ms"] = 300
        self.fixture.segments[0]["trailing_silence_ms"] = 400
        self.fixture.segments[0]["internal_silence_ms"] = 500
        self.fixture.build()
        result = self._generate()
        segment = result["report"]["segment_results"][0]
        self.assertIn("long_leading_silence", segment["risk_flags"])
        self.assertIn("long_trailing_silence", segment["risk_flags"])
        self.assertIn("long_internal_silence", segment["risk_flags"])

    def test_clean_audio_does_not_receive_clipping_flag(self):
        result = self._generate()
        segment = result["report"]["segment_results"][0]
        self.assertNotIn("hard_clipping", segment["risk_flags"])
        self.assertNotIn("near_clipping", segment["risk_flags"])

    def test_negative_full_scale_clipping_detected(self):
        self.fixture.segments[0]["samples"] = [-32768] * 1024
        self.fixture.segments[0]["lock_samples"] = True
        self.fixture.build()
        result = self._generate()
        segment = result["report"]["segment_results"][0]
        self.assertGreater(segment["hard_clipping_sample_count"], 0)
        self.assertEqual(segment["max_peak_dbfs"], 0.0)

    def test_isolated_full_scale_sample_has_quantitative_evidence(self):
        self.fixture.segments[0]["samples"] = [0] * 1000
        self.fixture.segments[0]["samples"][500] = 32767
        self.fixture.segments[0]["lock_samples"] = True
        self.fixture.build()
        result = self._generate()
        segment = result["report"]["segment_results"][0]
        self.assertEqual(segment["hard_clipping_sample_count"], 1)
        self.assertEqual(segment["longest_full_scale_run_samples"], 1)
        self.assertGreater(segment["hard_clipping_sample_ratio"], 0.0)

    def test_common_trailing_padding_is_measured_but_not_rank_flood(self):
        self.fixture.segments.append(
            {
                "sequence": 3,
                "text": "Them mot cau.",
                "character_name": None,
                "speaker_role": "narrator",
                "voice_id": "ngoc_lan",
                "character_id": None,
                "duration_ms": 1500,
                "amplitude": 5000,
                "trailing_silence_ms": 360,
                "wav_path": self.fixture.segment_dir / "000003.wav",
            }
        )
        self.fixture.segments[0]["duration_ms"] = 1500
        self.fixture.segments[1]["duration_ms"] = 1500
        self.fixture.segments[0]["trailing_silence_ms"] = 350
        self.fixture.segments[1]["trailing_silence_ms"] = 355
        self.fixture.build()
        result = self._generate()
        trailing_count = result["report"]["risk_summary"]["counts_by_type"].get("long_trailing_silence", 0)
        self.assertLess(trailing_count, len(result["report"]["segment_results"]))
        self.assertEqual(
            result["report"]["risk_summary"]["silence_distribution"]["trailing_silence_ms"]["count_above_absolute_threshold"],
            len(result["report"]["segment_results"]),
        )

    def test_excessive_trailing_silence_is_ranked(self):
        self.fixture.segments.append(
            {
                "sequence": 3,
                "text": "Qua dai.",
                "character_name": None,
                "speaker_role": "narrator",
                "voice_id": "ngoc_lan",
                "character_id": None,
                "duration_ms": 2200,
                "amplitude": 5000,
                "trailing_silence_ms": 750,
                "wav_path": self.fixture.segment_dir / "000003.wav",
            }
        )
        self.fixture.segments[0]["duration_ms"] = 1500
        self.fixture.segments[1]["duration_ms"] = 1500
        self.fixture.segments[0]["trailing_silence_ms"] = 350
        self.fixture.segments[1]["trailing_silence_ms"] = 360
        self.fixture.build()
        result = self._generate()
        flagged = next(item for item in result["report"]["segment_results"] if item["sequence"] == 3)
        self.assertIn("long_trailing_silence", flagged["risk_flags"])
        self.assertEqual(result["report"]["risk_summary"]["top_risk_segments"][0]["sequence"], 3)

    def test_voice_median_aggregation_and_representative_selection(self):
        self.fixture.segments.append(
            {
                "sequence": 3,
                "text": "Ati noi them.",
                "character_name": "Ati",
                "speaker_role": "character",
                "voice_id": "duc_tri",
                "character_id": 101,
                "duration_ms": 900,
                "amplitude": 6100,
                "wav_path": self.fixture.segment_dir / "000003.wav",
            }
        )
        self.fixture.build()
        result = self._generate()
        aggregates = {item["voice_id"]: item for item in result["report"]["voice_aggregates"]}
        self.assertEqual(aggregates["duc_tri"]["segment_count"], 2)
        representatives = result["report"]["risk_summary"]["representative_segments_by_voice"]
        self.assertTrue(any(item["voice_id"] == "duc_tri" for item in representatives))

    def test_loudness_outlier_detection(self):
        self.fixture.segments.append(
            {
                "sequence": 3,
                "text": "Ati noi rat nho.",
                "character_name": "Ati",
                "speaker_role": "character",
                "voice_id": "duc_tri",
                "character_id": 101,
                "duration_ms": 1000,
                "amplitude": 400,
                "wav_path": self.fixture.segment_dir / "000003.wav",
            }
        )
        self.fixture.segments.append(
            {
                "sequence": 4,
                "text": "Ati noi binh thuong.",
                "character_name": "Ati",
                "speaker_role": "character",
                "voice_id": "duc_tri",
                "character_id": 101,
                "duration_ms": 1000,
                "amplitude": 6100,
                "wav_path": self.fixture.segment_dir / "000004.wav",
            }
        )
        self.fixture.segments.append(
            {
                "sequence": 5,
                "text": "Ati noi them nua.",
                "character_name": "Ati",
                "speaker_role": "character",
                "voice_id": "duc_tri",
                "character_id": 101,
                "duration_ms": 1000,
                "amplitude": 6200,
                "wav_path": self.fixture.segment_dir / "000005.wav",
            }
        )
        self.fixture.build()
        result = self._generate()
        flagged = next(item for item in result["report"]["segment_results"] if item["sequence"] == 3)
        self.assertIn("loudness_outlier", flagged["risk_flags"])

    def test_small_voice_group_does_not_trigger_voice_median_outlier(self):
        self.fixture.segments[0]["voice_id"] = "my_duyen"
        self.fixture.segments[1]["voice_id"] = "my_duyen"
        self.fixture.segments.append(
            {
                "sequence": 3,
                "text": "Rat khac.",
                "character_name": "Lan",
                "speaker_role": "character",
                "voice_id": "my_duyen",
                "character_id": 101,
                "duration_ms": 1000,
                "amplitude": 500,
                "wav_path": self.fixture.segment_dir / "000003.wav",
            }
        )
        self.fixture.build()
        result = self._generate()
        flagged = next(item for item in result["report"]["segment_results"] if item["sequence"] == 3)
        self.assertNotIn("loudness_outlier", flagged["risk_flags"])
        self.assertIn("voice_sample_size_below_robust_outlier_threshold", flagged["source_limitations"])

    def test_zero_duration_and_empty_text_are_safe(self):
        result = _build_segment_result(
            sequence=1,
            segment_row={"id": 1, "text_sha256": "a" * 64, "audio_sha256": "b" * 64},
            timeline_item={"text": "", "utterance_sequence": 1},
            wav_path=None,
            data_root=self.temp_root,
            artifact_issue="missing_wav_path",
            metrics={"duration_ms": 0},
        )
        self.assertIsNone(result["chars_per_second"])
        self.assertIn("duration_missing_or_zero", result["source_limitations"])
        self.assertIn("character_count_missing_or_zero", result["source_limitations"])

    def test_adjacent_loudness_jump_detection(self):
        self.fixture.segments[1]["amplitude"] = 200
        self.fixture.build()
        result = self._generate()
        flagged = result["report"]["segment_results"][1]
        self.assertIn("adjacent_loudness_jump", flagged["risk_flags"])

    def test_speech_rate_outlier_detection(self):
        self.fixture.segments[0]["text"] = "a" * 400
        self.fixture.build()
        result = self._generate()
        flagged = result["report"]["segment_results"][0]
        self.assertIn("speech_rate_outlier", flagged["risk_flags"])

    def test_deterministic_risk_ordering_and_shortlist_deduplication(self):
        segments = [
            {"segment_id": 2, "sequence": 2, "risk_score": 40, "risk_flags": ["near_clipping"], "risk_reasons": ["a"]},
            {"segment_id": 1, "sequence": 1, "risk_score": 40, "risk_flags": ["near_clipping"], "risk_reasons": ["b"]},
            {"segment_id": 1, "sequence": 1, "risk_score": 40, "risk_flags": ["near_clipping"], "risk_reasons": ["dup"]},
        ]
        shortlist = _top_risky_segments(segments, max_segments=25)
        self.assertEqual([item["segment_id"] for item in shortlist], [1, 2])

    def test_maximum_shortlist_size_and_hard_clipped_summary(self):
        thresholds = QaThresholds(shortlist_max_segments=2)
        result = self._generate(thresholds=thresholds)
        shortlist = result["report"]["risk_summary"]["top_risk_segments"]
        self.assertLessEqual(len(shortlist), 2)
        self.assertIsInstance(result["report"]["risk_summary"]["all_hard_clipped_segments"], list)

    def test_unicode_speaker_voice_and_text_round_trip(self):
        self.fixture.segments[0]["text"] = "Trần Trí nói với Mỹ Duyên."
        self.fixture.segments[0]["character_name"] = "Trần Trí"
        self.fixture.segments[0]["voice_id"] = "đức_trí"
        self.fixture.build()
        result = self._generate()
        segment = result["report"]["segment_results"][0]
        self.assertEqual(segment["text"], "Trần Trí nói với Mỹ Duyên.")
        self.assertEqual(segment["character_name"], "Trần Trí")
        self.assertEqual(segment["resolved_voice_id"], "đức_trí")

    def test_atomic_output_write_and_identical_report_reuse(self):
        output_path = (self.config.data_dir / "qa" / "custom.json").resolve()
        with patch("story_audio.audio_qa.atomic_write_bytes", wraps=atomic_write_bytes) as writer:
            first = self._generate(output_path=output_path)
        second = self._generate(output_path=output_path)
        self.assertEqual(writer.call_count, 1)
        self.assertFalse(first["reused_existing"])
        self.assertTrue(second["reused_existing"])

    def test_default_output_reuses_byte_identical_report(self):
        first = self._generate()
        second = self._generate()
        self.assertFalse(first["reused_existing"])
        self.assertTrue(second["reused_existing"])
        self.assertEqual(first["report_sha256"], second["report_sha256"])

    def test_conflicting_report_fails_closed(self):
        output_path = (self.config.data_dir / "qa" / "custom.json").resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text('{"schema":"conflict"}', encoding="utf-8")
        with self.assertRaises(QaReportConflictError):
            self._generate(output_path=output_path)

    def test_threshold_change_conflicts_with_existing_report(self):
        output_path = (self.config.data_dir / "qa" / "custom.json").resolve()
        self._generate(output_path=output_path)
        with self.assertRaises(QaReportConflictError):
            self._generate(output_path=output_path, thresholds=QaThresholds(long_trailing_silence_ms=301))

    def test_source_audio_is_not_mutated(self):
        before = {
            "segment": sha256_file(self.fixture.segments[0]["wav_path"]),
            "master": sha256_file(self.fixture.master_path),
            "final": sha256_file(self.fixture.final_path),
        }
        self._generate()
        after = {
            "segment": sha256_file(self.fixture.segments[0]["wav_path"]),
            "master": sha256_file(self.fixture.master_path),
            "final": sha256_file(self.fixture.final_path),
        }
        self.assertEqual(before, after)

    def test_cli_structured_internal_error(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("story_audio.audio_qa.generate_audio_qa_report", side_effect=ValueError("boom")):
            exit_code = main(["--manifest", str(self.fixture.manifest_path.resolve())], stdout=stdout, stderr=stderr)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 9)
        self.assertEqual(payload["status"], "internal_error")

    def test_no_regenerate_accept_or_reject_api_calls(self):
        with patch("urllib.request.urlopen") as mocked:
            self._generate()
        mocked.assert_not_called()

    def test_ffmpeg_missing_produces_structured_error(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = main(
            ["--manifest", str(self.fixture.manifest_path.resolve()), "--ffmpeg-path", "__missing_ffmpeg__"],
            stdout=stdout,
            stderr=stderr,
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 6)
        self.assertEqual(payload["status"], "ffmpeg_unavailable")

    def test_ffmpeg_nonzero_exit_produces_structured_error(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        def _fake_run(command, *, timeout_seconds):
            if command[1] == "-version":
                return subprocess.CompletedProcess(command, 0, b"", b"")
            return subprocess.CompletedProcess(command, 1, b"", b"boom")
        with patch(
            "story_audio.audio_qa._run_completed_command",
            side_effect=_fake_run,
        ):
            exit_code = main(["--manifest", str(self.fixture.manifest_path.resolve())], stdout=stdout, stderr=stderr)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 5)
        self.assertEqual(payload["status"], "artifact_integrity_failure")

    def test_timeout_produces_structured_error(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch(
            "story_audio.audio_qa._check_binary_available",
            side_effect=QaFfmpegUnavailableError("FFmpeg command timed out", details={"command": "ffmpeg"}),
        ):
            exit_code = main(["--manifest", str(self.fixture.manifest_path.resolve())], stdout=stdout, stderr=stderr)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 6)
        self.assertEqual(payload["status"], "ffmpeg_unavailable")

    def test_no_temp_files_left_after_success_or_failure(self):
        before = sorted(str(path) for path in self.config.data_dir.rglob("*.partial"))
        self._generate()
        after_success = sorted(str(path) for path in self.config.data_dir.rglob("*.partial"))
        self.assertEqual(before, after_success)
        with patch("story_audio.audio_qa._analyze_audio_file", side_effect=QaArtifactIntegrityError("boom")):
            with self.assertRaises(QaArtifactIntegrityError):
                self._generate()
        after_failure = sorted(str(path) for path in self.config.data_dir.rglob("*.partial"))
        self.assertEqual(before, after_failure)


class AudioQaPureFunctionTests(IsolatedTestCase):
    def test_voice_aggregate_handles_empty(self):
        self.assertEqual(_build_voice_aggregates([]), [])
