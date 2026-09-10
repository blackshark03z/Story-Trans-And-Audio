from __future__ import annotations

import json
import subprocess
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from tests.test_production_scope_browser import ScopeFixtureHandler


ROOT = Path(__file__).resolve().parents[1]


class SidebarNavigationBrowserTests(unittest.TestCase):
    def test_resource_group_stays_visible_on_desktop_and_discloses_only_on_narrow_view(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ScopeFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        script = r'''
const {spawn}=require('node:child_process'),{existsSync}=require('node:fs'),{mkdtemp,readFile,rm}=require('node:fs/promises'),{tmpdir}=require('node:os'),{join}=require('node:path');
const base=process.argv[1],exe=[process.env.STORY_AUDIO_BROWSER_EXE,'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe','C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'].find(value=>value&&existsSync(value));if(!exe)throw Error('No Chromium browser');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms)),poll=async fn=>{const end=Date.now()+12000;let error;while(Date.now()<end){try{const value=await fn();if(value)return value}catch(e){error=e}await delay(50)}throw error||Error('Timed out')};
(async()=>{const profile=await mkdtemp(join(tmpdir(),'story-audio-sidebar-')),child=spawn(exe,['--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=0',`--user-data-dir=${profile}`,`${base}/#/home`],{stdio:'ignore'});let socket;try{const port=await poll(async()=>Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split(/\r?\n/)[0])||null),page=await poll(async()=>{const pages=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();return pages.find(item=>item.type==='page'&&item.url.startsWith(base))});socket=new WebSocket(page.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});let id=0;const pending=new Map();socket.onmessage=event=>{const message=JSON.parse(event.data),entry=pending.get(message.id);if(!entry)return;pending.delete(message.id);message.error?entry.reject(Error(message.error.message)):entry.resolve(message.result)};const send=(method,params={})=>new Promise((resolve,reject)=>{const request=++id;pending.set(request,{resolve,reject});socket.send(JSON.stringify({id:request,method,params}))}),evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value};await send('Runtime.enable');await poll(async()=>await evaluate(`document.readyState==='complete'&&document.querySelector('#appNavResourceLinks')`));await send('Emulation.setDeviceMetricsOverride',{width:1366,height:768,deviceScaleFactor:1,mobile:false});const desktopBefore=await evaluate(`(()=>{const group=document.querySelector('#appNavMore'),label=group.firstElementChild,links=[...group.querySelectorAll('[data-app-route]')];return{labelTag:label.tagName,labelText:label.textContent.trim(),toggleDisplay:getComputedStyle(document.querySelector('#appNavMoreToggle')).display,visibleRoutes:links.filter(link=>getComputedStyle(link).display!=='none'&&link.getClientRects().length).map(link=>link.dataset.appRoute),horizontal:document.documentElement.scrollWidth>innerWidth}})()`);await evaluate(`document.querySelector('#appNavMore').firstElementChild.click()`);const desktopAfter=await evaluate(`([...document.querySelectorAll('#appNavResourceLinks [data-app-route]')].filter(link=>getComputedStyle(link).display!=='none'&&link.getClientRects().length).map(link=>link.dataset.appRoute))`);await send('Emulation.setDeviceMetricsOverride',{width:820,height:900,deviceScaleFactor:1,mobile:false});const narrowBefore=await evaluate(`(()=>{const toggle=document.querySelector('#appNavMoreToggle'),links=document.querySelector('#appNavResourceLinks');return{toggleDisplay:getComputedStyle(toggle).display,expanded:toggle.getAttribute('aria-expanded'),linksVisible:getComputedStyle(links).display!=='none'}})()`);await evaluate(`document.querySelector('#appNavMoreToggle').click()`);const narrowOpen=await evaluate(`(()=>{const toggle=document.querySelector('#appNavMoreToggle'),links=document.querySelector('#appNavResourceLinks');return{expanded:toggle.getAttribute('aria-expanded'),linksVisible:getComputedStyle(links).display!=='none',horizontal:document.documentElement.scrollWidth>innerWidth}})()`);console.log(JSON.stringify({desktopBefore,desktopAfter,narrowBefore,narrowOpen}));}finally{socket?.close();const exited=new Promise(resolve=>child.once('exit',resolve));child.kill();await exited;for(let attempt=0;;attempt+=1){try{await rm(profile,{recursive:true,force:true});break}catch(error){if(!['EBUSY','EPERM'].includes(error?.code)||attempt>=29)throw error;await delay(200)}}}})();
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
        routes = ["home", "books", "voices", "storage", "settings"]
        self.assertEqual(evidence["desktopBefore"]["labelTag"], "SPAN")
        self.assertEqual(evidence["desktopBefore"]["labelText"], "Tài nguyên")
        self.assertEqual(evidence["desktopBefore"]["toggleDisplay"], "none")
        self.assertEqual(evidence["desktopBefore"]["visibleRoutes"], routes)
        self.assertEqual(evidence["desktopAfter"], routes)
        self.assertFalse(evidence["desktopBefore"]["horizontal"])
        self.assertNotEqual(evidence["narrowBefore"]["toggleDisplay"], "none")
        self.assertEqual(evidence["narrowBefore"]["expanded"], "false")
        self.assertFalse(evidence["narrowBefore"]["linksVisible"])
        self.assertEqual(evidence["narrowOpen"]["expanded"], "true")
        self.assertTrue(evidence["narrowOpen"]["linksVisible"])
        self.assertFalse(evidence["narrowOpen"]["horizontal"])


if __name__ == "__main__":
    unittest.main()
