from __future__ import annotations

import unittest
import unicodedata

from story_audio.text import (
    compare_bounded_orthographic_changes,
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

    def test_orthographic_compare_no_lexical_changes(self) -> None:
        result = compare_bounded_orthographic_changes("Trời mưa lớn hắn vẫn đi", "Trời mưa lớn, hắn vẫn đi.")
        self.assertTrue(result.qualifies)
        self.assertEqual(result.changed_cluster_count, 0)
        self.assertEqual(result.total_changed_source_tokens, 0)
        self.assertEqual(result.total_changed_candidate_tokens, 0)

    def test_orthographic_compare_single_accent_fix(self) -> None:
        result = compare_bounded_orthographic_changes("tiếng kèn vang lên", "tiếng kền vang lên")
        self.assertTrue(result.qualifies)
        self.assertEqual(result.changed_cluster_count, 1)
        self.assertEqual(result.clusters[0].source_tokens, ("kèn",))
        self.assertEqual(result.clusters[0].candidate_tokens, ("kền",))
        self.assertEqual(result.clusters[0].source_skeleton, "ken")
        self.assertTrue(result.clusters[0].skeletons_match)

    def test_orthographic_compare_repeated_accent_fix(self) -> None:
        result = compare_bounded_orthographic_changes("kền kèn", "kền kền")
        self.assertTrue(result.qualifies)
        self.assertEqual(result.changed_cluster_count, 1)
        self.assertEqual(result.total_changed_source_tokens, 1)
        self.assertEqual(result.total_changed_candidate_tokens, 1)

    def test_orthographic_compare_token_merge_qualifies(self) -> None:
        result = compare_bounded_orthographic_changes("thiế u", "thiếu")
        self.assertTrue(result.qualifies)
        self.assertEqual(result.clusters[0].source_tokens, ("thiế", "u"))
        self.assertEqual(result.clusters[0].candidate_tokens, ("thiếu",))

    def test_orthographic_compare_token_split_qualifies(self) -> None:
        result = compare_bounded_orthographic_changes("tră ng", "trắng")
        self.assertTrue(result.qualifies)
        self.assertEqual(result.clusters[0].source_skeleton, "trang")
        self.assertEqual(result.clusters[0].candidate_skeleton, "trang")

    def test_orthographic_compare_nfc_nfd_equivalence(self) -> None:
        source = "kền"
        candidate = unicodedata.normalize("NFD", source)
        result = compare_bounded_orthographic_changes(source, candidate)
        self.assertTrue(result.qualifies)
        self.assertEqual(result.changed_cluster_count, 0)

    def test_orthographic_compare_two_qualifying_clusters(self) -> None:
        result = compare_bounded_orthographic_changes("ken đứng ben", "kèn đứng bèn")
        self.assertTrue(result.qualifies)
        self.assertEqual(result.changed_cluster_count, 2)
        self.assertEqual(result.total_changed_source_tokens, 2)

    def test_orthographic_compare_rejects_more_than_two_clusters(self) -> None:
        result = compare_bounded_orthographic_changes("ken a ben b ten", "kèn a bèn b tèn")
        self.assertFalse(result.qualifies)
        self.assertEqual(result.reason_code, "changed_cluster_limit_exceeded")
        self.assertEqual(result.changed_cluster_count, 3)

    def test_orthographic_compare_rejects_cluster_larger_than_three_source_tokens(self) -> None:
        result = compare_bounded_orthographic_changes("x ab c d e y", "x abcde y")
        self.assertFalse(result.qualifies)
        self.assertEqual(result.reason_code, "cluster_source_token_limit_exceeded")

    def test_orthographic_compare_rejects_cluster_larger_than_three_candidate_tokens(self) -> None:
        result = compare_bounded_orthographic_changes("x abcde y", "x ab c d e y")
        self.assertFalse(result.qualifies)
        self.assertEqual(result.reason_code, "cluster_candidate_token_limit_exceeded")

    def test_orthographic_compare_rejects_more_than_four_total_source_tokens(self) -> None:
        result = compare_bounded_orthographic_changes("ken ben ten giữ mon son", "kèn bèn tèn giữ mòn sòn")
        self.assertFalse(result.qualifies)
        self.assertEqual(result.reason_code, "total_source_token_limit_exceeded")
        self.assertEqual(result.total_changed_source_tokens, 5)

    def test_orthographic_compare_rejects_more_than_four_total_candidate_tokens(self) -> None:
        result = compare_bounded_orthographic_changes("thieu giữ trang", "thi ế u giữ tra ng")
        self.assertFalse(result.qualifies)
        self.assertEqual(result.reason_code, "total_candidate_token_limit_exceeded")
        self.assertEqual(result.total_changed_candidate_tokens, 5)

    def test_orthographic_compare_rejects_semantic_substitution(self) -> None:
        result = compare_bounded_orthographic_changes("con chó chạy", "con mèo chạy")
        self.assertFalse(result.qualifies)
        self.assertEqual(result.reason_code, "skeleton_mismatch")

    def test_orthographic_compare_rejects_semantic_insertion(self) -> None:
        result = compare_bounded_orthographic_changes("hắn đi", "hắn đang đi")
        self.assertFalse(result.qualifies)
        self.assertEqual(result.reason_code, "semantic_insertion_or_deletion")

    def test_orthographic_compare_rejects_semantic_deletion(self) -> None:
        result = compare_bounded_orthographic_changes("hắn đang đi", "hắn đi")
        self.assertFalse(result.qualifies)
        self.assertEqual(result.reason_code, "semantic_insertion_or_deletion")

    def test_orthographic_compare_rejects_number_modification(self) -> None:
        result = compare_bounded_orthographic_changes("Có 12 người tới", "Có 13 người tới")
        self.assertFalse(result.qualifies)
        self.assertEqual(result.reason_code, "numbers_changed")

    def test_orthographic_compare_rejects_url_modification(self) -> None:
        result = compare_bounded_orthographic_changes(
            "Xem https://example.com/a rồi đi",
            "Xem https://example.com/b rồi đi",
        )
        self.assertFalse(result.qualifies)
        self.assertEqual(result.reason_code, "urls_changed")

    def test_orthographic_compare_rejects_structural_marker_modification(self) -> None:
        result = compare_bounded_orthographic_changes("[CHAPTER] tiếng kèn", "[TITLE] tiếng kèn")
        self.assertFalse(result.qualifies)
        self.assertEqual(result.reason_code, "protected_structural_markers_changed")

    def test_orthographic_compare_rejects_sentence_rewrite(self) -> None:
        result = compare_bounded_orthographic_changes("Hắn bước vào phòng yên lặng", "Nàng chạy khỏi núi ồn ào")
        self.assertFalse(result.qualifies)

    def test_orthographic_compare_rejects_reordered_words(self) -> None:
        result = compare_bounded_orthographic_changes("một hai ba", "ba hai một")
        self.assertFalse(result.qualifies)

    def test_current_lexical_validator_still_rejects_accent_fix(self) -> None:
        self.assertFalse(validate_lexical_identity("kèn", "kền")[0])


if __name__ == "__main__":
    unittest.main()
