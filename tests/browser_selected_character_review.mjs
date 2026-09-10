import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";

const baseUrl = process.argv[2];
const browserExe = [process.env.STORY_AUDIO_BROWSER_EXE, "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"].filter(Boolean).find(existsSync);
if (!baseUrl || !browserExe) throw new Error("Browser and base URL are required.");
const profile = await mkdtemp("C:\\StoryAudio_CharacterReview-");
const child = spawn(browserExe, ["--headless=new", "--disable-gpu", "--no-first-run", "--remote-debugging-port=0", `--user-data-dir=${profile}`, `${baseUrl}/#/character-review?book=1&from=2&to=2`], { stdio: "ignore" });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function poll(fn, timeout = 15000) { const until = Date.now() + timeout; let last; while (Date.now() < until) { try { const value = await fn(); if (value) return value; } catch (error) { last = error; } await delay(50); } throw last || new Error("Timed out"); }
let socket;
try {
  const port = await poll(async () => Number((await readFile(join(profile, "DevToolsActivePort"), "utf8")).split(/\r?\n/)[0]) || null);
  const page = await poll(async () => (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(item => item.type === "page" && item.url.startsWith(baseUrl)));
  socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.addEventListener("open", resolve, { once: true }); socket.addEventListener("error", reject, { once: true }); });
  let id = 0; const pending = new Map(); const errors = [];
  socket.addEventListener("message", event => { const message = JSON.parse(event.data); if (message.method === "Runtime.exceptionThrown") errors.push(message.params.exceptionDetails.text); if (!message.id || !pending.has(message.id)) return; const waiter = pending.get(message.id); pending.delete(message.id); message.error ? waiter.reject(new Error(message.error.message)) : waiter.resolve(message.result); });
  const send = (method, params = {}) => new Promise((resolve, reject) => { const next = ++id; pending.set(next, { resolve, reject }); socket.send(JSON.stringify({ id: next, method, params })); });
  const evaluate = async expression => { const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }); if (result.exceptionDetails) throw new Error(result.exceptionDetails.text); return result.result.value; };
  const visit = async hash => { await evaluate(`location.hash=${JSON.stringify(hash)}`); const status = await poll(() => evaluate("['ready','error'].includes(window.storyAudioAppState?.characterReview?.status) && window.storyAudioAppState.characterReview.status")); if (status !== 'ready') throw new Error(await evaluate("window.storyAudioAppState.characterReview.error")); return evaluate(`(() => ({scope:document.querySelector('#characterReviewScope').textContent,names:[...document.querySelectorAll('[data-character-review-row] .character-review-identity strong')].map(el=>el.textContent),voices:[...document.querySelectorAll('[data-character-review-voice]')].map(el=>el.textContent),unresolved:!document.querySelector('#characterReviewNotice').classList.contains('hidden')}))()`); };
  await send("Runtime.enable");
  const single = await visit("#/character-review?book=1&from=2&to=2");
  const multi = await visit("#/character-review?book=1&from=2&to=4");
  await evaluate("window.__characterReviewReloadMarker='before-reload'");
  await send("Page.reload", { ignoreCache: true });
  await poll(() => evaluate("window.__characterReviewReloadMarker !== 'before-reload' && window.storyAudioAppState?.characterReview?.status === 'ready' && document.querySelector('#characterReviewScope')?.textContent === 'Fixture Book · Chương 2–4'"));
  const reloaded = await evaluate(`(() => ({scope:document.querySelector('#characterReviewScope').textContent,names:[...document.querySelectorAll('[data-character-review-row] .character-review-identity strong')].map(el=>el.textContent),voices:[...document.querySelectorAll('[data-character-review-voice]')].map(el=>el.textContent),unresolved:!document.querySelector('#characterReviewNotice').classList.contains('hidden')}))()`);
  const other_book = await visit("#/character-review?book=2&from=1&to=1");
  if (errors.length) throw new Error(errors.join(" | "));
  process.stdout.write(JSON.stringify({ ok: true, single, multi, other_book, reloaded }));
} finally {
  try { socket?.close(); } catch {}
  const browserExited = child.exitCode === null ? new Promise(resolve => child.once("exit", resolve)) : Promise.resolve();
  child.kill();
  await Promise.race([browserExited, delay(3000)]);
  let cleanupError = null;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try { await rm(profile, { recursive: true, force: true }); cleanupError = null; break; }
    catch (error) { cleanupError = error; if (!["EBUSY", "EPERM"].includes(error?.code) || attempt === 29) break; await delay(200); }
  }
  if (cleanupError) process.stderr.write(`Warning: disposable Character Review browser profile cleanup deferred: ${cleanupError.message}\n`);
}
