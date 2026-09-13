from __future__ import annotations

from pathlib import Path

from tests.base import IsolatedTestCase


class CurrentQaAudioIdentityUiTests(IsolatedTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        root = Path(__file__).resolve().parents[1]
        cls.js = (root / "ui" / "app.js").read_text(encoding="utf-8")
        cls.html = (root / "ui" / "index.html").read_text(encoding="utf-8")

    def test_only_current_audio_identity_is_shown(self) -> None:
        for text in (
            "Bản thay thế mới nhất",
            "Bản audio mới nhất",
            "Bản thay thế mới đang chờ duyệt",
            "Bản trước đã được xóa",
        ):
            self.assertIn(text, self.js)
        for text in ("Nghe bản trước để so sánh", "Bản cũ — chỉ để so sánh", "setProductionQaComparison"):
            self.assertNotIn(text, self.js)

    def test_comparison_mode_does_not_change_the_qa_command_target(self) -> None:
        target_start = self.js.index("function currentProductionQaCommandTarget")
        target_end = self.js.index("async function updateHumanApproval", target_start)
        target = self.js[target_start:target_end]
        self.assertIn("qa.artifact_id", target)
        self.assertNotIn("productionQaComparisonArtifactId", target)

    def test_machine_findings_use_one_chapter_repair_request_path(self) -> None:
        for text in (
            "addMachineFindingsToHumanQa",
            "selectedMachineFindings",
            "automatedAudioQaCreateRepairRequest",
            "Một bản sửa cho cả chương",
            "Tạo yêu cầu sửa cho ${selected.length} điểm",
            "discardMachineRepairCandidate",
            "acceptMachineRepairCandidate",
            "/machine-repair-candidate",
            "Đã khôi phục bản sửa thử chưa quyết định",
        ):
            self.assertIn(text, self.html + self.js)
        self.assertNotIn("createMachineRepairCandidate", self.js)
        self.assertNotIn("addMachineFindingToHumanQa", self.js)
        self.assertNotIn("automated-audio-qa-repair-action", self.js)

    def test_saved_bulk_markers_and_machine_issue_labels_survive_review(self) -> None:
        self.assertIn("function savedAudioQaMarkers", self.js)
        self.assertIn("state.audioQa.markers=savedAudioQaMarkers(item)", self.js)
        self.assertIn("function repairRiskLabel", self.js)
        for label in ("Clipping", "Khoảng nghỉ dài", "Âm lượng không đều"):
            self.assertIn(label, self.js)
        self.assertIn("bound.issue||repairIssueFromRisk(bound.risk_kind)", self.js)

    def test_repair_plan_does_not_default_to_speed_change(self) -> None:
        self.assertIn("speed=Number(source.global_speed_target||1)", self.js)
        self.assertIn("source=Number(draft.evidence_id||0)>0?draft:Number(plan.evidence_id||0)>0?plan:feedback", self.js)
        self.assertNotIn("speed=Number(feedback.global_speed_target||1.25)", self.js)
        self.assertIn("feedback.global_speed_target||'1'", self.js)

    def test_only_machine_findings_with_a_deterministic_repair_are_selectable(self) -> None:
        self.assertIn("point?.repair?.supported===true", self.js)
