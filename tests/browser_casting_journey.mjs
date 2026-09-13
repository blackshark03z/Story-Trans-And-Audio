import { createServer } from "node:http";
import { existsSync } from "node:fs";
import { readFile, mkdtemp, rm } from "node:fs/promises";
import { spawn } from "node:child_process";
import { join, resolve } from "node:path";
import { boundedBrowserTimeout } from "../scripts/browser_acceptance_runtime.mjs";

const root = resolve(import.meta.dirname, "..");
const ui = join(root, "ui");
const browserExe = [process.env.STORY_AUDIO_BROWSER_EXE, "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("Browser executable is required.");
const files = { "/": ["index.html", "text/html; charset=utf-8"], "/assets/app.js": ["app.js", "application/javascript; charset=utf-8"], "/assets/styles.css": ["styles.css", "text/css; charset=utf-8"], "/assets/production_state.js": ["production_state.js", "application/javascript; charset=utf-8"], "/assets/casting_voice_map.js": ["casting_voice_map.js", "application/javascript; charset=utf-8"], "/assets/contextual_voice_detour.js": ["contextual_voice_detour.js", "application/javascript; charset=utf-8"] };
const stage = (key, label, state) => ({ key, label, state });
const server = createServer(async (request, response) => {
  const path = new URL(request.url, "http://fixture").pathname;
  if (path === "/api/books") { response.writeHead(200, { "content-type": "application/json" }); response.end(JSON.stringify([{ id: 1, title: "Fixture Book", chapter_count: 4 }])); return; }
  if (path === "/api/voice-catalog") { response.writeHead(200, { "content-type": "application/json" }); response.end(JSON.stringify({ items: [] })); return; }
  if (path === "/api/books/1/custom-voices") { response.writeHead(200, { "content-type": "application/json" }); response.end(JSON.stringify([{ id: 1, display_name: "Fixture Voice", description: null, is_active: true, preferred_synthesis_revision_id: 11 }])); return; }
  if (path === "/api/custom-voices/1/revisions") { response.writeHead(200, { "content-type": "application/json" }); response.end(JSON.stringify([{ id: 11, revision_number: 1, duration_ms: 5000, sample_rate: 24000, channels: 1, audio_format: "wav", created_at: "2026-09-11T00:00:00Z" }])); return; }
  if (path === "/api/production/book-voice-registry") { response.writeHead(200, { "content-type": "application/json" }); response.end(JSON.stringify({ book: { id: 1, title: "Fixture Book" }, speaker_state: { status: "APPROVED_CURRENT", unresolved_count: 0 }, rows: [{ speaker_key: "narrator", role: "narrator", status: "READY", display_name: "Người kể chuyện", effective_voice: { id: "narrator", display_name: "Narrator" }, actions: { requires_casting_plan_creation: false } }] })); return; }
  if (path === "/api/production/task-projection") { response.writeHead(200, { "content-type": "application/json" }); response.end(JSON.stringify({ canonical_task: { task_key: "fixture", task_type: "READY_TO_PREPARE", title: "Ready", summary: "Ready", current_stage_key: "prepare", primary_action: { key: "PREPARE_RANGE", label: "Prepare", target: "prepare" } } })); return; }
  const asset = files[path]; if (!asset) { response.writeHead(404).end(); return; }
  response.writeHead(200, { "content-type": asset[1] }); response.end(await readFile(join(ui, asset[0])));
});
await new Promise(resolveServer => server.listen(0, "127.0.0.1", resolveServer));
const baseUrl = `http://127.0.0.1:${server.address().port}`;
const profile = await mkdtemp("C:\\StoryAudio_CastingJourney-");
const child = spawn(browserExe, ["--headless=new", "--disable-gpu", "--no-first-run", "--remote-debugging-port=0", `--user-data-dir=${profile}`, `${baseUrl}/#/character-review`], { stdio: "ignore" });
const delay = ms => new Promise(resolveDelay => setTimeout(resolveDelay, ms));
async function poll(fn, timeout = 15000) { const until = Date.now() + boundedBrowserTimeout(timeout); let last; while (Date.now() < until) { try { const value = await fn(); if (value) return value; } catch (error) { last = error; } await delay(50); } throw last || new Error("Timed out"); }
let socket;
try {
  const port = await poll(async () => Number((await readFile(join(profile, "DevToolsActivePort"), "utf8")).split(/\r?\n/)[0]) || null);
  const page = await poll(async () => (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(item => item.type === "page" && item.url.startsWith(baseUrl)));
  socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolveSocket, reject) => { socket.addEventListener("open", resolveSocket, { once: true }); socket.addEventListener("error", reject, { once: true }); });
  let id = 0; const pending = new Map(); socket.addEventListener("message", event => { const message = JSON.parse(event.data); if (!message.id || !pending.has(message.id)) return; const waiter = pending.get(message.id); pending.delete(message.id); message.error ? waiter.reject(new Error(message.error.message)) : waiter.resolve(message.result); });
  const evaluate = async expression => { const result = await new Promise((resolveEval, reject) => { const next = ++id; pending.set(next, { resolve: resolveEval, reject }); socket.send(JSON.stringify({ id: next, method: "Runtime.evaluate", params: { expression, awaitPromise: true, returnByValue: true } })); }); if (result.exceptionDetails) throw new Error(result.exceptionDetails.text); return result.result.value; };
  const states = selector => evaluate(`(() => { const rows=[...(document.querySelector(${JSON.stringify(selector)})?.querySelectorAll('[data-casting-journey-stage]')||[])]; return rows.length===11?Object.fromEntries(rows.map(row=>[row.dataset.castingJourneyStage,[...row.classList].find(name=>['complete','current','blocked'].includes(name))])):null })()`);
  const unscoped = await poll(() => states('#characterReviewJourney'));
  if (unscoped.book !== 'current' || unscoped.chapters !== 'blocked' || unscoped['casting-ready'] !== 'blocked') throw new Error(`Unscoped state is inaccurate: ${JSON.stringify(unscoped)}`);
  await evaluate("location.hash='#/assignment?book=1&from=4&to=4'");
  await poll(() => states('#assignmentSummary'));
  await evaluate("state.productionProjection={canonical_task:{task_key:'fixture:ready',task_type:'READY_TO_PREPARE',current_stage_key:'prepare',title:'Ready',summary:'Ready',primary_action:{key:'PREPARE_RANGE',label:'Prepare',target:'prepare'}}};renderAssignmentPage();true");
  const scoped = await poll(() => states('#assignmentSummary'));
  if (scoped['character-review'] !== 'complete' || scoped['confirm-casting'] !== 'complete' || scoped['casting-ready'] !== 'complete') throw new Error(`Scoped ready state is inaccurate: ${JSON.stringify(scoped)}`);
  const labels = await evaluate("[...document.querySelectorAll('#assignmentSummary [data-casting-journey-stage] strong')].map(node=>node.textContent)");
  if (!["Sách", "Character Review", "Assign Book Voice", "Confirm Final Casting", "Casting Ready"].every(label => labels.some(value => value.includes(label)))) throw new Error(`Missing visible stages: ${JSON.stringify(labels)}`);
  await evaluate("location.hash='#/voices?book=1&from=1&to=4'");
  await poll(() => evaluate("!!document.querySelector('.voice-library-row')"));
  await evaluate("document.querySelector('.voice-library-row').click(); true");
  const voiceDetail = await poll(() => evaluate(`(() => {
    const summary=document.querySelector('#libraryTestRevisionSummary')?.textContent||'';
    if(!summary.includes('Fixture Voice')) return null;
    return {
      current:document.querySelector('#libraryActiveRevisionSummary')?.innerText||'',
      referenceAction:document.querySelector('#libraryListenActiveReference')?.textContent||'',
      testAction:document.querySelector('#libraryGenerateTestAudio')?.textContent||'',
      testActionPrimary:document.querySelector('#libraryGenerateTestAudio')?.classList.contains('primary')||false,
      generatedLabel:document.querySelector('#libraryPreviewBox>strong')?.textContent||'',
      advancedOpen:document.querySelector('#libraryVoiceAdvanced')?.open||false,
      duplicateVoiceInput:!!document.querySelector('#libraryTestVoice'),
      duplicateRevisionSelect:!!document.querySelector('#libraryTestRevisionSelect'),
      horizontalOverflow:document.documentElement.scrollWidth>document.documentElement.clientWidth
    };
  })()`));
  if(!voiceDetail.current.includes('Revision 1')||voiceDetail.referenceAction!=='Nghe audio tham chiếu'||voiceDetail.testAction!=='▶ Tạo bản nghe thử'||!voiceDetail.testActionPrimary||voiceDetail.generatedLabel!=='Bản nghe thử vừa tạo'||voiceDetail.advancedOpen||voiceDetail.duplicateVoiceInput||voiceDetail.duplicateRevisionSelect||voiceDetail.horizontalOverflow)throw new Error(`Custom voice detail hierarchy is inaccurate: ${JSON.stringify(voiceDetail)}`);
  process.stdout.write(JSON.stringify({ ok: true, stageCount: labels.length, unscoped, scoped, voiceDetail }));
} finally { socket?.close(); const exited = child.exitCode === null ? new Promise(resolveExit => child.once("exit", resolveExit)) : Promise.resolve(); child.kill(); await Promise.race([exited, delay(2000)]); server.close(); await rm(profile, { recursive: true, force: true }); }
