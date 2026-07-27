from __future__ import annotations

import unittest

from story_audio.production_preflight import (
    PREFLIGHT_SCHEMA,
    aggregate_effective_voice_map,
    decide_preflight_next_action,
    project_production_preflight,
)
from story_audio.voice_eligibility import EffectiveVoiceCatalog


def _action_state(**overrides) -> dict:
    state = {
        "task_type": "PREPARE_RANGE",
        "data_ready": True,
        "authorization_ready": True,
        "first_blocker": None,
    }
    state.update(overrides)
    return state


def _row(number: int, state: str = "READY_TO_PREPARE", **overrides) -> dict:
    row = {
        "chapter_id": 1000 + number,
        "chapter_number": number,
        "chapter_title": f"Chapter {number}",
        "state": state,
        "blockers": [],
        "voice_issues": [],
        "next_action": "PREPARE",
        "latest_casting_plan_id": 2000 + number,
    }
    row.update(overrides)
    return row


def _task(task_type: str = "PREPARE_RANGE", rows: list[dict] | None = None) -> dict:
    queue = [
        {
            "chapter_id": row["chapter_id"],
            "chapter_number": row["chapter_number"],
            "task_type": row.get("queue_task"),
            "canonical_task": bool(index == 0 and row.get("queue_task")),
        }
        for index, row in enumerate(rows or [])
    ]
    sections = {
        "speaker": None,
        "casting": None,
        "range_prepare": None,
        "render": None,
        "qa": None,
    }
    if task_type == "PREPARE_RANGE":
        sections["range_prepare"] = {
            "book_id": 1,
            "from_chapter": 1,
            "to_chapter": len(rows or []) or 1,
        }
    elif task_type in {"START_RENDER_RANGE", "MONITOR_RENDER", "RECOVER_RENDER"}:
        sections["render"] = {"job_id": 44, "job_status": "prepared"}
    elif task_type == "HUMAN_QA":
        sections["qa"] = {"chapter_id": 1001, "artifact_id": 90}
    return {
        "range_identity": "book:1:1-2",
        "chapter_queue": queue,
        "canonical_task": {
            "task_type": task_type,
            "task_key": f"task:{task_type}",
            "primary_action": {
                "key": task_type,
                "label": "Canonical action",
                "target": "production",
            },
            **sections,
        },
    }


def _snapshot(
    rows: list[dict],
    *,
    task_type: str = "PREPARE_RANGE",
    authorized: bool = True,
    voice_map: list[dict] | None = None,
    voice_warnings: list[str] | None = None,
) -> dict:
    included = [
        {
            "chapter_id": row["chapter_id"],
            "chapter_number": row["chapter_number"],
            "chapter_title": row["chapter_title"],
            "latest_casting_plan_id": row.get("latest_casting_plan_id"),
        }
        for row in rows
        if row["state"] == "READY_TO_PREPARE"
    ]
    excluded = [
        {
            "chapter_id": row["chapter_id"],
            "chapter_number": row["chapter_number"],
            "chapter_title": row["chapter_title"],
            "operator_message": (row.get("blockers") or ["Excluded"])[0],
            "reason_codes": ["EXCLUDED"],
        }
        for row in rows
        if row["state"] != "READY_TO_PREPARE"
    ]
    return {
        "readiness": {
            "scope": {
                "book_id": 1,
                "book_title": "Book",
                "from_chapter": rows[0]["chapter_number"],
                "to_chapter": rows[-1]["chapter_number"],
                "chapter_count": len(rows),
            },
            "chapters": rows,
        },
        "task_projection": _task(task_type, rows),
        "batch_plan": {
            "plan_fingerprint": "fingerprint",
            "included": included,
            "excluded": excluded,
        },
        "runtime_readiness": {
            "schema_version": 15,
            "required_schema_version": 15,
            "mutation_authorized": authorized,
            "authentication_state": (
                "AUTH_CONFIGURED" if authorized else "AUTH_NOT_CONFIGURED"
            ),
            "kill_switch_active": False,
            "start_render_available": True,
            "status": "READY",
            "reasons": [],
        },
        "skip_completed": True,
        "effective_voice_map": voice_map or [],
        "voice_warnings": voice_warnings or [],
        "voice_technical": [{"technical_voice_id": "custom:26"}],
        "estimated_segment_count": 18,
    }


