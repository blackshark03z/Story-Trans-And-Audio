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


class NoBooksFixtureHandler(ScopeFixtureHandler):
    imported = False

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/api/books":
            if type(self).imported:
                return self._json([{"id": 1, "title": "Imported Fixture", "author": "Owner", "chapter_count": 45, "audio_chapters": 0}])
            return self._json([])
        return super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path == "/api/books/import-upload":
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length)
            if b'filename="owner.epub"' not in body:
                return self._json({"detail": "Missing EPUB upload"}, 400)
            type(self).imported = True
            return self._json({"book_id": 1, "created": True, "chapter_count": 45})
        return self._json({"detail": "Unsupported fixture mutation"}, 404)


class DailyUseV2ABrowserTests(unittest.TestCase):
    def test_zero_book_home_offers_keyboard_import_and_compact_navigation(self) -> None:
        NoBooksFixtureHandler.imported = False
        server = ThreadingHTTPServer(("127.0.0.1", 0), NoBooksFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        script = r'''
const {spawn}=require('node:child_process'),{existsSync}=require('node:fs'),{mkdtemp,readFile,rm}=require('node:fs/promises'),{tmpdir}=require('node:os'),{join}=require('node:path');
const base=process.argv[1],exe=[process.env.STORY_AUDIO_BROWSER_EXE,'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe','C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'].find(Boolean&&existsSync);if(!exe)throw Error('No Chromium browser');
const delay=ms=>new Promise(r=>setTimeout(r,ms)),poll=async fn=>{const end=Date.now()+12000;let error;while(Date.now()<end){try{const value=await fn();if(value)return value}catch(e){error=e}await delay(50)}throw error||Error('Timed out')};
(async()=>{const profile=await mkdtemp(join(tmpdir(),'story-audio-v2a-')),child=spawn(exe,['--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=0',`--user-data-dir=${profile}`,`${base}/#/home`],{stdio:'ignore'});let socket;try{const port=await poll(async()=>Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split(/\r?\n/)[0])||null),page=await poll(async()=>{const pages=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();return pages.find(p=>p.type==='page'&&p.url.startsWith(base))});socket=new WebSocket(page.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});let id=0;const pending=new Map();socket.onmessage=e=>{const message=JSON.parse(e.data),entry=pending.get(message.id);if(!entry)return;pending.delete(message.id);message.error?entry.reject(Error(message.error.message)):entry.resolve(message.result)};const send=(method,params={})=>new Promise((resolve,reject)=>{const request=++id;pending.set(request,{resolve,reject});socket.send(JSON.stringify({id:request,method,params}))}),evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value};await send('Runtime.enable');await send('Page.enable');await poll(async()=>await evaluate(`document.readyState==='complete'&&document.querySelector('#homePrimaryAction')?.textContent==='Nhập EPUB'`));const inspect=async(width,height)=>{await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});return evaluate(`(()=>{const action=document.querySelector('#homePrimaryAction'),rect=action.getBoundingClientRect();return{horizontal:document.documentElement.scrollWidth>innerWidth,ctaVisible:rect.top>=0&&rect.bottom<=innerHeight&&rect.right<=innerWidth}})()`)};const compact=await evaluate(`(()=>({firstRun:!document.querySelector('#homeFirstRun').hidden,workHidden:document.querySelector('#homeWorkGrid').hidden,primary:[...document.querySelectorAll('#appNav > a')].map(link=>link.dataset.appRoute),secondary:document.querySelector('#appNavMore summary')?.textContent.trim()}))()`);await evaluate(`document.querySelector('#homePrimaryAction').focus()`);await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});await poll(async()=>await evaluate(`location.hash==='#/books'&&document.activeElement?.id==='epubUpload'`));const beforeImport=await evaluate(`({disabled:document.querySelector('#importBtn').disabled,existingHidden:document.querySelector('#epubExistingSource').classList.contains('hidden'),hint:document.querySelector('#epubImportHint').textContent.trim()})`);await evaluate(`(()=>{const input=document.querySelector('#epubUpload'),transfer=new DataTransfer();transfer.items.add(new File([new Uint8Array([80,75,3,4])],'owner.epub',{type:'application/epub+zip'}));input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));return true})()`);await poll(async()=>await evaluate(`document.querySelector('#importBtn').disabled===false`));await evaluate(`document.querySelector('#importBtn').click()`);await poll(async()=>await evaluate(`document.querySelector('#bookTitle')?.textContent==='Imported Fixture'&&!document.querySelector('#booksChapterWorkspace').classList.contains('hidden')`));const afterImport=await evaluate(`({bookCount:state.books.length,title:document.querySelector('#bookTitle').textContent,workspaceVisible:!document.querySelector('#booksChapterWorkspace').classList.contains('hidden')})`);console.log(JSON.stringify({compact,beforeImport,afterImport,layout1366:await inspect(1366,768),layout1920:await inspect(1920,1080)}));}finally{socket?.close();const exited=new Promise(resolve=>child.once('exit',resolve));child.kill();await exited;for(let attempt=0;;attempt+=1){try{await rm(profile,{recursive:true,force:true});break}catch(error){if(!['EBUSY','EPERM'].includes(error?.code)||attempt>=29)throw error;await delay(200)}}}})();
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
        self.assertEqual(evidence["compact"], {"firstRun": True, "workHidden": True, "primary": ["production", "assignment", "jobs", "audio"], "secondary": "Tài nguyên"})
        self.assertEqual(evidence["beforeImport"]["disabled"], True)
        self.assertEqual(evidence["beforeImport"]["existingHidden"], True)
        self.assertIn(".epub", evidence["beforeImport"]["hint"])
        self.assertEqual(evidence["afterImport"], {"bookCount": 1, "title": "Imported Fixture", "workspaceVisible": True})
        for viewport in ("layout1366", "layout1920"):
            self.assertTrue(evidence[viewport]["ctaVisible"])
            self.assertFalse(evidence[viewport]["horizontal"])

    def test_voice_detour_returns_to_the_original_production_scope_on_back(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ScopeFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        script = r'''
const {spawn}=require('node:child_process'),{existsSync}=require('node:fs'),{mkdtemp,readFile,rm}=require('node:fs/promises'),{tmpdir}=require('node:os'),{join}=require('node:path');const base=process.argv[1],exe=[process.env.STORY_AUDIO_BROWSER_EXE,'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe','C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'].find(Boolean&&existsSync),delay=ms=>new Promise(r=>setTimeout(r,ms)),poll=async fn=>{const end=Date.now()+12000;let error;while(Date.now()<end){try{const value=await fn();if(value)return value}catch(e){error=e}await delay(50)}throw error||Error('Timed out')};
(async()=>{const profile=await mkdtemp(join(tmpdir(),'story-audio-v2a-context-')),child=spawn(exe,['--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=0',`--user-data-dir=${profile}`,`${base}/#/voices?book=1&from=372&to=373&focus=1372`],{stdio:'ignore'});let socket;try{const port=await poll(async()=>Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split(/\r?\n/)[0])||null),page=await poll(async()=>{const pages=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();return pages.find(p=>p.type==='page'&&p.url.startsWith(base))});socket=new WebSocket(page.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});let id=0;const pending=new Map();socket.onmessage=e=>{const message=JSON.parse(e.data),entry=pending.get(message.id);if(!entry)return;pending.delete(message.id);message.error?entry.reject(Error(message.error.message)):entry.resolve(message.result)};const send=(method,params={})=>new Promise((resolve,reject)=>{const request=++id;pending.set(request,{resolve,reject});socket.send(JSON.stringify({id:request,method,params}))}),evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value};await send('Runtime.enable');await poll(async()=>await evaluate(`!document.querySelector('#productionContextReturn').hidden`));const before=await evaluate(`({hash:location.hash,text:document.querySelector('#productionContextReturnText').textContent,href:document.querySelector('#productionContextReturnLink').getAttribute('href')})`);await evaluate(`document.querySelector('#productionContextReturnLink').click()`);await poll(async()=>await evaluate(`location.hash.startsWith('#/production?')&&location.hash.includes('book=1')&&location.hash.includes('from=372')&&location.hash.includes('to=373')`));await evaluate(`history.back()`);await poll(async()=>await evaluate(`location.hash.startsWith('#/voices?')&&!document.querySelector('#productionContextReturn').hidden`));console.log(JSON.stringify({before,afterBack:await evaluate(`location.hash`)}));}finally{socket?.close();const exited=new Promise(resolve=>child.once('exit',resolve));child.kill();await exited;for(let attempt=0;;attempt+=1){try{await rm(profile,{recursive:true,force:true});break}catch(error){if(!['EBUSY','EPERM'].includes(error?.code)||attempt>=29)throw error;await delay(200)}}}})();
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
        self.assertIn("Sách #1, chương 372–373", evidence["before"]["text"])
        self.assertIn("#/production?book=1", evidence["before"]["href"])
        self.assertTrue(evidence["afterBack"].startswith("#/voices?book=1"))


if __name__ == "__main__":
    unittest.main()
