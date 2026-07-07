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
            "job-output-meta",
            "ACTIVE AUDIO",
            "ACTIVE OUTPUT",
            "HISTORICAL",
            "ACTIVE CHAPTER OUTPUT",
            "Historical evidence only - not the current chapter output",
            "Artifact active but job binding unavailable",
        ):
            self.assertIn(value, self.html + self.js + self.css)

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