class ProductionPreflightDecisionTests(unittest.TestCase):
    def test_decision_table(self) -> None:
        cases = (
            (
                _action_state(
                    data_ready=False,
                    first_blocker={
                        "next_task": "REVIEW_TEXT",
                        "action_label": "Review Chapter 3",
                        "target": "text",
                    },
                ),
                "REVIEW_TEXT",
            ),
            (
                _action_state(authorization_ready=False),
                "AUTHENTICATE_EXECUTION",
            ),
            (_action_state(), "PREPARE_RANGE"),
            (_action_state(task_type="START_RENDER_RANGE"), "START_RENDER_RANGE"),
            (_action_state(task_type="MONITOR_RENDER"), "MONITOR_RENDER"),
            (_action_state(task_type="HUMAN_QA"), "HUMAN_QA"),
        )
        for state, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    decide_preflight_next_action(state)["key"],
                    expected,
                )

    def test_lifecycle_authority_precedes_authorization(self) -> None:
        action = decide_preflight_next_action(
            _action_state(
                task_type="START_RENDER_RANGE",
                authorization_ready=False,
            )
        )
        self.assertEqual(action["key"], "START_RENDER_RANGE")


class ProductionPreflightProjectionTests(unittest.TestCase):
    def test_ready_projection_separates_data_and_authorization(self) -> None:
        projection = project_production_preflight(
            _snapshot([_row(1), _row(2)], authorized=False)
        )
        self.assertEqual(projection["schema"], PREFLIGHT_SCHEMA)
        self.assertTrue(projection["data_readiness"]["ready"])
        self.assertFalse(projection["execution_readiness"]["authorization_ready"])
        self.assertFalse(projection["execution_readiness"]["prepare_allowed"])
        self.assertEqual(
            projection["execution_preview"]["next_action"]["key"],
            "AUTHENTICATE_EXECUTION",
        )
        self.assertFalse(projection["execution_preview"]["tts_called"])

    def test_blockers_are_ordered_and_checklists_name_exact_chapters(self) -> None:
        rows = [
            _row(3, "SPEAKER_EXCEPTIONS", blockers=["Speaker review required."], queue_task="RESOLVE_SPEAKER"),
            _row(4, "VOICE_BLOCKED", blockers=["Voice unavailable."]),
        ]
        projection = project_production_preflight(
            _snapshot(rows, task_type="RESOLVE_SPEAKER")
        )
        readiness = projection["data_readiness"]
        self.assertFalse(readiness["ready"])
        self.assertEqual(
            [item["chapter_number"] for item in readiness["ordered_blockers"]],
            [3, 4],
        )
        self.assertEqual(readiness["speaker"]["failed_chapters"], [3])
        self.assertEqual(readiness["voice"]["failed_chapters"], [3, 4])
        self.assertEqual(
            projection["execution_preview"]["next_action"]["key"],
            "RESOLVE_SPEAKER",
        )

    def test_unavailable_voice_fails_closed(self) -> None:
        projection = project_production_preflight(
            _snapshot(
                [_row(1)],
                voice_map=[
                    {
                        "speaker_name": "Narrator",
                        "role": "narrator",
                        "effective_voice_name": "Unavailable",
                        "assignment_source": "book_default",
                        "affected_chapters": [1],
                        "line_count": 3,
                        "available": False,
                        "warning": "Voice is unavailable.",
                    }
                ],
                voice_warnings=["Chapter 1 uses an unavailable voice."],
            )
        )
        self.assertFalse(projection["data_readiness"]["ready"])
        self.assertFalse(projection["execution_readiness"]["prepare_allowed"])
        self.assertEqual(
            projection["data_readiness"]["voice"]["failed_chapters"],
            [1],
        )
        self.assertEqual(
            projection["data_readiness"]["ordered_blockers"][0]["state"],
            "VOICE_BLOCKED",
        )
        self.assertEqual(
            projection["data_readiness"]["ordered_blockers"][0]["chapter_number"],
            1,
        )

    def test_prepared_projection_has_one_start_action(self) -> None:
        projection = project_production_preflight(
            _snapshot(
                [_row(1, "PREPARED")],
                task_type="START_RENDER_RANGE",
            )
        )
        self.assertEqual(
            projection["execution_preview"]["next_action"]["key"],
            "START_RENDER_RANGE",
        )
        self.assertIsNotNone(
            projection["execution_readiness"]["prepared_job"]
        )
        self.assertFalse(projection["execution_readiness"]["prepare_allowed"])
        self.assertTrue(projection["execution_readiness"]["render_allowed"])


