from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tests.base import IsolatedTestCase


ROOT = Path(__file__).resolve().parents[1]


class ActiveOutputUiTests(IsolatedTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")

    def test_ui_contract_mentions_active_audio_and_historical_jobs(self) -> None:
        for value in (
            "chapterAudioMeta",
            "chapter-title-wrap",
            "chapter-title-meta",
            "chapter-casting-meta",
            "Mở quy trình sản xuất",
            "CASTING REVIEW NEEDED",
            "CASTING APPROVED",
            "job-output-meta",
            "ACTIVE AUDIO",
            "ACTIVE OUTPUT",
            "HISTORICAL",
            "ACTIVE CHAPTER OUTPUT",
            "Historical evidence only - not the current chapter output",
            "Artifact active but job binding unavailable",
            "Open current Production Flow",
            "Current active audio: Job",
            "Current playback still uses the active historical plan until a new job is rendered",
            "Nâng cao / Gỡ lỗi: dùng phần này để xem job hiện tại hoặc job lịch sử.",
            "Nâng cao / Gỡ lỗi: segment attempts chỉ dùng để xử lý lỗi audio cụ thể sau QA",
        ):
            self.assertIn(value, self.html + self.js + self.css)

    def test_chapter_summary_mentions_direct_character_voices_cta(self) -> None:
        for value in (
            "data-open-casting",
            "initialTab:'casting'",
            "openCastingShortcut",
            "casting-tab-shortcut",
            "castingPlanIdentity",
            "Quy trình sản xuất",
        ):
            self.assertIn(value, self.js + self.html + self.css)

    def test_active_output_and_plan_identity_are_explained_in_character_voices(self) -> None:
        for value in (
            "Technical: Casting Plan #",
            "Current active audio: Job",
            "Render / Production Output",
            "Historical Job",
            "Bản đồ giọng cuối đã duyệt này là bản Render / Production Output sẽ dùng cho đến khi có một plan mới hơn được duyệt.",
            "Đây là nguồn sự thật trước khi tạo audio.",
            "Chỉ dùng phần này sau khi Casting Plan đã được duyệt.",
            "Đây là bản đồ giọng cuối mà hệ thống sẽ dùng khi tạo audio.",
        ):
            self.assertIn(value, self.html + self.js)

    def test_chapter_ui_mentions_operator_flow_and_next_action(self) -> None:
        for value in (
            "Bắt đầu ở đây",
            "Quy trình sản xuất",
            "Bước nên làm tiếp theo",
            "productionFlowStepper",
            "productionFlowBack",
            "productionFlowContinue",
            "productionFlowNext",
            "productionFlowStepTitle",
            "productionFlowStepStatus",
            "productionFlowBlockedReason",
            "castingRecommendedActionTitle",
            "castingRecommendedActionBody",
            "castingRecommendedActionState",
            "PRODUCTION_FLOW_STEPS",
            "title:'Chọn chương'",
            "title:'Nghe kiểm tra / Chốt bản cuối'",
        ):
            self.assertIn(value, self.html + self.js + self.css)

    def test_active_audio_state_does_not_push_normal_rerender_path(self) -> None:
        for value in (
            "Chương này đã có audio; hãy dùng QA hoặc replacement workflow thay vì render thường.",
            "Hãy mở active artifact, listening checklist, và segment QA chỉ cho các lỗi thật sự cụ thể.",
            "Chốt bản audio cuối",
        ):
            self.assertIn(value, self.html + self.js)

    def test_primary_operator_flow_emphasizes_main_steps_over_debug(self) -> None:
        for value in (
            "Chọn chương",
            "Kiểm tra văn bản",
            "Gán giọng",
            "Duyệt bản đồ giọng cuối",
            "Tạo audio chương",
            "Nghe kiểm tra / Chốt bản cuối",
            "Nâng cao / Gỡ lỗi: công cụ nháp AI cho người nói",
            "Nâng cao / Gỡ lỗi: QA và xử lý sự cố segment",
        ):
            self.assertIn(value, self.html + self.js)

    def test_chapter_summary_prefers_artifact_binding_metadata(self) -> None:
        script = r"""
function chapterStatusSummary(chapter){if(chapter.active_output_has_trustworthy_binding&&chapter.active_output_job_id){const plan=chapter.active_output_casting_plan_revision?` | Plan v${chapter.active_output_casting_plan_revision}`:'';return {label:'ACTIVE AUDIO',className:'active-output',meta:`Job #${chapter.active_output_job_id}${plan}`}}if(chapter.audio_status==='completed')return {label:'HAS AUDIO',className:'done',meta:'Artifact active but job binding unavailable'};if(chapter.qa_count)return {label:`${chapter.qa_count} QA`,className:'',meta:''};return {label:'NOT RENDERED',className:'',meta:''}}
console.log(JSON.stringify({
  active: chapterStatusSummary({active_output_has_trustworthy_binding:true,active_output_job_id:7,active_output_casting_plan_revision:6,audio_status:'completed',qa_count:0}),
  fallback: chapterStatusSummary({active_output_has_trustworthy_binding:false,active_output_job_id:null,audio_status:'completed',qa_count:0}),
  pending: chapterStatusSummary({audio_status:'pending',qa_count:0}),
}));
"""
        result = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["active"]["label"], "ACTIVE AUDIO")
        self.assertEqual(payload["active"]["meta"], "Job #7 | Plan v6")
        self.assertEqual(payload["fallback"]["label"], "HAS AUDIO")
        self.assertEqual(payload["pending"]["label"], "NOT RENDERED")

    def test_job_output_helper_distinguishes_active_from_historical(self) -> None:
        script = r"""
function outputBadge(job){if(job.is_active_output)return '<span class="badge active-output">ACTIVE OUTPUT</span>';if(job.is_historical_output)return '<span class="badge historical">HISTORICAL</span>';return ''}
function jobOutputMeta(job){if(job.is_active_output&&job.active_output_chapters?.length){const chapter=job.active_output_chapters[0],plan=chapter.active_output_casting_plan_revision?` | Plan v${chapter.active_output_casting_plan_revision}`:'';return `Active chapter output: ${chapter.chapter_number}. ${chapter.chapter_title}${plan}`}if(job.is_historical_output)return 'Historical evidence only - not the current chapter output';return ''}
console.log(JSON.stringify({
  activeBadge: outputBadge({is_active_output:true,is_historical_output:false}),
  historicalBadge: outputBadge({is_active_output:false,is_historical_output:true}),
  activeMeta: jobOutputMeta({is_active_output:true,active_output_chapters:[{chapter_number:357,chapter_title:'Chapter 357',active_output_casting_plan_revision:6}]}),
  historicalMeta: jobOutputMeta({is_active_output:false,is_historical_output:true}),
}));
"""
        result = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        payload = json.loads(result.stdout)
        self.assertIn("ACTIVE OUTPUT", payload["activeBadge"])
        self.assertIn("HISTORICAL", payload["historicalBadge"])
        self.assertEqual(payload["activeMeta"], "Active chapter output: 357. Chapter 357 | Plan v6")
        self.assertEqual(payload["historicalMeta"], "Historical evidence only - not the current chapter output")


if __name__ == "__main__":
    import unittest

    unittest.main()
