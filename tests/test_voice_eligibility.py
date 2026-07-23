from __future__ import annotations

import json
import unittest

from story_audio.voice_eligibility import (
    EffectiveVoiceCatalog,
    VoiceCatalogAuthority,
    VoiceCatalogUnavailable,
    VoiceEligibilityBlocked,
    inspect_casting_plan,
    normalize_voice_id,
    require_casting_plan_eligible,
)


class VoiceEligibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = EffectiveVoiceCatalog.from_ids("Đức Trí", "custom:7")

    def test_normalization_is_nfc_and_custom_refs_are_canonical(self) -> None:
        self.assertEqual(normalize_voice_id(" Đức Trí "), "Đức Trí")
        self.assertEqual(normalize_voice_id("custom:007"), "custom:7")

    def test_malformed_and_unknown_voices_are_blocking_without_fallback(self) -> None:
        plan = {
            "narrator_voice_id": "voice1",
            "utterances": [
                {
                    "utterance_id": "u1",
                    "sequence": 1,
                    "role": "narrator",
                    "character_id": None,
                    "resolved_voice_id": "voice1",
                },
                {
                    "utterance_id": "u2",
                    "sequence": 2,
                    "role": "character",
                    "character_id": 23,
                    "resolved_voice_id": "custom:bad",
                },
            ],
        }
        issues = inspect_casting_plan(
            plan,
            self.catalog,
            chapter_id=1986,
            chapter_number=1,
        )
        self.assertEqual([item["code"] for item in issues], ["VOICE_UNAVAILABLE", "VOICE_ID_MALFORMED"])
        self.assertEqual(issues[0]["voice_id"], "voice1")
        self.assertEqual(issues[0]["speaker_role"], "narrator")
        self.assertEqual(issues[1]["character_id"], 23)
        self.assertTrue(all(item["replacement_required"] for item in issues))
        self.assertTrue(all("no fallback" in item["message"] for item in issues))

    def test_valid_existing_assignments_remain_unchanged(self) -> None:
        plan = {
            "narrator_voice_id": "Đức Trí",
            "utterances": [
                {
                    "utterance_id": "u1",
                    "sequence": 1,
                    "role": "narrator",
                    "character_id": None,
                    "resolved_voice_id": "Đức Trí",
                },
                {
                    "utterance_id": "u2",
                    "sequence": 2,
                    "role": "unknown",
                    "character_id": None,
                    "resolved_voice_id": "custom:7",
                },
            ],
        }
        before = json.dumps(plan, ensure_ascii=False, sort_keys=True)
        require_casting_plan_eligible(plan, self.catalog, chapter_id=1, chapter_number=1)
        self.assertEqual(json.dumps(plan, ensure_ascii=False, sort_keys=True), before)

    def test_catalog_loader_failure_is_fail_closed_with_retry_message(self) -> None:
        def broken():
            raise RuntimeError("provider unavailable")

        with self.assertRaisesRegex(VoiceCatalogUnavailable, "Retry"):
            VoiceCatalogAuthority(broken).load()

    def test_empty_or_duplicate_catalog_is_rejected(self) -> None:
        with self.assertRaises(VoiceCatalogUnavailable):
            EffectiveVoiceCatalog.from_payload({"items": []})
        item = {
            "assignment_key": "Đức Trí",
            "source_kind": "preset",
            "active": True,
            "usable": True,
            "selectable": True,
        }
        with self.assertRaisesRegex(VoiceCatalogUnavailable, "duplicate"):
            EffectiveVoiceCatalog.from_payload({"items": [item, item]})

    def test_require_raises_structured_issues(self) -> None:
        plan = {
            "narrator_voice_id": "missing",
            "utterances": [
                {
                    "utterance_id": "u1",
                    "sequence": 1,
                    "role": "narrator",
                    "resolved_voice_id": "missing",
                }
            ],
        }
        with self.assertRaises(VoiceEligibilityBlocked) as caught:
            require_casting_plan_eligible(plan, self.catalog, chapter_id=5, chapter_number=9)
        self.assertEqual(caught.exception.issues[0]["chapter_id"], 5)
        self.assertEqual(caught.exception.issues[0]["chapter_number"], 9)


if __name__ == "__main__":
    unittest.main()
