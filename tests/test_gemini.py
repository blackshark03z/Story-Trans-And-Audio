from __future__ import annotations

import json
import unittest
import unicodedata
from unittest.mock import patch

from story_audio.gemini import GeminiRepairError, repair_punctuation


class FakeGeminiResponse:
    def __init__(self, *, block_id: str, repaired_text: str | None = None, raw_text: str | None = None):
        if raw_text is None:
            raw_text = json.dumps(
                {"block_id": block_id, "repaired_text": repaired_text},
                ensure_ascii=False,
            )
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": raw_text}]
                    }
                }
            ]
        }
        self.body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self.body


class GeminiRepairResponseTests(unittest.TestCase):
    def repair(self, source: str, candidate: str, *, block_id: str = "b1") -> str:
        with patch(
            "story_audio.gemini.urllib.request.urlopen",
            return_value=FakeGeminiResponse(block_id=block_id, repaired_text=candidate),
        ):
            result = repair_punctuation(
                api_key="fake-key",
                model="fake-model",
                block_id=block_id,
                text=source,
                max_attempts=1,
            )
        return result.text

    def assert_rejected(self, source: str, candidate: str) -> None:
        with self.assertRaises(GeminiRepairError):
            self.repair(source, candidate)

    def test_punctuation_only_succeeds(self) -> None:
        self.assertEqual(self.repair("Trời mưa hắn đi", "Trời mưa, hắn đi."), "Trời mưa, hắn đi.")

    def test_lexically_identical_succeeds(self) -> None:
        self.assertEqual(self.repair("Trời mưa", "Trời mưa"), "Trời mưa")

    def test_punctuation_case_change_restores_source_spelling(self) -> None:
        self.assertEqual(
            self.repair("giÃ³ ná»•i lÃªn trá»i báº¯t Ä‘áº§u mÆ°a", "GiÃ³ ná»•i lÃªn. Trá»i báº¯t Ä‘áº§u mÆ°a."),
            "giÃ³ ná»•i lÃªn. trá»i báº¯t Ä‘áº§u mÆ°a.",
        )

    def test_repeated_accent_fix_succeeds(self) -> None:
        self.assertEqual(self.repair("kền kèn", "kền kền"), "kền kền")

    def test_single_accent_fix_succeeds(self) -> None:
        self.assertEqual(self.repair("kèn", "kền"), "kền")

    def test_token_merge_succeeds(self) -> None:
        self.assertEqual(self.repair("thiế u", "thiếu"), "thiếu")

    def test_nfc_nfd_only_spelling_succeeds(self) -> None:
        source = "kền"
        candidate = unicodedata.normalize("NFD", source)
        self.assertEqual(self.repair(source, candidate), source)

    def test_semantic_substitution_is_rejected(self) -> None:
        self.assert_rejected("con chó chạy", "con mèo chạy")

    def test_semantic_insertion_is_rejected(self) -> None:
        self.assert_rejected("hắn đi", "hắn đang đi")

    def test_semantic_deletion_is_rejected(self) -> None:
        self.assert_rejected("hắn đang đi", "hắn đi")

    def test_number_modification_is_rejected(self) -> None:
        self.assert_rejected("Có 12 người tới", "Có 13 người tới")

    def test_url_modification_is_rejected(self) -> None:
        self.assert_rejected("Xem https://example.com/a rồi đi", "Xem https://example.com/b rồi đi")

    def test_sentence_rewrite_is_rejected(self) -> None:
        self.assert_rejected("Hắn bước vào phòng yên lặng", "Nàng chạy khỏi núi ồn ào")

    def test_cluster_limit_exceeding_is_rejected(self) -> None:
        self.assert_rejected("ken a ben b ten", "kèn a bèn b tèn")

    def test_json_and_block_id_validation_are_unchanged(self) -> None:
        with patch(
            "story_audio.gemini.urllib.request.urlopen",
            return_value=FakeGeminiResponse(block_id="b1", raw_text="{"),
        ):
            with self.assertRaises(GeminiRepairError):
                repair_punctuation(
                    api_key="fake-key",
                    model="fake-model",
                    block_id="b1",
                    text="Trời mưa",
                    max_attempts=1,
                )
        with patch(
            "story_audio.gemini.urllib.request.urlopen",
            return_value=FakeGeminiResponse(block_id="wrong", repaired_text="Trời mưa."),
        ):
            with self.assertRaisesRegex(GeminiRepairError, "block_id"):
                repair_punctuation(
                    api_key="fake-key",
                    model="fake-model",
                    block_id="b1",
                    text="Trời mưa",
                    max_attempts=1,
                )

    def test_bounded_candidate_text_is_returned_without_source_spelling_restore(self) -> None:
        self.assertEqual(self.repair("kền kèn", "kền kền."), "kền kền.")


if __name__ == "__main__":
    unittest.main()
