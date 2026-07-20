from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def node_json(script: str) -> dict:
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        encoding="utf-8",
    )
    return json.loads(result.stdout)


class ContextualVoiceDetourUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.app_js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.detour_js = (ROOT / "ui" / "contextual_voice_detour.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")

    def test_detour_asset_loads_after_app_and_casting_overlay(self) -> None:
        self.assertIn("/assets/contextual_voice_detour.js", self.html)
        self.assertLess(self.html.index("/assets/app.js"), self.html.index("/assets/contextual_voice_detour.js"))
        self.assertLess(self.html.index("/assets/casting_voice_map.js"), self.html.index("/assets/contextual_voice_detour.js"))

    def test_context_contract_supports_required_origins_and_safe_storage(self) -> None:
        for value in (
            "storyAudio.voiceDetour.v1",
            "sessionStorage",
            "book_profile",
            "character_override",
            "casting_plan",
            "production_voice_blocker",
            "create_voice",
            "choose_voice",
            "configure_book_voice",
            "configure_character_override",
            "MAX_AGE_MS",
            "sanitizeDraft",
        ):
            self.assertIn(value, self.detour_js)
        self.assertNotIn("localStorage", self.detour_js)
        self.assertNotIn("returnUrl", self.detour_js)

    def test_valid_context_serializes_and_invalid_context_is_rejected(self) -> None:
        data = node_json(
            """
const detour = require('./ui/contextual_voice_detour.js');
const valid = detour.normalizeContext({
  originRoute: 'production',
  returnRoute: 'production',
  destination: 'voices',
  originType: 'book_profile',
  operation: 'create_voice',
  fieldId: 'profileNarratorVoice',
  bookId: 1,
  chapterId: 2,
  createdAt: 1000,
}, 1000);
console.log(JSON.stringify({
  validRoute: detour.routeHash('production', valid),
  externalRouteRejected: detour.normalizeContext({...valid, returnRoute: 'https://bad.invalid'}, 1000) === null,
  badOriginRejected: detour.normalizeContext({...valid, originType: 'freeform'}, 1000) === null,
  badFieldRejected: detour.normalizeContext({...valid, fieldId: 'saveCastingDraft'}, 1000) === null,
  expiredRejected: detour.normalizeContext({...valid, createdAt: 1}, 1 + detour.MAX_AGE_MS + 1) === null,
}));
"""
        )
        self.assertEqual(data["validRoute"], "#/production?book=1&chapter=2")
        self.assertTrue(data["externalRouteRejected"])
        self.assertTrue(data["badOriginRejected"])
        self.assertTrue(data["badFieldRejected"])
        self.assertTrue(data["expiredRejected"])

    def test_contextual_entry_points_are_injected_without_duplicating_modules(self) -> None:
        for value in (
            "enhanceProfileFields",
            "enhanceCharacterFields",
            "enhanceCastingPlan",
            "data-voice-detour",
            "Thêm giọng mới",
            "Quản lý giọng",
            "Quản lý giọng nhân vật",
            "Quản lý giọng trong Thư viện",
            "Cấu hình giọng còn thiếu",
        ):
            self.assertIn(value, self.detour_js)
        self.assertEqual(self.html.count("custom-voice-library-panel"), 1)
        self.assertEqual(self.html.count('id="booksView"'), 1)
        self.assertEqual(self.html.count('id="productionView"'), 1)

    def test_return_refreshes_catalog_resolver_and_preserves_explicit_save_boundaries(self) -> None:
        for value in (
            "await refreshCatalog()",
            "await root.openChapter(context.chapterId, {initialTab:'casting', replaceScopeRoute:true})",
            "await root.openCasting()",
            "applyUnsavedPreselection",
            "voiceDetourUnsaved",
            "Hãy kiểm tra rồi bấm Lưu",
            "Final Voice Map changed; the stale voice edit was not applied.",
        ):
            self.assertIn(value, self.detour_js)
        forbidden = (
            "saveVoiceProfile(",
            "saveCharacter(",
            "saveCastingDraft(",
            "approveCastingPlan(",
            "renderCastingPlan(",
            "/api/jobs",
            "/api/voice-previews",
            "generateTestAudio(",
        )
        for value in forbidden:
            self.assertNotIn(value, self.detour_js)

    def test_library_mutation_hooks_reload_catalog_but_do_not_preview_or_tts(self) -> None:
        for value in (
            "createLibraryVoice",
            "uploadLibraryRevision",
            "setPreferredSynthesisRevision",
            "afterVoiceMutation",
            "targetVoiceUsable",
        ):
            self.assertIn(value, self.detour_js)
        self.assertIn("/api/voice-catalog", self.app_js)
        for forbidden in ("previewVoice", "previewPresetVoice", "libraryGenerateTestAudio", "tts", "Gemini"):
            self.assertNotIn(forbidden, self.detour_js)

    def test_cancel_and_stale_context_clear_without_mutation(self) -> None:
        for value in (
            "clearContext()",
            "cancel = false",
            "Đã hủy đường vòng",
            "Return context is malformed or expired.",
            "Source chapter changed during the detour.",
            "The voice is not selectable yet.",
        ):
            self.assertIn(value, self.detour_js)
        self.assertIn(".voice-detour-banner", self.css)
        self.assertIn(".voice-detour-unsaved-note", self.css)

    def test_no_chapter_369_or_later_milestone_hardcoding(self) -> None:
        changed_ui = self.detour_js + self.css
        for forbidden in ("369", "Chapter 369", "range readiness", "batch", "Audio Library"):
            self.assertNotIn(forbidden, changed_ui)


if __name__ == "__main__":
    unittest.main()