class EffectiveVoiceMapTests(unittest.TestCase):
    def test_aggregates_display_names_sources_chapters_and_lines(self) -> None:
        catalog = EffectiveVoiceCatalog.from_payload(
            {
                "items": [
                    {
                        "assignment_key": "custom:26",
                        "display_name": "Narrator",
                        "source_kind": "custom",
                        "active": True,
                        "usable": True,
                        "selectable": True,
                    },
                    {
                        "assignment_key": "custom:25",
                        "display_name": "Hero",
                        "source_kind": "custom",
                        "active": True,
                        "usable": True,
                        "selectable": True,
                    },
                ]
            }
        )
        plans = [
            {
                "chapter_number": 1,
                "utterances": [
                    {
                        "role": "narrator",
                        "character_id": None,
                        "resolved_voice_id": "custom:26",
                        "resolution_source": "narrator",
                    },
                    {
                        "role": "character",
                        "character_id": 7,
                        "resolved_voice_id": "custom:25",
                        "resolution_source": "character_override",
                    },
                ],
            },
            {
                "chapter_number": 2,
                "utterances": [
                    {
                        "role": "character",
                        "character_id": 7,
                        "resolved_voice_id": "custom:25",
                        "resolution_source": "character_override",
                    }
                ],
            },
        ]
        voice_map, warnings, segments = aggregate_effective_voice_map(
            plans,
            character_names={7: "Hua Thanh"},
            voice_catalog=catalog,
        )
        self.assertEqual(segments, 3)
        self.assertEqual(warnings, [])
        self.assertEqual(voice_map[0]["speaker_name"], "Ng\u01b0\u1eddi k\u1ec3 chuy\u1ec7n")
        self.assertEqual(voice_map[0]["assignment_source"], "book_default")
        self.assertEqual(voice_map[1]["speaker_name"], "Hua Thanh")
        self.assertEqual(voice_map[1]["effective_voice_name"], "Hero")
        self.assertEqual(voice_map[1]["assignment_source"], "override")
        self.assertEqual(voice_map[1]["affected_chapters"], [1, 2])
        self.assertEqual(voice_map[1]["line_count"], 2)

    def test_unavailable_voice_never_falls_back(self) -> None:
        catalog = EffectiveVoiceCatalog.from_ids("custom:26")
        voice_map, warnings, _ = aggregate_effective_voice_map(
            [
                {
                    "chapter_number": 9,
                    "utterances": [
                        {
                            "role": "unknown",
                            "resolved_voice_id": "custom:999",
                            "resolution_source": "unknown_fallback",
                        }
                    ],
                }
            ],
            character_names={},
            voice_catalog=catalog,
        )
        self.assertFalse(voice_map[0]["available"])
        self.assertEqual(
            voice_map[0]["effective_voice_name"],
            "Gi\u1ecdng kh\u00f4ng kh\u1ea3 d\u1ee5ng",
        )
        self.assertEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
