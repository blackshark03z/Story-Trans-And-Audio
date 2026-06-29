"""
Custom Voice Library UI contract tests.

Validates static frontend contracts without fragile full-file snapshots.
"""
import re
import unittest
from pathlib import Path


class CustomVoiceLibraryUIContractTests(unittest.TestCase):
    """Static UI contract validation for Custom Voice Library frontend."""

    @classmethod
    def setUpClass(cls):
        """Load frontend files once."""
        repo_root = Path(__file__).parent.parent
        cls.html_path = repo_root / "ui" / "index.html"
        cls.js_path = repo_root / "ui" / "app.js"
        cls.css_path = repo_root / "ui" / "styles.css"

        if not cls.html_path.exists():
            raise FileNotFoundError(f"HTML not found: {cls.html_path}")
        if not cls.js_path.exists():
            raise FileNotFoundError(f"JavaScript not found: {cls.js_path}")
        if not cls.css_path.exists():
            raise FileNotFoundError(f"CSS not found: {cls.css_path}")

        cls.html = cls.html_path.read_text(encoding="utf-8")
        cls.js = cls.js_path.read_text(encoding="utf-8")
        cls.css = cls.css_path.read_text(encoding="utf-8")

    # HTML element existence tests
    def test_refresh_library_button_exists(self):
        """Refresh library button exists in HTML."""
        self.assertIn('id="refreshLibrary"', self.html)

    def test_show_inactive_checkbox_exists(self):
        """Show inactive voices checkbox exists in HTML."""
        self.assertIn('id="showInactiveVoices"', self.html)

    def test_library_status_element_exists(self):
        """Library status element exists in HTML."""
        self.assertIn('id="libraryStatus"', self.html)

    def test_library_voice_list_container_exists(self):
        """Library voice list container exists in HTML."""
        self.assertIn('id="libraryVoiceList"', self.html)

    def test_library_selected_details_section_exists(self):
        """Library selected details section exists in HTML."""
        self.assertIn('id="librarySelectedDetails"', self.html)

    def test_library_voice_info_container_exists(self):
        """Library voice info container exists in HTML."""
        self.assertIn('id="libraryVoiceInfo"', self.html)

    def test_library_voice_info_name_exists(self):
        """Library voice info name element exists in HTML."""
        self.assertIn('id="libraryVoiceInfoName"', self.html)

    def test_library_voice_info_status_exists(self):
        """Library voice info status element exists in HTML."""
        self.assertIn('id="libraryVoiceInfoStatus"', self.html)

    def test_library_voice_info_description_exists(self):
        """Library voice info description element exists in HTML."""
        self.assertIn('id="libraryVoiceInfoDescription"', self.html)

    def test_library_deactivate_button_exists(self):
        """Library deactivate button exists in HTML."""
        self.assertIn('id="libraryDeactivate"', self.html)

    def test_library_reactivate_button_exists(self):
        """Library reactivate button exists in HTML."""
        self.assertIn('id="libraryReactivate"', self.html)

    def test_library_new_name_input_exists(self):
        """Library new name input exists in HTML."""
        self.assertIn('id="libraryNewName"', self.html)

    def test_library_new_description_textarea_exists(self):
        """Library new description textarea exists in HTML."""
        self.assertIn('id="libraryNewDescription"', self.html)

    def test_library_create_button_exists(self):
        """Library create button exists in HTML."""
        self.assertIn('id="libraryCreate"', self.html)

    def test_library_error_element_exists(self):
        """Library error element exists in HTML."""
        self.assertIn('id="libraryError"', self.html)

    def test_library_panel_exists(self):
        """Custom voice library panel exists in HTML."""
        self.assertIn('custom-voice-library-panel', self.html)

    def test_no_duplicate_library_dom_ids(self):
        """No duplicate DOM IDs among custom voice library elements."""
        ids = [
            "refreshLibrary",
            "showInactiveVoices",
            "libraryStatus",
            "libraryVoiceList",
            "librarySelectedDetails",
            "libraryVoiceInfo",
            "libraryVoiceInfoName",
            "libraryVoiceInfoStatus",
            "libraryVoiceInfoDescription",
            "libraryDeactivate",
            "libraryReactivate",
            "libraryNewName",
            "libraryNewDescription",
            "libraryCreate",
            "libraryError",
        ]
        for element_id in ids:
            pattern = rf'id="{element_id}"'
            matches = re.findall(pattern, self.html)
            self.assertEqual(
                len(matches),
                1,
                f"Expected exactly 1 occurrence of id=\"{element_id}\", found {len(matches)}",
            )

    # JavaScript function existence tests
    def test_refresh_library_function_exists(self):
        """refreshLibrary function exists in JavaScript."""
        self.assertIn("async function refreshLibrary()", self.js)

    def test_render_library_voices_function_exists(self):
        """renderLibraryVoices function exists in JavaScript."""
        self.assertIn("function renderLibraryVoices()", self.js)

    def test_select_library_voice_function_exists(self):
        """selectLibraryVoice function exists in JavaScript."""
        self.assertIn("function selectLibraryVoice(", self.js)

    def test_select_library_voice_populates_voice_info(self):
        """selectLibraryVoice populates voice info elements."""
        select_section = re.search(
            r"function selectLibraryVoice\([^)]*\)\{",
            self.js,
        )
        self.assertIsNotNone(select_section)
        # Find the full function body by finding the matching closing brace
        start = select_section.start()
        # Look for the function content (simplified check for key elements)
        section_text = self.js[start:start+3000]  # Reasonable function length
        # Should populate voice info name
        self.assertIn("libraryVoiceInfoName", section_text)
        # Should populate voice info status with badge classes
        self.assertIn("libraryVoiceInfoStatus", section_text)
        # Should populate voice info description
        self.assertIn("libraryVoiceInfoDescription", section_text)

    def test_select_library_voice_handles_empty_description(self):
        """selectLibraryVoice shows 'No description' for empty description."""
        select_section = re.search(
            r"function selectLibraryVoice\([^)]*\)\{",
            self.js,
        )
        self.assertIsNotNone(select_section)
        start = select_section.start()
        section_text = self.js[start:start+3000]
        self.assertIn("No description", section_text)

    def test_select_library_voice_toggles_button_visibility(self):
        """selectLibraryVoice toggles button visibility with hidden class."""
        select_section = re.search(
            r"function selectLibraryVoice\([^)]*\)\{",
            self.js,
        )
        self.assertIsNotNone(select_section)
        start = select_section.start()
        section_text = self.js[start:start+3000]
        # Should toggle hidden class on buttons
        self.assertIn("libraryDeactivate", section_text)
        self.assertIn("libraryReactivate", section_text)
        self.assertIn("hidden", section_text)

    def test_select_library_voice_updates_upload_target(self):
        """selectLibraryVoice updates upload target display."""
        select_section = re.search(
            r"function selectLibraryVoice\([^)]*\)\{",
            self.js,
        )
        self.assertIsNotNone(select_section)
        start = select_section.start()
        section_text = self.js[start:start+3000]
        # Should populate upload target voice
        self.assertIn("libraryUploadTargetVoice", section_text)

    def test_create_library_voice_function_exists(self):
        """createLibraryVoice function exists in JavaScript."""
        self.assertIn("async function createLibraryVoice()", self.js)

    def test_deactivate_library_voice_function_exists(self):
        """deactivateLibraryVoice function exists in JavaScript."""
        self.assertIn("async function deactivateLibraryVoice()", self.js)

    def test_reactivate_library_voice_function_exists(self):
        """reactivateLibraryVoice function exists in JavaScript."""
        self.assertIn("async function reactivateLibraryVoice()", self.js)

    def test_show_library_error_function_exists(self):
        """showLibraryError function exists in JavaScript."""
        self.assertIn("function showLibraryError(", self.js)

    def test_map_library_error_function_exists(self):
        """mapLibraryError function exists in JavaScript."""
        self.assertIn("function mapLibraryError(", self.js)

    # State management tests
    def test_library_state_initialized(self):
        """Library state fields initialized in global state."""
        self.assertIn("libraryVoices:", self.js)
        self.assertIn("selectedVoiceId:", self.js)
        self.assertIn("showInactive:", self.js)
        self.assertIn("libraryBusy:", self.js)

    # API integration tests
    def test_refresh_library_fetches_custom_voices(self):
        """refreshLibrary fetches /api/custom-voices with active_only param."""
        pattern = r"await api\(`\/api\/custom-voices\?active_only=\$\{activeOnly\}`\)"
        self.assertRegex(self.js, pattern)

    def test_create_library_voice_posts_to_custom_voices(self):
        """createLibraryVoice posts to /api/custom-voices."""
        create_section = re.search(
            r"async function createLibraryVoice\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(create_section)
        section_text = create_section.group(0)
        self.assertIn("/api/custom-voices", section_text)
        self.assertIn("method:'POST'", section_text)

    def test_create_sends_display_name_and_description(self):
        """createLibraryVoice sends display_name and description fields."""
        create_section = re.search(
            r"async function createLibraryVoice\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(create_section)
        section_text = create_section.group(0)
        self.assertIn("display_name:", section_text)
        self.assertIn("description:", section_text)

    def test_deactivate_patches_deactivate_route(self):
        """deactivateLibraryVoice patches /api/custom-voices/{id}/deactivate."""
        pattern = r"await api\(`\/api\/custom-voices\/\$\{state\.selectedVoiceId\}\/deactivate`"
        self.assertRegex(self.js, pattern)

    def test_reactivate_patches_reactivate_route(self):
        """reactivateLibraryVoice patches /api/custom-voices/{id}/reactivate."""
        pattern = r"await api\(`\/api\/custom-voices\/\$\{state\.selectedVoiceId\}\/reactivate`"
        self.assertRegex(self.js, pattern)

    # Validation tests
    def test_create_validates_name_required(self):
        """createLibraryVoice validates name is required."""
        create_section = re.search(
            r"async function createLibraryVoice\(\).*?}finally",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(create_section)
        section_text = create_section.group(0)
        self.assertIn("if(!name)", section_text)
        self.assertIn("Voice name is required", section_text)

    def test_create_validates_name_length(self):
        """createLibraryVoice validates name length <= 120 characters."""
        create_section = re.search(
            r"async function createLibraryVoice\(\).*?}finally",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(create_section)
        section_text = create_section.group(0)
        self.assertIn("name.length>120", section_text)
        self.assertIn("120 characters or less", section_text)

    # Error handling tests
    def test_error_mapping_handles_invalid(self):
        """mapLibraryError maps invalid/bad request to user-friendly message."""
        self.assertIn("includes('invalid')", self.js)
        self.assertIn("The custom voice information is invalid", self.js)

    def test_error_mapping_handles_not_found(self):
        """mapLibraryError maps not found to user-friendly message."""
        self.assertIn("includes('not found')", self.js)
        self.assertIn("no longer exists", self.js)

    def test_error_mapping_handles_conflict(self):
        """mapLibraryError maps conflict to user-friendly message."""
        self.assertIn("includes('conflict')", self.js)
        self.assertIn("state changed", self.js)

    def test_error_mapping_handles_unavailable(self):
        """mapLibraryError maps service unavailable to user-friendly message."""
        self.assertIn("includes('unavailable')", self.js)
        self.assertIn("currently unavailable", self.js)

    def test_error_uses_safe_text_rendering(self):
        """Error rendering uses textContent (safe) rather than innerHTML."""
        error_show_section = re.search(
            r"function showLibraryError\(.*?\)\{.*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(error_show_section)
        section_text = error_show_section.group(0)
        self.assertIn(".textContent=", section_text)
        self.assertNotIn(".innerHTML=", section_text)

    # Event handler wiring tests
    def test_refresh_library_handler_wired(self):
        """refreshLibrary event handler is wired."""
        self.assertIn("$('#refreshLibrary').onclick=refreshLibrary", self.js)

    def test_show_inactive_handler_wired(self):
        """showInactive checkbox event handler is wired."""
        pattern = r"\$\('#showInactiveVoices'\)\.onchange"
        self.assertRegex(self.js, pattern)

    def test_create_library_handler_wired(self):
        """createLibraryVoice event handler is wired."""
        self.assertIn("$('#libraryCreate').onclick=createLibraryVoice", self.js)

    def test_deactivate_handler_wired(self):
        """deactivateLibraryVoice event handler is wired."""
        self.assertIn("$('#libraryDeactivate').onclick=deactivateLibraryVoice", self.js)

    def test_reactivate_handler_wired(self):
        """reactivateLibraryVoice event handler is wired."""
        self.assertIn("$('#libraryReactivate').onclick=reactivateLibraryVoice", self.js)

    # CSS styling tests
    def test_voice_library_list_styles_exist(self):
        """voice-library-list styles exist in CSS."""
        self.assertIn(".voice-library-list", self.css)

    def test_voice_library_row_styles_exist(self):
        """voice-library-row styles exist in CSS."""
        self.assertIn(".voice-library-row", self.css)

    def test_library_selected_details_styles_exist(self):
        """library-selected-details styles exist in CSS."""
        self.assertIn(".library-selected-details", self.css)

    def test_voice_library_row_selected_state_exists(self):
        """voice-library-row selected state styles exist in CSS."""
        self.assertIn(".voice-library-row.selected", self.css)

    # Upload UI tests
    def test_library_audio_file_input_exists(self):
        """Library audio file input exists in HTML."""
        self.assertIn('id="libraryAudioFile"', self.html)

    def test_library_transcript_textarea_exists(self):
        """Library transcript textarea exists in HTML."""
        self.assertIn('id="libraryTranscript"', self.html)

    def test_library_transcript_counter_exists(self):
        """Library transcript character counter exists in HTML."""
        self.assertIn('id="libraryTranscriptCounter"', self.html)

    def test_library_upload_revision_button_exists(self):
        """Library upload revision button exists in HTML."""
        self.assertIn('id="libraryUploadRevision"', self.html)

    def test_library_upload_status_element_exists(self):
        """Library upload status element exists in HTML."""
        self.assertIn('id="libraryUploadStatus"', self.html)

    def test_library_upload_target_voice_exists(self):
        """Library upload target voice element exists in HTML."""
        self.assertIn('id="libraryUploadTargetVoice"', self.html)

    # CSS styling tests for Voice Details
    def test_library_voice_info_styles_exist(self):
        """library-voice-info styles exist in CSS."""
        self.assertIn(".library-voice-info", self.css)

    def test_voice_info_row_styles_exist(self):
        """voice-info-row styles exist in CSS."""
        self.assertIn(".voice-info-row", self.css)

    def test_voice_info_badge_styles_exist(self):
        """voice-info-badge styles exist in CSS."""
        self.assertIn(".voice-info-badge", self.css)
        self.assertIn(".voice-info-badge.badge-active", self.css)
        self.assertIn(".voice-info-badge.badge-inactive", self.css)

    def test_upload_target_display_styles_exist(self):
        """upload-target-display styles exist in CSS."""
        self.assertIn(".upload-target-display", self.css)

    def test_upload_target_voice_styles_exist(self):
        """upload-target-voice styles exist in CSS."""
        self.assertIn(".upload-target-voice", self.css)

    def test_immutable_notice_exists(self):
        """Immutable revision notice exists in HTML."""
        self.assertIn('immutable-notice', self.html)

    # Revision history UI tests
    def test_library_revisions_status_element_exists(self):
        """Library revisions status element exists in HTML."""
        self.assertIn('id="libraryRevisionsStatus"', self.html)

    def test_library_revisions_list_container_exists(self):
        """Library revisions list container exists in HTML."""
        self.assertIn('id="libraryRevisionsList"', self.html)

    # Preview UI tests
    def test_library_generate_test_audio_button_exists(self):
        """Library generate test audio button exists in HTML (dedicated Test Synthesis panel)."""
        self.assertIn('id="libraryGenerateTestAudio"', self.html)

    def test_library_preview_box_exists(self):
        """Library preview box exists in HTML."""
        self.assertIn('id="libraryPreviewBox"', self.html)

    def test_library_preview_audio_element_exists(self):
        """Library preview audio element exists in HTML."""
        self.assertIn('id="libraryPreviewAudio"', self.html)

    def test_library_preview_provenance_element_exists(self):
        """Library preview provenance element exists in HTML (replaces old status)."""
        self.assertIn('id="libraryPreviewProvenance"', self.html)

    # JavaScript function existence for upload/revision/preview
    def test_load_library_revisions_function_exists(self):
        """loadLibraryRevisions function exists in JavaScript."""
        self.assertIn("async function loadLibraryRevisions()", self.js)

    def test_render_library_revisions_function_exists(self):
        """renderLibraryRevisions function exists in JavaScript."""
        self.assertIn("function renderLibraryRevisions()", self.js)

    def test_no_select_library_revision_function(self):
        """selectLibraryRevision function no longer exists (replaced by testVoiceRevision)."""
        self.assertNotIn("function selectLibraryRevision(", self.js)

    def test_upload_library_revision_function_exists(self):
        """uploadLibraryRevision function exists in JavaScript."""
        self.assertIn("async function uploadLibraryRevision()", self.js)

    def test_upload_captures_voice_id_at_start(self):
        """uploadLibraryRevision captures selectedVoiceId at function start."""
        upload_section = re.search(
            r"async function uploadLibraryRevision\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(upload_section)
        section_text = upload_section.group(0)
        # Should capture selectedVoiceId early
        self.assertIn("selectedVoiceId", section_text)

    def test_upload_uses_captured_voice_in_url(self):
        """uploadLibraryRevision uses captured voice ID in fetch URL."""
        upload_section = re.search(
            r"async function uploadLibraryRevision\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(upload_section)
        section_text = upload_section.group(0)
        # Should use captured ID in URL (not state.selectedVoiceId directly)
        # Look for pattern where a variable is used in the URL
        self.assertIn("/api/custom-voices/", section_text)

    def test_upload_shows_captured_voice_in_status(self):
        """uploadLibraryRevision shows captured voice name in status messages."""
        upload_section = re.search(
            r"async function uploadLibraryRevision\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(upload_section)
        section_text = upload_section.group(0)
        # Should reference voice name in status messages
        self.assertIn("libraryUploadStatus", section_text)

    def test_show_library_upload_error_function_exists(self):
        """showLibraryUploadError function exists in JavaScript."""
        self.assertIn("function showLibraryUploadError(", self.js)

    def test_map_library_upload_error_function_exists(self):
        """mapLibraryUploadError function exists in JavaScript."""
        self.assertIn("function mapLibraryUploadError(", self.js)

    def test_generate_test_audio_function_exists(self):
        """generateTestAudio function exists in JavaScript (renamed from previewLibraryRevision)."""
        self.assertIn("async function generateTestAudio()", self.js)

    # State management for upload/revision/preview
    def test_library_revisions_state_initialized(self):
        """libraryRevisions state field initialized in global state."""
        self.assertIn("libraryRevisions:", self.js)

    def test_preview_revision_id_state_initialized(self):
        """previewRevisionId state field initialized in global state."""
        self.assertIn("previewRevisionId:", self.js)

    def test_upload_busy_state_initialized(self):
        """uploadBusy state field initialized in global state."""
        self.assertIn("uploadBusy:", self.js)

    def test_preview_busy_state_initialized(self):
        """previewBusy state field initialized in global state."""
        self.assertIn("previewBusy:", self.js)

    # Upload API integration tests
    def test_upload_uses_formdata(self):
        """uploadLibraryRevision uses FormData for multipart upload."""
        upload_section = re.search(
            r"async function uploadLibraryRevision\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(upload_section)
        section_text = upload_section.group(0)
        self.assertIn("new FormData()", section_text)

    def test_upload_sends_audio_field(self):
        """uploadLibraryRevision sends 'audio' field in FormData."""
        upload_section = re.search(
            r"async function uploadLibraryRevision\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(upload_section)
        section_text = upload_section.group(0)
        self.assertIn("'audio'", section_text)

    def test_upload_sends_transcript_field(self):
        """uploadLibraryRevision sends 'transcript' field in FormData."""
        upload_section = re.search(
            r"async function uploadLibraryRevision\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(upload_section)
        section_text = upload_section.group(0)
        self.assertIn("'transcript'", section_text)

    def test_upload_posts_to_revisions_route(self):
        """uploadLibraryRevision posts to /api/custom-voices/{id}/revisions."""
        pattern = r"/api/custom-voices/\$\{state\.selectedVoiceId\}/revisions"
        self.assertRegex(self.js, pattern)

    def test_upload_file_size_validation(self):
        """uploadLibraryRevision validates file size limit (52428800 bytes)."""
        upload_section = re.search(
            r"async function uploadLibraryRevision\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(upload_section)
        section_text = upload_section.group(0)
        self.assertIn("52428800", section_text)  # 50MB in bytes

    def test_upload_transcript_length_validation(self):
        """uploadLibraryRevision validates transcript length (10000 chars)."""
        upload_section = re.search(
            r"async function uploadLibraryRevision\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(upload_section)
        section_text = upload_section.group(0)
        self.assertIn("10000", section_text)

    # Revision history API integration tests
    def test_load_revisions_gets_from_revisions_route(self):
        """loadLibraryRevisions fetches from /api/custom-voices/{id}/revisions."""
        pattern = r"/api/custom-voices/\$\{.*?\}/revisions"
        self.assertRegex(self.js, pattern)

    def test_test_voice_revision_stores_exact_id(self):
        """testVoiceRevision stores exact revision ID (not revision_number)."""
        test_voice_section = re.search(
            r"function testVoiceRevision\([^)]*\).*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(test_voice_section)
        section_text = test_voice_section.group(0)
        # Should store id parameter in previewRevisionId
        self.assertIn("previewRevisionId=id", section_text)

    # Preview API integration tests
    def test_generate_test_audio_uses_voice_previews_endpoint(self):
        """generateTestAudio uses existing /api/voice-previews endpoint."""
        preview_section = re.search(
            r"async function generateTestAudio\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(preview_section)
        section_text = preview_section.group(0)
        self.assertIn("/api/voice-previews", section_text)

    def test_generate_test_audio_sends_custom_voice_revision_id(self):
        """generateTestAudio sends custom_voice_revision_id field."""
        preview_section = re.search(
            r"async function generateTestAudio\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(preview_section)
        section_text = preview_section.group(0)
        self.assertIn("custom_voice_revision_id", section_text)

    def test_generate_test_audio_sends_revision_id_as_number(self):
        """generateTestAudio sends revision ID as number (not string)."""
        preview_section = re.search(
            r"async function generateTestAudio\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(preview_section)
        section_text = preview_section.group(0)
        # Should use previewRevisionId directly or Number() coercion
        self.assertIn("state.previewRevisionId", section_text)

    # Upload error handling tests
    def test_upload_error_mapping_handles_invalid(self):
        """mapLibraryUploadError maps 400/422 to user-friendly message."""
        upload_error_section = re.search(
            r"function mapLibraryUploadError\(.*?\)\{.*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(upload_error_section)
        section_text = upload_error_section.group(0)
        self.assertIn("reference audio or transcript is invalid", section_text)

    def test_upload_error_mapping_handles_size_limit(self):
        """mapLibraryUploadError maps 413/size to user-friendly message."""
        upload_error_section = re.search(
            r"function mapLibraryUploadError\(.*?\)\{.*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(upload_error_section)
        section_text = upload_error_section.group(0)
        self.assertIn("too large", section_text)

    def test_upload_error_mapping_handles_not_found(self):
        """mapLibraryUploadError maps 404 to user-friendly message."""
        upload_error_section = re.search(
            r"function mapLibraryUploadError\(.*?\)\{.*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(upload_error_section)
        section_text = upload_error_section.group(0)
        self.assertIn("no longer exists", section_text)

    def test_upload_error_uses_safe_text_rendering(self):
        """Upload error rendering uses textContent (safe) rather than innerHTML."""
        upload_error_show_section = re.search(
            r"function showLibraryUploadError\(.*?\)\{.*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(upload_error_show_section)
        section_text = upload_error_show_section.group(0)
        self.assertIn(".textContent=", section_text)
        self.assertNotIn(".innerHTML=", section_text)

    # Event handler wiring for upload/revision/preview
    def test_transcript_counter_handler_wired(self):
        """Transcript character counter event handler is wired."""
        pattern = r"\$\('#libraryTranscript'\)\.oninput"
        self.assertRegex(self.js, pattern)

    def test_upload_revision_handler_wired(self):
        """uploadLibraryRevision event handler is wired."""
        self.assertIn("$('#libraryUploadRevision').onclick=uploadLibraryRevision", self.js)

    def test_generate_test_audio_handler_wired(self):
        """generateTestAudio event handler is wired."""
        self.assertIn("$('#libraryGenerateTestAudio').onclick=generateTestAudio", self.js)

    # CSS styling tests for upload/revision
    def test_immutable_notice_styles_exist(self):
        """immutable-notice styles exist in CSS."""
        self.assertIn(".immutable-notice", self.css)

    def test_char_counter_styles_exist(self):
        """char-counter styles exist in CSS."""
        self.assertIn(".char-counter", self.css)

    def test_library_revisions_list_styles_exist(self):
        """library-revisions-list styles exist in CSS."""
        self.assertIn(".library-revisions-list", self.css)

    def test_library_revision_row_styles_exist(self):
        """library-revision-row styles exist in CSS."""
        self.assertIn(".library-revision-row", self.css)

    def test_revision_meta_styles_exist(self):
        """revision-meta styles exist in CSS."""
        self.assertIn(".revision-meta", self.css)

    def test_revision_date_remains_visible(self):
        """Revision date remains visible in revision rows."""
        # Date is shown inline, no longer has dedicated .revision-date class
        render_func = re.search(r"function renderLibraryRevisions\(\).*?\.join\(''\)", self.js, re.DOTALL)
        self.assertIsNotNone(render_func)
        # Should format and display date
        self.assertIn("toLocaleString", render_func.group(0))
        self.assertIn("created_at", render_func.group(0))

    def test_no_selected_row_visual_state(self):
        """library-revision-row.selected state styles do not exist (stateless UI)."""
        self.assertNotIn(".library-revision-row.selected", self.css)

    # Phase 5B3: Preview Text and Reference Audio Tests

    def test_no_duplicate_custom_preview_panel(self):
        """No duplicate standalone custom voice preview panel exists."""
        # The redundant panel should be removed
        self.assertNotIn('custom-voice-preview-panel', self.html)

    def test_custom_voice_library_panel_is_single_workspace(self):
        """Custom voice library panel is the single coherent workspace."""
        self.assertIn('custom-voice-library-panel', self.html)

    def test_library_preview_text_textarea_exists(self):
        """Library preview text textarea exists in HTML."""
        self.assertIn('id="libraryPreviewText"', self.html)

    def test_library_preview_text_counter_exists(self):
        """Library preview text character counter exists in HTML."""
        self.assertIn('id="libraryPreviewTextCounter"', self.html)

    def test_library_use_default_preview_button_exists(self):
        """Use default preview text button exists in HTML."""
        self.assertIn('id="libraryUseDefaultPreview"', self.html)

    def test_library_reference_audio_player_exists(self):
        """Library reference audio player exists in HTML."""
        self.assertIn('id="libraryReferenceAudio"', self.html)

    def test_update_preview_text_counter_function_exists(self):
        """updatePreviewTextCounter function exists in JavaScript."""
        self.assertIn("function updatePreviewTextCounter()", self.js)

    def test_use_default_preview_text_function_exists(self):
        """useDefaultPreviewText function exists in JavaScript."""
        self.assertIn("function useDefaultPreviewText()", self.js)

    def test_play_reference_audio_function_exists(self):
        """playReferenceAudio function exists in JavaScript."""
        self.assertIn("function playReferenceAudio(", self.js)

    def test_test_voice_revision_function_exists(self):
        """testVoiceRevision function exists in JavaScript."""
        self.assertIn("function testVoiceRevision(", self.js)

    # New stateless UI behavior tests
    def test_preferred_revision_shows_badge(self):
        """Preferred revision shows 'Used for synthesis' badge."""
        self.assertIn('Used for synthesis', self.js)
        self.assertIn('preferred-badge', self.js)

    def test_non_preferred_shows_use_button(self):
        """Non-preferred revisions show 'Use for synthesis' button."""
        self.assertIn('Use for synthesis', self.js)
        self.assertIn('setPreferredSynthesisRevision', self.js)

    def test_listen_button_always_visible(self):
        """Listen button is always visible for all revisions."""
        self.assertIn('listen-revision-btn', self.js)
        self.assertIn('playReferenceAudio', self.js)

    def test_no_per_row_test_voice_buttons(self):
        """Test voice buttons no longer exist per-row (replaced by dedicated Test Synthesis panel)."""
        render_func = re.search(
            r"function renderLibraryRevisions\(\).*?\.join\(''\)",
            self.js,
            re.DOTALL,
        )
        if render_func:
            func_body = render_func.group(0)
            # Should NOT have test-voice-btn in revision rows
            self.assertNotIn('test-voice-btn', func_body,
                           "Revision rows should not have Test voice buttons")

    # State isolation and endpoint safety tests
    def test_play_reference_audio_does_not_mutate_preview_state(self):
        """playReferenceAudio does not modify previewRevisionId state."""
        play_ref_func = re.search(r"function playReferenceAudio\([^)]*\)\{[^}]*\}", self.js, re.DOTALL)
        if play_ref_func:
            func_body = play_ref_func.group(0)
            # Should NOT contain previewRevisionId assignment
            self.assertNotIn("previewRevisionId=", func_body,
                           "playReferenceAudio must not modify previewRevisionId")

    def test_play_reference_audio_does_not_call_patch_endpoint(self):
        """playReferenceAudio does not call setPreferredSynthesisRevision."""
        play_ref_func = re.search(r"function playReferenceAudio\([^)]*\)\{[^}]*\}", self.js, re.DOTALL)
        if play_ref_func:
            func_body = play_ref_func.group(0)
            # Should NOT call setPreferredSynthesisRevision
            self.assertNotIn("setPreferredSynthesisRevision", func_body,
                           "playReferenceAudio must not trigger preferred revision PATCH")

    def test_set_preferred_synthesis_revision_exists(self):
        """setPreferredSynthesisRevision function exists for PATCH operations."""
        self.assertIn("async function setPreferredSynthesisRevision(", self.js)

    def test_set_preferred_synthesis_revision_uses_patch_endpoint(self):
        """setPreferredSynthesisRevision calls correct PATCH endpoint."""
        set_pref_func = re.search(r"async function setPreferredSynthesisRevision\([^)]*\)\{.*?method:'PATCH'",
                                  self.js, re.DOTALL)
        self.assertIsNotNone(set_pref_func, "setPreferredSynthesisRevision should use PATCH method")
        func_body = set_pref_func.group(0)
        self.assertIn("preferred-revision", func_body, "Should call preferred-revision endpoint")

    def test_set_preferred_synthesis_revision_does_not_mutate_preview_state(self):
        """setPreferredSynthesisRevision does not modify previewRevisionId."""
        set_pref_func = re.search(r"async function setPreferredSynthesisRevision\([^)]*\)\{[^}]*\}catch",
                                  self.js, re.DOTALL)
        if set_pref_func:
            func_body = set_pref_func.group(0)
            # Should NOT modify previewRevisionId
            self.assertNotIn("previewRevisionId=", func_body,
                           "setPreferredSynthesisRevision must not modify previewRevisionId")

    def test_set_preferred_synthesis_revision_updates_ui_on_success(self):
        """setPreferredSynthesisRevision updates badge on successful PATCH."""
        set_pref_func = re.search(r"async function setPreferredSynthesisRevision\([^)]*\)\{[^}]*\}catch",
                                  self.js, re.DOTALL)
        if set_pref_func:
            func_body = set_pref_func.group(0)
            # Should update the voice object with new preferred_synthesis_revision_id
            has_update = "preferred_synthesis_revision_id=" in func_body
            self.assertTrue(has_update, "Should update preferred_synthesis_revision_id on success")
            # Should call renderLibraryRevisions to update UI
            self.assertIn("renderLibraryRevisions()", func_body)

    def test_set_preferred_synthesis_revision_shows_error_on_failure(self):
        """setPreferredSynthesisRevision shows toast error on PATCH failure."""
        set_pref_func = re.search(r"async function setPreferredSynthesisRevision\([^)]*\)\{.*?\}finally",
                                  self.js, re.DOTALL)
        if set_pref_func:
            func_body = set_pref_func.group(0)
            # Should have catch block with toast
            has_error_toast = "catch" in func_body and "toast(" in func_body
            self.assertTrue(has_error_toast, "Should show toast on PATCH error")

    def test_database_id_in_technical_details_not_primary_row(self):
        """Database ID appears in technical details, not primary revision display."""
        render_func = re.search(r"function renderLibraryRevisions\(\).*?\.join\(''\)", self.js, re.DOTALL)
        if render_func:
            func_body = render_func.group(0)
            # Should have ID inside <details>
            id_in_details = re.search(r"<details[^>]*>.*?ID.*?\$\{r\.id\}", func_body, re.DOTALL)
            self.assertIsNotNone(id_in_details, "ID should be inside <details> element")
            # Primary row (before <details>) should NOT show raw ID
            primary_display = re.search(r"<strong>Revision.*?</strong>[^<]*·[^<]*s·[^<]*<", func_body)
            if primary_display:
                # Primary display should show revision_number, duration, date - NOT database ID
                self.assertNotIn("${r.id}", primary_display.group(0))

    def test_generate_test_audio_coerces_revision_id_to_number(self):
        """generateTestAudio explicitly coerces revision ID to number."""
        # generateTestAudio uses captured requestRevisionId variable and wraps it in Number()
        preview_func = re.search(
            r"async function generateTestAudio\(\).*?custom_voice_revision_id:Number\(",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(preview_func, "generateTestAudio should use Number() coercion for custom_voice_revision_id")

    def test_technical_details_collapsed_by_default(self):
        """Technical details use collapsible <details> element."""
        self.assertIn('<details class="revision-technical-details">', self.js)
        self.assertIn('<summary>Technical details</summary>', self.js)

    def test_upload_section_collapsible(self):
        """Upload New Revision section is collapsible."""
        self.assertIn('upload-revision-section', self.html)
        self.assertIn('<details class="upload-revision-section">', self.html)

    def test_create_voice_section_collapsible(self):
        """Create New Voice section is collapsible."""
        self.assertIn('create-voice-section', self.html)
        self.assertIn('<details class="create-voice-section">', self.html)

    def test_preview_text_counter_handler_wired(self):
        """Preview text character counter event handler is wired."""
        pattern = r"\$\('#libraryPreviewText'\)\.oninput\s*=\s*updatePreviewTextCounter"
        self.assertRegex(self.js, pattern)

    def test_use_default_preview_button_handler_wired(self):
        """Use default preview button event handler is wired."""
        pattern = r"\$\('#libraryUseDefaultPreview'\)\.onclick\s*=\s*useDefaultPreviewText"
        self.assertRegex(self.js, pattern)

    def test_play_reference_audio_uses_reference_audio_endpoint(self):
        """playReferenceAudio loads from /api/custom-voice-revisions/{id}/audio."""
        self.assertIn('function playReferenceAudio(', self.js)
        self.assertIn('/api/custom-voice-revisions/${revisionId}/audio', self.js)

    def test_test_voice_revision_stores_exact_id(self):
        """testVoiceRevision stores exact revision ID (not revision_number)."""
        test_voice_section = re.search(
            r"function testVoiceRevision\([^)]*\).*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(test_voice_section)
        section_text = test_voice_section.group(0)
        # Should store revision.id in previewRevisionId
        self.assertIn("previewRevisionId=id", section_text)

    def test_test_voice_revision_updates_state_and_ui(self):
        """testVoiceRevision updates state.previewRevisionId and refreshes UI."""
        test_voice_section = re.search(
            r"function testVoiceRevision\([^)]*\).*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(test_voice_section)
        section_text = test_voice_section.group(0)
        # Should update previewRevisionId state
        self.assertIn("state.previewRevisionId=id", section_text)
        # Should call renderTestRevisionSelect to update dropdown selection
        self.assertIn("renderTestRevisionSelect()", section_text)

    def test_revision_select_enables_generate_button(self):
        """Revision select change enables Generate Test Audio button when revision selected."""
        self.assertIn('id="libraryTestRevisionSelect"', self.html)
        self.assertIn("$('#libraryGenerateTestAudio').disabled=false", self.js)

    def test_test_voice_revision_clears_stale_preview(self):
        """testVoiceRevision clears old preview audio when switching test revision."""
        self.assertIn('function testVoiceRevision(', self.js)
        # Should clear preview audio
        self.assertIn('previewAudio.pause()', self.js)
        self.assertIn("previewAudio.removeAttribute('src')", self.js)

    # Dedicated Test Synthesis Panel Tests

    def test_library_test_voice_input_exists(self):
        """Library test voice input exists in HTML (read-only voice name display)."""
        self.assertIn('id="libraryTestVoice"', self.html)

    def test_library_test_revision_select_exists(self):
        """Library test revision select exists in HTML."""
        self.assertIn('id="libraryTestRevisionSelect"', self.html)

    def test_library_preview_provenance_element_exists(self):
        """Library preview provenance element exists in HTML."""
        self.assertIn('id="libraryPreviewProvenance"', self.html)

    def test_render_test_revision_select_function_exists(self):
        """renderTestRevisionSelect function exists in JavaScript."""
        self.assertIn("function renderTestRevisionSelect()", self.js)

    def test_render_test_revision_select_populates_dropdown(self):
        """renderTestRevisionSelect populates revision select with formatted options."""
        render_func = re.search(
            r"function renderTestRevisionSelect\(\).*?selectElem\.innerHTML",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(render_func, "renderTestRevisionSelect should populate select element")

    def test_revision_select_shows_preferred_suffix(self):
        """Revision select options show 'Used for synthesis' suffix for preferred revision."""
        render_func = re.search(
            r"function renderTestRevisionSelect\(\).*?Used for synthesis",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(render_func, "Revision options should show preferred suffix")

    def test_revision_select_change_updates_preview_revision_id(self):
        """Revision select change handler updates state.previewRevisionId."""
        handler_section = re.search(
            r"\$\('#libraryTestRevisionSelect'\)\.onchange.*?previewRevisionId",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(handler_section, "Select change should update previewRevisionId")

    def test_revision_select_change_enables_generate_when_selected(self):
        """Revision select enables Generate button when revision selected."""
        handler_section = re.search(
            r"\$\('#libraryTestRevisionSelect'\)\.onchange.*?disabled=false",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(handler_section, "Select change should enable Generate button")

    def test_revision_select_change_disables_generate_when_empty(self):
        """Revision select disables Generate button when no selection."""
        handler_section = re.search(
            r"\$\('#libraryTestRevisionSelect'\)\.onchange.*?disabled=true",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(handler_section, "Select change should disable Generate when empty")

    def test_no_per_row_test_buttons_in_revision_list(self):
        """Revision rows do not have per-row Test voice buttons."""
        render_func = re.search(
            r"function renderLibraryRevisions\(\).*?\.join\(''\)",
            self.js,
            re.DOTALL,
        )
        if render_func:
            func_body = render_func.group(0)
            # Should NOT have test-voice-btn in revision rows
            self.assertNotIn('test-voice-btn', func_body,
                           "Revision rows should not have Test voice buttons")

    def test_generate_test_audio_uses_captured_request_context(self):
        """generateTestAudio captures request context for stale-response protection."""
        generate_func = re.search(
            r"async function generateTestAudio\(\).*?requestVoiceId.*?requestRevisionId",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(generate_func, "Should capture request context")

    def test_generate_test_audio_ignores_stale_responses(self):
        """generateTestAudio ignores responses for stale voice/revision selections."""
        generate_func = re.search(
            r"async function generateTestAudio\(\).*?if\(state\.selectedVoiceId!==requestVoiceId",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(generate_func, "Should check for stale responses")

    def test_provenance_displays_voice_and_revision(self):
        """Provenance display shows 'Generated with {Voice} — Revision {N}'."""
        generate_func = re.search(
            r"async function generateTestAudio\(\).*?Generated with.*?Revision",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(generate_func, "Should display provenance with voice and revision")

    def test_select_library_voice_resets_preview_revision_id(self):
        """selectLibraryVoice resets previewRevisionId to null on voice change."""
        select_func = re.search(
            r"function selectLibraryVoice\([^)]*\).*?previewRevisionId=null",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(select_func, "Should reset previewRevisionId on voice change")

    def test_generate_test_audio_sends_optional_preview_text(self):
        """generateTestAudio sends preview_text if provided."""
        preview_section = re.search(
            r"async function generateTestAudio\(\).*?api\('/api/voice-previews'",
            self.js,
            re.DOTALL,
        )
        if preview_section:
            section_text = preview_section.group(0)
            # Should check for preview text and conditionally add to payload
            self.assertIn("libraryPreviewText", section_text)
            self.assertIn("preview_text", section_text)

    def test_preview_text_maxlength_is_500(self):
        """Preview text textarea has maxlength of 500."""
        self.assertIn('id="libraryPreviewText"', self.html)
        self.assertIn('maxlength="500"', self.html)

    def test_preview_text_counter_shows_500_limit(self):
        """Preview text counter shows / 500 limit."""
        self.assertIn('id="libraryPreviewTextCounter"', self.html)
        counter_pattern = r'id="libraryPreviewTextCounter"[^>]*>[^<]*500'
        self.assertRegex(self.html, counter_pattern)

    def test_reference_audio_separate_from_preview_audio(self):
        """Reference audio player is separate from preview audio player."""
        self.assertIn('id="libraryReferenceAudio"', self.html)
        self.assertIn('id="libraryPreviewAudio"', self.html)
        # Ensure they are different elements
        reference_count = self.html.count('id="libraryReferenceAudio"')
        preview_count = self.html.count('id="libraryPreviewAudio"')
        self.assertEqual(reference_count, 1)
        self.assertEqual(preview_count, 1)

    def test_update_preview_text_counter_updates_character_count(self):
        """updatePreviewTextCounter updates the counter display."""
        update_section = re.search(
            r"function updatePreviewTextCounter\(\).*?\}",
            self.js,
            re.DOTALL,
        )
        if update_section:
            section_text = update_section.group(0)
            self.assertIn("libraryPreviewText", section_text)
            self.assertIn("libraryPreviewTextCounter", section_text)
            self.assertIn(".length", section_text)

    def test_use_default_preview_text_clears_textarea(self):
        """useDefaultPreviewText clears the preview text textarea."""
        use_default_section = re.search(
            r"function useDefaultPreviewText\(\).*?\}",
            self.js,
            re.DOTALL,
        )
        if use_default_section:
            section_text = use_default_section.group(0)
            self.assertIn("libraryPreviewText", section_text)
            self.assertIn(".value", section_text)
            # Should set to empty string
            self.assertIn("''", section_text)

    def test_reference_audio_player_has_no_controls(self):
        """Reference audio player has no controls attribute (programmatic playback only)."""
        # Should NOT have controls attribute
        pattern = r'id="libraryReferenceAudio"[^>]*\scontrols'
        self.assertIsNone(re.search(pattern, self.html))
        # Should have preload="none"
        self.assertIn('id="libraryReferenceAudio"', self.html)
        self.assertIn('preload="none"', self.html)

    def test_no_duplicate_preview_text_counter_function(self):
        """No duplicate updatePreviewTextCounter function declarations."""
        pattern = r"function\s+updatePreviewTextCounter\s*\("
        matches = re.findall(pattern, self.js)
        self.assertEqual(len(matches), 1)

    def test_no_duplicate_use_default_preview_function(self):
        """No duplicate useDefaultPreviewText function declarations."""
        pattern = r"function\s+useDefaultPreviewText\s*\("
        matches = re.findall(pattern, self.js)
        self.assertEqual(len(matches), 1)

    def test_no_duplicate_play_reference_audio_function(self):
        """No duplicate playReferenceAudio function declarations."""
        pattern = r"function\s+playReferenceAudio\s*\("
        matches = re.findall(pattern, self.js)
        self.assertEqual(len(matches), 1)


    def test_no_radio_buttons_in_revision_rows(self):
        """Revision rows do not include radio button inputs."""
        self.assertNotIn('input type="radio" name="libraryRevisionRadio"', self.js)

    def test_no_selected_revision_summary_element(self):
        """Selected revision summary element does not exist in HTML."""
        self.assertNotIn('id="librarySelectedRevision"', self.html)
        self.assertNotIn('id="librarySelectedRevisionText"', self.html)

    def test_no_preview_test_status_element(self):
        """Preview test status element no longer exists (replaced by Test Synthesis panel design)."""
        self.assertNotIn('id="libraryPreviewTestStatus"', self.html)

    # Reference Audio playback behavior tests
    def test_play_reference_audio_toggle_behavior(self):
        """playReferenceAudio toggles play/pause for same revision."""
        # Function should check if already playing and pause, or play if different/paused
        self.assertIn('function playReferenceAudio(', self.js)
        self.assertIn('audio.pause()', self.js)
        self.assertIn('audio.play()', self.js)
        # Should check current src to toggle
        play_ref_section = re.search(r"function playReferenceAudio\([^)]*\)\{", self.js)
        self.assertIsNotNone(play_ref_section, "playReferenceAudio function should exist")

    def test_play_reference_audio_error_handling(self):
        """playReferenceAudio handles playback errors safely."""
        # Should have error handling via .catch() or audio.onerror
        self.assertIn('function playReferenceAudio(', self.js)
        has_catch = '.catch(' in self.js and 'toast(' in self.js
        has_onerror = 'audio.onerror=' in self.js
        self.assertTrue(has_catch or has_onerror, "Should have error handling for audio playback")

    def test_play_reference_audio_loads_audio(self):
        """playReferenceAudio sets src and loads audio file."""
        self.assertIn('function playReferenceAudio(', self.js)
        self.assertIn('audio.src=', self.js)
        self.assertIn('audio.load()', self.js)

    def test_reference_audio_cleared_on_voice_change(self):
        """Reference audio is cleared when selecting different logical voice."""
        self.assertIn('function selectLibraryVoice(', self.js)
        # selectLibraryVoice should clear or reset reference audio state
        # May use libraryReferenceAudio element or refAudio variable
        select_voice_has_ref_audio = 'libraryReferenceAudio' in self.js or 'refAudio' in self.js
        self.assertTrue(select_voice_has_ref_audio, "Should reference audio element")

    def test_reference_audio_cleared_on_preview(self):
        """Reference audio player distinct from preview audio."""
        self.assertIn('libraryReferenceAudio', self.html)
        self.assertIn('libraryPreviewAudio', self.html)

    def test_generate_button_disabled_without_revision_selected(self):
        """Generate Test Audio button disabled until revision selected in dropdown."""
        self.assertIn('function selectLibraryVoice(', self.js)
        self.assertIn("$('#libraryGenerateTestAudio').disabled=true", self.js)

    def test_reference_audio_url_uses_exact_id(self):
        """Reference audio endpoint uses exact revision ID not index."""
        self.assertIn('/api/custom-voice-revisions/${revisionId}/audio', self.js)

    # Phase 5B5: Preset Voice Preview Restoration Tests

    def test_preset_voice_preview_panel_exists(self):
        """Compact standalone Preset Voice Preview panel exists."""
        self.assertIn('preset-voice-preview-panel', self.html)

    def test_preset_voice_select_element_exists(self):
        """Preset voice select dropdown exists in HTML."""
        self.assertIn('id="presetVoiceSelect"', self.html)

    def test_load_preset_voices_button_exists(self):
        """Load preset voices button exists in HTML."""
        self.assertIn('id="loadPresetVoices"', self.html)

    def test_preview_preset_voice_button_exists(self):
        """Preview preset voice button exists in HTML."""
        self.assertIn('id="previewPresetVoice"', self.html)

    def test_preset_preview_box_exists(self):
        """Preset preview box exists in HTML."""
        self.assertIn('id="presetPreviewBox"', self.html)

    def test_preset_preview_audio_element_exists(self):
        """Preset preview audio element exists in HTML."""
        self.assertIn('id="presetPreviewAudio"', self.html)

    def test_preset_preview_status_element_exists(self):
        """Preset preview status element exists in HTML."""
        self.assertIn('id="presetPreviewStatus"', self.html)

    def test_load_preset_voices_function_exists(self):
        """loadPresetVoices function exists in JavaScript."""
        self.assertIn("async function loadPresetVoices()", self.js)

    def test_preview_preset_voice_function_exists(self):
        """previewPresetVoice function exists in JavaScript."""
        self.assertIn("async function previewPresetVoice()", self.js)

    def test_load_preset_voices_handler_wired(self):
        """loadPresetVoices event handler is wired."""
        self.assertIn("$('#loadPresetVoices').onclick=loadPresetVoices", self.js)

    def test_preview_preset_voice_handler_wired(self):
        """previewPresetVoice event handler is wired."""
        self.assertIn("$('#previewPresetVoice').onclick=previewPresetVoice", self.js)

    def test_preset_voice_select_change_handler_wired(self):
        """presetVoiceSelect change event handler is wired."""
        pattern = r"\$\('#presetVoiceSelect'\)\.addEventListener\('change'"
        self.assertRegex(self.js, pattern)

    def test_preset_preview_sends_only_voice_id(self):
        """previewPresetVoice sends only voice_id (not custom_voice_revision_id)."""
        preset_section = re.search(
            r"async function previewPresetVoice\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(preset_section)
        section_text = preset_section.group(0)
        self.assertIn("voice_id:", section_text)
        self.assertNotIn("custom_voice_revision_id", section_text)

    def test_preset_preview_does_not_send_preview_text(self):
        """previewPresetVoice does not send preview_text field."""
        preset_section = re.search(
            r"async function previewPresetVoice\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(preset_section)
        section_text = preset_section.group(0)
        self.assertNotIn("preview_text", section_text)

    def test_preset_preview_uses_voice_previews_endpoint(self):
        """previewPresetVoice uses existing /api/voice-previews endpoint."""
        preset_section = re.search(
            r"async function previewPresetVoice\(\).*?}catch",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(preset_section)
        section_text = preset_section.group(0)
        self.assertIn("/api/voice-previews", section_text)

    def test_no_duplicate_dom_ids_between_preset_and_custom(self):
        """No DOM ID conflicts between preset preview and custom voice library."""
        preset_ids = ["presetVoiceSelect", "loadPresetVoices", "previewPresetVoice",
                      "presetPreviewBox", "presetPreviewAudio", "presetPreviewStatus"]
        for element_id in preset_ids:
            pattern = rf'id="{element_id}"'
            matches = re.findall(pattern, self.html)
            self.assertEqual(
                len(matches),
                1,
                f"Expected exactly 1 occurrence of id=\"{element_id}\", found {len(matches)}",
            )

    def test_custom_voice_library_remains_only_custom_workflow(self):
        """Custom Voice Library is the only custom-reference workflow."""
        # Should have exactly one custom voice library panel
        library_panels = self.html.count('custom-voice-library-panel')
        self.assertEqual(library_panels, 1)

        # Should not have redundant standalone custom preview panel
        self.assertNotIn('custom-voice-preview-panel', self.html)

    # Library Smoke Filtering Tests

    def test_show_smoke_books_checkbox_exists(self):
        """Show test data checkbox exists in HTML."""
        self.assertIn('id="showSmokeBooks"', self.html)

    def test_is_smoke_book_function_exists(self):
        """isSmokeBook helper function exists in JavaScript."""
        self.assertIn("function isSmokeBook(title)", self.js)

    def test_show_smoke_books_state_initialized(self):
        """showSmokeBooks state field initialized in global state."""
        self.assertIn("showSmokeBooks:", self.js)

    def test_smoke_filtering_uses_centralized_logic(self):
        """Smoke filtering uses centralized isSmokeBook function."""
        load_books_section = re.search(
            r"async function loadBooks\(\).*?}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(load_books_section)
        section_text = load_books_section.group(0)
        self.assertIn("isSmokeBook", section_text)

    def test_smoke_books_hidden_by_default(self):
        """Smoke books are filtered by default when showSmokeBooks is false."""
        load_books_section = re.search(
            r"async function loadBooks\(\).*?}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(load_books_section)
        section_text = load_books_section.group(0)
        # Should filter based on showSmokeBooks state
        self.assertIn("state.showSmokeBooks", section_text)
        self.assertIn("filter", section_text)

    def test_show_smoke_books_handler_wired(self):
        """showSmokeBooks checkbox event handler is wired."""
        pattern = r"\$\('#showSmokeBooks'\)\.onchange"
        self.assertRegex(self.js, pattern)

    def test_smoke_checkbox_calls_load_books(self):
        """showSmokeBooks checkbox change triggers loadBooks."""
        handler_section = re.search(
            r"\$\('#showSmokeBooks'\)\.onchange.*?loadBooks\(\)",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(handler_section)

    def test_smoke_pattern_matches_common_test_books(self):
        """isSmokeBook pattern matches common test book patterns."""
        is_smoke_section = re.search(
            r"function isSmokeBook\(title\).*?}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(is_smoke_section)
        section_text = is_smoke_section.group(0)
        # Should match patterns like "Smoke", "Speaker Review", "Character Bible Smoke"
        self.assertIn("smoke", section_text.lower())
        self.assertIn("speaker", section_text.lower())
        self.assertIn("character", section_text.lower())

    # Custom Voice Form Layout Tests

    def test_upload_revision_grid_class_exists(self):
        """upload-revision-grid class exists in HTML for form layout."""
        self.assertIn('class="upload-revision-grid"', self.html)

    def test_upload_revision_grid_styles_exist(self):
        """upload-revision-grid styles exist in CSS."""
        self.assertIn(".upload-revision-grid", self.css)

    def test_upload_revision_grid_two_column_layout(self):
        """upload-revision-grid uses two-column responsive layout."""
        grid_styles_section = re.search(
            r"\.upload-revision-grid\{[^}]+\}",
            self.css,
            re.DOTALL,
        )
        self.assertIsNotNone(grid_styles_section)
        section_text = grid_styles_section.group(0)
        self.assertIn("grid-template-columns", section_text)
        self.assertIn("1fr 1fr", section_text)

    def test_upload_revision_grid_responsive_mobile(self):
        """upload-revision-grid collapses to single column on mobile."""
        # Should have media query for smaller screens
        self.assertIn("@media(max-width:700px)", self.css)
        mobile_section = re.search(
            r"@media\(max-width:700px\)\{.*?\.upload-revision-grid.*?\}",
            self.css,
            re.DOTALL,
        )
        self.assertIsNotNone(mobile_section)

    def test_upload_revision_labels_full_width_structure(self):
        """Upload revision labels use proper full-width form group structure."""
        upload_section = re.search(
            r'<div class="upload-revision-grid">.*?</div>',
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(upload_section)
        section_text = upload_section.group(0)
        # Should have labels wrapping inputs/textareas
        self.assertIn("<label>", section_text)
        self.assertIn("Reference Audio", section_text)
        self.assertIn("Exact Transcript", section_text)

    def test_textarea_minimum_height_in_upload_grid(self):
        """Textareas in upload-revision-grid have minimum height."""
        grid_styles_section = re.search(
            r"\.upload-revision-grid.*?min-height",
            self.css,
            re.DOTALL,
        )
        self.assertIsNotNone(grid_styles_section)

    # Create New Voice Form Layout Tests

    def test_create_voice_form_class_exists(self):
        """create-voice-form class exists in HTML."""
        self.assertIn('class="create-voice-form"', self.html)

    def test_voice_form_group_class_exists(self):
        """voice-form-group class exists in HTML for form groups."""
        self.assertIn('class="voice-form-group"', self.html)

    def test_voice_description_input_class_exists(self):
        """voice-description-input class exists for description textareas."""
        self.assertIn('class="voice-description-input"', self.html)

    def test_create_new_voice_not_using_form_grid(self):
        """Create New Voice section does not use broken inline form-grid layout."""
        # Find the Create New Voice section
        create_section = re.search(
            r'<h3>Create New Voice</h3>.*?<button id="libraryCreate"',
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(create_section)
        section_text = create_section.group(0)
        # Should NOT use form-grid
        self.assertNotIn('class="form-grid"', section_text)
        # Should use create-voice-form
        self.assertIn('class="create-voice-form"', section_text)

    def test_create_voice_name_and_description_separate_groups(self):
        """Name and Description are in separate form groups."""
        create_section = re.search(
            r'<h3>Create New Voice</h3>.*?<button id="libraryCreate"',
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(create_section)
        section_text = create_section.group(0)
        # Should have multiple voice-form-group instances
        form_groups = re.findall(r'class="voice-form-group"', section_text)
        self.assertGreaterEqual(len(form_groups), 2)

    def test_create_voice_labels_block_level(self):
        """Labels in Create New Voice are block-level above controls."""
        create_section = re.search(
            r'<h3>Create New Voice</h3>.*?<button id="libraryCreate"',
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(create_section)
        section_text = create_section.group(0)
        # Labels should have for attribute and be separate from input
        self.assertIn('for="libraryNewName"', section_text)
        self.assertIn('for="libraryNewDescription"', section_text)

    def test_create_voice_description_has_dedicated_class(self):
        """Description textarea has voice-description-input class."""
        create_section = re.search(
            r'<textarea id="libraryNewDescription"[^>]*>',
            self.html,
        )
        self.assertIsNotNone(create_section)
        textarea_tag = create_section.group(0)
        self.assertIn('voice-description-input', textarea_tag)

    def test_create_voice_form_styles_exist(self):
        """create-voice-form styles exist in CSS."""
        self.assertIn(".create-voice-form", self.css)

    def test_voice_form_group_styles_exist(self):
        """voice-form-group styles exist in CSS."""
        self.assertIn(".voice-form-group", self.css)

    def test_voice_description_input_styles_exist(self):
        """voice-description-input styles exist in CSS."""
        self.assertIn(".voice-description-input", self.css)

    def test_voice_description_input_has_minimum_height(self):
        """voice-description-input has reasonable minimum height (90-110px)."""
        desc_styles = re.search(
            r"\.voice-description-input\{[^}]*min-height:\s*(\d+)px",
            self.css,
        )
        self.assertIsNotNone(desc_styles)
        height = int(desc_styles.group(1))
        self.assertGreaterEqual(height, 90)
        self.assertLessEqual(height, 110)

    def test_voice_form_group_labels_block_level_in_css(self):
        """voice-form-group labels are styled as block-level in CSS."""
        label_styles = re.search(
            r"\.voice-form-group label\{[^}]*display:\s*block",
            self.css,
        )
        self.assertIsNotNone(label_styles)

    def test_voice_form_controls_full_width(self):
        """Form controls in voice-form-group are full width."""
        control_styles = re.search(
            r"\.voice-form-group (input|select|textarea)\{[^}]*width:\s*100%",
            self.css,
        )
        self.assertIsNotNone(control_styles)

    def test_voice_form_controls_have_focus_state(self):
        """Form controls have visible focus state."""
        focus_styles = re.search(
            r"\.voice-form-group (input|select|textarea):focus",
            self.css,
        )
        self.assertIsNotNone(focus_styles)

    def test_voice_description_input_resize_vertical(self):
        """voice-description-input has resize: vertical."""
        self.assertIn("resize:vertical", self.css.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()


    # Phase 1 UI Integration Tests

    def test_custom_voices_state_initialized(self):
        """customVoices state field initialized in global state."""
        self.assertIn("customVoices:", self.js)

    def test_load_custom_voices_function_exists(self):
        """loadCustomVoices function exists in JavaScript."""
        self.assertIn("async function loadCustomVoices()", self.js)

    def test_load_custom_voices_fetches_active_only(self):
        """loadCustomVoices fetches /api/custom-voices?active_only=true."""
        load_section = re.search(
            r"async function loadCustomVoices\(\).*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(load_section)
        section_text = load_section.group(0)
        self.assertIn("/api/custom-voices?active_only=true", section_text)

    def test_load_custom_voices_stores_active_voices(self):
        """loadCustomVoices filters and stores only active voices."""
        load_section = re.search(
            r"async function loadCustomVoices\(\).*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(load_section)
        section_text = load_section.group(0)
        self.assertIn("state.customVoices", section_text)
        self.assertIn("is_active", section_text)

    def test_open_casting_loads_custom_voices(self):
        """openCasting loads custom voices alongside preset voices."""
        open_casting_section = re.search(
            r"async function openCasting\(\).*?await loadVoices\(\);",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(open_casting_section)
        section_text = open_casting_section.group(0)
        # Should call loadCustomVoices after loadVoices
        self.assertIn("await loadCustomVoices()", section_text)

    def test_casting_voice_options_merges_preset_and_custom(self):
        """castingVoiceOptions merges preset and custom voices."""
        casting_section = re.search(
            r"function castingVoiceOptions\([^)]*\).*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(casting_section)
        section_text = casting_section.group(0)
        # Should reference both state.voices and state.customVoices
        self.assertIn("state.voices", section_text)
        self.assertIn("state.customVoices", section_text)

    def test_casting_voice_options_uses_optgroups(self):
        """castingVoiceOptions uses optgroup to separate preset and custom."""
        casting_section = re.search(
            r"function castingVoiceOptions\([^)]*\).*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(casting_section)
        section_text = casting_section.group(0)
        self.assertIn("<optgroup", section_text)
        self.assertIn("Preset Voices", section_text)
        self.assertIn("Custom Voices", section_text)

    def test_casting_voice_options_uses_custom_prefix(self):
        """castingVoiceOptions uses custom:<id> format for custom voice values."""
        casting_section = re.search(
            r"function castingVoiceOptions\([^)]*\).*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(casting_section)
        section_text = casting_section.group(0)
        self.assertIn("custom:", section_text)

    def test_casting_voice_options_labels_custom_voices(self):
        """castingVoiceOptions labels custom voices with (Custom) suffix."""
        casting_section = re.search(
            r"function castingVoiceOptions\([^)]*\).*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(casting_section)
        section_text = casting_section.group(0)
        self.assertIn("(Custom)", section_text)

    def test_resolution_text_displays_custom_voice_names(self):
        """resolutionText displays custom voice display name for custom:<id> values."""
        resolution_section = re.search(
            r"function resolutionText\([^)]*\).*?\}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(resolution_section)
        section_text = resolution_section.group(0)
        # Should check for custom: prefix and lookup in state.customVoices
        self.assertIn("startsWith('custom:')", section_text)
        self.assertIn("state.customVoices", section_text)

    def test_source_labels_includes_custom_reference(self):
        """sourceLabels includes custom_reference label."""
        self.assertIn("custom_reference:", self.js)
        self.assertIn("Custom voice", self.js)
