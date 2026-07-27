from __future__ import annotations

import unittest

from story_audio.production_task_projection import project_production_task


def _row(number: int, state: str = "READY_TO_PREPARE", **overrides) -> dict:
    row = {
        "chapter_id": number + 1000,
        "chapter_number": number,
        "chapter_title": f"Chapter {number}",
        "state": state,
        "blockers": [],
        "latest_speaker_draft_id": 10 + number,
        "latest_speaker_draft_status": "approved",
    }
    row.update(overrides)
    return row


def _readiness(*rows: dict) -> dict:
    return {
        "scope": {
            "book_id": 1,
            "book_title": "Book",
            "from_chapter": rows[0]["chapter_number"],
            "to_chapter": rows[-1]["chapter_number"],
            "chapter_count": len(rows),
        },
        "summary": {},
        "chapters": list(rows),
    }


class ProductionTaskProjectionTests(unittest.TestCase):
    def test_canonical_chapter_precedence(self) -> None:
        cases = (
            (
                _row(1, "TEXT_BLOCKED", latest_speaker_draft_id=None, blockers=["bad text"]),
                "REVIEW_TEXT",
            ),
            (
                _row(1, latest_speaker_draft_id=None),
                "CREATE_SPEAKER_PROPOSAL",
            ),
            (
                _row(
                    1,
                    latest_speaker_draft_status="generated",
                    speaker_review={"remaining_unreviewed_count": 2, "invalid_count": 0},
                ),
                "RESOLVE_SPEAKER",
            ),
            (
                _row(
                    1,
                    latest_speaker_draft_status="generated",
                    speaker_review={"remaining_unreviewed_count": 0, "invalid_count": 1},
                ),
                "APPROVE_SPEAKER_DRAFT",
            ),
            (_row(1, "VOICE_BLOCKED", blockers=["missing voice"]), "ASSIGN_VOICE"),
            (_row(1, "CASTING_REVIEW", blockers=["plan draft"]), "REVIEW_CASTING_PLAN"),
        )
        for row, expected in cases:
            with self.subTest(expected=expected):
                projection = project_production_task({"readiness": _readiness(row)})
                self.assertEqual(projection["task_type"], expected)
                self.assertEqual(projection["task_scope"], "chapter")
                self.assertEqual(projection["affected_chapter"]["number"], 1)

    def test_ready_range_is_the_only_prepare_gate(self) -> None:
        projection = project_production_task(
            {"readiness": _readiness(_row(1), _row(2))}
        )
        self.assertEqual(projection["task_type"], "PREPARE_RANGE")
        self.assertEqual(projection["task_scope"], "range")
        self.assertEqual(projection["primary_action"]["key"], "PREPARE_RANGE")
        self.assertTrue(all(item["status"] == "ready" for item in projection["chapter_queue"]))

    def test_blocked_chapter_prevents_range_prepare_even_when_another_is_ready(self) -> None:
        blocked = _row(
            1,
            latest_speaker_draft_id=None,
            blockers=["missing speaker proposal"],
        )
        ready = _row(2)
        projection = project_production_task({"readiness": _readiness(blocked, ready)})
        self.assertEqual(projection["task_type"], "CREATE_SPEAKER_PROPOSAL")
        self.assertNotEqual(projection["primary_action"]["key"], "PREPARE_RANGE")
        self.assertEqual(projection["affected_chapter"]["number"], 1)

    def test_exact_prepared_job_is_a_separate_range_task(self) -> None:
        projection = project_production_task(
            {
                "readiness": _readiness(_row(1), _row(2)),
                "range_jobs": [
                    {
                        "id": 44,
                        "status": "prepared",
                        "chapter_count": 2,
                        "all_chapters_match": True,
                    }
                ],
            }
        )
        self.assertEqual(projection["task_type"], "START_RENDER_RANGE")
        self.assertEqual(projection["primary_action"]["key"], "START_RENDER_RANGE")
        self.assertIn("job:44", projection["task_key"])

    def test_multiple_exact_jobs_never_offer_start_or_prepare(self) -> None:
        projection = project_production_task(
            {
                "readiness": _readiness(_row(1), _row(2)),
                "range_jobs": [
                    {
                        "id": 44,
                        "status": "prepared",
                        "chapter_count": 2,
                        "all_chapters_match": True,
                    },
                    {
                        "id": 45,
                        "status": "scheduled",
                        "chapter_count": 2,
                        "all_chapters_match": True,
                    },
                ],
            }
        )

        self.assertEqual(projection["task_type"], "RECOVER_RENDER")
        self.assertIsNone(projection["primary_action"])
        self.assertIn(
            "blocker_code:MULTIPLE_EXACT_RANGE_JOBS",
            projection["technical_details"],
        )

    def test_cancelled_job_does_not_block_a_new_prepare(self) -> None:
        projection = project_production_task(
            {
                "readiness": _readiness(_row(1), _row(2)),
                "range_jobs": [
                    {
                        "id": 44,
                        "status": "cancelled",
                        "chapter_count": 2,
                        "all_chapters_match": True,
                    }
                ],
            }
        )

        self.assertEqual(projection["task_type"], "PREPARE_RANGE")
        self.assertEqual(projection["primary_action"]["key"], "PREPARE_RANGE")

    def test_completed_historical_job_does_not_block_new_prepare(self) -> None:
        projection = project_production_task(
            {
                "readiness": _readiness(_row(1), _row(2)),
                "range_jobs": [
                    {
                        "id": 43,
                        "status": "completed",
                        "chapter_count": 2,
                        "all_chapters_match": True,
                    }
                ],
            }
        )
        self.assertEqual(projection["task_type"], "PREPARE_RANGE")

    def test_monitor_and_recovery_are_distinct(self) -> None:
        for status, expected in (
            ("running", "MONITOR_RENDER"),
            ("paused", "RECOVER_RENDER"),
            ("failed", "RECOVER_RENDER"),
        ):
            with self.subTest(status=status):
                projection = project_production_task(
                    {
                        "readiness": _readiness(_row(1), _row(2)),
                        "range_jobs": [
                            {
                                "id": 45,
                                "status": status,
                                "chapter_count": 2,
                                "all_chapters_match": True,
                            }
                        ],
                    }
                )
                self.assertEqual(projection["task_type"], expected)

    def test_human_qa_precedes_prepare_and_complete_is_quiet(self) -> None:
        qa = _row(1, "RENDERED_NOT_QA", blockers=["audio awaits QA"])
        projection = project_production_task({"readiness": _readiness(qa)})
        self.assertEqual(projection["task_type"], "HUMAN_QA")
        self.assertEqual(projection["user_stage"], 5)
        self.assertIsNone(projection["primary_action"])
        self.assertEqual(projection["chapter_queue"][0]["status"], "current")

        complete = _row(1, "COMPLETE")
        projection = project_production_task({"readiness": _readiness(complete)})
        self.assertEqual(projection["task_type"], "COMPLETE")
        self.assertIsNone(projection["primary_action"])
        self.assertEqual(projection["task_scope"], "range")


if __name__ == "__main__":
    unittest.main()
