from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from story_audio.db import utcnow
from story_audio.production_task_projection import _qa_replacement_context
from story_audio.production_task_projection import get_production_task_projection
from story_audio.production_task_projection import project_production_task
from tests.base import IsolatedTestCase
from tests.test_active_output import seed_active_output


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
    def assert_typed_section(self, projection: dict, expected: str | None) -> None:
        task = projection["canonical_task"]
        sections = ("speaker", "casting", "range_prepare", "render", "qa", "repair")
        self.assertEqual(task["task_type"], projection["task_type"])
        self.assertEqual(task["task_key"], projection["task_key"])
        for section in sections:
            if section == expected:
                self.assertIsInstance(task[section], dict)
            else:
                self.assertIsNone(task[section])

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
            (
                _row(1, "REPAIR_REQUIRED", blockers=["needs fixes"], active_artifact_id=39),
                "REPAIR_REQUIRED",
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
                expected_section = (
                    "speaker"
                    if expected in {
                        "CREATE_SPEAKER_PROPOSAL",
                        "RESOLVE_SPEAKER",
                        "APPROVE_SPEAKER_DRAFT",
                    }
                    else "casting" if expected in {"ASSIGN_VOICE", "REVIEW_CASTING_PLAN"} else None
                )
                if expected == "REPAIR_REQUIRED":
                    expected_section = "repair"
                self.assert_typed_section(projection, expected_section)

    def test_mixed_range_uses_workflow_priority_before_chapter_order(self) -> None:
        qa = _row(
            1,
            "RENDERED_NOT_QA",
            blockers=["audio awaits QA"],
            active_artifact_id=39,
            active_output_job_id=14,
        )
        speaker = _row(
            3,
            "SPEAKER_EXCEPTIONS",
            latest_speaker_draft_status="generated",
            speaker_review={
                "remaining_unreviewed_count": 0,
                "invalid_count": 1,
            },
        )

        projection = project_production_task(
            {
                "readiness": _readiness(qa, _row(2), speaker),
                "inspected_chapter_id": qa["chapter_id"],
            }
        )

        self.assertEqual(projection["task_type"], "APPROVE_SPEAKER_DRAFT")
        self.assertEqual(projection["affected_chapter"]["number"], 3)
        self.assert_typed_section(projection, "speaker")
        self.assertEqual(projection["inspected_chapter"]["number"], 1)
        self.assertTrue(projection["inspection_summary"]["read_only"])
        self.assertEqual(projection["inspection_summary"]["task_type"], "HUMAN_QA")
        self.assertNotIn("primary_action", projection["inspection_summary"])
        queue = {item["chapter_number"]: item for item in projection["chapter_queue"]}
        self.assertTrue(queue[3]["canonical_task"])
        self.assertTrue(queue[1]["inspected"])

    def test_render_range_task_precedes_pending_qa(self) -> None:
        qa = _row(1, "RENDERED_NOT_QA", active_artifact_id=39)
        ready = _row(2)
        projection = project_production_task(
            {
                "readiness": _readiness(qa, ready),
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
        self.assertEqual(projection["canonical_task"]["render"]["job_id"], 44)
        self.assert_typed_section(projection, "render")

    def test_human_qa_keeps_current_target_when_comparison_is_available(self) -> None:
        qa = _row(
            1,
            "RENDERED_NOT_QA",
            active_artifact_id=117,
            active_output_job_id=33,
            artifact_duration_ms=334080,
            artifact_size_bytes=5407866,
            qa_replacement=True,
            qa_previous_artifact={"artifact_id": 114, "duration_ms": 324800},
            qa_repair_goals={"repeated_words": True, "global_speed_target": 1.25},
        )

        projection = project_production_task({"readiness": _readiness(qa)})

        details = projection["canonical_task"]["qa"]
        self.assertEqual(details["artifact_id"], 117)
        self.assertTrue(details["replacement"])
        self.assertEqual(details["previous_artifact"]["artifact_id"], 114)
        self.assertTrue(details["repair_goals"]["repeated_words"])

    def test_ready_range_is_the_only_prepare_gate(self) -> None:
        projection = project_production_task(
            {"readiness": _readiness(_row(1), _row(2))}
        )
        self.assertEqual(projection["task_type"], "PREPARE_RANGE")
        self.assertEqual(projection["task_scope"], "range")
        self.assertEqual(projection["primary_action"]["key"], "PREPARE_RANGE")
        self.assertTrue(all(item["status"] == "ready" for item in projection["chapter_queue"]))
        self.assert_typed_section(projection, "range_prepare")

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

    def test_range_input_tasks_replace_chapter_repetition(self) -> None:
        rows = (_row(1), _row(2))
        base = {
            "scope": _readiness(*rows)["scope"],
            "summary": {
                "total_chapters": 2,
                "ready_chapters": 0,
                "blocked_chapters": 0,
                "proposal_required_chapters": 0,
                "speaker_exception_count": 0,
                "voice_exception_count": 0,
                "chapters_awaiting_speaker_approval": 0,
                "chapters_awaiting_casting_approval": 0,
                "casting_generation_ready_chapters": 0,
                "inherited_voice_count": 0,
                "skipped_chapters": 0,
            },
            "proposal_chapters": [],
            "speaker_exception_queue": [],
            "ready_speaker_drafts": [],
            "voice_exception_queue": [],
            "casting_generation_ready": [],
            "casting_approvals": [],
            "blocked": [],
            "skipped": [],
        }
        exception = {
            "chapter_id": rows[0]["chapter_id"],
            "chapter_number": 1,
            "chapter_title": "Chapter 1",
            "draft_id": 41,
            "utterance_id": "u0002-test",
            "sequence": 2,
        }
        cases = (
            (
                {"proposal_chapters": [{
                    "chapter_id": rows[0]["chapter_id"],
                    "chapter_number": 1,
                    "chapter_title": "Chapter 1",
                }]},
                "PREPARE_RANGE_INPUTS",
                "speaker",
            ),
            (
                {"speaker_exception_queue": [exception]},
                "REVIEW_RANGE_SPEAKER_EXCEPTIONS",
                "speaker",
            ),
            (
                {"ready_speaker_drafts": [{
                    "chapter_id": rows[0]["chapter_id"],
                    "chapter_number": 1,
                    "chapter_title": "Chapter 1",
                    "draft_id": 41,
                }]},
                "APPROVE_READY_SPEAKER_DRAFTS",
                "speaker",
            ),
            (
                {"voice_exception_queue": [{
                    "chapter_id": rows[0]["chapter_id"],
                    "chapter_number": 1,
                    "chapter_title": "Chapter 1",
                    "speaker_key": "character:7",
                }]},
                "REVIEW_RANGE_VOICE_EXCEPTIONS",
                "casting",
            ),
            (
                {"casting_generation_ready": [{
                    "chapter_id": rows[0]["chapter_id"],
                    "chapter_number": 1,
                    "chapter_title": "Chapter 1",
                    "draft_id": 41,
                }]},
                "PREPARE_RANGE_INPUTS",
                "speaker",
            ),
            (
                {"casting_approvals": [{
                    "chapter_id": rows[0]["chapter_id"],
                    "chapter_number": 1,
                    "chapter_title": "Chapter 1",
                    "plan_id": 81,
                }]},
                "APPROVE_RANGE_CASTING_PLANS",
                "casting",
            ),
        )
        for changes, expected, section in cases:
            with self.subTest(expected=expected):
                range_inputs = {
                    **base,
                    **changes,
                    "summary": {
                        **base["summary"],
                        "proposal_required_chapters": len(
                            changes.get("proposal_chapters", [])
                        ),
                        "speaker_exception_count": len(
                            changes.get("speaker_exception_queue", [])
                        ),
                        "voice_exception_count": len(
                            changes.get("voice_exception_queue", [])
                        ),
                    },
                }
                projection = project_production_task({
                    "readiness": _readiness(*rows),
                    "range_inputs": range_inputs,
                })
                self.assertEqual(projection["task_type"], expected)
                self.assert_typed_section(projection, section)

    def test_mixed_range_regenerates_analysis_before_reviewing_existing_exceptions(self) -> None:
        rows = (
            _row(1, "SPEAKER_EXCEPTIONS", blockers=["analysis required"]),
            _row(2, "SPEAKER_EXCEPTIONS", blockers=["review required"]),
        )
        range_inputs = {
            "summary": {
                "total_chapters": 2,
                "proposal_required_chapters": 1,
                "speaker_exception_count": 1,
            },
            "proposal_chapters": [{
                "chapter_id": rows[0]["chapter_id"],
                "chapter_number": 1,
                "chapter_title": "Chapter 1",
                "reason": "analysis_required",
                "draft_id": 11,
            }],
            "speaker_exception_queue": [{
                "chapter_id": rows[1]["chapter_id"],
                "chapter_number": 2,
                "chapter_title": "Chapter 2",
                "draft_id": 22,
                "utterance_id": "u0002-mixed",
                "sequence": 2,
            }],
            "ready_speaker_drafts": [],
            "voice_exception_queue": [],
            "casting_generation_ready": [],
            "casting_approvals": [],
            "blocked": [],
            "skipped": [],
        }
        projection = project_production_task({
            "readiness": _readiness(*rows),
            "range_inputs": range_inputs,
        })
        self.assertEqual(projection["task_type"], "PREPARE_RANGE_INPUTS")
        speaker = projection["canonical_task"]["speaker"]
        self.assertEqual(speaker["proposal_chapters"][0]["chapter_number"], 1)
        self.assertEqual(len(speaker["exception_queue"]), 1)

    def test_repair_required_precedes_stale_range_input_preparation(self) -> None:
        repair = _row(
            1,
            "REPAIR_REQUIRED",
            blockers=["needs fixes"],
            active_artifact_id=93,
            latest_casting_plan_id=28,
        )
        range_inputs = {
            "summary": {
                "total_chapters": 1,
                "proposal_required_chapters": 1,
            },
            "proposal_chapters": [{
                "chapter_id": repair["chapter_id"],
                "chapter_number": 1,
                "chapter_title": "Chapter 1",
                "reason": "stale",
                "draft_id": 16,
            }],
        }

        projection = project_production_task({
            "readiness": _readiness(repair),
            "range_inputs": range_inputs,
        })

        self.assertEqual(projection["task_type"], "REPAIR_REQUIRED")
        self.assertEqual(projection["affected_chapter"]["number"], 1)
        self.assertIn("artifact:93", projection["task_key"])
        self.assertEqual(projection["chapter_queue"][0]["status"], "current")
        self.assert_typed_section(projection, "repair")

        complete = _row(1, "COMPLETE", active_artifact_id=93)
        projection = project_production_task({"readiness": _readiness(complete)})
        self.assertEqual(projection["task_type"], "COMPLETE")
        self.assertIsNone(projection["primary_action"])
        self.assertEqual(projection["task_scope"], "range")
        self.assertEqual(projection["range_readiness"]["chapters"][0]["state"], "COMPLETE")
        self.assertEqual(projection["range_readiness"]["chapters"][0]["active_artifact_id"], 93)

    def test_text_blocker_precedes_range_input_orchestration(self) -> None:
        blocked = _row(
            1,
            "TEXT_BLOCKED",
            latest_speaker_draft_id=None,
            blockers=["bad text"],
        )
        range_inputs = {
            "summary": {"total_chapters": 1},
            "proposal_chapters": [{
                "chapter_id": blocked["chapter_id"],
                "chapter_number": 1,
                "chapter_title": "Chapter 1",
            }],
        }
        projection = project_production_task({
            "readiness": _readiness(blocked),
            "range_inputs": range_inputs,
        })
        self.assertEqual(projection["task_type"], "REVIEW_TEXT")

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

    def test_prepared_job_can_skip_complete_chapter_and_remain_exact_range(self) -> None:
        projection = project_production_task(
            {
                "readiness": _readiness(
                    _row(6, "PREPARED"),
                    _row(7, "COMPLETE"),
                    _row(8, "PREPARED"),
                ),
                "range_jobs": [
                    {
                        "id": 39,
                        "status": "prepared",
                        "chapter_count": 2,
                        "all_chapters_match": True,
                    }
                ],
            }
        )
        self.assertEqual(projection["task_type"], "START_RENDER_RANGE")
        self.assertEqual(projection["canonical_task"]["render"]["job_id"], 39)
        queue = {item["chapter_number"]: item for item in projection["chapter_queue"]}
        self.assertEqual(queue[7]["status"], "complete")

    def test_prepared_job_cannot_hide_noncomplete_chapter_outside_job(self) -> None:
        projection = project_production_task(
            {
                "readiness": _readiness(
                    _row(6, "PREPARED"),
                    _row(7, "COMPLETE"),
                    _row(
                        8,
                        "TEXT_BLOCKED",
                        latest_speaker_draft_id=None,
                        blockers=["bad text"],
                    ),
                ),
                "range_jobs": [
                    {
                        "id": 39,
                        "status": "prepared",
                        "chapter_count": 1,
                        "all_chapters_match": True,
                    }
                ],
            }
        )
        self.assertEqual(projection["task_type"], "REVIEW_TEXT")
        self.assertNotEqual(projection["task_type"], "START_RENDER_RANGE")

    def test_projection_builder_matches_job_against_noncomplete_chapters(self) -> None:
        readiness = _readiness(
            _row(
                6,
                "PREPARED",
                latest_speaker_draft_id=None,
                speaker_state={"status": "APPROVED_CURRENT"},
            ),
            _row(
                7,
                "COMPLETE",
                latest_speaker_draft_id=None,
                speaker_state={"status": "APPROVED_CURRENT"},
            ),
            _row(
                8,
                "PREPARED",
                latest_speaker_draft_id=None,
                speaker_state={"status": "APPROVED_CURRENT"},
            ),
        )
        db = object()
        exact_job = {
            "id": 39,
            "status": "prepared",
            "chapter_count": 2,
            "all_chapters_match": True,
        }
        with patch(
            "story_audio.production_task_projection.get_range_readiness",
            return_value=readiness,
        ), patch(
            "story_audio.production_task_projection._exact_range_jobs",
            return_value=[exact_job],
        ) as exact_jobs:
            projection = get_production_task_projection(
                db,
                book_id=1,
                from_chapter=6,
                to_chapter=8,
            )
        exact_jobs.assert_called_once_with(
            db,
            book_id=1,
            from_chapter=6,
            to_chapter=8,
            chapter_ids=[1006, 1008],
        )
        self.assertEqual(projection["task_type"], "START_RENDER_RANGE")

    def test_subset_of_prepared_job_routes_to_owner_scope_without_starting(self) -> None:
        owner = {
            "live_job_id": 35,
            "live_job_status": "prepared",
            "live_job_book_id": 1,
            "live_job_from_chapter": 2,
            "live_job_to_chapter": 8,
        }
        projection = project_production_task(
            {
                "readiness": _readiness(
                    _row(2, "PREPARED", **owner),
                    _row(3, "PREPARED", **owner),
                    _row(4, "PREPARED", **owner),
                ),
                "range_jobs": [],
            }
        )
        self.assertEqual(projection["task_type"], "OPEN_JOB_RANGE")
        self.assertEqual(projection["primary_action"]["key"], "OPEN_JOB_RANGE")
        self.assertEqual(projection["primary_action"]["label"], "M\u1edf Ch\u01b0\u01a1ng 2-8")
        self.assertEqual(projection["canonical_task"]["render"]["job_id"], 35)
        self.assertEqual(projection["canonical_task"]["render"]["from_chapter"], 2)
        self.assertEqual(projection["canonical_task"]["render"]["to_chapter"], 8)
        self.assertNotEqual(projection["task_type"], "START_RENDER_RANGE")
        self.assert_typed_section(projection, "render")

    def test_prepared_replacement_exposes_human_repair_summary(self) -> None:
        projection = project_production_task(
            {
                "readiness": _readiness(_row(1)),
                "range_jobs": [
                    {
                        "id": 44,
                        "status": "prepared",
                        "chapter_count": 1,
                        "all_chapters_match": True,
                        "replacement_for_artifact_id": 39,
                        "repair_summary": {
                            "repeated_words": True,
                            "global_speed_target": 1.25,
                            "local_pacing_adjustment_required": True,
                            "marker_count": 0,
                        },
                    }
                ],
            }
        )
        render = projection["canonical_task"]["render"]
        self.assertTrue(render["replacement"])
        self.assertEqual(render["repair_summary"]["global_speed_target"], 1.25)
        self.assertTrue(render["repair_summary"]["repeated_words"])

    def test_current_qa_output_precedes_historical_recovery_job(self) -> None:
        current = _row(1, "RENDERED_NOT_QA", active_artifact_id=114)
        projection = project_production_task({
            "readiness": _readiness(current),
            "range_jobs": [{"id": 7, "status": "completed_with_errors", "all_chapters_match": True}],
        })
        self.assertEqual(projection["task_type"], "HUMAN_QA")
        self.assertEqual(projection["canonical_task"]["qa"]["artifact_id"], 114)

    def test_recoverable_job_remains_current_without_output(self) -> None:
        projection = project_production_task({
            "readiness": _readiness(_row(1)),
            "range_jobs": [{"id": 44, "status": "failed", "chapter_count": 1, "all_chapters_match": True}],
        })
        self.assertEqual(projection["task_type"], "RECOVER_RENDER")

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
        qa = _row(1, "RENDERED_NOT_QA", blockers=["audio awaits QA"], active_artifact_id=99)
        projection = project_production_task({"readiness": _readiness(qa)})
        self.assertEqual(projection["task_type"], "HUMAN_QA")
        self.assertIn("artifact:99", projection["task_key"])
        self.assertEqual(projection["canonical_task"]["qa"]["artifact_id"], 99)
        self.assertEqual(projection["user_stage"], 5)
        self.assertIsNone(projection["primary_action"])
        self.assertEqual(projection["chapter_queue"][0]["status"], "current")
        self.assert_typed_section(projection, "qa")

        repair = _row(1, "REPAIR_REQUIRED", blockers=["needs fixes"], active_artifact_id=39)
        projection = project_production_task({"readiness": _readiness(repair)})
        self.assertEqual(projection["task_type"], "REPAIR_REQUIRED")
        self.assertEqual(projection["user_stage"], 5)
        self.assertEqual(projection["current_stage_key"], "repair")
        self.assertEqual(projection["title"], "Cần sửa và tạo bản thay thế")
        self.assertEqual(len(projection["phases"]), 4)
        self.assertEqual(projection["phases"][0]["label"], "Xác nhận nội dung và người nói")
        self.assertIsNone(projection["primary_action"])
        self.assertEqual(projection["chapter_queue"][0]["status"], "current")
        self.assert_typed_section(projection, "repair")

    def test_repair_blockers_are_structured_for_assignment_deep_links(self) -> None:
        repair = _row(
            1,
            "REPAIR_REQUIRED",
            blockers=["needs fixes"],
            active_artifact_id=39,
            repair_input_blockers=[
                "Latest Speaker Draft is stale for the active Text Revision.",
                "Final Voice Map is missing.",
            ],
        )

        projection = project_production_task({"readiness": _readiness(repair)})
        details = projection["canonical_task"]["repair"]["input_blocker_details"]

        self.assertEqual(
            [item["code"] for item in details],
            ["SPEAKER_DRAFT_STALE", "VOICE_MAP_DEPENDS_ON_SPEAKER"],
        )
        self.assertEqual(
            [item["assignment_focus"] for item in details],
            ["review", "voices"],
        )
        self.assertFalse(details[0].get("dependent", False))
        self.assertTrue(details[1]["dependent"])
        self.assertIsNone(details[1]["action_label"])
        self.assertEqual(projection["phases"][0]["state"], "current")

class ProductionTaskProjectionAuditTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        seeded = seed_active_output(self.temp_root)
        self.db = seeded["db"]
        self.chapter_id = seeded["chapter_one"]
        self.artifact_id = seeded["old_artifact_id"]
        self.new_artifact_id = seeded["new_artifact_id"]
        self.output_job_id = seeded["job_old"]
        self.new_job_id = seeded["job_new"]
        self.book_id = int(
            self.db.fetch_one(
                "SELECT book_id FROM chapters WHERE id=?",
                (self.chapter_id,),
            )["book_id"]
        )
        self.full_note = "Khoảng 3:11, audio repeats: “truyền tống truyền tống”."
        self.full_recorded_at = utcnow()
        self.placeholder_recorded_at = utcnow()
        approval = {
            "status": "needs_fixes",
            "recorded_at": self.placeholder_recorded_at,
            "approved_at": None,
            "notes": "x",
            "artifact_id": self.artifact_id,
            "job_id": seeded["job_old"],
            "output_path": "placeholder",
            "sha256": "placeholder",
            "duration_ms": 1000,
        }
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE chapters SET human_approval_json=?, updated_at=? WHERE id=?",
                (
                    json.dumps(approval, ensure_ascii=False),
                    self.placeholder_recorded_at,
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
                    seeded["job_old"],
                    self.chapter_id,
                    json.dumps(
                        {
                            "status": "needs_fixes",
                            "notes": self.full_note,
                            "artifact_id": self.artifact_id,
                            "job_id": seeded["job_old"],
                            "sha256": "placeholder",
                            "duration_ms": 1000,
                        },
                        ensure_ascii=False,
                    ),
                    self.full_recorded_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO audit_events(event_code,job_id,chapter_id,details_json,created_at)
                VALUES(?,?,?,?,?)
                """,
                (
                    "human_qa_recorded",
                    seeded["job_old"],
                    self.chapter_id,
                    json.dumps(
                        {
                            "status": "needs_fixes",
                            "notes": "x",
                            "artifact_id": self.artifact_id,
                            "job_id": seeded["job_old"],
                            "sha256": "placeholder",
                            "duration_ms": 1000,
                        },
                        ensure_ascii=False,
                    ),
                    self.placeholder_recorded_at,
                ),
            )

    def test_pending_replacement_uses_pinned_predecessor_and_repair_goals(self) -> None:
        instruction = {
            "schema": "story-audio-repair-instruction/v1",
            "replacement_for_artifact_id": self.artifact_id,
            "repeated_words": False,
            "global_speed_target": 1.25,
            "local_pacing_adjustment_required": True,
        }
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE jobs SET settings_json=? WHERE id=?",
                (json.dumps({"repair_instruction": instruction}), self.new_job_id),
            )
            connection.execute(
                """
                INSERT INTO audit_events(event_code,job_id,chapter_id,details_json,created_at)
                VALUES(?,?,?,?,?)
                """,
                (
                    "human_qa_recorded",
                    self.output_job_id,
                    self.chapter_id,
                    json.dumps(
                        {
                            "status": "needs_fixes",
                            "artifact_id": self.artifact_id,
                            "notes": "Có lặp chữ ở đoạn giữa.",
                        },
                        ensure_ascii=False,
                    ),
                    utcnow(),
                ),
            )

        result = _qa_replacement_context(
            self.db,
            chapter_id=self.chapter_id,
            artifact_id=self.new_artifact_id,
        )

        self.assertEqual(result["previous_artifact"]["artifact_id"], self.artifact_id)
        self.assertEqual(result["previous_artifact"]["human_qa_status"], "needs_fixes")
        self.assertTrue(result["repair_goals"]["repeated_words"])
        self.assertEqual(result["repair_goals"]["global_speed_target"], 1.25)
        self.assertTrue(result["repair_goals"]["local_pacing_adjustment_required"])

    def test_repair_projection_uses_audit_note_when_snapshot_contains_placeholder(self) -> None:
        qa_event_id = self.db.fetch_one(
            """
            SELECT id FROM audit_events
            WHERE chapter_id=? AND event_code='human_qa_recorded'
            ORDER BY id ASC LIMIT 1
            """,
            (self.chapter_id,),
        )["id"]
        with self.db.transaction() as connection:
            repair_plan_id = connection.execute(
                """
                INSERT INTO audit_events(event_code,job_id,chapter_id,details_json,created_at)
                VALUES(?,?,?,?,?)
                """,
                (
                    "repair_plan_confirmed",
                    self.output_job_id,
                    self.chapter_id,
                    json.dumps(
                        {
                            "artifact_id": self.artifact_id,
                            "qa_evidence_id": qa_event_id,
                            "repeated_words": True,
                            "global_speed_target": 1.25,
                            "local_pacing_adjustment_required": True,
                            "operator_note": None,
                        },
                        ensure_ascii=False,
                    ),
                    utcnow(),
                ),
            ).lastrowid
        readiness = {
            "scope": {
                "book_id": self.book_id,
                "book_title": "Book",
                "from_chapter": 10,
                "to_chapter": 10,
                "chapter_count": 1,
            },
            "summary": {},
            "chapters": [
                {
                    "chapter_id": self.chapter_id,
                    "chapter_number": 10,
                    "chapter_title": "Chapter 10",
                    "state": "REPAIR_REQUIRED",
                    "blockers": ["needs fixes"],
                    "latest_speaker_draft_id": 12,
                    "latest_speaker_draft_status": "approved",
                    "active_artifact_id": self.artifact_id,
                    "active_output_job_id": self.output_job_id,
                    "latest_casting_plan_id": 6,
                    "latest_casting_plan_revision": 1,
                    "latest_casting_plan_status": "approved",
                    "active_text_revision_id": 1,
                    "active_output_text_revision_id": 1,
                    "active_output_casting_plan_id": 4,
                    "active_output_casting_plan_revision": 4,
                    "human_qa_status": "needs_fixes",
                    "repair_prepare_ready": True,
                    "repair_input_blockers": [],
                    "effective_voice_map": [],
                    "voice_map_diff": [],
                }
            ],
        }
        historical_job = {
            "id": self.output_job_id - 1,
            "job_id": self.output_job_id - 1,
            "status": "completed_with_errors",
            "chapter_count": 1,
            "all_chapters_match": True,
        }
        with patch("story_audio.production_task_projection.get_range_readiness", return_value=readiness), patch(
            "story_audio.production_task_projection._exact_range_jobs",
            return_value=[historical_job],
        ):
            projection = get_production_task_projection(
                self.db,
                book_id=self.book_id,
                from_chapter=10,
                to_chapter=10,
                store=None,
            )
        self.assertEqual(projection["task_type"], "REPAIR_REQUIRED")
        self.assertEqual(projection["canonical_task"]["repair"]["qa_note"], self.full_note)
        self.assertEqual(
            projection["canonical_task"]["repair"]["qa_recorded_at"],
            self.full_recorded_at,
        )
        plan = projection["canonical_task"]["repair"]["repair_plan"]
        self.assertEqual(plan["evidence_id"], repair_plan_id)
        self.assertEqual(plan["qa_evidence_id"], qa_event_id)
        self.assertEqual(plan["global_speed_target"], 1.25)


if __name__ == "__main__":
    unittest.main()
