import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { boundedBrowserTimeout } from "./browser_acceptance_runtime.mjs";

const baseUrl = process.argv[2];
if (!baseUrl) throw new Error("Usage: node scripts/browser_speaker_batch_review_smoke.mjs <base-url>");
const browserExe = [process.env.STORY_AUDIO_BROWSER_EXE,"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe","C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No Chromium browser found");
const profile = await mkdtemp(join(tmpdir(), "story-audio-speaker-batch-"));
const child = spawn(browserExe,["--headless=new","--disable-gpu","--no-first-run","--remote-debugging-port=0",`--user-data-dir=${profile}`,`${baseUrl}/#/assignment?book=1&from=2&to=5&skip_completed=0`],{stdio:"ignore"});
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function poll(fn,timeout=15000){const end=Date.now()+boundedBrowserTimeout(timeout);let last;while(Date.now()<end){try{const v=await fn();if(v)return v}catch(e){last=e}await delay(50)}throw last||new Error("Timed out")}
let socket;
try{
  const port=await poll(async()=>Number((await readFile(join(profile,"DevToolsActivePort"),"utf8")).split(/\r?\n/)[0])||null);
  const page=await poll(async()=>{const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();return pages.find(p=>p.type==="page"&&p.url.startsWith(baseUrl))});
  socket=new WebSocket(page.webSocketDebuggerUrl);await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j});
  let id=0;const pending=new Map(),errors=[];
  socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==="Runtime.exceptionThrown")errors.push(m.params?.exceptionDetails?.exception?.description||m.params?.exceptionDetails?.text||"runtime exception");const w=pending.get(m.id);if(!w)return;pending.delete(m.id);m.error?w.reject(new Error(m.error.message)):w.resolve(m.result)};
  const send=(method,params={})=>new Promise((resolve,reject)=>{const request=++id;pending.set(request,{resolve,reject});socket.send(JSON.stringify({id:request,method,params}))});
  const evaluate=async expression=>{const r=await send("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value};
  const waitFor=(expression,timeout=15000)=>poll(async()=>(await evaluate(expression))||null,timeout);
  const click=selector=>evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)throw Error('missing '+${JSON.stringify(selector)});el.click();return true})()`);
  const key="unresolved-dialogue:1002:u0002-deadbeef0000";
  const attr=(name,value)=>`[${name}="${value}"]`;
  await send("Runtime.enable");await send("Page.enable");await send("Emulation.setDeviceMetricsOverride",{width:1366,height:768,deviceScaleFactor:1,mobile:false});
  await waitFor(`window.storyAudioAppState?.bookVoiceRegistry?.speakerSuggestions?.result?.suggestions?.length&&document.querySelector('[data-speaker-review-workspace]')&&document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card",key))})`);
  await click(attr("data-speaker-suggestion-select",key));
  const selected=await waitFor(`(()=>{const bar=document.querySelector('[data-speaker-review-batch-bar]'),list=document.querySelector('.speaker-suggestion-list'),button=bar?.querySelector('[data-batch-selected-speaker-suggestions]');return bar&&list&&button&&!button.disabled&&button.textContent.includes('(1)')?{count:bar.querySelector('[data-speaker-selected-count]')?.textContent,outcomes:bar.textContent.includes('Nếu chấp nhận tất cả đủ điều kiện')&&bar.textContent.includes('Nếu chấp nhận mục đã chọn')&&bar.textContent.includes('Sau khi batch hoàn tất'),direct:bar.innerText.includes('checkbox trên từng đề xuất'),safe:bar.innerText.includes('Chấp nhận tất cả đủ điều kiện'),staticPosition:getComputedStyle(bar).position==='static',afterList:!!(list.compareDocumentPosition(bar)&Node.DOCUMENT_POSITION_FOLLOWING),noOpenDialog:document.querySelectorAll('dialog[open]').length===0}:null})()`);
  const beforePending=await evaluate(`window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions.filter(item=>item.review_state==='PENDING_REVIEW').length`);
  await click('[data-batch-selected-speaker-suggestions]');
  await waitFor(`window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions.find(item=>item.unresolved_key===${JSON.stringify(key)})?.review_state==='ACCEPTED'`,15000);
  const afterPending=await evaluate(`window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions.filter(item=>item.review_state==='PENDING_REVIEW').length`);
  const commandState=await evaluate(`fetch('/api/fixture/speaker-review-command-state').then(r=>r.json())`);
  const batch=commandState.commands.find(command=>command.command_type==='APPROVE_SPEAKER_REVIEW_BATCH');
  const noRender=commandState.commands.every(command=>!['PREPARE','START_RENDER'].includes(command.command_type));
  const payloadOk=!!batch?.payload?.items?.[0]?.reviewer_payload&&batch.payload.items[0].unresolved_key===key;
  if(errors.length)throw new Error(errors.join(' | '));
  if(!(selected.count==='1'&&selected.outcomes&&selected.direct&&selected.safe&&selected.staticPosition&&selected.afterList&&selected.noOpenDialog&&payloadOk&&noRender&&afterPending===beforePending-1))throw new Error(JSON.stringify({selected,beforePending,afterPending,payloadOk,noRender}));
  process.stdout.write(JSON.stringify({ok:true,selected,beforePending,afterPending,payloadOk,noRender}));
} finally {try{socket?.close()}catch{}const exited=new Promise(r=>child.once('exit',r));child.kill();await Promise.race([exited,delay(1500)]);await rm(profile,{recursive:true,force:true}).catch(()=>{})}
