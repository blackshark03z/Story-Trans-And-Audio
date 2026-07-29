from __future__ import annotations

from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from story_audio.production_commands import ProductionCommandMutation
from tests.base import IsolatedTestCase


class ProductionCommandApiTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._multipart = patch(
            "fastapi.dependencies.utils.ensure_multipart_is_installed",
            lambda: None,
        )
        self._multipart.start()
        from story_audio.api import app

        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._multipart.stop()
        super().tearDown()

    @staticmethod
    def projection(_scope):
        return (
            {
                "canonical_task": {
                    "task_key": "range:next",
                    "task_type": "REVIEW_VOICE_MAP",
                }
            },
            {"schema": "story-audio-production-preflight/v1"},
        )

    def test_gateway_returns_common_envelope_after_executor(self) -> None:
        captured = {}

        def executor(command, *, authorization_header):
            captured["command"] = command
            captured["authorization"] = authorization_header
            return lambda: ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({"chapter_id": 7},),
                operator_message="Đã áp dụng.",
            )

        with (
            patch("story_audio.api._production_command_executor", executor),
            patch("story_audio.api._project_production_command", self.projection),
        ):
            response = self.client.post(
                "/api/production/commands",
                headers={"Authorization": "Bearer fake-test-token"},
                json={
                    "command_type": "APPROVE_SPEAKER_DRAFT",
                    "idempotency_key": "speaker-draft-0007",
                    "scope": {"chapter": {"id": 7}},
                    "payload": {"chapter_id": 7, "draft_id": 11},
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["outcome"], "APPLIED")
        self.assertEqual(payload["applied_count"], 1)
        self.assertEqual(
            payload["resulting_task_projection"]["canonical_task"]["task_key"],
            "range:next",
        )
        self.assertEqual(captured["authorization"], "Bearer fake-test-token")

    def test_domain_rejection_still_returns_authoritative_envelope(self) -> None:
        def executor(_command, *, authorization_header):
            del authorization_header

            def rejected():
                raise ValueError("Draft is stale.")

            return rejected

        with (
            patch("story_audio.api._production_command_executor", executor),
            patch("story_audio.api._project_production_command", self.projection),
        ):
            response = self.client.post(
                "/api/production/commands",
                json={
                    "command_type": "APPROVE_SPEAKER_DRAFT",
                    "idempotency_key": "speaker-draft-stale",
                    "scope": {"chapter": {"id": 7}},
                    "payload": {"chapter_id": 7, "draft_id": 11},
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["outcome"], "REJECTED")
        self.assertEqual(payload["applied_count"], 0)
        self.assertEqual(payload["failed_count"], 1)
        self.assertIn("stale", payload["operator_message"])

    def test_invalid_contract_is_rejected_before_executor(self) -> None:
        for command_type, idempotency_key in (
            ("x", "short"),
            ("START_RENDER", "!!!!!!!!"),
        ):
            response = self.client.post(
                "/api/production/commands",
                json={
                    "command_type": command_type,
                    "idempotency_key": idempotency_key,
                    "scope": {},
                },
            )
            self.assertEqual(response.status_code, 400)

    def test_voice_assignment_batch_reports_partial_result_in_common_envelope(self) -> None:
        command = {
            "command_type": "SAVE_VOICE_ASSIGNMENTS",
            "idempotency_key": "voice-assignment-batch-0001",
            "scope": {"chapter": {"id": 7}},
            "payload": {
                "book_id": 2,
                "profile": {
                    "narrator_voice_id": "narrator",
                    "male_dialogue_voice_id": "male",
                    "female_dialogue_voice_id": "female",
                    "unknown_fallback": "narrator",
                    "unknown_voice_id": None,
                },
                "assignments": [
                    {
                        "character_id": 11,
                        "gender": "male",
                        "voice_override_id": "male",
                    },
                    {
                        "character_id": 12,
                        "gender": "female",
                        "voice_override_id": "female",
                    },
                ],
            },
        }

        def save_character(character_id, _request):
            if character_id == 12:
                raise HTTPException(400, "Voice is unavailable")
            return {"character_id": character_id, "voice_override_id": "male"}

        with (
            patch("story_audio.api._project_production_command", self.projection),
            patch(
                "story_audio.api.write_book_voice_profile",
                return_value={"config_version": 3},
            ),
            patch(
                "story_audio.api.write_character_voice_override",
                side_effect=save_character,
            ),
        ):
            response = self.client.post("/api/production/commands", json=command)

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["outcome"], "PARTIAL")
        self.assertEqual(result["submitted_count"], 3)
        self.assertEqual(result["applied_count"], 2)
        self.assertEqual(result["failed_count"], 1)
        self.assertEqual(result["failed_items"][0]["character_id"], 12)
        self.assertIn("unavailable", result["failed_items"][0]["reason"])

    def test_range_voice_override_uses_common_command_envelope(self) -> None:
        command = {
            "command_type": "SET_RANGE_VOICE_OVERRIDE",
            "idempotency_key": "range-voice-override-0001",
            "scope": {"range": {"book_id": 1, "from_chapter": 5, "to_chapter": 7}},
            "payload": {
                "book_id": 1,
                "speaker_key": "narrator",
                "voice_id": "male",
            },
        }
        applied = {
            "operation": "set",
            "speaker_key": "narrator",
            "voice_id": "male",
            "chapter_count": 3,
            "reused_count": 0,
            "applied": [
                {"chapter_id": 5, "chapter_number": 5, "casting_plan_id": 51, "plan_revision": 2, "reused": False},
                {"chapter_id": 6, "chapter_number": 6, "casting_plan_id": 61, "plan_revision": 2, "reused": False},
                {"chapter_id": 7, "chapter_number": 7, "casting_plan_id": 71, "plan_revision": 2, "reused": False},
            ],
        }

        with (
            patch("story_audio.api._project_production_command", self.projection),
            patch("story_audio.api._load_voice_catalog", return_value=object()),
            patch("story_audio.api.apply_chapter_voice_override", return_value=applied) as save,
        ):
            response = self.client.post("/api/production/commands", json=command)

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["outcome"], "APPLIED")
        self.assertEqual(result["submitted_count"], 3)
        self.assertEqual(result["applied_count"], 3)
        self.assertEqual(result["applied_items"][0]["speaker_key"], "narrator")
        save.assert_called_once()
        self.assertEqual(save.call_args.kwargs["idempotency_key"], "range-voice-override-0001")


if __name__ == "__main__":
    import unittest

    unittest.main()
