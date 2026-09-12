from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from story_audio.custom_voice import CustomVoiceRepository
from story_audio.db import utcnow
from story_audio.storage import ContentStore
from tests.base import IsolatedTestCase
from tests.test_active_output import seed_active_output


class HumanApprovalApiTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        seeded = seed_active_output(self.temp_root)
        self.db = seeded["db"]
        self.config = seeded["config"]
        self.store = ContentStore(self.config)
        self.chapter_id = seeded["chapter_one"]
        self.old_artifact_id = seeded["old_artifact_id"]
        self.new_artifact_id = seeded["new_artifact_id"]
        self._multipart_patcher = patch("fastapi.dependencies.utils.ensure_multipart_is_installed", lambda: None)
        self._multipart_patcher.start()
        import story_audio.api as api_module

        self._original_db = api_module.db
        self._original_store = api_module.store
        self._original_settings = api_module.settings
        self._original_tts = api_module.tts_service
        self._original_custom_voice_repo = api_module.custom_voice_repo
        api_module.db = self.db
        api_module.store = self.store
        api_module.settings = self.config
        api_module.tts_service = MagicMock()
        api_module.tts_service.voices.return_value = [
            {"id": "ngoc_lan", "label": "Ngọc Lan"},
        ]
        api_module.custom_voice_repo = CustomVoiceRepository(self.db, self.store)
        from story_audio.api import app

        self.client = TestClient(app)

    def tearDown(self) -> None:
        import story_audio.api as api_module

        api_module.db = self._original_db
        api_module.store = self._original_store
        api_module.settings = self._original_settings
        api_module.tts_service = self._original_tts
        api_module.custom_voice_repo = self._original_custom_voice_repo
        self._multipart_patcher.stop()
        super().tearDown()

    def test_chapter_without_human_approval_reports_pending(self) -> None:
        response = self.client.get(f"/api/chapters/{self.chapter_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["human_approval"])
        self.assertEqual(data["chapter"]["human_qa_status"], "pending")
        self.assertEqual(data["chapter"]["human_approval_label"], "Chưa chốt")

    def test_put_human_approval_records_active_output_snapshot(self) -> None:
        response = self.client.put(
            f"/api/chapters/{self.chapter_id}/human-approval",
            json={"status": "approved", "notes": "Nghe kiểm tra xong."},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        approval = data["human_approval"]
        self.assertEqual(approval["status"], "approved")
        self.assertEqual(approval["artifact_id"], self.old_artifact_id)
        self.assertEqual(approval["job_id"], 1)
        self.assertEqual(approval["notes"], "Nghe kiểm tra xong.")
        self.assertTrue(approval["matches_active_artifact"])
        self.assertEqual(data["chapter"]["human_qa_status"], "accepted")
        self.assertEqual(data["chapter"]["human_approval_label"], "Đã chốt")

    def test_production_command_accept_normalizes_json_string_body(self) -> None:
        command = {
            "command_type": "HUMAN_QA_ACCEPT",
            "idempotency_key": "qa-json-string-0001",
            "scope": {"artifact": {"id": self.old_artifact_id}},
            "payload": {"chapter_id": self.chapter_id, "notes": "QA accepted."},
        }
        response = self.client.post(
            "/api/production/commands",
            content=json.dumps(json.dumps(command)),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["outcome"], "APPLIED")
        self.assertEqual(payload["applied_items"][0]["artifact_id"], self.old_artifact_id)
        qa_events = self.db.fetch_one(
            "SELECT COUNT(*) AS count FROM audit_events WHERE chapter_id=? AND event_code='human_qa_recorded'",
            (self.chapter_id,),
        )
        self.assertEqual(int(qa_events["count"]), 1)

    def test_production_command_rejects_non_object_body(self) -> None:
        response = self.client.post("/api/production/commands", json=["not", "object"])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"],
            "PRODUCTION_COMMAND_BODY_INVALID",
        )

    def test_put_human_approval_can_mark_needs_fixes(self) -> None:
        response = self.client.put(
            f"/api/chapters/{self.chapter_id}/human-approval",
            json={"status": "needs_fixes", "notes": "Còn vài lỗi nhỏ."},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["human_approval"]["status"], "needs_fixes")
        self.assertIsNone(data["human_approval"]["approved_at"])
        self.assertEqual(data["chapter"]["human_qa_status"], "needs_fixes")
        self.assertEqual(data["chapter"]["human_approval_label"], "Cần sửa")

    def test_needs_fixes_persists_structured_feedback_and_reuses_exact_submission(self) -> None:
        feedback = {
            "global_speed_target": 1.25,
            "repeated_words": True,
            "local_pacing_adjustment_required": True,
            "issue_types": ["repeated_words", "overall_pacing", "local_pacing"],
            "operator_note": "Một số đoạn còn lặp chữ.",
            "position_markers": [],
        }
        payload = {
            "status": "needs_fixes",
            "notes": feedback["operator_note"],
            "qa_feedback": feedback,
        }
        first = self.client.put(
            f"/api/chapters/{self.chapter_id}/human-approval", json=payload
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["human_approval"]["qa_feedback"], feedback)
        second = self.client.put(
            f"/api/chapters/{self.chapter_id}/human-approval", json=payload
        )
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["idempotent_reused"])
        audit = self.db.fetch_one(
            "SELECT details_json FROM audit_events WHERE chapter_id=?",
            (self.chapter_id,),
        )
        self.assertEqual(json.loads(audit["details_json"])["qa_feedback"], feedback)

    def test_confirm_repair_plan_is_artifact_scoped_and_idempotent(self) -> None:
        feedback = {
            "global_speed_target": 1.25,
            "repeated_words": True,
            "local_pacing_adjustment_required": True,
            "issue_types": ["repeated_words", "overall_pacing", "local_pacing"],
            "operator_note": "Cần sửa lặp chữ và tốc độ.",
            "position_markers": [],
        }
        qa = self.client.put(
            f"/api/chapters/{self.chapter_id}/human-approval",
            json={
                "status": "needs_fixes",
                "notes": feedback["operator_note"],
                "qa_feedback": feedback,
            },
        )
        self.assertEqual(qa.status_code, 200)
        qa_event = self.db.fetch_one(
            """
            SELECT id FROM audit_events
            WHERE chapter_id=? AND event_code='human_qa_recorded'
            ORDER BY id DESC LIMIT 1
            """,
            (self.chapter_id,),
        )
        chapter = self.db.fetch_one(
            "SELECT book_id,chapter_number FROM chapters WHERE id=?",
            (self.chapter_id,),
        )
        command = {
            "command_type": "CONFIRM_REPAIR_PLAN",
            "idempotency_key": "repair-plan-confirm-0001",
            "scope": {"chapter": {"id": self.chapter_id}},
            "payload": {
                "chapter_id": self.chapter_id,
                "artifact_id": self.old_artifact_id,
                "qa_evidence_id": int(qa_event["id"]),
                "repeated_words": True,
                "global_speed_target": 1.25,
                "local_pacing_adjustment_required": True,
                "operator_note": "",
            },
        }
        jobs_before = self.db.fetch_one("SELECT COUNT(*) AS count FROM jobs")["count"]
        artifacts_before = self.db.fetch_one("SELECT COUNT(*) AS count FROM artifacts")["count"]
        projected = ({"canonical_task": {"task_key": "fixture"}}, None)
        with patch("story_audio.api._project_production_command", return_value=projected):
            first = self.client.post("/api/production/commands", json=command)
            self.assertEqual(first.status_code, 200)
            first_payload = first.json()
            self.assertEqual(first_payload["outcome"], "APPLIED")
            evidence_id = first_payload["applied_items"][0]["repair_plan_evidence_id"]
            self.assertFalse(first_payload["applied_items"][0]["reused"])

            second = self.client.post("/api/production/commands", json=command)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(second.json()["outcome"], "APPLIED")
        self.assertEqual(
            self.db.fetch_one(
                """
                SELECT COUNT(*) AS count FROM audit_events
                WHERE chapter_id=? AND event_code='repair_plan_confirmed'
                """,
                (self.chapter_id,),
            )["count"],
            1,
        )
        evidence = self.db.fetch_one(
            "SELECT details_json FROM audit_events WHERE id=?", (evidence_id,)
        )
        details = json.loads(evidence["details_json"])
        self.assertEqual(details["artifact_id"], self.old_artifact_id)
        self.assertEqual(details["qa_evidence_id"], int(qa_event["id"]))
        self.assertTrue(details["repeated_words"])
        self.assertEqual(details["global_speed_target"], 1.25)
        self.assertTrue(details["local_pacing_adjustment_required"])
        self.assertEqual(
            self.db.fetch_one("SELECT COUNT(*) AS count FROM jobs")["count"], jobs_before
        )
        self.assertEqual(
            self.db.fetch_one("SELECT COUNT(*) AS count FROM artifacts")["count"], artifacts_before
        )

    def test_apply_repair_plan_creates_one_review_draft_without_media(self) -> None:
        feedback = {"repeated_words": True, "global_speed_target": 1.25, "local_pacing_adjustment_required": True, "operator_note": "Review repair locations.", "issue_types": ["repeated_words", "overall_pacing", "local_pacing"], "position_markers": []}
        self.assertEqual(self.client.put(f"/api/chapters/{self.chapter_id}/human-approval", json={"status": "needs_fixes", "notes": feedback["operator_note"], "qa_feedback": feedback}).status_code, 200)
        qa_id = int(self.db.fetch_one("SELECT id FROM audit_events WHERE chapter_id=? AND event_code='human_qa_recorded' ORDER BY id DESC LIMIT 1", (self.chapter_id,))["id"])
        scope = {"chapter": {"id": self.chapter_id}}
        confirm = {"command_type": "CONFIRM_REPAIR_PLAN", "idempotency_key": "repair-plan-confirm-apply", "scope": scope, "payload": {"chapter_id": self.chapter_id, "artifact_id": self.old_artifact_id, "qa_evidence_id": qa_id, **{key: feedback[key] for key in ("repeated_words", "global_speed_target", "local_pacing_adjustment_required", "operator_note")}}}
        projected = ({"canonical_task": {"task_key": "fixture"}}, None)
        with patch("story_audio.api._project_production_command", return_value=projected):
            confirmed = self.client.post("/api/production/commands", json=confirm).json()
            plan_id = confirmed["applied_items"][0]["repair_plan_evidence_id"]
            apply = {"command_type": "APPLY_REPAIR_PLAN", "idempotency_key": "repair-plan-apply-0001", "scope": scope, "payload": {"chapter_id": self.chapter_id, "artifact_id": self.old_artifact_id, "qa_evidence_id": qa_id, "repair_plan_evidence_id": plan_id}}
            jobs_before = self.db.fetch_one("SELECT COUNT(*) AS count FROM jobs")["count"]
            artifacts_before = self.db.fetch_one("SELECT COUNT(*) AS count FROM artifacts")["count"]
            first = self.client.post("/api/production/commands", json=apply)
            self.assertEqual(first.status_code, 200)
            self.assertFalse(first.json()["applied_items"][0]["reused"])
            second = self.client.post("/api/production/commands", json=apply)
            self.assertEqual(second.status_code, 200)
        draft = self.db.fetch_one("SELECT details_json FROM audit_events WHERE chapter_id=? AND event_code='repair_draft_created'", (self.chapter_id,))
        self.assertIsNotNone(draft)
        details = json.loads(draft["details_json"])
        self.assertEqual(details["repair_plan_evidence_id"], plan_id)
        self.assertEqual(details["global_speed_target"], 1.25)
        self.assertTrue(details["repeated_words"])
        self.assertTrue(details["local_pacing_adjustment_required"])
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS count FROM jobs")["count"], jobs_before)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS count FROM artifacts")["count"], artifacts_before)

    def test_repair_draft_review_is_idempotent_and_does_not_create_media(self) -> None:
        machine_marker = {
            "timestamp": 12.3,
            "segment_id": 77,
            "segment_audio_sha256": "a" * 64,
            "issue_type": "silence",
            "risk_kind": "silence",
            "repair_kind": "trim_leading_silence",
            "machine_finding_key": "77:silence:trim_leading_silence:12300",
            "note": "Khoảng lặng đầu dài.",
        }
        feedback = {"repeated_words": True, "global_speed_target": 1.25, "local_pacing_adjustment_required": True, "operator_note": "Review repair locations.", "issue_types": ["repeated_words", "overall_pacing", "local_pacing"], "position_markers": [machine_marker]}
        self.assertEqual(self.client.put(f"/api/chapters/{self.chapter_id}/human-approval", json={"status": "needs_fixes", "notes": feedback["operator_note"], "qa_feedback": feedback}).status_code, 200)
        qa_id = int(self.db.fetch_one("SELECT id FROM audit_events WHERE chapter_id=? AND event_code='human_qa_recorded' ORDER BY id DESC LIMIT 1", (self.chapter_id,))["id"])
        scope = {"chapter": {"id": self.chapter_id}}
        projected = ({"canonical_task": {"task_key": "fixture"}}, None)
        with patch("story_audio.api._project_production_command", return_value=projected):
            plan = self.client.post("/api/production/commands", json={"command_type": "CONFIRM_REPAIR_PLAN", "idempotency_key": "repair-plan-confirm-review", "scope": scope, "payload": {"chapter_id": self.chapter_id, "artifact_id": self.old_artifact_id, "qa_evidence_id": qa_id, **{key: feedback[key] for key in ("repeated_words", "global_speed_target", "local_pacing_adjustment_required", "operator_note")}}}).json()
            plan_id = int(plan["applied_items"][0]["repair_plan_evidence_id"])
            draft = self.client.post("/api/production/commands", json={"command_type": "APPLY_REPAIR_PLAN", "idempotency_key": "repair-plan-apply-review", "scope": scope, "payload": {"chapter_id": self.chapter_id, "artifact_id": self.old_artifact_id, "qa_evidence_id": qa_id, "repair_plan_evidence_id": plan_id}}).json()
            draft_id = int(draft["applied_items"][0]["repair_draft_evidence_id"])
            review_marker = {
                "timestamp_seconds": machine_marker["timestamp"],
                "segment_id": machine_marker["segment_id"],
                "segment_audio_sha256": machine_marker["segment_audio_sha256"],
                "nearest_utterance": "Câu gần nhất",
                "issue": "needs_pause",
                "risk_kind": machine_marker["risk_kind"],
                "repair_kind": machine_marker["repair_kind"],
                "machine_finding_key": machine_marker["machine_finding_key"],
                "note": machine_marker["note"],
                "local_pace": None,
            }
            review = {"command_type": "CONFIRM_REPAIR_DRAFT", "idempotency_key": "repair-draft-review-0001", "scope": scope, "payload": {"chapter_id": self.chapter_id, "artifact_id": self.old_artifact_id, "qa_evidence_id": qa_id, "repair_plan_evidence_id": plan_id, "repair_draft_evidence_id": draft_id, "markers": [review_marker]}}
            jobs_before = self.db.fetch_one("SELECT COUNT(*) AS count FROM jobs")["count"]
            artifacts_before = self.db.fetch_one("SELECT COUNT(*) AS count FROM artifacts")["count"]
            first = self.client.post("/api/production/commands", json=review)
            second = self.client.post("/api/production/commands", json=review)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["outcome"], "APPLIED")
        self.assertFalse(first.json()["applied_items"][0]["reused"])
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["applied_items"][0]["reused"])
        row = self.db.fetch_one("SELECT details_json FROM audit_events WHERE chapter_id=? AND event_code='repair_draft_reviewed'", (self.chapter_id,))
        self.assertIsNotNone(row)
        details = json.loads(row["details_json"])
        self.assertEqual(details["repair_draft_evidence_id"], draft_id)
        self.assertEqual(details["global_speed_target"], 1.25)
        self.assertEqual(details["marker_count"], 1)
        self.assertEqual(details["markers"][0]["segment_id"], 77)
        self.assertEqual(details["markers"][0]["segment_audio_sha256"], "a" * 64)
        self.assertEqual(details["markers"][0]["repair_kind"], "trim_leading_silence")
        plan_details = json.loads(
            self.db.fetch_one("SELECT details_json FROM audit_events WHERE id=?", (plan_id,))["details_json"]
        )
        draft_details = json.loads(
            self.db.fetch_one("SELECT details_json FROM audit_events WHERE id=?", (draft_id,))["details_json"]
        )
        self.assertEqual(plan_details["position_markers"], [machine_marker])
        self.assertEqual(draft_details["position_markers"], [machine_marker])
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS count FROM audit_events WHERE chapter_id=? AND event_code='repair_draft_reviewed'", (self.chapter_id,))["count"], 1)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS count FROM jobs")["count"], jobs_before)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) AS count FROM artifacts")["count"], artifacts_before)

    def test_chapter_detail_prefers_audit_note_over_placeholder_snapshot(self) -> None:
        response = self.client.put(
            f"/api/chapters/{self.chapter_id}/human-approval",
            json={
                "status": "needs_fixes",
                "notes": "Khoảng 3:11, audio repeats: “truyền tống truyền tống”.",
            },
        )
        self.assertEqual(response.status_code, 200)
        approval = response.json()["human_approval"]
        original_recorded_at = approval["recorded_at"]
        placeholder_recorded_at = utcnow()
        placeholder = dict(approval)
        placeholder["notes"] = "x"
        placeholder["recorded_at"] = placeholder_recorded_at
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE chapters SET human_approval_json=?, updated_at=? WHERE id=?",
                (
                    json.dumps(placeholder, ensure_ascii=False),
                    placeholder_recorded_at,
                    self.chapter_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO audit_events(event_code,job_id,chapter_id,details_json,created_at)
                VALUES(?,?,?,?,?)
                """,
                (
                    "human_qa_recorded",
                    approval["job_id"],
                    self.chapter_id,
                    json.dumps(
                        {
                            "status": "needs_fixes",
                            "notes": "x",
                            "artifact_id": approval["artifact_id"],
                            "job_id": approval["job_id"],
                            "sha256": approval["sha256"],
                            "duration_ms": approval["duration_ms"],
                        },
                        ensure_ascii=False,
                    ),
                    placeholder_recorded_at,
                ),
            )
        refreshed = self.client.get(f"/api/chapters/{self.chapter_id}")
        self.assertEqual(refreshed.status_code, 200)
        data = refreshed.json()
        self.assertEqual(
            data["human_approval"]["notes"],
            "Khoảng 3:11, audio repeats: “truyền tống truyền tống”.",
        )
        self.assertEqual(data["human_approval"]["recorded_at"], original_recorded_at)
        self.assertEqual(data["chapter"]["human_qa_status"], "needs_fixes")
        self.assertEqual(data["chapter"]["human_approval_label"], "Cần sửa")

    def test_needs_fixes_requires_note_and_creates_no_partial_record(self) -> None:
        response = self.client.put(
            f"/api/chapters/{self.chapter_id}/human-approval",
            json={"status": "needs_fixes", "notes": "   "},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"],
            "QA_REJECTION_NOTE_REQUIRED",
        )
        chapter = self.db.fetch_one(
            "SELECT human_approval_json FROM chapters WHERE id=?",
            (self.chapter_id,),
        )
        self.assertIsNone(chapter["human_approval_json"])
        self.assertEqual(
            self.db.fetch_one(
                "SELECT COUNT(*) AS count FROM audit_events WHERE chapter_id=?",
                (self.chapter_id,),
            )["count"],
            0,
        )

    def test_human_qa_keeps_only_the_current_decision(self) -> None:
        first = self.client.put(
            f"/api/chapters/{self.chapter_id}/human-approval",
            json={"status": "needs_fixes", "notes": "Pronunciation issue."},
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.put(
            f"/api/chapters/{self.chapter_id}/human-approval",
            json={"status": "approved", "notes": "Reviewed again."},
        )
        self.assertEqual(second.status_code, 200)

        rows = self.db.fetch_all(
            "SELECT details_json,created_at FROM audit_events WHERE chapter_id=? AND event_code='human_qa_recorded'",
            (self.chapter_id,),
        )
        self.assertEqual(len(rows), 1)
        current = json.loads(rows[0]["details_json"])
        self.assertEqual(current["status"], "approved")
        self.assertEqual(current["artifact_id"], self.old_artifact_id)
        self.assertTrue(rows[0]["created_at"])
        self.assertNotIn("output_path", str(current))

    def test_detail_does_not_inherit_approval_when_active_output_changes(self) -> None:
        response = self.client.put(
            f"/api/chapters/{self.chapter_id}/human-approval",
            json={"status": "approved", "notes": "Approved against old artifact."},
        )
        self.assertEqual(response.status_code, 200)
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE chapters SET active_audio_artifact_id=?, updated_at=datetime('now') WHERE id=?",
                (self.new_artifact_id, self.chapter_id),
            )
        refreshed = self.client.get(f"/api/chapters/{self.chapter_id}")
        self.assertEqual(refreshed.status_code, 200)
        data = refreshed.json()
        self.assertEqual(data["chapter"]["human_qa_status"], "pending")
        self.assertIsNone(data["chapter"]["human_approval_warning"])
        self.assertIsNone(data["human_approval"])


if __name__ == "__main__":
    unittest.main()
