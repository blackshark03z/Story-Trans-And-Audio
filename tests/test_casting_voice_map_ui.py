from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CastingVoiceMapUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.app_js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.voice_map_js = (ROOT / "ui" / "casting_voice_map.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")

    def test_final_voice_map_loads_after_app_and_uses_central_catalog_helpers(self) -> None:
        self.assertIn('/assets/app.js', self.html)
        self.assertIn('/assets/casting_voice_map.js', self.html)
        self.assertLess(
            self.html.index('/assets/app.js'),
            self.html.index('/assets/casting_voice_map.js'),
        )
        for value in (
            "voiceCatalogState",
            "voiceCatalogItem",
            "selectedVoiceProvenance",
            "state?.casting?.casting?.plan",
        ):
            self.assertIn(value, self.voice_map_js)

    def test_final_voice_map_summary_and_provenance_surfaces_exist(self) -> None:
        for value in (
            'id="flowVoiceMapCatalogNote"',
            'id="flowVoiceUsageSummary"',
            "voice-usage-summary",
            "voice-usage-card",
            "voice-provenance",
        ):
            self.assertIn(value, self.html + self.css)
        self.assertIn("renderUsageSummary", self.voice_map_js)
        self.assertIn("effective_revision_source", self.app_js)
        self.assertIn("effective revision #", self.app_js)

    def test_voice_map_preserves_speaker_identity_and_unknown_fallback_semantics(self) -> None:
        for value in (
            "Speaker identity remains separate from voice selection.",
            "speakerName(utterance.role, utterance.character_id)",
            "utterance.role === 'unknown'",
            "unknown fallback",
            "resolution_source || resolution?.source",
        ):
            self.assertIn(value, self.voice_map_js)
        self.assertNotIn("character_id=voice", self.voice_map_js)
        self.assertNotIn("gender=voice", self.voice_map_js)

    def test_unavailable_legacy_voice_is_preserved_and_flagged(self) -> None:
        for value in (
            "Legacy / unavailable",
            "Giá trị cũ được giữ nguyên",
            "Giọng không khả dụng",
            "không tự thay thế",
        ):
            self.assertIn(value, self.app_js + self.voice_map_js)

    def test_overlay_adds_no_mutating_or_provider_endpoints(self) -> None:
        forbidden = (
            "method:'POST'",
            'method:"POST"',
            "method:'PUT'",
            'method:"PUT"',
            "method:'PATCH'",
            "/api/jobs",
            "/api/voice-previews",
            "/api/custom-voices",
            "approveCastingPlan()",
            "saveCastingDraft()",
            "renderCastingPlan()",
        )
        for value in forbidden:
            self.assertNotIn(value, self.voice_map_js)

    def test_prepare_start_and_qa_remain_outside_casting_review(self) -> None:
        self.assertIn('data-production-owned-stage="voice_map"', self.html)
        self.assertIn('id="flowStepRenderChapter" class="flow-step-panel hidden" data-production-owned-stage="prepare render"', self.html)
        self.assertIn('id="flowStepReviewAudio" class="flow-step-panel hidden" data-production-owned-stage="qa"', self.html)
        self.assertNotIn('data-production-owned-stage="voice_map prepare"', self.html)


if __name__ == "__main__":
    unittest.main()
