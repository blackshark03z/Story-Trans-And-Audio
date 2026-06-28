"""
Custom Voice Preview UI contract tests.

Validates static frontend contracts without fragile full-file snapshots.
"""
import os
import re
import unittest
from pathlib import Path


class CustomVoicePreviewUIContractTests(unittest.TestCase):
    """Static UI contract validation for Custom Voice Preview frontend."""

    @classmethod
    def setUpClass(cls):
        """Load frontend files once."""
        repo_root = Path(__file__).parent.parent
        cls.html_path = repo_root / "ui" / "index.html"
        cls.js_path = repo_root / "ui" / "app.js"

        if not cls.html_path.exists():
            raise FileNotFoundError(f"HTML not found: {cls.html_path}")
        if not cls.js_path.exists():
            raise FileNotFoundError(f"JavaScript not found: {cls.js_path}")

        cls.html = cls.html_path.read_text(encoding="utf-8")
        cls.js = cls.js_path.read_text(encoding="utf-8")

    def test_custom_voice_selector_exists(self):
        """Custom voice selector element exists in HTML."""
        self.assertIn('id="customVoiceSelect"', self.html)

    def test_custom_revision_selector_exists(self):
        """Custom revision selector element exists in HTML."""
        self.assertIn('id="customRevisionSelect"', self.html)

    def test_load_custom_voices_button_exists(self):
        """Load custom voices button exists in HTML."""
        self.assertIn('id="loadCustomVoices"', self.html)

    def test_preview_custom_voice_button_exists(self):
        """Preview custom voice button exists in HTML."""
        self.assertIn('id="previewCustomVoice"', self.html)

    def test_custom_voice_preview_audio_element_exists(self):
        """Custom voice preview audio element exists in HTML."""
        self.assertIn('id="customVoicePreviewAudio"', self.html)

    def test_custom_voice_preview_status_element_exists(self):
        """Custom voice preview status element exists in HTML."""
        self.assertIn('id="customVoicePreviewStatus"', self.html)

    def test_custom_voice_preview_box_exists(self):
        """Custom voice preview box container exists in HTML."""
        self.assertIn('id="customVoicePreviewBox"', self.html)

    def test_no_duplicate_custom_voice_dom_ids(self):
        """No duplicate DOM IDs among custom voice preview elements."""
        ids = [
            "customVoiceSelect",
            "customRevisionSelect",
            "loadCustomVoices",
            "previewCustomVoice",
            "customVoicePreviewAudio",
            "customVoicePreviewStatus",
            "customVoicePreviewBox",
        ]
        for element_id in ids:
            pattern = rf'id="{element_id}"'
            matches = re.findall(pattern, self.html)
            self.assertEqual(
                len(matches),
                1,
                f"Expected exactly 1 occurrence of id=\"{element_id}\", found {len(matches)}",
            )

    def test_load_custom_voices_function_exists(self):
        """loadCustomVoices function exists in JavaScript."""
        self.assertIn("async function loadCustomVoices()", self.js)

    def test_load_custom_revisions_function_exists(self):
        """loadCustomRevisions function exists in JavaScript."""
        self.assertIn("async function loadCustomRevisions()", self.js)

    def test_preview_custom_voice_function_exists(self):
        """previewCustomVoice function exists in JavaScript."""
        self.assertIn("async function previewCustomVoice()", self.js)

    def test_no_duplicate_load_custom_voices_declaration(self):
        """No duplicate loadCustomVoices function declarations."""
        pattern = r"(?:async\s+)?function\s+loadCustomVoices\s*\("
        matches = re.findall(pattern, self.js)
        self.assertEqual(
            len(matches),
            1,
            f"Expected exactly 1 loadCustomVoices declaration, found {len(matches)}",
        )

    def test_no_duplicate_load_custom_revisions_declaration(self):
        """No duplicate loadCustomRevisions function declarations."""
        pattern = r"(?:async\s+)?function\s+loadCustomRevisions\s*\("
        matches = re.findall(pattern, self.js)
        self.assertEqual(
            len(matches),
            1,
            f"Expected exactly 1 loadCustomRevisions declaration, found {len(matches)}",
        )

    def test_no_duplicate_preview_custom_voice_declaration(self):
        """No duplicate previewCustomVoice function declarations."""
        pattern = r"(?:async\s+)?function\s+previewCustomVoice\s*\("
        matches = re.findall(pattern, self.js)
        self.assertEqual(
            len(matches),
            1,
            f"Expected exactly 1 previewCustomVoice declaration, found {len(matches)}",
        )

    def test_custom_request_sends_custom_voice_revision_id(self):
        """Custom preview request sends custom_voice_revision_id field."""
        self.assertIn("custom_voice_revision_id", self.js)
        # Verify it's sent in the request payload
        self.assertIn("custom_voice_revision_id:revisionId", self.js)

    def test_custom_request_does_not_send_voice_type(self):
        """Custom preview request does not send voice_type field."""
        # voice_type should not appear in custom preview payload
        pattern = r'voice_type\s*:\s*["\']?custom["\']?'
        self.assertNotRegex(self.js, pattern)

    def test_custom_request_does_not_send_preview_text(self):
        """Custom preview request does not send preview_text field."""
        # preview_text should not appear in custom preview payload
        custom_preview_section = re.search(
            r"async function previewCustomVoice\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        if custom_preview_section:
            section_text = custom_preview_section.group(0)
            self.assertNotIn("preview_text", section_text)

    def test_custom_revision_id_converted_to_integer(self):
        """Custom revision ID converted to integer before sending."""
        self.assertIn("parseInt", self.js)
        # Verify parseInt is used on customRevisionSelect.value
        pattern = r"parseInt\(\$\('#customRevisionSelect'\)\.value\)"
        self.assertRegex(self.js, pattern)

    def test_preset_request_still_sends_voice_id(self):
        """Preset request still sends voice_id field (backward compatibility)."""
        # Find preset preview function (previewVoice, not previewCustomVoice)
        preset_section = re.search(
            r"async function previewVoice\(\).*?}catch", self.js, re.DOTALL
        )
        self.assertIsNotNone(preset_section, "previewVoice function not found")
        section_text = preset_section.group(0)
        self.assertIn("voice_id", section_text)

    def test_load_custom_voices_fetches_correct_route(self):
        """loadCustomVoices fetches /api/custom-voices route."""
        pattern = r"await api\(['\"]\/api\/custom-voices['\"]"
        self.assertRegex(self.js, pattern)

    def test_load_custom_revisions_fetches_correct_route(self):
        """loadCustomRevisions fetches /api/custom-voices/{voiceId}/revisions route."""
        pattern = r"await api\(`\/api\/custom-voices\/\$\{voiceId\}\/revisions`\)"
        self.assertRegex(self.js, pattern)

    def test_preview_custom_voice_posts_to_voice_previews_route(self):
        """previewCustomVoice posts to /api/voice-previews route."""
        custom_preview_section = re.search(
            r"async function previewCustomVoice\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(custom_preview_section)
        section_text = custom_preview_section.group(0)
        self.assertIn("/api/voice-previews", section_text)
        self.assertIn("method:'POST'", section_text)

    def test_error_rendering_uses_safe_text_api(self):
        """Error rendering uses textContent (safe) rather than innerHTML."""
        custom_preview_section = re.search(
            r"async function previewCustomVoice\(\).*?}finally",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(custom_preview_section)
        section_text = custom_preview_section.group(0)
        # toast() is safe (uses textContent internally)
        self.assertIn("toast(", section_text)
        # Verify no innerHTML injection in error path
        self.assertNotIn(".innerHTML=", section_text)

    def test_loading_state_disables_preview_button(self):
        """Loading state disables the preview button."""
        pattern = r"button\.disabled\s*=\s*true"
        self.assertRegex(self.js, pattern)

    def test_success_assigns_audio_source(self):
        """Success assigns the preview audio source."""
        custom_preview_section = re.search(
            r"async function previewCustomVoice\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(custom_preview_section)
        section_text = custom_preview_section.group(0)
        self.assertIn("audio.src=", section_text)
        self.assertIn("result.audio_url", section_text)

    def test_failure_reenables_preview_button(self):
        """Failure re-enables the preview button."""
        custom_preview_section = re.search(
            r"async function previewCustomVoice\(\).*",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(custom_preview_section)
        section_text = custom_preview_section.group(0)
        # finally block should re-enable button
        self.assertIn("}finally{", section_text)
        self.assertIn("button.disabled=false", section_text)

    def test_event_handlers_wired(self):
        """Custom voice preview event handlers are wired."""
        self.assertIn("$('#loadCustomVoices').onclick=loadCustomVoices", self.js)
        self.assertIn("$('#customVoiceSelect').onchange=loadCustomRevisions", self.js)
        self.assertIn("$('#previewCustomVoice').onclick=previewCustomVoice", self.js)


if __name__ == "__main__":
    unittest.main()
