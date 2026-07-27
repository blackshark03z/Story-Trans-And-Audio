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
        self.assertIn("styles.css?v=20260727-task-workbench-1", html)
        self.assertIn("production_state.js?v=20260727-task-workbench-1", html)
        self.assertIn("app.js?v=20260727-task-workbench-1", html)

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
            ["Chọn chương", "Xác nhận nội dung và người nói", "Gán và duyệt giọng", "Chuẩn bị và render", "Nghe và duyệt"],
        )
