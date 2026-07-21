from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from story_audio.db import utcnow
from story_audio.files import sha256_file
from tests.base import IsolatedTestCase
from tests.test_active_output import seed_active_output


class AudioLibraryApiTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        seeded = seed_active_output(self.temp_root)
        self.db = seeded["db"]
        self.chapter_id = seeded["chapter_one"]
        self.pending_chapter_id = seeded["chapter_two"]
        self.old_artifact_id = seeded["old_artifact_id"]
        self.new_artifact_id = seeded["new_artifact_id"]
        self._multipart_patcher = patch("fastapi.dependencies.utils.ensure_multipart_is_installed", lambda: None)
        self._multipart_patcher.start()
        import story_audio.api as api_module

        self._original_db = api_module.db
        api_module.db = self.db
        from story_audio.api import app

        self.client = TestClient(app)

    def tearDown(self) -> None:
        import story_audio.api as api_module

        api_module.db = self._original_db
        self._multipart_patcher.stop()
        super().tearDown()

    def _items(self) -> list[dict]:
        response = self.client.get("/api/audio-library")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], len(data["items"]))
        return data["items"]

    def test_active_pointer_wins_over_newest_completed_job(self) -> None:
        items = self._items()
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["chapter_id"], self.chapter_id)
        self.assertEqual(item["artifact_id"], self.old_artifact_id)
        self.assertNotEqual(item["artifact_id"], self.new_artifact_id)
        self.assertEqual(item["job_id"], 1)
        self.assertEqual(item["casting_plan_revision"], 4)

    def test_chapter_without_active_artifact_is_absent(self) -> None:
        chapter_ids = {item["chapter_id"] for item in self._items()}
        self.assertIn(self.chapter_id, chapter_ids)
        self.assertNotIn(self.pending_chapter_id, chapter_ids)

    def test_safe_file_url_does_not_expose_absolute_path(self) -> None:
        item = self._items()[0]
        self.assertEqual(item["file_url"], f"/api/artifacts/{self.old_artifact_id}/file")
        self.assertEqual(item["download_url"], item["file_url"])
        self.assertNotIn(":", item["file_url"])
        self.assertNotIn("\\", item["file_url"])
        self.assertNotIn("path", item)
        self.assertNotIn("output_path", item)

    def test_qa_state_uses_database_approval_semantics(self) -> None:
        item = self._items()[0]
        self.assertEqual(item["human_qa_status"], "pending")
        self.assertEqual(item["human_approval_status"], "pending")
        self.assertIsNone(item["human_approval_matches_active_artifact"])

        now = utcnow()
        approval = {
            "status": "approved",
            "recorded_at": now,
            "approved_at": now,
            "artifact_id": self.old_artifact_id,
            "job_id": 1,
            "output_path": "D:/not/exposed/chapter.m4a",
            "sha256": "sha",
            "duration_ms": 1000,
        }
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE chapters SET human_approval_json=?, updated_at=? WHERE id=?",
                (json.dumps(approval), now, self.chapter_id),
            )
        item = self._items()[0]
        self.assertEqual(item["human_qa_status"], "accepted")
        self.assertEqual(item["human_approval_status"], "approved")
        self.assertTrue(item["human_approval_matches_active_artifact"])
        self.assertNotIn("human_approval", item)

    def test_invalid_active_binding_does_not_fallback_to_historical_artifact(self) -> None:
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE chapters SET active_audio_artifact_id=? WHERE id=?",
                (999999, self.chapter_id),
            )
        self.assertEqual(self._items(), [])

    def test_items_are_ordered_by_book_title_then_chapter_number(self) -> None:
        now = utcnow()
        artifact_path = self.temp_root / "data" / "output" / "job_3" / "chapter_0011" / "chapter.m4a"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(b"pending-now-active")
        chapter = self.db.fetch_one(
            "SELECT book_id, active_text_revision_id FROM chapters WHERE id=?",
            (self.pending_chapter_id,),
        )
        with self.db.transaction() as connection:
            job_id = int(
                connection.execute(
                    """INSERT INTO jobs(
                        book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                        settings_json,total_chapters,scheduled_at,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (chapter["book_id"], "completed", 11, 11, "Voice C", "off", "m4a", "{}", 1, now, now, now),
                ).lastrowid
            )
            job_chapter_id = int(
                connection.execute(
                    "INSERT INTO job_chapters(job_id,chapter_id,sequence,status,text_revision_id) VALUES(?,?,?,?,?)",
                    (job_id, self.pending_chapter_id, 1, "completed", chapter["active_text_revision_id"]),
                ).lastrowid
            )
            artifact_id = int(
                connection.execute(
                    """INSERT INTO artifacts(
                        chapter_id,job_chapter_id,text_revision_id,artifact_type,path,sha256,size_bytes,
                        duration_ms,status,created_at,verified_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        self.pending_chapter_id,
                        job_chapter_id,
                        chapter["active_text_revision_id"],
                        "chapter_m4a",
                        str(artifact_path),
                        sha256_file(artifact_path),
                        artifact_path.stat().st_size,
                        2000,
                        "active",
                        now,
                        now,
                    ),
                ).lastrowid
            )
            connection.execute(
                "UPDATE chapters SET audio_status='completed', active_audio_artifact_id=? WHERE id=?",
                (artifact_id, self.pending_chapter_id),
            )
        items = self._items()
        self.assertEqual([item["chapter_number"] for item in items], [10, 11])


if __name__ == "__main__":
    unittest.main()
