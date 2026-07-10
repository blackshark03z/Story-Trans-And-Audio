from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

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
