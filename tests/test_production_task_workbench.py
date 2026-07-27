from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def resolve(payload: dict) -> dict:
    script = """
const resolver = require('./ui/production_state.js');
const vm = resolver.resolveProductionState(JSON.parse(process.argv[1]));
console.log(JSON.stringify(vm));
"""
    result = subprocess.run(
        ["node", "-e", script, json.dumps(payload, ensure_ascii=False)],
        cwd=str(ROOT),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def base_payload() -> dict:
    return {
        "book": {"id": 1},
        "chapter": {
            "id": 501,
            "book_id": 1,
            "chapter_number": 401,
            "title": "Chương kiểm thử",
            "active_text_revision_id": 8001,
            "audio_status": "not_created",
        },
        "revisions": [{"id": 8001, "status": "approved"}],
        "speakerDraft": {
            "id": 31,
            "status": "approved",
            "stale": False,
            "remaining_unreviewed_count": 0,
            "invalid_count": 0,
        },
        "casting": {
            "voice_profile": {"validation": {"valid": True}},
            "casting": {
                "id": 41,
                "status": "draft",
                "plan": {"utterances": [{"utterance_id": "u1", "resolved_voice_id": "voice:test"}]},
            },
        },
        "jobs": [],
        "active_output": {},
    }


class ProductionTaskWorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")

    def test_pure_view_model_exposes_task_contract(self) -> None:
        vm = resolve(base_payload())
        self.assertEqual(
            set(
                (
                    "user_stage",
                    "task_type",
                    "task_title",
                    "task_summary",
                    "affected_chapter",
                    "primary_action",
                    "secondary_links",
                    "blocker",
                    "technical_details",
                    "next_task_after_success",
                )
            ).difference(vm),
            set(),
        )
        self.assertEqual(vm["user_stage"], 3)
        self.assertEqual(vm["task_type"], "REVIEW_VOICE_MAP")
        self.assertEqual(vm["primary_action"]["label"], "Duyệt và tiếp tục")

    def test_speaker_draft_states_have_one_imperative_action(self) -> None:
        payload = base_payload()
        payload["casting"] = {"voice_profile": {"validation": {"valid": True}}, "casting": {}}
        payload["speakerDraft"] = None
        vm = resolve(payload)
        self.assertEqual(vm["task_type"], "CREATE_SPEAKER_PROPOSAL")
        self.assertEqual(vm["primary_action"]["label"], "Tạo đề xuất người nói")

        payload["speakerDraft"] = {
            "id": 31,
            "status": "draft",
            "stale": False,
            "remaining_unreviewed_count": 0,
            "invalid_count": 0,
        }
        vm = resolve(payload)
        self.assertEqual(vm["task_type"], "CONFIRM_SPEAKER_REVIEW")
        self.assertEqual(vm["primary_action"]["label"], "Xác nhận và tiếp tục")

    def test_prepare_start_running_retry_and_qa_actions_are_separate(self) -> None:
        payload = base_payload()
        payload["casting"]["casting"]["status"] = "approved"
        self.assertEqual(resolve(payload)["primary_action"]["key"], "PREPARE_RANGE")
        payload["jobs"] = [{"id": 1, "status": "prepared", "book_id": 1, "from_chapter": 401, "to_chapter": 401, "casting_plan_id": 41}]
        self.assertEqual(resolve(payload)["primary_action"]["key"], "START_RENDER")
        payload["jobs"][0].update({"status": "running", "actions": {"can_retry": False}})
        self.assertEqual(resolve(payload)["primary_action"]["key"], "MONITOR_RENDER")
        payload["jobs"][0].update({"status": "failed", "actions": {"can_retry": True}, "is_historical_output": False})
        self.assertEqual(resolve(payload)["primary_action"]["key"], "RETRY_RENDER")
        payload["jobs"] = []
        payload["active_output"] = {"active_output_job_id": 1, "active_output_artifact_id": 2}
        self.assertIsNone(resolve(payload)["primary_action"])

    def test_workbench_replaces_visible_all_in_one_architecture(self) -> None:
        for element_id in (
            "productionRangeContext",
            "productionWorkbench",
            "productionChapterQueue",
            "productionTaskWorkspace",
            "productionTaskContent",
            "productionTechnicalDetails",
        ):
            self.assertEqual(self.html.count(f'id="{element_id}"'), 1)
        self.assertEqual(self.html.count('id="productionPrimaryAction"'), 1)
        self.assertIn('id="productionQaNeedsFixes"', self.html)
        self.assertIn('id="productionQaAccept"', self.html)
        self.assertIn("runProductionPrimaryAction", self.js)
        self.assertIn("renderProductionQueue", self.js)
        self.assertIn("production-workbench", self.css)

    def test_advanced_and_technical_controls_are_progressively_disclosed(self) -> None:
        self.assertIn("Chi tiết kỹ thuật", self.html)
        self.assertIn("Tùy chọn nâng cao", self.js)
        self.assertIn("người nói đã xác nhận", self.js)
        self.assertNotIn("Casting Plan #", self.html[self.html.index('id="productionView"'):self.html.index('id="assignmentView"')])

    def test_one_primary_action_never_chains_two_mutations(self) -> None:
        self.assertIn("if(action==='CONFIRM_SPEAKER_REVIEW'){await approveSpeakerReview();return}", self.js)
        self.assertNotIn("await approveSpeakerReview();await createSpeakerReviewCastingPlan()", self.js)
        self.assertIn("restoreProductionRangeScope({...state.productionRange,chapterId:null})", self.js)


if __name__ == "__main__":
    unittest.main()
