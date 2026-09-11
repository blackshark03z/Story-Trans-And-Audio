from __future__ import annotations

import json
import subprocess
import threading
import unittest
from http.server import ThreadingHTTPServer

from tests.test_speaker_review_workspace_browser import SpeakerReviewWorkspaceFixtureHandler


class ApprovedReviewFixtureHandler(SpeakerReviewWorkspaceFixtureHandler):
    @classmethod
    def registry(cls, book_id: int, start: int, end: int) -> dict:
        voice = {"id": "narrator", "display_name": "Bình An"}

        def row(*, key: str, role: str, name: str, character_id: int | None) -> dict:
            requested_chapters = [1, 2, 3, 4, 5, 6] if role == "narrator" else [1, 2, 4, 5, 6]
            return {
                "speaker_key": key,
                "role": role,
                "character_id": character_id,
                "character_role": "minor" if character_id else None,
                "display_name": name,
                "status": "READY",
                "line_count": 48 if role == "narrator" else 1,
                "chapter_numbers": [1],
                "chapter_range_label": "Chương 1",
                "requested_scope": {
                    "chapter_numbers": requested_chapters,
                    "chapter_range_label": "Chương 1-6" if role == "narrator" else "Chương 1-2, 4-6",
                    "chapter_count": len(requested_chapters),
                    "line_count": 315 if role == "narrator" else 7,
                },
                "effective_scope": {
                    "chapter_numbers": [1],
                    "chapter_range_label": "Chương 1",
                    "chapter_count": 1,
                    "line_count": 48 if role == "narrator" else 1,
                },
                "sample_lines": [] if role == "narrator" else [
                    {
                        "chapter_number": chapter,
                        "sequence": chapter,
                        "utterance_id": f"sample-{chapter}",
                        "text": "Một đoạn thoại đủ dài để kiểm tra vùng làm việc giữ nguyên vị trí cuộn sau khi dữ liệu được làm mới. " * 8,
                        "context_before": [],
                        "context_after": [],
                    }
                    for chapter in [1, 2, 4, 5, 6]
                ],
                "effective_voice": voice,
                "current_book_default_voice": voice,
                "assignment_source": "inherited",
                "resolution_source": "book_default",
                "actions": {
                    "requires_casting_plan_creation": False,
                    "can_create_range_or_chapter_override": False,
                    "can_save_book_default": True,
                },
            }

        return {
            "book": {"id": book_id, "title": "Quang Âm Chi Ngoại"},
            "range": {
                "from_chapter": 1,
                "to_chapter": 1,
                "chapter_count": 1,
                "chapter_ids": [1],
                "requested_from_chapter": start,
                "requested_to_chapter": end,
                "requested_chapter_count": end - start + 1,
                "skip_completed": True,
                "included_chapters": [{"id": 1, "chapter_number": 1}],
                "excluded_chapters": [
                    {"id": chapter, "chapter_number": chapter, "reason": "completed"}
                    for chapter in range(2, 7)
                ],
            },
            "speaker_state": {
                "status": "APPROVED_CURRENT",
                "current_revision_id": 2,
                "unresolved_count": 1,
                "remaining_review_count": 0,
                "blocks_progress": False,
                "history": [],
            },
            "characters": [
                {"id": 25, "display_name": "Hứa Thanh", "aliases": []},
                {"id": 26, "display_name": "Quần chúng nam", "aliases": []},
            ],
            "rows": [
                row(key="narrator", role="narrator", name="Người kể chuyện", character_id=None),
                row(key="character:25", role="character", name="Hứa Thanh", character_id=25),
            ],
            "summary": {"total_rows": 2, "status_counts": {"READY": 2}},
        }


