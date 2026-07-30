from __future__ import annotations

import unittest

from story_audio.speaker_review_workspace import (
    batch_exclusion_reasons,
    command_lifecycle_label,
    queue_view_counts,
    queue_view_for,
)


class SpeakerReviewWorkspaceContractTests(unittest.TestCase):
    def test_queue_views_keep_approved_corrections_in_history_and_edited_views(self) -> None:
        items = [
            {"review_state": "PENDING_REVIEW", "proposed_resolution": "EXISTING_CHARACTER"},
            {"review_state": "PENDING_REVIEW", "proposed_resolution": "NEEDS_HUMAN_DECISION"},
            {"review_state": "CORRECTED", "proposed_resolution": "EXISTING_CHARACTER"},
            {"review_state": "DEFERRED", "proposed_resolution": "NEW_CHARACTER"},
            {"review_state": "ERROR", "proposed_resolution": "EXISTING_CHARACTER"},
        ]

        self.assertEqual(queue_view_for(items[0]), "NEEDS_REVIEW")
        self.assertEqual(queue_view_for(items[1]), "NEEDS_DECISION")
        self.assertEqual(queue_view_for(items[2]), "APPROVED")
        counts = queue_view_counts(items)
        self.assertEqual(counts["ALL"]["count"], 5)
        self.assertEqual(counts["APPROVED"]["count"], 1)
        self.assertEqual(counts["EDITED"]["count"], 1)
        self.assertEqual(counts["DEFERRED"]["count"], 1)
        self.assertEqual(counts["ERROR"]["count"], 1)

    def test_batch_eligibility_rejects_every_unsafe_high_confidence_condition(self) -> None:
        safe = {
            "confidence": "HIGH",
            "review_state": "PENDING_REVIEW",
            "unresolved_key": "unresolved-dialogue:1:u1",
            "proposed_resolution": "EXISTING_CHARACTER",
            "existing_character_id": 7,
            "alternative_candidates": [],
            "possible_duplicates": [],
            "warnings": [],
            "source_revision_current": True,
            "effective_inherited_voice": {"available": True},
        }
        self.assertEqual(batch_exclusion_reasons(safe), [])

        unsafe = {
            **safe,
            "alternative_candidates": [{"character_id": 8}],
            "possible_duplicates": [{"character_id": 9}],
            "warnings": ["continuity warning"],
            "source_revision_current": False,
            "effective_inherited_voice": {"available": False},
        }
        reasons = batch_exclusion_reasons(unsafe, unsaved_edit=True)
        self.assertIn("unsaved_human_edit", reasons)
        self.assertIn("alternative_candidate_conflict", reasons)
        self.assertIn("duplicate_character_warning", reasons)
        self.assertIn("warning_requires_review", reasons)
        self.assertIn("stale_source_revision", reasons)
        self.assertIn("unavailable_effective_voice", reasons)
        self.assertEqual(
            batch_exclusion_reasons(
                {**safe, "approved_final_voice_map_available": False}
            ),
            ["approved_final_voice_map_missing"],
        )

    def test_command_lifecycle_hides_internal_status_names(self) -> None:
        self.assertEqual(command_lifecycle_label("SUBMITTING"), "Đang lưu quyết định…")
        self.assertEqual(command_lifecycle_label("VERIFYING_UNKNOWN"), "Đang xác minh kết quả…")
        self.assertEqual(command_lifecycle_label("APPLIED"), "Đã lưu và cập nhật Preflight")
        self.assertNotIn("VERIFYING_UNKNOWN", command_lifecycle_label("VERIFYING_UNKNOWN"))


if __name__ == "__main__":
    unittest.main()
