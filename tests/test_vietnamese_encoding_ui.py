from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOJIBAKE_MARKERS = ("Ã", "Ä", "Æ", "á»", "áº", "\ufffd")
USER_FACING_FILES = (
    "ui/index.html",
    "ui/app.js",
    "ui/casting_voice_map.js",
    "ui/production_state.js",
    "ui/styles.css",
    "story_audio/api.py",
    "story_audio/pipeline.py",
    "CHANGELOG.md",
    "PROJECT_STATUS.md",
    ".ai/STATE.md",
)


class VietnameseEncodingUiTests(unittest.TestCase):
    def test_primary_sources_are_utf8_without_mojibake(self) -> None:
        for relative in USER_FACING_FILES:
            raw = (ROOT / relative).read_bytes()
            text = raw.decode("utf-8", errors="strict")
            for marker in MOJIBAKE_MARKERS:
                self.assertNotIn(marker, text, f"{relative} contains {marker!r}")

    def test_charset_precedes_text_and_assets_are_cache_versioned(self) -> None:
        html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index('<meta charset="utf-8">'), html.index("<title>"))
        self.assertIn("styles.css?v=20260727-production-preflight-1", html)
        self.assertIn("production_state.js?v=20260727-production-preflight-1", html)
        self.assertIn("app.js?v=20260729-golden-journey-3", html)

    def test_operator_phase_copy_renders_as_unicode(self) -> None:
        script = """
const resolver = require('./ui/production_state.js');
const states = ['NO_SCOPE','TEXT_BLOCKED','SPEAKER_EXCEPTIONS','VOICE_BLOCKED','CASTING_REVIEW','READY_TO_PREPARE','PREPARED','RENDERING_OR_PAUSED','RENDERED_NOT_QA','COMPLETE'];
console.log(JSON.stringify(resolver.PHASES.map(item => item.label)));
"""
        result = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            encoding="utf-8",
        )
        self.assertEqual(
            json.loads(result.stdout),
            ["Ch\u1ecdn ch\u01b0\u01a1ng", "X\u00e1c nh\u1eadn n\u1ed9i dung v\u00e0 ng\u01b0\u1eddi n\u00f3i", "G\u00e1n v\u00e0 duy\u1ec7t gi\u1ecdng", "Chu\u1ea9n b\u1ecb v\u00e0 render", "Nghe v\u00e0 duy\u1ec7t", "Ho\u00e0n t\u1ea5t v\u00e0 t\u1ea3i xu\u1ed1ng"],
        )
