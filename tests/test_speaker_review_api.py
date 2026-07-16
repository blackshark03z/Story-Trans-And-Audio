from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from story_audio.speaker_assignment import generate_speaker_assignment_draft
from tests.base import IsolatedTestCase
from story_audio.text import lexical_sha256
from tests.test_speaker_assignment import ZERO_TARGET_TEXT, fake_response, seed


class SpeakerReviewDraftApiTests(IsolatedTestCase):
    voices = {"narrator", "male", "female"}

    def setUp(self) -> None:
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(dir=self.temp_root)
        root = Path(self.temp.name)
        self.config, self.db, self.store, _book, self.chapter_id, self.revision_id, self.character_id = seed(root)
        with patch.object(type(self.config), "gemini_key", return_value="fake-key"):
            self.draft = generate_speaker_assignment_draft(
                self.db,
                self.store,
                self.config,
                chapter_id=self.chapter_id,
                provider=lambda **kwargs: fake_response(kwargs["request_data"], self.character_id),
            )
        self._multipart_patcher = patch(
            "fastapi.dependencies.utils.ensure_multipart_is_installed",
            lambda: None,
        )
        self._multipart_patcher.start()
        import story_audio.api as api_module

        self._original_db = api_module.db
        self._original_store = api_module.store
        self._original_settings = api_module.settings
        self._original_preset_ids = api_module._preset_voice_ids
        self._original_custom_context = api_module._build_custom_voice_context
        api_module.db = self.db
        api_module.store = self.store
        api_module.settings = self.config
        api_module._preset_voice_ids = lambda: set(self.voices)
        api_module._build_custom_voice_context = lambda: None
        from story_audio.api import app

        self.client = TestClient(app)

    def tearDown(self) -> None:
        import story_audio.api as api_module

        api_module.db = self._original_db
        api_module.store = self._original_store
        api_module.settings = self._original_settings
        api_module._preset_voice_ids = self._original_preset_ids
        api_module._build_custom_voice_context = self._original_custom_context
        self._multipart_patcher.stop()
        self.temp.cleanup()
        super().tearDown()

    def _full_decisions(self):
        return [
            {
                "utterance_id": item["utterance_id"],
                "speaker_type": item["speaker_type"],
                "character_id": item["character_id"],
                "decision_source": "gemini_suggestion",
            }
            for item in self.draft["draft"]["assignments"]
        ]

    def test_create_draft_only_response_stays_unapproved(self) -> None:
        response = self.client.post(
            f"/api/chapters/{self.chapter_id}/speaker-review/casting-plan-draft",
            json={
                "speaker_draft_id": self.draft["id"],
                "expected_draft_fingerprint": self.draft["input_fingerprint"],
                "expected_text_revision_id": self.draft["text_revision_id"],
                "decisions": self._full_decisions(),
                "idempotency_key": "api-stage-1",
                "operator_note": "Create draft only.",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["chapter_id"], self.chapter_id)
        self.assertEqual(data["text_revision_id"], self.revision_id)
        self.assertEqual(data["speaker_draft_id"], self.draft["id"])
        self.assertEqual(data["casting_plan_status"], "draft")
        self.assertFalse(data["approved"])
        self.assertEqual(data["remaining_unreviewed_count"], 0)
        self.assertEqual(data["role_counts"]["character"], len(self.draft["draft"]["assignments"]))
        self.assertEqual(data["effective_voice_counts"]["male"], len(self.draft["draft"]["assignments"]))
        self.assertEqual(int(self.db.fetch_one("SELECT COUNT(*) AS n FROM casting_plans WHERE status='approved'")["n"]), 0)

    def test_incomplete_review_returns_400_with_no_partial_mutation(self) -> None:
        before = int(self.db.fetch_one("SELECT COUNT(*) AS n FROM casting_plans WHERE chapter_id=?", (self.chapter_id,))["n"])
        response = self.client.post(
            f"/api/chapters/{self.chapter_id}/speaker-review/casting-plan-draft",
            json={
                "speaker_draft_id": self.draft["id"],
                "expected_draft_fingerprint": self.draft["input_fingerprint"],
                "expected_text_revision_id": self.draft["text_revision_id"],
                "decisions": self._full_decisions()[:1],
                "idempotency_key": "api-stage-incomplete",
            },
        )
        self.assertEqual(response.status_code, 400)
        after = int(self.db.fetch_one("SELECT COUNT(*) AS n FROM casting_plans WHERE chapter_id=?", (self.chapter_id,))["n"])
        self.assertEqual(before, after)

    def test_zero_target_empty_decisions_create_narrator_only_draft(self) -> None:
        content_path, digest = self.store.put_text(ZERO_TARGET_TEXT)
        with self.db.connect() as connection:
            connection.execute(
                """UPDATE text_revisions
                   SET content_path=?,content_sha256=?,lexical_sha256=?,char_count=?
                   WHERE id=?""",
                (
                    content_path,
                    digest,
                    lexical_sha256(ZERO_TARGET_TEXT),
                    len(ZERO_TARGET_TEXT),
                    self.revision_id,
                ),
            )
            connection.execute(
                "UPDATE chapters SET char_count=? WHERE id=?",
                (len(ZERO_TARGET_TEXT), self.chapter_id),
            )
        draft = generate_speaker_assignment_draft(
            self.db,
            self.store,
            self.config,
            chapter_id=self.chapter_id,
            provider=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("provider called")),
        )
        response = self.client.post(
            f"/api/chapters/{self.chapter_id}/speaker-review/casting-plan-draft",
            json={
                "speaker_draft_id": draft["id"],
                "expected_draft_fingerprint": draft["input_fingerprint"],
                "expected_text_revision_id": draft["text_revision_id"],
                "decisions": [],
                "idempotency_key": "api-zero-target",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["casting_plan_status"], "draft")
        self.assertFalse(data["approved"])
        self.assertEqual(data["approved_item_count"], 0)
        self.assertEqual(data["remaining_unreviewed_count"], 0)
        self.assertGreater(data["role_counts"]["narrator"], 0)
        self.assertEqual(data["role_counts"]["character"], 0)
        self.assertEqual(data["role_counts"]["unknown"], 0)

    def test_missing_draft_and_missing_character_classifications(self) -> None:
        missing_draft = self.client.post(
            f"/api/chapters/{self.chapter_id}/speaker-review/casting-plan-draft",
            json={
                "speaker_draft_id": 999999,
                "expected_draft_fingerprint": self.draft["input_fingerprint"],
                "expected_text_revision_id": self.draft["text_revision_id"],
                "decisions": self._full_decisions(),
                "idempotency_key": "api-missing-draft",
            },
        )
        self.assertEqual(missing_draft.status_code, 404)

        bad_decisions = self._full_decisions()
        bad_decisions[0] = {
            **bad_decisions[0],
            "speaker_type": "character",
            "character_id": 999999,
            "decision_source": "manual_character",
        }
        missing_character = self.client.post(
            f"/api/chapters/{self.chapter_id}/speaker-review/casting-plan-draft",
            json={
                "speaker_draft_id": self.draft["id"],
                "expected_draft_fingerprint": self.draft["input_fingerprint"],
                "expected_text_revision_id": self.draft["text_revision_id"],
                "decisions": bad_decisions,
                "idempotency_key": "api-missing-character",
            },
        )
        self.assertEqual(missing_character.status_code, 404)

    def test_stale_fingerprint_is_409_and_same_identity_reuses(self) -> None:
        success = self.client.post(
            f"/api/chapters/{self.chapter_id}/speaker-review/casting-plan-draft",
            json={
                "speaker_draft_id": self.draft["id"],
                "expected_draft_fingerprint": self.draft["input_fingerprint"],
                "expected_text_revision_id": self.draft["text_revision_id"],
                "decisions": self._full_decisions(),
                "idempotency_key": "api-stage-reuse",
            },
        )
        self.assertEqual(success.status_code, 200)
        reused = self.client.post(
            f"/api/chapters/{self.chapter_id}/speaker-review/casting-plan-draft",
            json={
                "speaker_draft_id": self.draft["id"],
                "expected_draft_fingerprint": self.draft["input_fingerprint"],
                "expected_text_revision_id": self.draft["text_revision_id"],
                "decisions": list(reversed(self._full_decisions())),
                "idempotency_key": "api-stage-reuse",
            },
        )
        self.assertEqual(reused.status_code, 200)
        self.assertTrue(reused.json()["idempotent_reused"])

        stale = self.client.post(
            f"/api/chapters/{self.chapter_id}/speaker-review/casting-plan-draft",
            json={
                "speaker_draft_id": self.draft["id"],
                "expected_draft_fingerprint": "0" * 64,
                "expected_text_revision_id": self.draft["text_revision_id"],
                "decisions": self._full_decisions(),
                "idempotency_key": "api-stage-stale",
            },
        )
        self.assertEqual(stale.status_code, 200)
        self.assertTrue(stale.json()["idempotent_reused"])


if __name__ == "__main__":
    unittest.main()
