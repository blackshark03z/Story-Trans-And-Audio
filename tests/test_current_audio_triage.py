from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from story_audio.files import sha256_file
from story_audio.current_audio_triage import _MAX_RISK_POINTS, _MAX_SHORTLIST_POINTS, _merge_shortlist
from tests.base import IsolatedTestCase
from tests.test_audio_qa import AudioQaFixture


class CurrentAudioTriageTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            self.skipTest("ffmpeg/ffprobe are required for current-audio triage tests")
        self.fixture = AudioQaFixture(self)
        self.fixture.build()
        self.db = self.fixture.db
        self._multipart_patcher = patch("fastapi.dependencies.utils.ensure_multipart_is_installed", lambda: None)
        self._multipart_patcher.start()
        import story_audio.api as api_module

        self._api_module = api_module
        self._original_db = api_module.db
        self._original_settings = api_module.settings
        api_module.db = self.db
        api_module.settings = self.fixture.config
        from story_audio.api import app

        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._api_module.db = self._original_db
        self._api_module.settings = self._original_settings
        self._multipart_patcher.stop()
        super().tearDown()

    def _get(self, artifact_id: int = 3):
        return self.client.get(f"/api/audio-library/{artifact_id}/automated-qa")

    def test_clean_full_fixture_is_clear_and_does_not_decide_human_qa(self) -> None:
        before = self.db.fetch_one("SELECT human_approval_json FROM chapters WHERE id=?", (self.fixture.chapter_id,))
        response = self._get()
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["state"], "clear")
        self.assertEqual(payload["mode"], "full")
        self.assertEqual(payload["human_qa"], "required")
        self.assertFalse(payload["mutation_performed"])
        self.assertEqual(payload["assessment"]["technical_score"], 100)
        self.assertEqual(payload["assessment"]["coverage_percent"], 100)
        self.assertEqual(payload["assessment"]["confidence"], "high")
        self.assertEqual(payload["assessment"]["capabilities"]["spoken_content"], "not_scored")
        self.assertIn("Human QA", " ".join(payload["assessment"]["limitations"]))
        self.assertGreaterEqual(len(payload["shortlist"]), 2)
        after = self.db.fetch_one("SELECT human_approval_json FROM chapters WHERE id=?", (self.fixture.chapter_id,))
        self.assertEqual(before["human_approval_json"], after["human_approval_json"])
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS count FROM audit_events")["count"], 0)
        self.assertFalse((self.fixture.config.data_dir / "qa").exists())

    def test_risk_fixture_shortlists_attention_without_human_mutation(self) -> None:
        metrics = {
            "hard_clipping_sample_count": 1,
            "near_clipping_sample_count": 0,
            "longest_internal_silence_ms": 0,
            "trailing_silence_ms": 0,
        }
        with patch("story_audio.current_audio_triage.analyze_audio_file", return_value=metrics):
            response = self._get()
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["state"], "attention")
        self.assertTrue(payload["summary"]["risk_detected"])
        self.assertLess(payload["assessment"]["technical_score"], 100)
        self.assertEqual(payload["assessment"]["method"], "rule_based_technical_v1")
        self.assertTrue(any(point["priority"] == "hard_clipping" for point in payload["shortlist"]))
        self.assertIsNone(self.db.fetch_one("SELECT human_approval_json FROM chapters WHERE id=?", (self.fixture.chapter_id,))["human_approval_json"])

    def test_supported_finding_is_bound_to_exact_segment_and_offline_repair(self) -> None:
        first = self.fixture.segments[0]
        first["leading_silence_ms"] = 900
        self.fixture.build()
        self.db = self.fixture.db
        self._api_module.db = self.db
        response = self._get()
        self.assertEqual(response.status_code, 200, response.text)
        point = next(item for item in response.json()["shortlist"] if item.get("repair", {}).get("kind") == "trim_leading_silence")
        bound_segment = self.fixture.segments[int(point["segment_id"]) - 1]
        self.assertEqual(point["segment_audio_sha256"], bound_segment["sha256"])
        self.assertEqual(point["repair"]["kind"], "trim_leading_silence")
        self.assertEqual(point["repair"]["label"], "Có thể sửa tự động")

        candidate = self.client.post(
            "/api/audio-library/3/machine-repair-candidate",
            json={
                "artifact_sha256": sha256_file(self.fixture.final_path),
                "segment_id": point["segment_id"],
                "repair_kind": point["repair"]["kind"],
            },
        )
        self.assertEqual(candidate.status_code, 200, candidate.text)
        payload = candidate.json()
        self.assertFalse(payload["mutation_performed"])
        self.assertTrue(payload["comparison"]["improved"])
        self.assertLess(payload["comparison"]["after"], payload["comparison"]["before"])
        self.assertEqual(self.db.fetch_one("SELECT active_audio_artifact_id FROM chapters WHERE id=1")["active_audio_artifact_id"], 3)
        attempt = self.db.fetch_one("SELECT * FROM segment_attempts WHERE id=?", (payload["attempt_id"],))
        self.assertEqual(attempt["status"], "candidate")

        restored = self.client.get(
            "/api/audio-library/3/machine-repair-candidate",
            params={"artifact_sha256": sha256_file(self.fixture.final_path)},
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["candidate"]["attempt_id"], payload["attempt_id"])
        self.assertTrue(restored.json()["candidate"]["restored"])

        repeated = self.client.post(
            "/api/audio-library/3/machine-repair-candidate",
            json={
                "artifact_sha256": sha256_file(self.fixture.final_path),
                "segment_id": point["segment_id"],
                "repair_kind": point["repair"]["kind"],
            },
        )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()["attempt_id"], payload["attempt_id"])
        self.assertEqual(
            self.db.fetch_one("SELECT COUNT(*) AS count FROM segment_attempts WHERE status='candidate'")["count"],
            1,
        )

        discarded = self.client.post(
            f"/api/segments/{point['segment_id']}/machine-repair-candidate/{payload['attempt_id']}/discard",
            json={},
        )
        self.assertEqual(discarded.status_code, 200, discarded.text)
        self.assertTrue(discarded.json()["candidate_deleted"])
        self.assertFalse(discarded.json()["current_audio_changed"])
        self.assertIsNone(self.db.fetch_one("SELECT id FROM segment_attempts WHERE id=?", (payload["attempt_id"],)))
        self.assertFalse(Path(attempt["wav_path"]).exists())

        empty = self.client.get(
            "/api/audio-library/3/machine-repair-candidate",
            params={"artifact_sha256": sha256_file(self.fixture.final_path)},
        )
        self.assertEqual(empty.status_code, 200, empty.text)
        self.assertIsNone(empty.json()["candidate"])

    def test_hard_clipping_uses_deterministic_peak_reduction(self) -> None:
        metrics = {
            "duration_ms": 1000,
            "hard_clipping_sample_count": 1,
            "near_clipping_sample_count": 0,
            "leading_silence_ms": 0,
            "trailing_silence_ms": 0,
            "longest_internal_silence_ms": 0,
            "mean_volume_dbfs": -18.0,
        }
        with patch("story_audio.current_audio_triage.analyze_audio_file", return_value=metrics):
            response = self._get()
        point = next(item for item in response.json()["shortlist"] if item.get("risk_kind") == "hard_clipping")
        self.assertTrue(point["repair"]["supported"])
        self.assertEqual(point["repair"]["kind"], "reduce_peak")
        rejected = self.client.post(
            "/api/audio-library/3/machine-repair-candidate",
            json={
                "artifact_sha256": sha256_file(self.fixture.final_path),
                "segment_id": point["segment_id"],
                "repair_kind": "hard_clipping",
            },
        )
        self.assertEqual(rejected.status_code, 409, rejected.text)

    def test_peak_reduction_candidate_removes_full_scale_samples(self) -> None:
        self.fixture.segments[0]["amplitude"] = 32767
        self.fixture.build()
        self.db = self.fixture.db
        self._api_module.db = self.db

        response = self._get()
        self.assertEqual(response.status_code, 200, response.text)
        point = next(
            item
            for item in response.json()["shortlist"]
            if item.get("risk_kind") == "hard_clipping" and item.get("segment_id") == 1
        )
        self.assertEqual(point["repair"]["kind"], "reduce_peak")

        candidate = self.client.post(
            "/api/audio-library/3/machine-repair-candidate",
            json={
                "artifact_sha256": sha256_file(self.fixture.final_path),
                "segment_id": 1,
                "repair_kind": "reduce_peak",
            },
        )
        self.assertEqual(candidate.status_code, 200, candidate.text)
        comparison = candidate.json()["comparison"]
        self.assertEqual(comparison["label"], "Mẫu clipping")
        self.assertGreater(comparison["before"], 0)
        self.assertEqual(comparison["after"], 0)

    def test_trailing_candidate_improves_an_outlier_below_500ms(self) -> None:
        first = self.fixture.segments[0]
        first["trailing_silence_ms"] = 490
        self.fixture.build()
        self.db = self.fixture.db
        self._api_module.db = self.db

        created = self.client.post(
            "/api/audio-library/3/machine-repair-candidate",
            json={
                "artifact_sha256": sha256_file(self.fixture.final_path),
                "segment_id": 1,
                "repair_kind": "trim_trailing_silence",
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        payload = created.json()
        self.assertEqual(payload["comparison"]["label"], "Khoảng lặng cuối")
        self.assertLess(payload["comparison"]["after"], payload["comparison"]["before"])
        self.assertLessEqual(payload["comparison"]["after"], 300)

    def test_shortlist_merges_duplicate_seek_points_by_priority_and_caps_risks(self) -> None:
        points: list[dict] = []
        _merge_shortlist(points, {"sequence": 1, "timestamp_ms": 0, "priority": "technical_risk", "label": "Rủi ro kỹ thuật"}, maximum=_MAX_RISK_POINTS)
        _merge_shortlist(points, {"sequence": 1, "timestamp_ms": 0, "priority": "hard_clipping", "label": "Clipping"}, maximum=_MAX_RISK_POINTS)
        for sequence in range(2, 30):
            _merge_shortlist(points, {"sequence": sequence, "timestamp_ms": sequence * 1000, "priority": "technical_risk", "label": "Rủi ro kỹ thuật"}, maximum=_MAX_RISK_POINTS)
        self.assertEqual(len(points), _MAX_RISK_POINTS)
        self.assertEqual(points[0]["priority"], "hard_clipping")
        self.assertLessEqual(_MAX_RISK_POINTS + 1 + 2, _MAX_SHORTLIST_POINTS)

    def test_master_is_hash_verified_but_not_signal_analyzed(self) -> None:
        observed: list[str] = []

        def fake_analysis(path, **_kwargs):
            observed.append(str(path))
            return {
                "hard_clipping_sample_count": 0,
                "near_clipping_sample_count": 0,
                "longest_internal_silence_ms": 0,
                "trailing_silence_ms": 0,
            }

        with patch("story_audio.current_audio_triage.analyze_audio_file", side_effect=fake_analysis):
            response = self._get()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(str(self.fixture.final_path), observed)
        self.assertNotIn(str(self.fixture.master_path), observed)

    def test_cleaned_segment_wavs_are_degraded_not_corruption(self) -> None:
        for segment in self.fixture.segments:
            segment["wav_path"].unlink()
        response = self._get()
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["state"], "degraded")
        self.assertEqual(payload["mode"], "degraded")
        self.assertEqual(payload["summary"]["missing_segment_wavs"], len(self.fixture.segments))
        self.assertEqual(payload["assessment"]["coverage_percent"], 0)
        self.assertEqual(payload["assessment"]["confidence"], "limited")
        self.assertFalse(payload["mutation_performed"])

    def test_common_segment_boundary_silence_is_not_flagged_as_risk(self) -> None:
        metrics = {
            "duration_ms": 2000,
            "hard_clipping_sample_count": 0,
            "near_clipping_sample_count": 0,
            "leading_silence_ms": 0,
            "trailing_silence_ms": 500,
            "longest_internal_silence_ms": 0,
            "mean_volume_dbfs": -18.0,
        }
        with patch("story_audio.current_audio_triage.analyze_audio_file", return_value=metrics):
            response = self._get()
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["state"], "clear")
        self.assertEqual(payload["assessment"]["risk_counts"]["silence"], 0)

    def test_timeline_text_binding_mismatch_blocks_score(self) -> None:
        timeline = json.loads(self.fixture.timeline_path.read_text(encoding="utf-8"))
        timeline["items"][0]["text"] = "Nội dung đã bị thay đổi"
        self.fixture.timeline_path.write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
        with self.db.transaction() as connection:
            connection.execute("UPDATE artifacts SET sha256=? WHERE id=2", (sha256_file(self.fixture.timeline_path),))
        response = self._get()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"], "blocked")
        self.assertNotIn("assessment", response.json())

    def test_timeline_mismatch_is_blocked_without_mutation(self) -> None:
        timeline = json.loads(self.fixture.timeline_path.read_text(encoding="utf-8"))
        timeline["chapter_id"] = 999
        self.fixture.timeline_path.write_text(json.dumps(timeline), encoding="utf-8")
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE artifacts SET sha256=? WHERE id=2",
                (sha256_file(self.fixture.timeline_path),),
            )
        response = self._get()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"], "blocked")
        self.assertEqual(response.json()["code"], "BLOCKED_TIMELINE")
        self.assertIsNone(self.db.fetch_one("SELECT human_approval_json FROM chapters WHERE id=?", (self.fixture.chapter_id,))["human_approval_json"])

    def test_non_current_artifact_fails_closed(self) -> None:
        with self.db.transaction() as connection:
            connection.execute("UPDATE chapters SET active_audio_artifact_id=? WHERE id=?", (1, self.fixture.chapter_id))
        response = self._get()
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "STALE_ARTIFACT")

    def test_missing_artifact_is_not_treated_as_a_machine_clear(self) -> None:
        response = self._get(99999)
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["detail"]["code"], "MISSING_ARTIFACT")


if __name__ == "__main__":
    unittest.main()
