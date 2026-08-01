from __future__ import annotations

from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from story_audio.production_commands import ProductionCommandMutation
from story_audio.speaker_review_suggestions import SpeakerReviewSuggestionError
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

    def test_chapter_voice_override_rejects_range_with_vietnamese_guidance(self) -> None:
        with patch("story_audio.api._project_production_command", self.projection):
            response = self.client.post(
                "/api/production/commands",
                json={
                    "command_type": "SET_CHAPTER_VOICE_OVERRIDE",
                    "idempotency_key": "chapter-voice-stale-range-0001",
                    "scope": {
                        "range": {
                            "book_id": 1,
                            "from_chapter": 1,
                            "to_chapter": 10,
                        }
                    },
                    "payload": {
                        "book_id": 1,
                        "speaker_key": "narrator",
                        "voice_id": "male",
                    },
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["outcome"], "REJECTED")
        self.assertEqual(payload["applied_count"], 0)
        self.assertIn("chỉ áp dụng cho đúng một chương", payload["operator_message"])
        self.assertIn("Chương 1-10", payload["operator_message"])

    def test_create_character_uses_common_command_envelope(self) -> None:
        command = {
            "command_type": "CREATE_CHARACTER",
            "idempotency_key": "create-character-0001",
            "scope": {"range": {"book_id": 1, "from_chapter": 1, "to_chapter": 10}},
            "payload": {
                "book_id": 1,
                "display_name": "Gate Commander",
                "aliases": ["gate chief"],
                "gender": "unknown",
                "role": "unknown",
            },
        }
        created = {
            "character": {"id": 31, "display_name": "Gate Commander"},
            "created": True,
            "reused": False,
            "aliases": [{"alias": "gate chief", "alias_id": 9}],
        }

        with (
            patch("story_audio.api._project_production_command", self.projection),
            patch("story_audio.api.create_assignment_character", return_value=created) as create,
        ):
            response = self.client.post("/api/production/commands", json=command)

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["outcome"], "APPLIED")
        self.assertEqual(result["applied_items"][0]["type"], "character")
        self.assertEqual(result["applied_items"][0]["character_id"], 31)
        create.assert_called_once()
        self.assertEqual(create.call_args.kwargs["idempotency_key"], "create-character-0001")

    def test_map_speaker_to_character_uses_common_command_envelope(self) -> None:
        command = {
            "command_type": "MAP_SPEAKER_TO_CHARACTER",
            "idempotency_key": "map-speaker-character-0001",
            "scope": {"range": {"book_id": 1, "from_chapter": 2, "to_chapter": 4}},
            "payload": {
                "book_id": 1,
                "speaker_key": "unresolved-dialogue:1002:u0002-deadbeef0000",
                "character_id": 31,
                "aliases": ["gate chief"],
            },
        }
        mapped = {
            "operation": "map",
            "speaker_key": "unresolved-dialogue:1002:u0002-deadbeef0000",
            "character_id": 31,
            "utterance_count": 1,
            "applied": [
                {
                    "chapter_id": 1002,
                    "chapter_number": 2,
                    "casting_plan_id": 42,
                    "plan_revision": 2,
                    "utterance_ids": ["u0002-deadbeef0000"],
                    "reused": False,
                }
            ],
        }

        with (
            patch("story_audio.api._project_production_command", self.projection),
            patch("story_audio.api._load_voice_catalog", return_value=object()),
            patch("story_audio.api.apply_speaker_character_mapping", return_value=mapped) as map_speaker,
        ):
            response = self.client.post("/api/production/commands", json=command)

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["outcome"], "APPLIED")
        self.assertEqual(result["submitted_count"], 1)
        self.assertEqual(result["applied_items"][0]["operation"], "map")
        self.assertEqual(result["applied_items"][0]["character_id"], 31)
        map_speaker.assert_called_once()
        self.assertEqual(map_speaker.call_args.kwargs["from_chapter"], 2)
        self.assertEqual(map_speaker.call_args.kwargs["to_chapter"], 4)
        self.assertEqual(map_speaker.call_args.kwargs["idempotency_key"], "map-speaker-character-0001")

    def test_generate_speaker_suggestions_uses_common_command_envelope(self) -> None:
        command = {
            "command_type": "GENERATE_SPEAKER_SUGGESTIONS",
            "idempotency_key": "speaker-review-analysis-0001",
            "scope": {
                "range": {
                    "book_id": 1,
                    "from_chapter": 2,
                    "to_chapter": 10,
                    "skip_completed": True,
                }
            },
            "payload": {
                "book_id": 1,
                "from_chapter": 2,
                "to_chapter": 10,
                "skip_completed": True,
                "unresolved_keys": ["unresolved-dialogue:1:u0002-a"],
                "expected_input_fingerprint": "abc123",
            },
        }
        analysis = {
            "analysis_run_id": "gsr-abc",
            "input_fingerprint": "abc123",
            "target_count": 1,
            "chunk_count": 1,
            "request_count": 1,
            "cache_hit_count": 0,
            "cache_miss_count": 1,
            "reused": False,
            "summary": {"high_confidence": 1},
        }

        with (
            patch("story_audio.api._project_production_command", self.projection),
            patch(
                "story_audio.api._speaker_review_command_context",
                return_value=(
                    {
                        "book_id": 1,
                        "from_chapter": 2,
                        "to_chapter": 10,
                        "skip_completed": True,
                    },
                    object(),
                    None,
                    {"rows": []},
                ),
            ) as context,
            patch(
                "story_audio.api.generate_speaker_review_suggestions",
                return_value=analysis,
            ) as generate,
        ):
            response = self.client.post("/api/production/commands", json=command)

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["outcome"], "APPLIED")
        self.assertEqual(result["applied_items"][0]["analysis_run_id"], "gsr-abc")
        self.assertEqual(result["applied_items"][0]["request_count"], 1)
        context.assert_called_once()
        generate.assert_called_once()
        self.assertEqual(
            generate.call_args.kwargs["unresolved_keys"],
            ["unresolved-dialogue:1:u0002-a"],
        )
        self.assertEqual(generate.call_args.kwargs["expected_input_fingerprint"], "abc123")

    def test_accept_speaker_suggestion_does_not_forward_scope_filter(self) -> None:
        command = {
            "command_type": "EDIT_AND_ACCEPT_SPEAKER_SUGGESTION",
            "idempotency_key": "speaker-review-accept-0001",
            "scope": {
                "range": {
                    "book_id": 1,
                    "from_chapter": 2,
                    "to_chapter": 10,
                    "skip_completed": False,
                }
            },
            "payload": {
                "book_id": 1,
                "from_chapter": 2,
                "to_chapter": 10,
                "skip_completed": False,
                "analysis_run_id": "gsr-source-a",
                "unresolved_key": "unresolved-dialogue:1:u0002-a",
                "reviewer_payload": {
                    "proposed_resolution": "EXISTING_CHARACTER",
                    "existing_character_id": 25,
                    "voice_mode": "keep",
                },
            },
        }
        context = (
            {
                "book_id": 1,
                "from_chapter": 2,
                "to_chapter": 10,
                "skip_completed": False,
            },
            object(),
            None,
            {"rows": []},
        )
        with (
            patch("story_audio.api._project_production_command", self.projection),
            patch(
                "story_audio.api._speaker_review_command_context",
                return_value=context,
            ),
            patch(
                "story_audio.api.accept_speaker_review_suggestion",
                return_value={
                    "applied": {"chapter_count": 1},
                    "review": {"decision": "EDITED_AND_ACCEPTED"},
                },
            ) as accept,
        ):
            response = self.client.post("/api/production/commands", json=command)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["outcome"], "APPLIED")
        accept.assert_called_once()
        self.assertNotIn("skip_completed", accept.call_args.kwargs)
        self.assertEqual(accept.call_args.kwargs["book_id"], 1)
        self.assertEqual(accept.call_args.kwargs["from_chapter"], 2)
        self.assertEqual(accept.call_args.kwargs["to_chapter"], 10)

    def test_replacement_and_uncertain_commands_record_reversible_decisions(self) -> None:
        context = (
            {
                "book_id": 1,
                "from_chapter": 2,
                "to_chapter": 10,
                "skip_completed": True,
            },
            object(),
            None,
            {"rows": []},
        )
        cases = (
            (
                "CREATE_SPEAKER_REPLACEMENT_DECISION",
                "speaker-review-replacement-0001",
                "REPLACEMENT_DRAFT",
                "speaker_review_replacement_draft",
            ),
            (
                "MARK_SPEAKER_SUGGESTION_UNCERTAIN",
                "speaker-review-uncertain-0001",
                "MARKED_UNCERTAIN",
                "speaker_review_uncertain",
            ),
        )
        for command_type, idempotency_key, decision, item_type in cases:
            with self.subTest(command_type=command_type):
                with (
                    patch("story_audio.api._project_production_command", self.projection),
                    patch(
                        "story_audio.api._speaker_review_command_context",
                        return_value=context,
                    ),
                    patch(
                        "story_audio.api.record_speaker_suggestion_decision",
                        return_value={"decision": {"decision": decision}, "reused": False},
                    ) as record,
                ):
                    response = self.client.post(
                        "/api/production/commands",
                        json={
                            "command_type": command_type,
                            "idempotency_key": idempotency_key,
                            "scope": {
                                "range": {
                                    "book_id": 1,
                                    "from_chapter": 2,
                                    "to_chapter": 10,
                                    "skip_completed": True,
                                }
                            },
                            "payload": {
                                "book_id": 1,
                                "from_chapter": 2,
                                "to_chapter": 10,
                                "skip_completed": True,
                                "analysis_run_id": "gsr-source-a",
                                "unresolved_key": "unresolved-dialogue:1:u0002-a",
                                "reviewer_payload": {"note": "operator decision"},
                            },
                        },
                    )

                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result["outcome"], "APPLIED")
                self.assertEqual(result["applied_items"][0]["type"], item_type)
                record.assert_called_once()
                self.assertEqual(record.call_args.kwargs["decision"], decision)
                self.assertEqual(
                    record.call_args.kwargs["idempotency_key"],
                    idempotency_key,
                )

    def test_approved_speaker_correction_requires_approved_source(self) -> None:
        command = {
            "command_type": "CORRECT_APPROVED_SPEAKER_SUGGESTION",
            "idempotency_key": "speaker-review-correction-0001",
            "scope": {
                "range": {
                    "book_id": 1,
                    "from_chapter": 2,
                    "to_chapter": 10,
                    "skip_completed": True,
                }
            },
            "payload": {
                "book_id": 1,
                "from_chapter": 2,
                "to_chapter": 10,
                "skip_completed": True,
                "analysis_run_id": "gsr-source-a",
                "unresolved_key": "unresolved-dialogue:1:u0002-a",
                "reviewer_payload": {
                    "proposed_resolution": "EXISTING_CHARACTER",
                    "existing_character_id": 25,
                    "voice_mode": "keep",
                },
            },
        }
        context = (
            {
                "book_id": 1,
                "from_chapter": 2,
                "to_chapter": 10,
                "skip_completed": True,
            },
            object(),
            None,
            {"rows": []},
        )
        with (
            patch("story_audio.api._project_production_command", self.projection),
            patch(
                "story_audio.api._speaker_review_command_context",
                return_value=context,
            ),
            patch(
                "story_audio.api.accept_speaker_review_suggestion",
                return_value={"applied": {"chapter_count": 1}, "review": {"decision": "CORRECTED"}},
            ) as correct,
        ):
            response = self.client.post("/api/production/commands", json=command)

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["outcome"], "APPLIED")
        self.assertEqual(result["applied_items"][0]["type"], "speaker_review_correction")
        self.assertEqual(correct.call_args.kwargs["decision_override"], "CORRECTED")
        self.assertTrue(correct.call_args.kwargs["require_approved"])
        self.assertNotIn("skip_completed", correct.call_args.kwargs)

    def test_note_and_safe_restore_commands_use_durable_gateway(self) -> None:
        context = (
            {
                "book_id": 1,
                "from_chapter": 2,
                "to_chapter": 10,
                "skip_completed": True,
            },
            object(),
            None,
            {"rows": []},
        )
        common = {
            "book_id": 1,
            "from_chapter": 2,
            "to_chapter": 10,
            "skip_completed": True,
            "analysis_run_id": "gsr-source-a",
            "unresolved_key": "unresolved-dialogue:1:u0002-a",
            "reviewer_payload": {"note": "operator note"},
        }
        for command_type, key, function_name, item_type in (
            (
                "ADD_SPEAKER_REVIEW_NOTE",
                "speaker-review-note-0001",
                "record_speaker_suggestion_note",
                "speaker_review_note",
            ),
            (
                "RESTORE_SPEAKER_SUGGESTION_PENDING",
                "speaker-review-restore-0001",
                "restore_speaker_suggestion_pending",
                "speaker_review_restored_pending",
            ),
        ):
            with self.subTest(command_type=command_type):
                with (
                    patch("story_audio.api._project_production_command", self.projection),
                    patch(
                        "story_audio.api._speaker_review_command_context",
                        return_value=context,
                    ),
                    patch(
                        f"story_audio.api.{function_name}",
                        return_value={"reused": False},
                    ) as action,
                ):
                    response = self.client.post(
                        "/api/production/commands",
                        json={
                            "command_type": command_type,
                            "idempotency_key": key,
                            "scope": {
                                "range": {
                                    "book_id": 1,
                                    "from_chapter": 2,
                                    "to_chapter": 10,
                                    "skip_completed": True,
                                }
                            },
                            "payload": common,
                        },
                    )
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result["outcome"], "APPLIED")
                self.assertEqual(result["applied_items"][0]["type"], item_type)
                action.assert_called_once()
                self.assertEqual(action.call_args.kwargs["idempotency_key"], key)

    def test_multi_run_speaker_review_batch_uses_atomic_items_adapter(self) -> None:
        items = [
            {
                "analysis_run_id": "gsr-source-a",
                "unresolved_key": "unresolved-dialogue:1:u0002-a",
            },
            {
                "analysis_run_id": "gsr-source-b",
                "unresolved_key": "unresolved-dialogue:2:u0003-b",
            },
        ]
        command = {
            "command_type": "APPROVE_SPEAKER_REVIEW_BATCH",
            "idempotency_key": "speaker-review-batch-items-0001",
            "scope": {
                "range": {
                    "book_id": 1,
                    "from_chapter": 2,
                    "to_chapter": 10,
                    "skip_completed": True,
                }
            },
            "payload": {
                "book_id": 1,
                "from_chapter": 2,
                "to_chapter": 10,
                "skip_completed": True,
                "items": items,
            },
        }
        context = (
            {
                "book_id": 1,
                "from_chapter": 2,
                "to_chapter": 10,
                "skip_completed": True,
            },
            object(),
            None,
            {"rows": []},
        )
        with (
            patch("story_audio.api._project_production_command", self.projection),
            patch(
                "story_audio.api._speaker_review_command_context",
                return_value=context,
            ),
            patch(
                "story_audio.api.approve_speaker_review_batch_items",
                return_value={"submitted_count": 2, "items": items},
            ) as approve,
        ):
            response = self.client.post("/api/production/commands", json=command)

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["outcome"], "APPLIED")
        self.assertEqual(result["submitted_count"], 2)
        self.assertEqual(
            {item["analysis_run_id"] for item in result["applied_items"]},
            {"gsr-source-a", "gsr-source-b"},
        )
        approve.assert_called_once()
        self.assertNotIn("skip_completed", approve.call_args.kwargs)
        self.assertEqual(approve.call_args.kwargs["items"], items)
        self.assertEqual(
            approve.call_args.kwargs["idempotency_key"],
            "speaker-review-batch-items-0001",
        )

    def test_speaker_suggestion_stale_scope_returns_rejected_envelope(self) -> None:
        command = {
            "command_type": "GENERATE_SPEAKER_SUGGESTIONS",
            "idempotency_key": "speaker-review-stale-0001",
            "scope": {
                "range": {
                    "book_id": 1,
                    "from_chapter": 2,
                    "to_chapter": 10,
                    "skip_completed": True,
                }
            },
            "payload": {
                "book_id": 1,
                "from_chapter": 2,
                "to_chapter": 10,
                "skip_completed": True,
                "unresolved_keys": ["unresolved-dialogue:1:u0002-a"],
                "expected_input_fingerprint": "old",
            },
        }

        with (
            patch("story_audio.api._project_production_command", self.projection),
            patch(
                "story_audio.api._speaker_review_command_context",
                return_value=(
                    {
                        "book_id": 1,
                        "from_chapter": 2,
                        "to_chapter": 10,
                        "skip_completed": True,
                    },
                    object(),
                    None,
                    {"rows": []},
                ),
            ),
            patch(
                "story_audio.api.generate_speaker_review_suggestions",
                side_effect=SpeakerReviewSuggestionError(
                    "Speaker suggestion input is stale"
                ),
            ),
        ):
            response = self.client.post("/api/production/commands", json=command)

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["outcome"], "REJECTED")
        self.assertIn("stale", result["operator_message"])


if __name__ == "__main__":
    import unittest

    unittest.main()
