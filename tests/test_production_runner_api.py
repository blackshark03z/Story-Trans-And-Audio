from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from story_audio.casting import approve_plan, create_casting_draft
from story_audio.db import Database
from story_audio.files import sha256_text
from story_audio.storage import ContentStore
from story_audio.voice_profile import set_book_voice_profile
from tests.base import IsolatedTestCase


class ProductionRunnerApiTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.db = Database(self.config.db_path)
        self.db.initialize()
        self.store = ContentStore(self.config)

        with self.db.transaction() as conn:
            self.book_id = int(conn.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                ("Test Book", "test://book", "a" * 64, 1),
            ).lastrowid)
            self.chapter_id = int(conn.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
                (self.book_id, 629, "Chapter 629", 120),
            ).lastrowid)

        text = '“Ati nói.” Người kể chuyện tiếp tục.'
        content_path, content_sha = self.store.put_text(text)
        lexical_sha = sha256_text(text)
        with self.db.transaction() as conn:
            self.text_revision_id = int(conn.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,datetime('now'))""",
                (self.chapter_id, "reflowed", content_path, content_sha, lexical_sha, len(text), "v1", "approved"),
            ).lastrowid)
            conn.execute(
                "UPDATE chapters SET active_text_revision_id=?,updated_at=datetime('now') WHERE id=?",
                (self.text_revision_id, self.chapter_id),
            )

        set_book_voice_profile(
            self.db,
            self.book_id,
            narrator_voice_id="ngoc_lan",
            male_dialogue_voice_id="duc_tri",
            female_dialogue_voice_id="my_duyen",
            unknown_fallback="narrator",
            unknown_voice_id=None,
            allowed_voice_ids={"ngoc_lan", "duc_tri", "my_duyen"},
        )
        draft = create_casting_draft(
            self.db,
            self.store,
            chapter_id=self.chapter_id,
            text_revision_id=self.text_revision_id,
            narrator_voice_id="ngoc_lan",
            assignments=[],
            allowed_voice_ids={"ngoc_lan", "duc_tri", "my_duyen"},
        )
        self.plan_id = int(draft["id"])
        approve_plan(self.db, self.store, self.plan_id)

        self._multipart_patcher = patch("fastapi.dependencies.utils.ensure_multipart_is_installed", lambda: None)
        self._multipart_patcher.start()
        import story_audio.api as api_module
        self._original_db = api_module.db
        self._original_store = api_module.store
        self._original_settings = api_module.settings
        self._original_tts = api_module.tts_service
        api_module.db = self.db
        api_module.store = self.store
        api_module.settings = self.config
        mock_tts = MagicMock()
        mock_tts.voices.return_value = [
            {"id": "ngoc_lan", "label": "Ngọc Lan"},
            {"id": "duc_tri", "label": "Đức Trí"},
            {"id": "my_duyen", "label": "Mỹ Duyên"},
        ]
        api_module.tts_service = mock_tts
        from story_audio.api import app
        self.client = TestClient(app)

    def tearDown(self) -> None:
        import story_audio.api as api_module
        api_module.db = self._original_db
        api_module.store = self._original_store
        api_module.settings = self._original_settings
        api_module.tts_service = self._original_tts
        self._multipart_patcher.stop()
        super().tearDown()

    def test_runtime_endpoint_reports_isolated_identity(self):
        response = self.client.get("/api/runtime")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["data_root"], str(self.config.data_dir.resolve()))
        self.assertEqual(data["db_path"], str(self.config.db_path.resolve()))
        self.assertFalse(data["is_canonical_live_data_root"])
        self.assertFalse(data["is_canonical_live_db"])

    def test_read_casting_plan_endpoint_returns_exact_plan(self):
        response = self.client.get(f"/api/casting/{self.plan_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], self.plan_id)
        self.assertEqual(data["chapter_id"], self.chapter_id)
        self.assertEqual(data["text_revision_id"], self.text_revision_id)
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["plan"]["book_voice_profile"]["narrator_voice_id"], "ngoc_lan")
        self.assertTrue(data["plan"]["utterances"])

    def test_read_casting_plan_endpoint_returns_404_for_missing_plan(self):
        response = self.client.get("/api/casting/999999")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
