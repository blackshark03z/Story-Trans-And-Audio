from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def resolve(payload: dict) -> dict:
    script = """
const resolver = require('./ui/production_state.js');
const input = JSON.parse(process.argv[1]);
const vm = resolver.resolveProductionState(input);
console.log(JSON.stringify({
  conceptualState: vm.conceptualState,
  currentStageKey: vm.currentStageKey,
  currentStageLabel: vm.currentStageLabel,
  completedStageKeys: vm.completedStageKeys,
  lockedStageKeys: vm.lockedStageKeys,
  primaryActionKey: vm.primaryActionKey,
  primaryActionLabel: vm.primaryActionLabel,
  mutationActionsMayBeDisplayed: vm.mutationActionsMayBeDisplayed,
  currentCount: vm.stages.filter(stage => stage.current).length,
  lockedCount: vm.stages.filter(stage => stage.locked).length,
  blockerReason: vm.blockerReason,
  targetPanel: vm.targetPanel,
}));
"""
    result = subprocess.run(
        ["node", "-e", script, json.dumps(payload, ensure_ascii=False)],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def base_state() -> dict:
    return {
        "book": {"id": 1},
        "chapter": {
            "id": 369,
            "book_id": 1,
            "chapter_number": 369,
            "active_text_revision_id": 738,
            "audio_status": "not_created",
        },
        "revisions": [{"id": 738, "status": "approved"}],
        "speakerDraft": {
            "id": 15,
            "status": "approved",
            "stale": False,
            "remaining_unreviewed_count": 0,
            "invalid_count": 0,
        },
        "casting": {
            "voice_profile": {"validation": {"valid": True}},
            "casting": {
                "id": 24,
                "status": "draft",
                "plan_revision": 1,
                "plan": {"utterances": [{"utterance_id": "u1", "resolved_voice_id": "custom:26"}]},
            },
        },
        "jobs": [],
        "active_output": {},
    }


class ProductionStateResolverTests(unittest.TestCase):
    def assert_state(self, payload: dict, state: str, stage: str) -> dict:
        vm = resolve(payload)
        self.assertEqual(vm["conceptualState"], state)
        self.assertEqual(vm["currentStageKey"], stage)
        self.assertEqual(vm["currentCount"], 1)
        return vm

    def test_no_scope_returns_no_scope(self) -> None:
        self.assert_state({}, "NO_SCOPE", "scope")

    def test_text_unavailable_or_unapproved_blocks_text(self) -> None:
        payload = base_state()
        payload["revisions"] = [{"id": 738, "status": "draft"}]
        self.assert_state(payload, "TEXT_BLOCKED", "text")

    def test_unresolved_speaker_exceptions_block_speaker_review(self) -> None:
        payload = base_state()
        payload["speakerDraft"] = {"id": 15, "status": "draft", "stale": False}
        self.assert_state(payload, "SPEAKER_EXCEPTIONS", "speakers")

    def test_missing_effective_voice_blocks_voice_configuration(self) -> None:
        payload = base_state()
        payload["voice"] = {"missingEffectiveVoiceCount": 1}
        self.assert_state(payload, "VOICE_BLOCKED", "voices")

    def test_draft_unapproved_casting_plan_goes_to_casting_review(self) -> None:
        vm = self.assert_state(base_state(), "CASTING_REVIEW", "voice_map")
        self.assertEqual(vm["primaryActionKey"], "REVIEW_FINAL_VOICE_MAP")
        self.assertEqual(vm["primaryActionLabel"], "Duyệt bản đồ giọng")

    def test_approved_plan_without_job_is_ready_to_prepare(self) -> None:
        payload = base_state()
        payload["casting"]["casting"]["status"] = "approved"
        self.assert_state(payload, "READY_TO_PREPARE", "prepare")

    def test_prepared_job_takes_render_stage(self) -> None:
        payload = base_state()
        payload["casting"]["casting"]["status"] = "approved"
        payload["jobs"] = [{"id": 20, "status": "prepared", "book_id": 1, "from_chapter": 369, "to_chapter": 369, "casting_plan_id": 24}]
        self.assert_state(payload, "PREPARED", "render")

    def test_running_job_takes_render_stage(self) -> None:
        payload = base_state()
        payload["jobs"] = [{"id": 20, "status": "running", "book_id": 1, "from_chapter": 369, "to_chapter": 369, "casting_plan_id": 24}]
        self.assert_state(payload, "RENDERING_OR_PAUSED", "render")

    def test_paused_job_takes_render_stage(self) -> None:
        payload = base_state()
        payload["jobs"] = [{"id": 20, "status": "paused", "book_id": 1, "from_chapter": 369, "to_chapter": 369, "casting_plan_id": 24}]
        self.assert_state(payload, "RENDERING_OR_PAUSED", "render")

    def test_rendered_output_without_human_qa_goes_to_qa(self) -> None:
        payload = base_state()
        payload["active_output"] = {"active_output_job_id": 20, "active_output_artifact_id": 75}
        self.assert_state(payload, "RENDERED_NOT_QA", "qa")

    def test_accepted_active_output_is_complete(self) -> None:
        payload = base_state()
        payload["active_output"] = {"active_output_job_id": 20, "active_output_artifact_id": 75}
        payload["human_approval"] = {"status": "approved"}
        vm = self.assert_state(payload, "COMPLETE", "qa")
        self.assertEqual(len(vm["completedStageKeys"]), 8)

    def test_contradictory_partial_data_is_unresolved(self) -> None:
        payload = base_state()
        payload["active_output"] = {"active_output_job_id": 20}
        vm = self.assert_state(payload, "STATE_UNRESOLVED", "scope")
        self.assertFalse(vm["mutationActionsMayBeDisplayed"])

    def test_prepared_job_precedes_changed_upstream_state(self) -> None:
        payload = base_state()
        payload["revisions"] = [{"id": 738, "status": "draft"}]
        payload["jobs"] = [{"id": 20, "status": "prepared", "book_id": 1, "from_chapter": 369, "to_chapter": 369, "casting_plan_id": 24}]
        self.assert_state(payload, "PREPARED", "render")

    def test_unknown_hash_scope_is_non_mutating_no_scope(self) -> None:
        script = """
const resolver = require('./ui/production_state.js');
const scope = resolver.productionScopeFromHash('#/unknown?book=1&chapter=369');
const vm = resolver.resolveProductionState({});
console.log(JSON.stringify({route: scope.route, explicit: scope.explicit, state: vm.conceptualState, action: vm.primaryActionKey}));
"""
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True, cwd=str(ROOT), encoding="utf-8")
        self.assertEqual(json.loads(result.stdout), {"route": "unknown", "explicit": False, "state": "NO_SCOPE", "action": "SELECT_SCOPE"})


if __name__ == "__main__":
    unittest.main()