class AssignmentCompletedReviewBrowserTests(unittest.TestCase):
    def test_approved_review_uses_remaining_count_and_advances_to_voice_configuration(self) -> None:
        ApprovedReviewFixtureHandler.reset()
        server = ThreadingHTTPServer(("127.0.0.1", 0), ApprovedReviewFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        script = r'''
const {spawn}=require('node:child_process'),{existsSync}=require('node:fs'),{mkdtemp,readFile,rm}=require('node:fs/promises'),{tmpdir}=require('node:os'),{join}=require('node:path');
const base=process.argv[1],exe=[process.env.STORY_AUDIO_BROWSER_EXE,'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe','C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'].find(value=>value&&existsSync(value));if(!exe)throw Error('No Chromium browser');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms)),poll=async fn=>{const end=Date.now()+12000;let error;while(Date.now()<end){try{const value=await fn();if(value)return value}catch(e){error=e}await delay(50)}throw error||Error('Timed out')};
(async()=>{const profile=await mkdtemp(join(tmpdir(),'story-audio-approved-review-')),child=spawn(exe,['--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=0',`--user-data-dir=${profile}`,`${base}/#/assignment?book=1&from=1&to=6&skip_completed=1`],{stdio:'ignore'});let socket;try{const port=await poll(async()=>Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split(/\r?\n/)[0])||null),page=await poll(async()=>{const pages=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();return pages.find(item=>item.type==='page'&&item.url.startsWith(base))});socket=new WebSocket(page.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});let id=0;const pending=new Map();socket.onmessage=event=>{const message=JSON.parse(event.data),entry=pending.get(message.id);if(!entry)return;pending.delete(message.id);message.error?entry.reject(Error(message.error.message)):entry.resolve(message.result)};const send=(method,params={})=>new Promise((resolve,reject)=>{const request=++id;pending.set(request,{resolve,reject});socket.send(JSON.stringify({id:request,method,params}))}),evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value};await send('Runtime.enable');await poll(async()=>await evaluate(`document.querySelector('[data-assignment-section="voices"]')?.textContent.includes('Hứa Thanh')`));const scrollBefore=await evaluate(`(()=>{const rows=document.querySelector('#assignmentRows');rows.scrollTop=Math.min(240,rows.scrollHeight-rows.clientHeight);return rows.scrollTop})()`);await evaluate(`loadBookVoiceRegistry({force:true}).then(()=>true)`);const scrollAfter=await evaluate(`document.querySelector('#assignmentRows').scrollTop`);const evidence=await evaluate(`(()=>{const review=document.querySelector('[data-assignment-section="review"]'),voices=document.querySelector('[data-assignment-section="voices"]'),summary=voices.querySelector('.assignment-section-summary')?.textContent||'',notice=voices.querySelector('.assignment-unresolved-notice'),editor=voices.querySelector('[data-registry-editor="narrator"]'),narrator=document.querySelector('[data-voice-library-row="narrator"]'),character=document.querySelector('[data-voice-library-row="character:25"]'),table=voices.querySelector('[data-registry-scroll-region]');return{reviewOpen:review.open,voicesOpen:voices.open,reviewStatus:review.querySelector('summary small')?.textContent.trim(),reviewNext:review.querySelector('[data-assignment-review-next]')?.textContent.trim(),voiceTitle:voices.querySelector('summary strong')?.textContent.trim(),voiceGuide:voices.querySelector('.section-guide')?.textContent.trim(),scope:document.querySelector('#assignmentScope')?.textContent.trim(),voiceSummary:summary.replace(/\\s+/g,' ').trim(),narratorScope:narrator?.textContent||'',characterScope:character?.textContent||'',nestedVerticalScroll:table.scrollHeight>table.clientHeight+1,hasUnresolvedNotice:!!notice,selectedVoiceScope:editor.querySelector('[data-registry-scope-key]')?.value,saveLabel:editor.querySelector('[data-registry-apply]')?.textContent.trim(),falseSpeakerBlocker:editor.textContent.includes('bản xác định người nói chưa được duyệt'),preflightDisabled:document.querySelector('[data-assignment-preflight-step] button')?.disabled}})()`);evidence.scrollBefore=scrollBefore;evidence.scrollAfter=scrollAfter;console.log(JSON.stringify(evidence));}finally{socket?.close();const exited=new Promise(resolve=>child.once('exit',resolve));child.kill();await exited;for(let attempt=0;;attempt+=1){try{await rm(profile,{recursive:true,force:true});break}catch(error){if(!['EBUSY','EPERM'].includes(error?.code)||attempt>=29)throw error;await delay(200)}}}})();
'''
        try:
            result = subprocess.run(
                ["node", "-e", script, f"http://127.0.0.1:{server.server_port}"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=45,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertFalse(evidence["reviewOpen"])
        self.assertTrue(evidence["voicesOpen"])
        self.assertEqual(evidence["reviewStatus"], "Đã duyệt")
        self.assertEqual(evidence["reviewNext"], "Tiếp tục cấu hình giọng")
        self.assertEqual(evidence["voiceTitle"], "2. Vai có lời trong phạm vi và cấu hình giọng")
        self.assertIn("Đang xử lý Chương 1 (1/6 chương)", evidence["scope"])
        self.assertIn("Bỏ qua 5 chương đã hoàn tất", evidence["scope"])
        self.assertIn("toàn bộ phạm vi đã chọn", evidence["voiceGuide"])
        self.assertIn("Chương 1-6", evidence["narratorScope"])
        self.assertIn("315 câu", evidence["narratorScope"])
        self.assertIn("Đang xử lý: Chương 1 · 48 câu", evidence["narratorScope"])
        self.assertIn("Chương 1-2, 4-6", evidence["characterScope"])
        self.assertIn("7 câu", evidence["characterScope"])
        self.assertIn("Đang xử lý: Chương 1 · 1 câu", evidence["characterScope"])
        self.assertFalse(evidence["nestedVerticalScroll"])
        self.assertIn("2 vai có giọng", evidence["voiceSummary"])
        self.assertIn("1 nhân vật/nhóm có lời", evidence["voiceSummary"])
        self.assertIn("1 người kể chuyện", evidence["voiceSummary"])
        self.assertIn("2 nhân vật trong sách", evidence["voiceSummary"])
        self.assertNotIn("giọng sẵn sàng", evidence["voiceSummary"])
        self.assertFalse(evidence["hasUnresolvedNotice"])
        self.assertEqual(evidence["selectedVoiceScope"], "book")
        self.assertEqual(evidence["saveLabel"], "Lưu làm giọng mặc định cho sách")
        self.assertFalse(evidence["falseSpeakerBlocker"])
        self.assertFalse(evidence["preflightDisabled"])


if __name__ == "__main__":
    unittest.main()
