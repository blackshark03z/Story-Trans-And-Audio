from __future__ import annotations

import unittest

from story_audio.production_commands import (
    COMMAND_SCHEMA,
    ProductionCommandError,
    ProductionCommandMutation,
    ProductionCommandService,
)


class ProductionCommandServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project_calls = []

        def projector(scope):
            self.project_calls.append(dict(scope))
            return (
                {"canonical_task": {"task_key": "next:2", "task_type": "REVIEW_VOICE_MAP"}},
                {"schema": "story-audio-production-preflight/v1", "data_readiness": {"ready": True}},
            )

        self.service = ProductionCommandService(projector)

    def test_applied_envelope_contains_authoritative_projections_and_tokens(self) -> None:
        calls = []
        result = self.service.execute(
            command_type="APPROVE_SPEAKER_DRAFTS",
            idempotency_key="speaker-batch-0001",
            scope={"range": {"book_id": 1, "from_chapter": 10, "to_chapter": 16}},
            executor=lambda: calls.append("executed") or ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=7,
                applied_items=tuple({"chapter_number": value} for value in range(10, 17)),
                operator_message="Đã duyệt 7/7 chương.",
            ),
        )
        self.assertEqual(calls, ["executed"])
        self.assertEqual(result["schema"], COMMAND_SCHEMA)
        self.assertEqual(result["outcome"], "APPLIED")
        self.assertEqual(result["submitted_count"], 7)
        self.assertEqual(result["applied_count"], 7)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(
            result["resulting_task_projection"]["canonical_task"]["task_key"],
            "next:2",
        )
        self.assertEqual(len(result["state_tokens"]["task_projection"]), 64)
        self.assertEqual(len(result["state_tokens"]["preflight"]), 64)
        self.assertEqual(len(self.project_calls), 1)

    def test_partial_preserves_deterministic_applied_and_failed_items(self) -> None:
        result = self.service.execute(
            command_type="APPROVE_CASTING_PLANS",
            idempotency_key="casting-batch-0001",
            scope={"range": {"book_id": 1, "from_chapter": 1, "to_chapter": 3}},
            executor=lambda: ProductionCommandMutation(
                outcome="PARTIAL",
                submitted_count=3,
                applied_items=({"chapter_number": 1}, {"chapter_number": 2}),
                failed_items=({"chapter_number": 3, "reason": "Plan stale."},),
                operator_message="Đã duyệt 2/3 chương.",
            ),
        )
        self.assertEqual(result["applied_count"], 2)
        self.assertEqual(result["failed_count"], 1)
        self.assertEqual(result["failed_items"][0]["chapter_number"], 3)

    def test_async_command_requires_existing_durable_reference(self) -> None:
        with self.assertRaises(ProductionCommandError):
            ProductionCommandMutation(
                outcome="ACCEPTED",
                submitted_count=1,
                applied_items=({"job_id": 25},),
            )
        result = self.service.execute(
            command_type="START_RENDER",
            idempotency_key="start-job-0025",
            scope={"job": {"id": 25}},
            executor=lambda: ProductionCommandMutation(
                outcome="ACCEPTED",
                submitted_count=1,
                applied_items=({"job_id": 25},),
                operator_message="Đã nhận lệnh.",
                asynchronous_reference={
                    "type": "job",
                    "id": 25,
                    "status": "queued",
                    "status_url": "/api/jobs/25",
                },
            ),
        )
        self.assertEqual(result["outcome"], "ACCEPTED")
        self.assertEqual(result["asynchronous_reference"]["id"], 25)

    def test_same_idempotency_key_has_same_command_id(self) -> None:
        def execute():
            return ProductionCommandMutation(
                outcome="APPLIED",
                submitted_count=1,
                applied_items=({"chapter_id": 9},),
            )

        kwargs = {
            "command_type": "HUMAN_QA_ACCEPT",
            "idempotency_key": "qa-artifact-0099",
            "scope": {"chapter": {"id": 9}, "artifact": {"id": 99}},
            "executor": execute,
        }
        first = self.service.execute(**kwargs)
        second = self.service.execute(**kwargs)
        self.assertEqual(first["command_id"], second["command_id"])
        self.assertEqual(first["idempotency_key"], second["idempotency_key"])

    def test_invalid_scope_and_key_fail_closed_before_execution(self) -> None:
        called = []
        for key, scope in (
            ("short", {"chapter": {"id": 1}}),
            ("valid-key-0001", {"owner_token": "forbidden"}),
        ):
            with self.assertRaises(ProductionCommandError):
                self.service.execute(
                    command_type="HUMAN_QA_ACCEPT",
                    idempotency_key=key,
                    scope=scope,
                    executor=lambda: called.append(True),
                )
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
