from __future__ import annotations

import unittest

from story_audio.text import (
    lexical_sha256,
    reflow_paragraphs,
    split_repair_blocks,
    split_tts_segments,
    restore_source_token_spelling,
    validate_lexical_identity,
)


class TextTests(unittest.TestCase):
    def test_reflow_repairs_hard_wrapped_sentence_without_changing_words(self) -> None:
        source = [
            "Toàn thân Hứa Thanh chấn động, khí tức tăng lên không",
            "ít.",
        ]
        result, issues = reflow_paragraphs(source, "Chương 1")
        self.assertEqual(result, "Toàn thân Hứa Thanh chấn động, khí tức tăng lên không ít.")
        self.assertFalse(issues)

    def test_reflow_removes_known_ad_with_audit_issue(self) -> None:
        result, issues = reflow_paragraphs(
            ["Nội dung thật.", "Bản dịch tại vip bachngocsach, vui lòng không copy!"],
            "Chương 1",
        )
        self.assertEqual(result, "Nội dung thật.")
        self.assertEqual(issues[0].code, "advertisement")

    def test_lexical_validator_allows_only_punctuation_and_space(self) -> None:
        source = "Trời mưa rất lớn hắn vẫn đi"
        repaired = "Trời mưa rất lớn, hắn vẫn đi."
        self.assertEqual(lexical_sha256(source), lexical_sha256(repaired))
        self.assertTrue(validate_lexical_identity(source, repaired)[0])
        self.assertFalse(validate_lexical_identity(source, "Trời mưa rất lớn, hắn vẫn bước đi.")[0])

    def test_gemini_capitalization_is_restored_to_source(self) -> None:
        source = "gió nổi lên trời bắt đầu mưa"
        repaired = "Gió nổi lên. Trời bắt đầu mưa."
        restored = restore_source_token_spelling(source, repaired)
        self.assertEqual(restored, "gió nổi lên. trời bắt đầu mưa.")
        self.assertTrue(validate_lexical_identity(source, restored)[0])

    def test_tts_segments_never_exceed_limit(self) -> None:
        text = " ".join(["Đây là một câu khá dài để kiểm tra việc chia đoạn hợp lý."] * 30)
        segments = split_tts_segments(text, maximum=256, target=230)
        self.assertGreater(len(segments), 1)
        self.assertTrue(all(0 < len(item) <= 256 for item in segments))
        self.assertTrue(validate_lexical_identity(text, " ".join(segments))[0])

    def test_repair_blocks_preserve_words(self) -> None:
        text = " ".join(["Một đoạn truyện có dấu câu đầy đủ."] * 200)
        blocks = split_repair_blocks(text, target=500, maximum=700)
        self.assertGreater(len(blocks), 2)
        self.assertTrue(all(len(block) <= 700 for block in blocks))
        self.assertTrue(validate_lexical_identity(text, " ".join(blocks))[0])


if __name__ == "__main__":
    unittest.main()
