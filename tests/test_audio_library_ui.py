from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AudioLibraryUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")

    def _function_block(self, name: str) -> str:
        marker = f"function {name}"
        start = self.js.index(marker)
        next_match = re.search(r"\nfunction\s+\w+", self.js[start + 1 :])
        end = start + 1 + next_match.start() if next_match else len(self.js)
        return self.js[start:end]

    def test_audio_library_is_the_dedicated_post_render_review_workspace(self) -> None:
        for value in (
            'data-app-route="audio" aria-label="Duyệt audio">Duyệt audio</a>',
            'id="audioView"',
            'id="audioHeading">Duyệt audio</h2>',
            "Đây là nơi duy nhất để nghe, duyệt, yêu cầu sửa và tải thành phẩm.",
            'id="audioReviewSummary"',
            'id="audioPendingCount"',
            'id="audioNeedsFixesCount"',
            'id="audioAcceptedCount"',
            'id="audioReviewDetail"',
            'id="audioLibraryList" class="audio-library-list audio-review-table" role="table"',
            'id="audioLibraryPlayer"',
            'id="audioLibraryAudio"',
            'id="audioLibraryDownload"',
            'id="audioQaAccept"',
            'id="audioQaOpenRepair"',
            'id="audioQaNeedsFixes"',
        ):
            self.assertIn(value, self.html)
        self.assertIn("Sản xuất chỉ tạo audio", self.html)

    def test_audio_route_fetches_audio_library_and_pauses_when_leaving(self) -> None:
        route_block = self._function_block("setAppRoute")
        self.assertIn("if(next!=='audio')resetAudioLibraryPlayer()", route_block)
        self.assertIn("if(next==='audio')ensureAudioLibraryLoaded()", route_block)
        load_block = self._function_block("loadAudioLibrary")
        self.assertIn("api('/api/audio-library')", load_block)
        self.assertNotIn("method:'POST'", load_block)
        self.assertNotIn("method:'PUT'", load_block)
        self.assertNotIn("method:'PATCH'", load_block)
        self.assertNotIn("method:'DELETE'", load_block)

    def test_queue_rows_use_safe_dom_and_expose_review_columns(self) -> None:
        block = self._function_block("renderAudioLibraryItem")
        for value in (
            "document.createElement('article')",
            "row.setAttribute('role','row')",
            "title.textContent=audioLibraryTitle(item)",
            "created.textContent=audioLibraryCreatedAt(item)",
            "duration.textContent=formatDurationMs(item.duration_ms)",
            "badge.textContent=qa.label",
            "open.textContent=audioReviewActionLabel(item)",
            "row.append(main,created,duration,statusCell,actions)",
        ):
            self.assertIn(value, block)
        self.assertNotIn("innerHTML", block)
        header = self._function_block("audioReviewTableHeader")
        for label in ("Chương", "Tạo lúc", "Thời lượng", "Trạng thái", "Hành động"):
            self.assertIn(label, header)

    def test_artifact_configuration_is_read_only_and_detail_scoped(self) -> None:
        self.assertIn("function sequenceRanges", self.js)
        self.assertIn("function artifactConfigurationText", self.js)
        self.assertIn("async function loadArtifactConfiguration", self.js)
        self.assertIn("/api/artifacts/${Number(item.artifact_id)}/configuration", self.js)
        text_block = self._function_block("artifactConfigurationText")
        self.assertIn("actor.segment_count", text_block)
        self.assertIn("sequenceRanges(actor.sequences)", text_block)
        self.assertIn("source.parent_id", text_block)
        self.assertIn("synthesis.attempt_count", text_block)
        self.assertIn("artifact.human_qa_event_id", text_block)
        detail = self._function_block("renderAudioDetailActions")
        self.assertIn("audioArtifactConfiguration", detail)
        self.assertIn("loadArtifactConfiguration(item,configurationBody)", detail)
        self.assertNotIn("method:'POST'", detail)
        self.assertIn(".audio-artifact-configuration", self.css)

    def test_qa_labels_preserve_api_semantics(self) -> None:
        block = self._function_block("audioLibraryQaLabel")
        self.assertIn("value==='pending'", block)
        self.assertIn("Chờ Human QA", block)
        self.assertIn("value==='accepted'", block)
        self.assertIn("Đã chấp nhận", block)
        self.assertIn("Chưa xác định", block)
        unknown_tail = block[block.index("return{label:'Chưa xác định'") :]
        self.assertNotIn("accepted", unknown_tail)

    def test_pending_filter_and_summary_share_the_same_status_group(self) -> None:
        group = self._function_block("audioQaFilterGroup")
        summary = self._function_block("renderAudioReviewSummary")
        filtered = self._function_block("filteredAudioLibraryItems")
        self.assertIn("String(status||'pending').toLowerCase()", group)
        self.assertIn("audioQaFilterGroup(item.human_qa_status)===status", summary)
        self.assertIn("set('audioPendingCount',count('pending'))", summary)
        self.assertIn("audioQaFilterGroup(item.human_qa_status)!==qa", filtered)

    def test_repair_feedback_separates_playback_and_replacement_speed(self) -> None:
        for value in (
            'id="audioQaPlaybackSpeed"',
            'id="audioQaReplacementSpeed"',
            'id="audioQaRepeatedWords"',
            'id="audioQaLocalPacing"',
            'id="audioQaMarkPosition"',
            'id="audioQaResult"',
            "Gửi yêu cầu sửa",
        ):
            self.assertIn(value, self.html)
        self.assertIn("Tiếp tục sửa audio", self.js)
        self.assertIn("audio.playbackRate=Number(event.target.value||1)", self.js)
        self.assertIn("global_speed_target:speed", self.js)
        self.assertIn("repeated_words:repeated", self.js)
        self.assertIn("local_pacing_adjustment_required:local", self.js)
        self.assertIn("position_markers:state.audioQa.markers", self.js)
        self.assertIn("if(changed)state.audioQa.markers=savedAudioQaMarkers(item)", self.js)
        self.assertIn("draft={repeated:Boolean($('#audioQaRepeatedWords')?.checked)", self.js)
        self.assertIn("$('#audioQaRepeatedWords').checked=draft.repeated", self.js)
        self.assertIn("submit.disabled=true", self.js)
        self.assertIn("Đang lưu phản hồi…", self.js)
        self.assertIn("qa_feedback", self.js)

    def test_repair_request_opens_one_combined_review_and_keeps_media_gates_separate(self) -> None:
        block = self._function_block("productionRepairPlanContent")
        for value in (
            "Kiểm tra toàn bộ bản sửa",
            "Khắc phục đoạn bị lặp chữ",
            "Xác nhận bản sửa",
            "Quay lại nghe audio",
            "Vị trí cần xử lý",
            "Chi tiết kỹ thuật",
        ):
            self.assertIn(value, block)
        self.assertIn("CONFIRM_REPAIR_PLAN", self.js)
        self.assertIn("APPLY_REPAIR_PLAN", self.js)
        self.assertIn("CONFIRM_REPAIR_DRAFT", self.js)
        self.assertIn("repairPlanRequestedFromHash", self.js)
        self.assertIn("repair_plan=1", self.js)
        self.assertIn("openAudioQaRepairPlan", self.js)
        self.assertIn("data-audio-qa-repair-plan", self.js)
        self.assertIn("REPAIR_PLAN_OPEN_STORAGE_KEY", self.js)
        self.assertIn("consumeRepairPlanOpen", self.js)
        self.assertNotIn("PREPARE", block)
        submit = self._function_block("submitAudioQa")
        self.assertIn("await openAudioQaRepairPlan(previous)", submit)

    def test_playback_and_download_use_only_api_safe_relative_url(self) -> None:
        safe_block = self._function_block("safeAudioLibraryUrl")
        self.assertIn(r"^\/api\/artifacts\/\d+\/file$", safe_block)
        item_block = self._function_block("renderAudioLibraryItem")
        select_block = self._function_block("selectAudioLibraryItem")
        detail_block = self._function_block("renderAudioDetailActions")
        combined = item_block + select_block + detail_block
        self.assertIn("safeAudioLibraryUrl(item.file_url||item.download_url)", combined)
        self.assertIn("download.href=url||'#'", detail_block)
        self.assertIn("audio.src=url", select_block)
        self.assertNotIn("output_path", combined)

    def test_unsafe_url_disables_queue_action_and_download(self) -> None:
        item_block = self._function_block("renderAudioLibraryItem")
        detail_block = self._function_block("renderAudioDetailActions")
        self.assertIn("open.disabled=!url", item_block)
        self.assertIn("download.href=url||'#'", detail_block)
        self.assertIn("aria-disabled", detail_block)
        self.assertIn("event=>event.preventDefault()", detail_block)

    def test_video_export_controls_live_in_selected_detail_and_are_retry_safe(self) -> None:
        safe_block = self._function_block("safeVideoExportUrl")
        detail_block = self._function_block("renderAudioDetailActions")
        export_block = self._function_block("exportAudioLibraryVideo")
        self.assertIn(r"^\/api\/video-exports\/artifact-\d+-[0-9a-f]{12}-[0-9a-f]{12}\/file$", safe_block)
        self.assertIn("audioLibraryVideoState(item)", detail_block)
        self.assertIn("video.status==='exporting'?'Đang xuất video…':'Xuất video'", detail_block)
        self.assertIn("exportButton.disabled=video.status==='exporting'||!!videoUrl||!videoAllowed", detail_block)
        self.assertIn("videoDownload.classList.toggle('hidden',!videoUrl)", detail_block)
        self.assertIn("videoPreview.src=videoUrl", detail_block)
        self.assertNotIn("videoPreview.play()", detail_block)
        self.assertIn("current?.status==='exporting'", export_block)
        self.assertIn("api(`/api/artifacts/${artifactId}/video-export`,{method:'POST'})", export_block)
        self.assertIn("safeVideoExportUrl(result.download_url)", export_block)

    def test_audio_library_does_not_autoplay_on_load(self) -> None:
        self.assertIn('id="audioLibraryAudio" controls preload="metadata"', self.html)
        load_block = self._function_block("loadAudioLibrary")
        render_block = self._function_block("renderAudioLibrary")
        self.assertNotIn(".play()", load_block)
        self.assertNotIn("play:true", render_block)
        self.assertIn("selectAudioLibraryItem(selected,{play:false})", render_block)

    def test_audio_route_selects_current_one_chapter_context_without_autoplay(self) -> None:
        self.assertIn("function audioLibraryContextSelection(items)", self.js)
        self.assertIn("currentProductionWorkingContext()", self.js)
        self.assertIn("Number(context.fromChapter)!==Number(context.toChapter)", self.js)
        load_block = self._function_block("loadAudioLibrary")
        self.assertIn("contextItem=audioLibraryContextSelection(items)", load_block)
        self.assertIn("selectedArtifactId:contextItem?Number(contextItem.artifact_id):null", load_block)
        self.assertNotIn("play:true", load_block)

    def test_audio_route_preselects_range_context_and_checks_zip_readiness(self) -> None:
        self.assertIn("function audioLibraryContextRange(items)", self.js)
        self.assertIn("function syncAudioRangeFromWorkingContext", self.js)
        self.assertIn("state.audioArchive.selectedChapterIds=desired", self.js)
        self.assertIn("await checkAudioRange()", self.js)
        load_block = self._function_block("loadAudioLibrary")
        self.assertIn("await syncAudioRangeFromWorkingContext(state.audioLibrary.items)", load_block)
        self.assertIn("await syncAudioRangeFromWorkingContext(items)", load_block)

    def test_empty_loading_error_and_retry_are_explicit(self) -> None:
        render_block = self._function_block("renderAudioLibrary")
        for value in (
            "Đang tải hàng đợi audio…",
            "Không tải được hàng đợi audio.",
            "Chưa có audio hoàn thành.",
            "const items=Array.isArray(lib.items)?lib.items:[]",
            "resetAudioLibraryPlayer()",
        ):
            self.assertIn(value, render_block)
        self.assertIn("$('#refreshAudioLibrary').onclick=refreshAudioLibrary", self.js)
        self.assertIn("$('#retryAudioLibrary').onclick=refreshAudioLibrary", self.js)

    def test_refresh_replaces_view_without_duplicate_static_listeners(self) -> None:
        render_block = self._function_block("renderAudioLibrary")
        self.assertIn("clearElement(list)", render_block)
        self.assertIn("list.appendChild(frag)", render_block)
        self.assertEqual(self.js.count("$('#refreshAudioLibrary').onclick=refreshAudioLibrary"), 1)
        self.assertEqual(self.js.count("$('#retryAudioLibrary').onclick=refreshAudioLibrary"), 1)

    def test_audio_library_mutation_is_bounded_to_explicit_human_qa(self) -> None:
        audio_related = "\n".join(
            line
            for line in self.js.splitlines()
            if "AudioLibrary" in line or "audioLibrary" in line or "audio-library" in line
        )
        forbidden = (
            "/api/jobs",
            "/api/jobs/prepare",
            "/start",
            "/api/voice-previews",
            "method:'PATCH'",
            "method:'DELETE'",
            "369",
        )
        for value in forbidden:
            self.assertNotIn(value, audio_related)
        self.assertIn("api(`/api/artifacts/${artifactId}/video-export`,{method:'POST'})", audio_related)
        self.assertNotIn("/human-approval", audio_related)
        self.assertIn("HUMAN_QA_ACCEPT", self.js)
        self.assertIn("HUMAN_QA_NEEDS_FIXES", self.js)
        self.assertNotIn("RESTORE_ACCEPTED_ARTIFACT", self.js)
        self.assertIn("/api/production/commands", self.js)
        submit = self._function_block("submitAudioQa")
        self.assertIn("runProductionCommand", submit)
        self.assertNotIn("window.confirm", submit)
        self.assertIn("notes", submit)
        self.assertNotIn("Chapter 369", self.html + self.js + self.css)
        self.assertNotIn("chapter 369", self.html + self.js + self.css)

    def test_audio_review_does_not_expose_history_or_restore(self) -> None:
        self.assertNotIn('id="audioQaHistory"', self.html)
        self.assertNotIn("Khôi phục làm bản hiện tại", self.js)
        self.assertNotIn("restoreAcceptedAudioArtifact", self.js)
        self.assertNotIn("RESTORE_ACCEPTED_ARTIFACT", self.js)

    def test_production_stage_accessibility_label_matches_four_visible_stages(self) -> None:
        self.assertIn('aria-label="Bốn giai đoạn sản xuất"', self.html)
        self.assertNotIn('aria-label="Sáu giai đoạn sản xuất"', self.html)
        shell = self.html.split('id="productionStageShell"', 1)[1].split("</ol>", 1)[0]
        self.assertEqual(shell.count("<li"), 4)
        self.assertIn("grid-template-columns:repeat(4,minmax(0,1fr))", self.css)

    def test_audio_review_styles_cover_master_detail_queue_and_mobile_layout(self) -> None:
        for value in (
            ".audio-review-summary",
            ".audio-review-workspace",
            ".audio-review-table-head",
            ".audio-review-row",
            ".audio-review-detail",
            ".audio-qa-primary-actions",
            ".audio-qa-repair-details",
            "@media(max-width:760px)",
        ):
            self.assertIn(value, self.css)

    def test_audio_review_row_grid_wins_over_legacy_card_layout(self) -> None:
        specific = ".audio-review-table-head,.audio-library-card.audio-review-row{grid-template-columns:minmax(145px,1.45fr)"
        self.assertIn(specific, self.css)
        self.assertGreater(self.css.index(specific), self.css.rindex(".audio-library-card{"))
        self.assertIn(
            "@media(max-width:760px){.audio-library-card.audio-review-row{grid-template-columns:1fr auto",
            self.css,
        )

    def test_audio_review_player_stays_in_flow_and_cannot_cover_qa_when_scrolling(self) -> None:
        legacy_sticky = ".audio-library-player{position:sticky"
        review_override = ".audio-review-detail .audio-library-player{position:static;top:auto;z-index:auto}"
        self.assertIn(legacy_sticky, self.css)
        self.assertIn(review_override, self.css)
        self.assertGreater(self.css.index(review_override), self.css.rindex(legacy_sticky))
        player = self.html.split('id="audioLibraryPlayer"', 1)[1].split("</div>\n            <section", 1)[0]
        self.assertIn('id="audioArtifactConfiguration"', player)
        self.assertIn('id="audioLibraryQaPanel"', self.html)

    def test_machine_triage_sits_between_player_and_human_qa_and_discards_stale_response(self) -> None:
        player = self.html.index('id="audioLibraryPlayer"')
        machine = self.html.index('id="automatedAudioQaPanel"')
        human = self.html.index('id="audioLibraryQaPanel"')
        self.assertLess(player, machine)
        self.assertLess(machine, human)
        for value in (
            "Điểm máy &amp; đoạn cần nghe",
            'id="automatedAudioQaSummary"',
            'id="automatedAudioQaScore"',
            "Độ đúng lời đọc, độ giống giọng và độ tự nhiên chưa được chấm tự động.",
            "automatedAudioQaIdentity(selected)!==identity",
            "requestId!==automatedAudioQaState().requestId",
            "/api/audio-library/${Number(item.artifact_id)}/automated-qa",
            "pointTime=formatDurationMs(point.timestamp_ms)||'0:00'",
            "audio.currentTime=Math.max(0,Number(point.timestamp_ms||0)/1000)",
            "if(options.force){const current=automatedAudioQaState();state.audioLibrary.automatedQa={state:'not_loaded'",
            "Có thể mất khoảng 1 phút; Player và Human QA vẫn dùng được.",
            "assessment.technical_score",
            "assessment.coverage_percent",
            "Tiếp theo:",
            "Máy phát hiện ${Number(resultSummary.risk_count||0)} dấu hiệu kỹ thuật và gom thành ${points.length} điểm cần nghe.",
            "points.slice(0,5)",
            "Xem thêm ${remaining} điểm",
            "Thu gọn danh sách",
            "if(changed){const detail=$('#audioReviewDetail');if(detail)detail.scrollTop=0}",
        ):
            self.assertIn(value, self.html + self.js)
        self.assertNotIn("localStorage.setItem('automated", self.js)
        self.assertIn(".automated-audio-qa-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))", self.css)
        self.assertIn(".automated-audio-qa-shortlist,.automated-audio-qa-more-list{display:grid;gap:7px}", self.css)
        self.assertIn("grid-template-columns:48px minmax(0,1fr)", self.css)
        self.assertIn("height:auto!important;min-height:0", self.css)
        self.assertIn("-webkit-line-clamp:2", self.css)
        self.assertNotIn(".automated-audio-qa-shortlist{max-height:", self.css)

    def test_audio_review_detail_and_repair_form_own_readable_layout(self) -> None:
        self.assertIn("@media(min-width:1101px){.audio-review-detail{position:sticky", self.css)
        self.assertIn("max-height:calc(100vh - var(--ux-topbar-height) - 24px);overflow-y:auto", self.css)
        self.assertIn(".audio-qa-feedback-options label{display:grid;grid-template-columns:20px minmax(0,1fr)", self.css)
        self.assertIn('.audio-qa-feedback-options input[type="checkbox"]{width:18px!important', self.css)

    def test_audio_removal_is_a_separate_confirmed_selection_flow(self) -> None:
        for value in (
            'id="audioDeleteMode"',
            'id="audioDeleteSelected"',
            'id="audioDeleteAllVisible"',
            'id="audioDeleteDialog"',
            'id="audioDeleteConfirmation"',
            "Job, văn bản, cấu hình giọng và custom voice vẫn được giữ",
        ):
            self.assertIn(value, self.html)
        self.assertIn("audioDeleteSelectedIds()", self.js)
        self.assertIn("deleteSelection", self.js)
        self.assertIn("'/api/audio-library/removal-preview'", self.js)
        self.assertIn("'/api/audio-library/remove'", self.js)
        self.assertIn("fingerprint:preview.fingerprint", self.js)
        self.assertIn("idempotency_key:preview.idempotency_key", self.js)
        self.assertIn("window.scrollTo({top:scrollY", self.js)
        self.assertIn("audio-delete-mode .audio-range-selector{display:none}", self.css)

    def test_filter_change_clears_hidden_delete_selection(self) -> None:
        block = self._function_block("audioFilterChanged")
        self.assertIn("state.audioLibrary.deleteSelection=[]", block)
        self.assertIn("renderAudioLibrary()", block)


if __name__ == "__main__":
    unittest.main()
