from __future__ import annotations

from pathlib import Path

from tests.base import IsolatedTestCase


class CurrentQaAudioIdentityUiTests(IsolatedTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        root = Path(__file__).resolve().parents[1]
        cls.js = (root / "ui" / "app.js").read_text(encoding="utf-8")

    def test_current_and_comparison_audio_have_unambiguous_labels(self) -> None:
        for text in (
            "Bản thay thế mới nhất",
            "Bản audio mới nhất",
            "Thay cho bản trước đã được đánh dấu Cần sửa",
            "Nghe bản trước để so sánh",
            "Bản cũ — chỉ để so sánh",
            "Đánh giá bên dưới vẫn áp dụng cho bản thay thế mới nhất.",
            "Quay lại bản mới nhất",
        ):
            self.assertIn(text, self.js)

    def test_comparison_mode_does_not_change_the_qa_command_target(self) -> None:
        target_start = self.js.index("function currentProductionQaCommandTarget")
        target_end = self.js.index("async function updateHumanApproval", target_start)
        target = self.js[target_start:target_end]
        self.assertIn("qa.artifact_id", target)
        self.assertNotIn("productionQaComparisonArtifactId", target)
