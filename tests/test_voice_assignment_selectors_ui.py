from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VoiceAssignmentSelectorsUIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")

    def test_central_voice_catalog_state_and_loader_exist(self) -> None:
        self.assertIn("voiceCatalog:{items:[]}", self.js)
        self.assertIn("async function loadVoiceCatalog()", self.js)
        self.assertIn("/api/voice-catalog", self.js)
        self.assertIn("function voiceCatalogItems()", self.js)
        self.assertIn("function voiceCatalogItem(key)", self.js)

    def test_selector_options_use_stable_assignment_keys_not_display_names_or_revisions(self) -> None:
        section = self.js[self.js.index("function castingVoiceOptions"): self.js.index("const sourceLabels")]
        self.assertIn("assignment_key", section)
        self.assertIn("custom:${v.id}", self.js)
        self.assertNotIn("custom:${v.id}:${", section)
        self.assertNotIn("effective_synthesis_revision_id}\"", section)
        self.assertNotIn("display_name}\"", section)

    def test_unusable_custom_options_are_disabled_unless_preserving_existing_selection(self) -> None:
        section = self.js[self.js.index("function castingVoiceOptions"): self.js.index("const sourceLabels")]
        self.assertIn("!item.selectable&&item.assignment_key!==selected", section)
        self.assertIn("disabled", section)
        self.assertIn("Legacy / unavailable", section)
        self.assertIn("data-legacy-voice", section)

    def test_book_profile_fields_share_catalog_and_show_provenance(self) -> None:
        for element_id, provenance_id in (
            ("profileNarratorVoice", "profileNarratorProvenance"),
            ("profileMaleVoice", "profileMaleProvenance"),
            ("profileFemaleVoice", "profileFemaleProvenance"),
            ("profileExplicitVoice", "profileExplicitProvenance"),
        ):
            self.assertIn(f'id="{element_id}"', self.html)
            self.assertIn(f'id="{provenance_id}"', self.html)
            self.assertIn(f'aria-describedby="{provenance_id}"', self.html)
        self.assertIn("renderProfileProvenance()", self.js)
        self.assertIn("selectedVoiceProvenance", self.js)
        self.assertIn("snapshot cũ giữ nguyên", self.js)

    def test_profile_save_boundary_and_payload_stay_explicit(self) -> None:
        save_section = self.js[self.js.index("async function saveVoiceProfile"): self.js.index("async function openCasting")]
        self.assertIn("runProductionCommand", save_section)
        self.assertIn("commandType:'SAVE_VOICE_ASSIGNMENTS'", save_section)
        self.assertIn("narrator_voice_id:$('#profileNarratorVoice').value", save_section)
        self.assertIn("male_dialogue_voice_id:$('#profileMaleVoice').value", save_section)
        self.assertIn("female_dialogue_voice_id:$('#profileFemaleVoice').value", save_section)
        self.assertNotIn("method:'PUT'", save_section)
        self.assertNotIn("/api/casting", save_section)
        self.assertNotIn("/api/jobs", save_section)

    def test_character_override_has_no_override_option_and_custom_catalog_selector(self) -> None:
        row_section = self.js[self.js.index("function renderCharacterRow"): self.js.index("function bibleSummary")]
        self.assertIn("Không dùng giọng riêng", row_section)
        self.assertIn("castingVoiceOptions(c.voice_override_id||'')", row_section)
        self.assertIn("character-voice-provenance", row_section)
        self.assertIn("Đang kế thừa giọng hiệu lực từ Book Voice Profile", row_section)

    def test_character_save_sends_override_without_touching_plan_job_or_render(self) -> None:
        save_section = self.js[self.js.index("async function saveCharacter"): self.js.index("async function deleteCharacter")]
        self.assertIn("/voice-override", save_section)
        self.assertIn("voice_override_id:custom?$(`#character-voice-${id}`).value:null", save_section)
        self.assertNotIn("/api/casting", save_section)
        self.assertNotIn("/api/jobs", save_section)
        self.assertNotIn("renderCastingPlan", save_section)

    def test_loading_routes_do_not_auto_save_voice_assignments(self) -> None:
        open_section = self.js[self.js.index("async function openCasting"): self.js.index("function speakerName")]
        self.assertIn("await loadVoices()", open_section)
        self.assertIn("/api/chapters/${chapterId}/casting", open_section)
        self.assertNotIn("saveVoiceProfile", open_section)
        self.assertNotIn("saveCharacter", open_section)
        self.assertNotIn("method:'PUT'", open_section)
        self.assertNotIn("method:'POST'", open_section)

    def test_voice_library_remains_separate_and_production_forms_are_not_duplicated_in_books_view(self) -> None:
        books_view = re.search(
            r'<section id="booksView".*?</section>\s*<section id="audioView"',
            self.html,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(books_view)
        self.assertNotIn("custom-voice-library-panel", books_view.group(0))
        self.assertNotIn('id="profileNarratorVoice"', books_view.group(0))
        self.assertIn('href="#/production"', books_view.group(0))

    def test_accessibility_and_styles_for_provenance(self) -> None:
        self.assertIn(".voice-provenance", self.css)
        self.assertIn("font-weight:500", self.css)
        self.assertIn("aria-describedby", self.html)

    def test_no_provider_or_chapter_369_hardcoding_in_selector_work(self) -> None:
        selector_source = self.js[self.js.index("async function loadVoices"): self.js.index("async function previewVoice")]
        selector_source += self.js[self.js.index("function renderVoiceProfile"): self.js.index("async function previewProfileVoice")]
        selector_source += self.js[self.js.index("function renderCharacterRow"): self.js.index("function bibleSummary")]
        self.assertNotIn("369", selector_source)
        self.assertNotIn("/api/voice-previews", selector_source)
        self.assertNotIn("/api/jobs", selector_source)

    def test_daily_prod_stage_isolation_hooks_remain_present(self) -> None:
        self.assertIn("applyProductionStageIsolation", self.js)
        self.assertIn("productionCurrentFlowStep", self.js)
        self.assertIn("productionFlowNext').disabled=true", self.js)

    def test_assignment_registry_is_not_read_only_and_uses_production_commands(self) -> None:
        section = self.js[
            self.js.index("function registryScopeOptions"):
            self.js.index("async function loadBookVoiceRegistry")
        ] + self.js[
            self.js.index("renderBookVoiceRegistryPage=function"):
            self.js.index("async function saveBookRegistryVoice")
        ]
        self.assertIn("data-registry-scope-key", section)
        self.assertIn("data-registry-voice-key", section)
        self.assertIn("data-registry-apply", section)
        self.assertIn("data-registry-clear", section)
        self.assertIn("Mặc định cho sách", section)
        self.assertIn("Phạm vi chương", section)
        self.assertIn("SET_CHAPTER_VOICE_OVERRIDE", section)
        self.assertIn("SET_RANGE_VOICE_OVERRIDE", section)
        self.assertIn("CLEAR_CHAPTER_VOICE_OVERRIDE", section)
        self.assertIn("CLEAR_RANGE_VOICE_OVERRIDE", section)
        self.assertIn("runProductionCommand", section)
        self.assertNotIn("Narrator/unknown", section)
        self.assertNotIn("disabled title=\"Override", section)

    def test_assignment_registry_exposes_character_mapping_flow(self) -> None:
        section = self.js[
            self.js.index("function registryStatusLabel"):
            self.js.index("async function saveBookRegistryVoice")
        ]
        self.assertIn("UNRESOLVED_DIALOGUE", section)
        self.assertIn("unresolved_dialogue", section)
        self.assertIn("data-registry-map", section)
        self.assertIn("data-registry-new-character", section)
        self.assertIn("data-registry-character-key", section)
        self.assertIn("data-registry-alias-key", section)
        self.assertIn("data-create-character-top", section)
        self.assertIn("CREATE_CHARACTER", section)
        self.assertIn("MAP_SPEAKER_TO_CHARACTER", section)
        self.assertIn("expected_registry_fingerprint:registryRowFingerprint(row)", section)
        mapping_function = self.js[
            self.js.index("async function saveRegistrySpeakerMapping"):
            self.js.index("async function createTopLevelAssignmentCharacter")
        ]
        self.assertNotIn("commandType:'PREPARE'", mapping_function)
        self.assertNotIn("commandType:'START_RENDER'", mapping_function)

    def test_exact_assignment_range_url_remains_supported_by_working_context(self) -> None:
        self.assertIn("#/assignment", self.js)
        self.assertIn("book=1&from=1&to=10&skip_completed=1", "#/assignment?book=1&from=1&to=10&skip_completed=1")
        self.assertIn("restoreScopedWorkingContextFromRoute", self.js)
        self.assertIn("loadBookVoiceRegistry", self.js)
        self.assertIn("renderRegistryTableRow(row,context)", self.js)

    def test_assignment_registry_preserves_details_focus_scroll_and_drafts(self) -> None:
        self.assertIn("emptyBookVoiceRegistryState", self.js)
        self.assertIn("speakerSuggestions:emptySpeakerSuggestionState()", self.js)
        self.assertIn("openDetails:{}", self.js)
        self.assertIn("mergeBookVoiceRegistryState", self.js)
        self.assertIn("captureRegistryUiSnapshot", self.js)
        self.assertIn("restoreRegistryUiSnapshot", self.js)
        self.assertIn("pruneRegistryLocalState", self.js)
        self.assertIn("data-registry-detail", self.js)
        self.assertIn("rememberRegistryDetailState", self.js)
        self.assertIn("state.bookVoiceRegistry=mergeBookVoiceRegistryState", self.js)
        self.assertNotIn(
            "state.bookVoiceRegistry={status:'ready',loading:false,error:null,result,scopeKey,requestId}",
            self.js,
        )

    def test_gemini_speaker_review_workspace_is_draft_only(self) -> None:
        section = self.js[
            self.js.index("function speakerSuggestionScopeKey"):
            self.js.index("function clearRegistryDraft")
        ]
        self.assertIn("/api/production/speaker-review-suggestions", section)
        self.assertIn("GENERATE_SPEAKER_SUGGESTIONS", section)
        self.assertIn("DEFER_SPEAKER_SUGGESTION", section)
        self.assertIn("EDIT_AND_ACCEPT_SPEAKER_SUGGESTION", section)
        self.assertIn("APPROVE_SPEAKER_REVIEW_BATCH", section)
        self.assertIn("data-speaker-suggestion-filter", section)
        self.assertIn("data-speaker-suggestion-resolution", section)
        self.assertIn("data-speaker-suggestion-character", section)
        self.assertIn("data-speaker-suggestion-voice", section)
        self.assertIn("Phân tích người nói bằng Gemini", section)
        self.assertIn("Gemini chỉ tạo đề xuất", section)
        self.assertNotIn("commandType:'PREPARE'", section)
        self.assertNotIn("commandType:'START_RENDER'", section)


if __name__ == "__main__":
    unittest.main()
