import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";

const baseUrl = process.argv[2];
if (!baseUrl) throw new Error("Usage: node scripts/browser_speaker_review_workspace_smoke.mjs <base-url>");
const browserExe = [
  process.env.STORY_AUDIO_BROWSER_EXE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");

const root = `C:\\StoryAudio_ReviewWorkspace_Test\\${Date.now()}`;
await mkdir(root, { recursive: true });
const profile = await mkdtemp(join(root, "browser-profile-"));
const child = spawn(browserExe, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--remote-debugging-port=0",
  `--user-data-dir=${profile}`,
  `${baseUrl}/#/assignment?book=1&from=2&to=5&skip_completed=0`,
], { stdio: "ignore" });

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function poll(callback, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const result = await callback();
      if (result) return result;
    } catch (error) {
      lastError = error;
    }
    await delay(50);
  }
  throw lastError || new Error("Timed out waiting for browser state.");
}

let socket;
try {
  const port = await poll(async () => Number(
    (await readFile(join(profile, "DevToolsActivePort"), "utf8")).split(/\r?\n/)[0],
  ) || null);
  const page = await poll(async () => {
    const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    return pages.find(item => item.type === "page" && item.url.startsWith(baseUrl));
  });
  socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  let nextId = 1;
  const pending = new Map();
  const browserErrors = [];
  socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (message.method === "Runtime.exceptionThrown") {
      browserErrors.push(message.params?.exceptionDetails?.exception?.description || message.params?.exceptionDetails?.text || "runtime exception");
    }
    if (!message.id || !pending.has(message.id)) return;
    const waiter = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) waiter.reject(new Error(message.error.message));
    else waiter.resolve(message.result);
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async expression => {
    const response = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (response.exceptionDetails) throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text);
    return response.result.value;
  };
  const waitFor = (expression, timeoutMs = 15000) => poll(async () => (await evaluate(expression)) || null, timeoutMs);
  const click = selector => evaluate(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); if(!el)throw new Error("Missing selector"); el.click(); return true })()`);
  const setInput = (selector, value) => evaluate(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); if(!el)throw new Error("Missing input"); el.value=${JSON.stringify(value)}; el.dispatchEvent(new Event("input",{bubbles:true})); el.dispatchEvent(new Event("change",{bubbles:true})); return true })()`);
  const setSelect = (selector, value) => evaluate(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); if(!el)throw new Error("Missing select"); el.value=${JSON.stringify(value)}; el.dispatchEvent(new Event("change",{bubbles:true})); return true })()`);
  const key1 = "unresolved-dialogue:1002:u0002-deadbeef0000";
  const key2 = "unresolved-dialogue:1003:u0002-feedface0000";
  const key3 = "unresolved-dialogue:1004:u0002-cafebabe0000";
  const key4 = "unresolved-dialogue:1005:u0002-010203040506";
  const key5 = "unresolved-dialogue:1006:u0002-111213141516";
  const attr = (name, value) => `[${name}="${value}"]`;

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
  await waitFor(`window.storyAudioAppState && document.querySelector('[data-speaker-review-workspace]')`);
  await waitFor(`document.querySelectorAll('[data-speaker-review-view]').length===7`);
  const defaultView = await evaluate(`document.querySelector('[data-speaker-review-view="NEEDS_REVIEW"]').classList.contains('active')`);
  await click('[data-speaker-review-view="ALL"]');
  await waitFor(`document.querySelectorAll('[data-speaker-suggestion-card]').length===5`);
  const allCardCount = await evaluate(`document.querySelectorAll('[data-speaker-suggestion-card]').length`);
  const labelsReadable = await evaluate(`[...document.querySelectorAll('[data-speaker-suggestion-card]')].every(card => card.querySelector('.status-symbol') && card.querySelector('.speaker-card-evidence') && card.querySelector('.speaker-card-decision') && card.querySelector('.speaker-card-actions'))`);

  await click(`${attr("data-speaker-suggestion-context", key1)} > summary`);
  await click(`${attr("data-speaker-suggestion-context", key2)} > summary`);
  await setInput(attr("data-speaker-suggestion-name", key2), "Edited Sentinel");
  await click(attr("data-speaker-suggestion-select", key1));
  await setSelect('[data-speaker-review-filter="confidence"]', "HIGH");
  const beforeDraft = await evaluate(`document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-name", key2))}).value`);
  await evaluate(`(async()=>{for(let i=0;i<3;i+=1)await loadSpeakerReviewSuggestions({force:true})})()`);
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-name", key2))})?.value==="Edited Sentinel"`);
  const draftsPreserved = await evaluate(`document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-context", key1))})?.open && document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-context", key2))})?.open && document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-name", key2))})?.value===${JSON.stringify(beforeDraft)} && window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.filters.confidence==="HIGH"`);

  await click(`${attr("data-speaker-suggestion-focus", key2)}[data-speaker-focus-target="character"]`);
  const characterFocus = await evaluate(`document.activeElement?.matches(${JSON.stringify(attr("data-speaker-suggestion-character", key2))})`);
  await click(`${attr("data-speaker-suggestion-focus", key2)}[data-speaker-focus-target="name"]`);
  const newCharacterFocus = await evaluate(`document.activeElement?.matches(${JSON.stringify(attr("data-speaker-suggestion-name", key2))})`);
  await click(`${attr("data-speaker-suggestion-focus", key2)}[data-speaker-focus-target="voice-mode"]`);
  const voiceFocus = await evaluate(`document.activeElement?.matches(${JSON.stringify(attr("data-speaker-suggestion-voice-mode", key2))})`);
  await setSelect(attr("data-speaker-suggestion-resolution", key2), "NEW_CHARACTER");
  await setInput(attr("data-speaker-suggestion-name", key2), "Edited Sentinel");
  await setSelect(attr("data-speaker-suggestion-voice-mode", key2), "exact");
  await setSelect(attr("data-speaker-suggestion-voice", key2), "commander");
  await click(attr("data-speaker-suggestion-save", key2));
  await waitFor(`window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions.find(item=>item.unresolved_key===${JSON.stringify(key2)}).review_state==="EDITED_AND_ACCEPTED"`);
  const editedDecisionSaved = await evaluate(`document.querySelector('[data-speaker-review-view="APPROVED"]')?.innerText.includes("1")`);

  await click(attr("data-speaker-suggestion-reanalyze", key3));
  await waitFor(`window.storyAudioAppState.productionCommand.commandType==="GENERATE_SPEAKER_SUGGESTIONS" && window.storyAudioAppState.productionCommand.status==="APPLIED"`);
  const reanalysisApplied = await evaluate(`window.storyAudioAppState.productionCommand.status==="APPLIED"`);
  await click(attr("data-speaker-suggestion-defer", key3));
  await waitFor(`window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions.find(item=>item.unresolved_key===${JSON.stringify(key3)}).review_state==="DEFERRED"`);
  const deferApplied = await evaluate(`window.storyAudioAppState.productionCommand.status==="APPLIED"`);

  await click(attr("data-speaker-suggestion-accept", key1));
  const busyVisible = await poll(async () => evaluate(`!!document.querySelector('.command-spinner') && !!document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-accept", key1))})?.disabled`), 2000);
  await waitFor(`window.storyAudioAppState.productionCommand.status==="APPLIED"`);
  await waitFor(`document.querySelector('[data-speaker-review-view="NEEDS_REVIEW"]')`);
  await click('[data-speaker-review-view="NEEDS_REVIEW"]');
  const approvedMoved = await waitFor(`!document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key1))}) && [...document.querySelectorAll('[data-speaker-review-view]')].find(el=>el.dataset.speakerReviewView==="APPROVED")?.innerText.includes("2")`);
  await click('[data-speaker-review-view="APPROVED"]');
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key1))})`);
  await click(attr("data-speaker-suggestion-replace", key1));
  await waitFor(`window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions.find(item=>item.unresolved_key===${JSON.stringify(key1)}).review_state==="REPLACEMENT_DRAFT"`);
  await setSelect(attr("data-speaker-suggestion-character", key1), "25");
  await setSelect(attr("data-speaker-suggestion-voice-mode", key1), "exact");
  await setSelect(attr("data-speaker-suggestion-voice", key1), "commander");
  await click(attr("data-speaker-suggestion-correct", key1));
  await waitFor(`window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions.find(item=>item.unresolved_key===${JSON.stringify(key1)}).review_state==="CORRECTED"`);
  const correctionHistoryVisible = await evaluate(`document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key1))})?.innerText.includes("Audit #") && document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key1))})?.innerText.includes("Audio đã chấp nhận hiện tại không bị thay đổi")`);

  await click('[data-speaker-review-view="NEEDS_REVIEW"]');
  await click('[data-speaker-batch-preview] > summary');
  const batchExcludedUnsafe = await evaluate(`document.querySelector('[data-speaker-batch-preview]')?.textContent.includes(${JSON.stringify(key4)})`);
  await evaluate(`(() => { const button=document.querySelector('[data-batch-speaker-suggestions]'); button.click(); button.click(); return true })()`);
  const batchBusyVisible = await poll(async () => evaluate(`!!document.querySelector('.command-spinner') && !!document.querySelector('[data-batch-speaker-suggestions]')?.disabled`), 2000);
  await waitFor(`window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions.find(item=>item.unresolved_key===${JSON.stringify(key5)}).review_state==="ACCEPTED"`);
  await waitFor(`(() => { const text=document.querySelector('.speaker-review-durable-result')?.innerText||""; return ["Yêu cầu: 1","Đã duyệt: 1","Bị loại: 1","Thất bại: 0"].every(value=>text.includes(value)) })()`);
  const batchResultText = await evaluate(`document.querySelector('.speaker-review-durable-result')?.innerText||""`);
  const batchResultVisible = ["Yêu cầu: 1", "Đã duyệt: 1", "Bị loại: 1", "Thất bại: 0"].every(value => batchResultText.includes(value));

  await evaluate(`(() => { const original=postProductionCommand; let lost=true; postProductionCommand=async(request,token=null)=>{const response=await original(request,token);if(lost&&request.command_type==="MARK_SPEAKER_SUGGESTION_UNCERTAIN"){lost=false;throw new Error("simulated response loss after apply")}return response}; return true })()`);
  await click(attr("data-speaker-suggestion-uncertain", key4));
  await waitFor(`["VERIFYING","VERIFYING_UNKNOWN"].includes(window.storyAudioAppState.productionCommand.status)`, 3000);
  await waitFor(`window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions.find(item=>item.unresolved_key===${JSON.stringify(key4)}).review_state==="MARKED_UNCERTAIN"`, 15000);
  const unknownResponseReconciled = await evaluate(`window.storyAudioAppState.productionCommand.status==="APPLIED"`);

  await send("Page.reload", { ignoreCache: true });
  await waitFor(`window.storyAudioAppState && document.querySelector('[data-speaker-review-workspace]')`, 20000);
  await waitFor(`document.querySelectorAll('[data-speaker-review-view]').length===7`, 20000);
  await waitFor(
    `document.querySelector('.speaker-review-durable-result')?.innerText===${JSON.stringify(batchResultText)}`,
    20000,
  );
  const batchResultReloadedText = await evaluate(`document.querySelector('.speaker-review-durable-result')?.innerText||""`);
  const batchResultReloaded = batchResultReloadedText === batchResultText;
  await click('[data-speaker-review-view="APPROVED"]');
  const reloadPersisted = await waitFor(`document.querySelectorAll('[data-speaker-suggestion-card]').length===3 && document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key1))})?.innerText.includes("Đã thay thế quyết định")`);
  const horizontalOverflow1366 = await evaluate(`document.documentElement.scrollWidth>innerWidth+1`);
  await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  const horizontalOverflow1920 = await evaluate(`document.documentElement.scrollWidth>innerWidth+1`);
  const durableMutationCount = await evaluate(`new Set((window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions||[]).flatMap(item=>(item.review_history||[]).map(entry=>entry.idempotency_key))).size`);
  if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);
  process.stdout.write(JSON.stringify({
    ok: defaultView && labelsReadable,
    allCardCount,
    busyVisible: !!busyVisible,
    characterFocus,
    newCharacterFocus,
    voiceFocus,
    editedDecisionSaved,
    reanalysisApplied,
    deferApplied,
    draftsPreserved: !!draftsPreserved,
    approvedMoved: !!approvedMoved,
    correctionHistoryVisible,
    batchExcludedUnsafe,
    batchBusyVisible: !!batchBusyVisible,
    batchResultText,
    batchResultVisible,
    batchResultReloadedText,
    batchResultReloaded,
    unknownResponseReconciled,
    reloadPersisted: !!reloadPersisted,
    horizontalOverflow1366,
    horizontalOverflow1920,
    durableMutationCount,
  }));
} finally {
  try { socket?.close(); } catch {}
  child.kill();
  await Promise.race([
    new Promise(resolve => child.once("exit", resolve)),
    delay(1500),
  ]);
  try {
    await rm(root, { recursive: true, force: true, maxRetries: 4, retryDelay: 200 });
  } catch {
    // A late Chromium crash reporter may briefly retain the disposable profile.
  }
}
