import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { boundedBrowserTimeout } from "./browser_acceptance_runtime.mjs";

const baseUrl = process.argv[2];
if (!baseUrl) throw new Error("Usage: node scripts/browser_speaker_review_invariant_smoke.mjs <base-url> [--read-only] [--from=N] [--to=N]");
const readOnly = process.argv.includes("--read-only");
const argNumber = (prefix, fallback) => {
  const raw = process.argv.find(item => item.startsWith(prefix));
  const value = Number(raw?.slice(prefix.length));
  return Number.isFinite(value) && value > 0 ? value : fallback;
};
const fromChapter = argNumber("--from=", 1);
const toChapter = argNumber("--to=", 10);
const browserExe = [
  process.env.STORY_AUDIO_BROWSER_EXE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");

const profile = await mkdtemp(join(tmpdir(), "story-audio-review-invariant-"));
const child = spawn(browserExe, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--remote-debugging-port=0",
  `--user-data-dir=${profile}`,
  `${baseUrl}/#/assignment?book=1&from=${fromChapter}&to=${toChapter}&skip_completed=1`,
], { stdio: "ignore" });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function poll(fn, timeoutMs = 15000) {
  const end = Date.now() + boundedBrowserTimeout(timeoutMs);
  let last;
  while (Date.now() < end) {
    try { const value = await fn(); if (value) return value; } catch (error) { last = error; }
    await delay(50);
  }
  throw last || new Error("Timed out");
}

let socket;
try {
  const port = await poll(async () => Number((await readFile(join(profile, "DevToolsActivePort"), "utf8")).split(/\r?\n/)[0]) || null);
  const page = await poll(async () => (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(item => item.type === "page" && item.url.startsWith(baseUrl)));
  socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let id = 0;
  const pending = new Map();
  const errors = [];
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.method === "Runtime.exceptionThrown") errors.push(message.params?.exceptionDetails?.exception?.description || message.params?.exceptionDetails?.text || "runtime exception");
    const waiter = pending.get(message.id);
    if (!waiter) return;
    pending.delete(message.id);
    message.error ? waiter.reject(new Error(message.error.message)) : waiter.resolve(message.result);
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => { const request = ++id; pending.set(request, { resolve, reject }); socket.send(JSON.stringify({ id: request, method, params })); });
  const evaluate = async expression => { const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }); if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text); return result.result.value; };
  const waitFor = (expression, timeout = 15000) => poll(async () => (await evaluate(expression)) || null, timeout);
  const setSelect = (selector, value) => evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)throw Error('missing select');el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}));return true})()`);
  const click = selector => evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)throw Error('missing click target');el.click();return true})()`);

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
  await waitFor(`window.storyAudioAppState?.bookVoiceRegistry?.status === 'ready' && document.querySelector('[data-speaker-manual-review]') && document.querySelector('[data-registry-map]')?.disabled === false`);
  await evaluate(`(()=>{window.__speakerInvariantCommands=[];const original=postProductionCommand;postProductionCommand=async(request,token=null)=>{window.__speakerInvariantCommands.push(request.command_type);return original(request,token)};return true})()`);

  const before = await evaluate(`(()=>{
    const workspace=document.querySelector('[data-speaker-review-workspace]');
    const metrics=workspace?.querySelector('.speaker-review-metrics')?.innerText||'';
    return {
      geminiDisabled: !!workspace?.querySelector('[data-generate-speaker-suggestions]')?.disabled,
      geminiLabel: workspace?.querySelector('[data-generate-speaker-suggestions]')?.textContent.trim()||'',
      providerBlocker: !!workspace?.querySelector('[data-open-gemini-settings]'),
      suggestionCards: workspace?.querySelectorAll('[data-speaker-suggestion-card]').length||0,
      manualCards: workspace?.querySelectorAll('[data-manual-speaker-key]').length||0,
      manualMapActions: workspace?.querySelectorAll('[data-registry-map]').length||0,
      queueTabs: workspace?.querySelectorAll('[data-speaker-review-view]').length||0,
      metrics,
      genericEmpty: workspace?.innerText.includes('Không có mục trong hàng đợi này')||false,
    };
  })()`);

  let after = null;
  if (!readOnly) {
    const key = "unresolved-dialogue:1002:u0002-deadbeef0000";
    await setSelect(`[data-registry-character-key="${key}"]`, "25");
    await click(`[data-registry-map="${key}"]`);
    await waitFor(`(window.__speakerInvariantCommands||[]).includes('MAP_SPEAKER_TO_CHARACTER')`, 30000);
    await waitFor(`document.querySelectorAll('[data-manual-speaker-key]').length === 2`, 30000);
    after = await evaluate(`({manualCards:document.querySelectorAll('[data-manual-speaker-key]').length,commands:window.__speakerInvariantCommands||[],hash:location.hash})`);
  } else {
    after = await evaluate(`({manualCards:document.querySelectorAll('[data-manual-speaker-key]').length,commands:window.__speakerInvariantCommands||[],hash:location.hash})`);
  }
  if (errors.length) throw new Error(errors.join(" | "));
  process.stdout.write(JSON.stringify({ ok: true, readOnly, before, after }));
} finally {
  try { socket?.close(); } catch {}
  const exited = new Promise(resolve => child.once("exit", resolve));
  child.kill();
  await Promise.race([exited, delay(2000)]);
  for (let attempt = 0; attempt < 20; attempt += 1) {
    try { await rm(profile, { recursive: true, force: true }); break; }
    catch (error) { if (!["EBUSY", "EPERM"].includes(error?.code) || attempt === 19) throw error; await delay(150); }
  }
}
