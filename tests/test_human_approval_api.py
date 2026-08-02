from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

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
        api_module.db = self.db
        api_module.store = self.store
        api_module.settings = self.config
        from story_audio.api import app

        self.client = TestClient(app)

    def tearDown(self) -> None:
        import story_audio.api as api_module

        api_module.db = self._original_db
        api_module.store = self._original_store
        api_module.settings = self._original_settings
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
        history = self.client.get(
            f"/api/chapters/{self.chapter_id}/human-approval-history"
        ).json()
        self.assertEqual(len(history["items"]), 1)

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

    def test_history_is_timestamped_and_bound_to_each_active_artifact(self) -> None:
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

        history = self.client.get(
            f"/api/chapters/{self.chapter_id}/human-approval-history"
        )
        self.assertEqual(history.status_code, 200)
        payload = history.json()
        self.assertEqual(payload["total"], 2)
        self.assertEqual(
            [item["status"] for item in payload["items"]],
            ["approved", "needs_fixes"],
        )
        self.assertTrue(all(item["recorded_at"] for item in payload["items"]))
        self.assertTrue(
            all(item["artifact_id"] == self.old_artifact_id for item in payload["items"])
        )
        self.assertNotIn("output_path", str(payload))

    def test_detail_warns_when_approved_artifact_no_longer_matches_active_output(self) -> None:
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
        self.assertEqual(data["chapter"]["human_qa_status"], "approved_stale")
        self.assertEqual(
            data["chapter"]["human_approval_warning"],
            "Bản audio hiện tại khác với bản đã chốt trước đó. Cần kiểm tra lại.",
        )
        self.assertFalse(data["human_approval"]["matches_active_artifact"])


if __name__ == "__main__":
    unittest.main()
