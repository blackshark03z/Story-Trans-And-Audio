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

    def test_audio_library_view_replaces_placeholder_with_read_only_surface(self) -> None:
        for value in (
            'id="audioView"',
            'id="audioHeading">Thư viện audio</h2>',
            "Nghe và tải các chương đang có bản audio hoạt động.",
            'id="refreshAudioLibrary"',
            'id="audioLibraryStatus"',
            'id="audioLibraryList"',
            'id="audioLibraryPlayer"',
            'id="audioLibraryAudio"',
            'id="audioLibraryDownload"',
            'id="audioLibraryEmpty"',
            'id="audioLibraryError"',
            'id="retryAudioLibrary"',
        ):
            self.assertIn(value, self.html)
        self.assertNotIn("playback/download mới chưa được thêm", self.html)

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

    def test_item_rendering_uses_safe_dom_and_no_inner_html(self) -> None:
        block = self._function_block("renderAudioLibraryItem")
        for value in (
            "document.createElement('article')",
            "document.createElement('h3')",
            "title.textContent=audioLibraryTitle(item)",
            "book.textContent=item.book_title",
            "meta.textContent=pieces.join",
            "badge.textContent=qa.label",
            "card.append(main,actions,configuration)",
        ):
            self.assertIn(value, block)
        self.assertNotIn("innerHTML", block)

    def test_artifact_configuration_is_read_only_and_snapshot_scoped(self) -> None:
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
        block = self._function_block("renderAudioLibraryItem")
        self.assertIn("Cấu hình đã dùng để tạo audio này", block)
        self.assertIn("loadArtifactConfiguration(item,configurationBody)", block)
        self.assertNotIn("method:'POST'", block)
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
        self.assertIn("Xem kế hoạch sửa", self.js)
        self.assertIn("audio.playbackRate=Number(event.target.value||1)", self.js)
        self.assertIn("global_speed_target:speed", self.js)
        self.assertIn("repeated_words:repeated", self.js)
        self.assertIn("local_pacing_adjustment_required:local", self.js)
        self.assertIn("position_markers:state.audioQa.markers", self.js)
        self.assertIn("if(changed)state.audioQa.markers=[]", self.js)
        self.assertIn("submit.disabled=true", self.js)
        self.assertIn("Đang lưu phản hồi…", self.js)
        self.assertIn("qa_feedback", self.js)

    def test_repair_plan_confirmation_is_a_separate_single_action(self) -> None:
        block = self._function_block("productionRepairPlanContent")
        for value in (
            "Kế hoạch sửa Chương",
            "Khắc phục đoạn bị lặp chữ",
            "Xác nhận kế hoạch sửa",
            "Quay lại nghe audio",
            "Áp dụng sửa chữa",
            "Chi tiết kỹ thuật",
        ):
            self.assertIn(value, block)
        self.assertIn("CONFIRM_REPAIR_PLAN", self.js)
        self.assertIn("repairPlanRequestedFromHash", self.js)
        self.assertIn("repair_plan=1", self.js)
        self.assertIn("openAudioQaRepairPlan", self.js)
        self.assertIn("data-audio-qa-repair-plan", self.js)
        self.assertIn("REPAIR_PLAN_OPEN_STORAGE_KEY", self.js)
        self.assertIn("consumeRepairPlanOpen", self.js)
        self.assertNotIn("PREPARE", block)

    def test_playback_and_download_use_only_api_safe_relative_url(self) -> None:
        safe_block = self._function_block("safeAudioLibraryUrl")
        self.assertIn(r"^\/api\/artifacts\/\d+\/file$", safe_block)
        item_block = self._function_block("renderAudioLibraryItem")
        select_block = self._function_block("selectAudioLibraryItem")
        combined = item_block + select_block
        self.assertIn("safeAudioLibraryUrl(item.file_url||item.download_url)", combined)
        self.assertIn("download.href=url", combined)
        self.assertIn("audio.src=url", combined)
        self.assertNotIn("artifact_id}/file", combined)
        self.assertNotIn("job_id", combined)
        self.assertNotIn("output_path", combined)

    def test_unsafe_url_disables_playback_and_download(self) -> None:
        item_block = self._function_block("renderAudioLibraryItem")
        self.assertIn("play.disabled=!url", item_block)
        self.assertIn("download.href='#'", item_block)
        self.assertIn("download.setAttribute('aria-disabled','true')", item_block)
        self.assertIn("event.preventDefault()", item_block)
        self.assertIn("warning.textContent=", item_block)

    def test_video_export_controls_are_visible_bounded_and_retry_safe(self) -> None:
        safe_block = self._function_block("safeVideoExportUrl")
        item_block = self._function_block("renderAudioLibraryItem")
        export_block = self._function_block("exportAudioLibraryVideo")
        self.assertIn(r"^\/api\/video-exports\/artifact-\d+-[0-9a-f]{12}-[0-9a-f]{12}\/file$", safe_block)
        self.assertIn("audioLibraryVideoState(item)", item_block)
        self.assertIn("exportButton.textContent=video.status==='exporting'?'Đang xuất video…':'Xuất video'", item_block)
        self.assertIn("exportButton.disabled=video.status==='exporting'||!!videoUrl||!videoAllowed", item_block)
        self.assertIn("videoDownload.textContent='Tải video'", item_block)
        self.assertIn("videoPreview.controls=true", item_block)
        self.assertIn("videoPreview.preload='metadata'", item_block)
        self.assertIn("videoPreview.src=videoUrl", item_block)
        self.assertIn("videoPreview.setAttribute('aria-label',`Phát video ${audioLibraryTitle(item)}`)", item_block)
        self.assertNotIn("videoPreview.play()", item_block)
        self.assertIn("Video chỉ xuất sau khi audio đã được chấp nhận.", item_block)
        self.assertIn("current?.status==='exporting'", export_block)
        self.assertIn("api(`/api/artifacts/${artifactId}/video-export`,{method:'POST'})", export_block)
        self.assertIn("safeVideoExportUrl(result.download_url)", export_block)
        self.assertIn("message:result.reused?'Video đã sẵn sàng.':'Video đã xuất xong.'", export_block)

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

    def test_empty_loading_error_and_retry_are_explicit(self) -> None:
        render_block = self._function_block("renderAudioLibrary")
        for value in (
            "Đang tải thư viện audio...",
            "Không tải được thư viện audio.",
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
        self.assertIn("/api/production/commands", self.js)
        submit = self._function_block("submitAudioQa")
        self.assertIn("runProductionCommand", submit)
        self.assertNotIn("window.confirm", submit)
        self.assertIn("notes", submit)
        self.assertNotIn("Chapter 369", self.html + self.js + self.css)
        self.assertNotIn("chapter 369", self.html + self.js + self.css)

    def test_audio_library_styles_cover_list_player_and_mobile_layout(self) -> None:
        for value in (
            ".audio-library-card",
            ".audio-library-player",
            ".audio-library-qa.pending",
            ".audio-library-qa.accepted",
            ".audio-library-empty",
            "@media(max-width:800px){.audio-library-card,.audio-library-player{grid-template-columns:1fr}",
        ):
            self.assertIn(value, self.css)


if __name__ == "__main__":
    unittest.main()
