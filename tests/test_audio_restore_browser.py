from __future__ import annotations

import json
import subprocess
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from tests.test_production_scope_browser import ScopeFixtureHandler


ROOT = Path(__file__).resolve().parents[1]


class AudioRestoreFixtureHandler(ScopeFixtureHandler):
    active_artifact_id = 102
    commands: list[dict] = []

    @classmethod
    def _audio_item(cls) -> dict:
        artifact_id = cls.active_artifact_id
        return {
            "book_id": 1,
            "book_title": "Fixture Book",
            "chapter_id": 1010,
            "chapter_number": 10,
            "chapter_title": "Chapter 10",
            "audio_status": "completed",
            "artifact_id": artifact_id,
            "artifact_kind": "chapter_m4a",
            "artifact_status": "active",
            "file_url": f"/api/artifacts/{artifact_id}/file",
            "download_url": f"/api/artifacts/{artifact_id}/file",
            "sha256": "a" * 64,
            "size_bytes": 4096,
            "duration_ms": 61000,
            "artifact_created_at": "2026-09-10T08:00:00+00:00",
            "artifact_verified_at": "2026-09-10T08:01:00+00:00",
            "job_id": artifact_id,
            "job_chapter_id": artifact_id,
            "job_chapter_status": "completed",
            "casting_plan_id": artifact_id,
            "casting_plan_revision": 2 if artifact_id == 102 else 1,
            "requested_voice": "Giọng kể thử nghiệm",
            "applied_narrator_voice": "narrator",
            "human_qa_status": "accepted",
            "human_approval_status": "approved",
            "human_approval_label": "Đã chốt",
            "human_approval_warning": None,
            "qa_feedback": {},
            "human_approval_matches_active_artifact": True,
            "video_export": None,
        }

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/audio-library":
            return self._json({"items": [type(self)._audio_item()], "total": 1})
        if parsed.path == "/api/chapters/1010/human-approval-history":
            current = type(self).active_artifact_id
            historical = 101 if current == 102 else 102
            return self._json(
                {
                    "chapter_id": 1010,
                    "active_artifact_id": current,
                    "total": 2,
                    "items": [
                        {
                            "id": current,
                            "status": "approved",
                            "notes": "Bản hiện tại đã duyệt.",
                            "artifact_id": current,
                            "job_id": current,
                            "recorded_at": "2026-09-10T08:02:00+00:00",
                            "restore_eligible": False,
                            "restore_code": "ARTIFACT_ALREADY_ACTIVE",
                            "restore_message": "Bản audio này đã là bản hiện tại.",
                            "restore_label": None,
                        },
                        {
                            "id": historical,
                            "status": "approved",
                            "notes": "Bản đã duyệt trước đó.",
                            "artifact_id": historical,
                            "job_id": historical,
                            "recorded_at": "2026-09-09T08:02:00+00:00",
                            "restore_eligible": True,
                            "restore_code": "READY",
                            "restore_message": "Bản đã duyệt có thể được khôi phục.",
                            "restore_label": "Khôi phục làm bản hiện tại",
                        },
                    ],
                }
            )
        if parsed.path in {"/api/artifacts/101/file", "/api/artifacts/102/file"}:
            body = b"fixture-audio"
            self.send_response(200)
            self.send_header("Content-Type", "audio/mp4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/production/commands":
            return self._json({"detail": "Unsupported fixture mutation"}, 404)
        length = int(self.headers.get("Content-Length", "0") or 0)
        command = json.loads(self.rfile.read(length) or b"{}")
        type(self).commands.append(command)
        if command.get("command_type") != "RESTORE_ACCEPTED_ARTIFACT":
            return self._json({"detail": "Unexpected command"}, 400)
        payload = command["payload"]
        if int(payload["expected_active_artifact_id"]) != type(self).active_artifact_id:
            return self._json({"detail": "Stale active artifact"}, 409)
        previous = type(self).active_artifact_id
        type(self).active_artifact_id = int(payload["artifact_id"])
        return self._json(
            {
                "schema": "story-audio-production-command/v1",
                "command_id": "pc-fixture",
                "command_type": command["command_type"],
                "idempotency_key": command["idempotency_key"],
                "scope": command["scope"],
                "outcome": "APPLIED",
                "submitted_count": 1,
                "applied_count": 1,
                "failed_count": 0,
                "applied_items": [
                    {
                        "chapter_id": 1010,
                        "artifact_id": type(self).active_artifact_id,
                        "previous_artifact_id": previous,
                    }
                ],
                "failed_items": [],
                "operator_message": "Đã khôi phục bản audio đã duyệt làm bản hiện tại.",
                "result_metadata": None,
                "resulting_task_projection": {
                    "range_identity": None,
                    "chapter_queue": [],
                    "canonical_task": {
                        "task_scope": "range",
                        "task_type": "SELECT_SCOPE",
                        "task_key": "scope:fixture",
                        "user_stage": 1,
                        "title": "Chọn sách và chương",
                        "summary": "Chọn phạm vi sản xuất tiếp theo.",
                        "technical_details": [],
                        "speaker": None,
                        "casting": None,
                        "range_prepare": None,
                        "render": None,
                        "qa": None,
                        "repair": None,
                    },
                },
                "resulting_preflight": None,
                "asynchronous_reference": None,
                "state_tokens": {"task_projection": None, "preflight": None},
            }
        )


class AudioRestoreBrowserTests(unittest.TestCase):
    def test_real_browser_restores_accepted_history_without_render_command(self) -> None:
        AudioRestoreFixtureHandler.active_artifact_id = 102
        AudioRestoreFixtureHandler.commands = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), AudioRestoreFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        script = r'''
const {spawn}=require('node:child_process'),{existsSync}=require('node:fs'),{mkdtemp,readFile,rm}=require('node:fs/promises'),{tmpdir}=require('node:os'),{join}=require('node:path');
const base=process.argv[1],exe=[process.env.STORY_AUDIO_BROWSER_EXE,'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe','C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'].find(value=>value&&existsSync(value));if(!exe)throw Error('No Chromium browser');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms)),poll=async fn=>{const end=Date.now()+12000;let error;while(Date.now()<end){try{const value=await fn();if(value)return value}catch(e){error=e}await delay(50)}throw error||Error('Timed out')};
(async()=>{const profile=await mkdtemp(join(tmpdir(),'story-audio-restore-')),child=spawn(exe,['--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=0',`--user-data-dir=${profile}`,`${base}/#/audio`],{stdio:'ignore'});let socket;try{const port=await poll(async()=>Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split(/\r?\n/)[0])||null),page=await poll(async()=>{const pages=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();return pages.find(item=>item.type==='page'&&item.url.startsWith(base))});socket=new WebSocket(page.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});let id=0;const pending=new Map();socket.onmessage=event=>{const message=JSON.parse(event.data),entry=pending.get(message.id);if(!entry)return;pending.delete(message.id);message.error?entry.reject(Error(message.error.message)):entry.resolve(message.result)};const send=(method,params={})=>new Promise((resolve,reject)=>{const request=++id;pending.set(request,{resolve,reject});socket.send(JSON.stringify({id:request,method,params}))}),evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value};await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:1366,height:768,deviceScaleFactor:1,mobile:false});await poll(async()=>await evaluate(`document.querySelector('.audio-review-row button')`));await evaluate(`document.querySelector('.audio-review-row button').click()`);await poll(async()=>await evaluate(`document.querySelector('[data-restore-artifact="101"]')&&!document.querySelector('[data-restore-artifact="101"]').disabled`));const before=await evaluate(`({selected:state.audioLibrary.selectedArtifactId,history:document.querySelector('#audioQaHistory').textContent,stageLabel:document.querySelector('#productionStageShell').getAttribute('aria-label'),horizontal:document.documentElement.scrollWidth>innerWidth})`);await evaluate(`window.confirm=()=>true;document.querySelector('[data-restore-artifact="101"]').click()`);await poll(async()=>await evaluate(`state.audioLibrary.selectedArtifactId===101&&state.audioQa.activeArtifactId===101`));const after=await evaluate(`({selected:state.audioLibrary.selectedArtifactId,title:document.querySelector('#audioLibraryPlayerTitle').textContent.trim(),history:document.querySelector('#audioQaHistory').textContent,paused:document.querySelector('#audioLibraryAudio').paused,horizontal:document.documentElement.scrollWidth>innerWidth})`);console.log(JSON.stringify({before,after}));}finally{socket?.close();const exited=new Promise(resolve=>child.once('exit',resolve));child.kill();await exited;for(let attempt=0;;attempt+=1){try{await rm(profile,{recursive:true,force:true});break}catch(error){if(!['EBUSY','EPERM'].includes(error?.code)||attempt>=29)throw error;await delay(200)}}}})();
'''
        try:
            result = subprocess.run(
                ["node", "-e", script, f"http://127.0.0.1:{server.server_port}"],
                cwd=ROOT,
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
        self.assertEqual(evidence["before"]["selected"], 102)
        self.assertIn("Khôi phục làm bản hiện tại", evidence["before"]["history"])
        self.assertEqual(evidence["before"]["stageLabel"], "Bốn giai đoạn sản xuất")
        self.assertFalse(evidence["before"]["horizontal"])
        self.assertEqual(evidence["after"]["selected"], 101)
        self.assertIn("Chapter 10", evidence["after"]["title"])
        self.assertTrue(evidence["after"]["paused"])
        self.assertFalse(evidence["after"]["horizontal"])
        self.assertEqual(len(AudioRestoreFixtureHandler.commands), 1)
        command = AudioRestoreFixtureHandler.commands[0]
        self.assertEqual(command["command_type"], "RESTORE_ACCEPTED_ARTIFACT")
        self.assertEqual(command["payload"]["expected_active_artifact_id"], 102)
        self.assertNotIn("PREPARE", json.dumps(command))
        self.assertNotIn("START_RENDER", json.dumps(command))


if __name__ == "__main__":
    unittest.main()
