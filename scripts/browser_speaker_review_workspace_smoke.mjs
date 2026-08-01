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
  const click = selector => evaluate(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); if(!el)throw new Error("Missing selector"); el.focus(); el.click(); return true })()`);
  const setInput = (selector, value) => evaluate(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); if(!el)throw new Error("Missing input"); el.value=${JSON.stringify(value)}; el.dispatchEvent(new Event("input",{bubbles:true})); el.dispatchEvent(new Event("change",{bubbles:true})); return true })()`);
  const setSelect = (selector, value) => evaluate(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); if(!el)throw new Error("Missing select"); el.value=${JSON.stringify(value)}; el.dispatchEvent(new Event("change",{bubbles:true})); return true })()`);
  const key1 = "unresolved-dialogue:1002:u0002-deadbeef0000";
  const key2 = "unresolved-dialogue:1003:u0002-feedface0000";
  const key3 = "unresolved-dialogue:1004:u0002-cafebabe0000";
  const key4 = "unresolved-dialogue:1005:u0002-010203040506";
  const key5 = "unresolved-dialogue:1006:u0002-111213141516";
  const key6 = "unresolved-dialogue:1007:u0002-171819202122";
  const attr = (name, value) => `[${name}="${value}"]`;

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
  await waitFor(`window.storyAudioAppState && document.querySelector('[data-speaker-review-workspace]')`);
  await waitFor(`document.querySelectorAll('[data-speaker-review-view]').length===7`);
  const defaultView = await evaluate(`document.querySelector('[data-speaker-review-view="NEEDS_REVIEW"]').classList.contains('active')`);
  await click('[data-speaker-review-view="ALL"]');
  await waitFor(`document.querySelectorAll('[data-speaker-suggestion-card]').length===6`);
  const allCardCount = await evaluate(`document.querySelectorAll('[data-speaker-suggestion-card]').length`);
  const initialQueueRequestCount = await evaluate(`fetch('/api/fixture/speaker-review-queue-count').then(response=>response.json()).then(payload=>payload.count)`);
  const analysisCommandsBefore = await evaluate(`fetch('/api/fixture/speaker-review-command-state').then(response=>response.json()).then(payload=>payload.command_count)`);
  await evaluate(`(() => { const original=postProductionCommand; let lost=true; postProductionCommand=async(request,token=null)=>{const response=await original(request,token);if(lost&&request.command_type==="GENERATE_SPEAKER_SUGGESTIONS"){lost=false;throw new Error("simulated analyze response loss after persistence")}return response}; return true })()`);
  await click('[data-generate-speaker-suggestions]');
  const analysisPreparingSnapshot = await evaluate(`(() => { const progress=document.querySelector('[data-speaker-analysis-progress]'); const state=window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.analysisProgress; return {text:progress?.innerText||'',phase:state?.phase,targetCount:state?.targetCount,spinner:!!progress?.querySelector('.command-spinner')} })()`);
  await delay(250);
  const analysisImmediateSnapshot = await evaluate(`(() => { const progress=document.querySelector('[data-speaker-analysis-progress]'); const button=document.querySelector('[data-generate-speaker-suggestions]'); return {text:progress?.innerText||'',hidden:progress?.classList.contains('hidden'),spinner:!!progress?.querySelector('.command-spinner'),disabled:!!button?.disabled,phase:window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.analysisProgress?.phase,active:window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.analysisProgress?.active,targetCount:window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.analysisProgress?.targetCount} })()`);
  if (!(analysisPreparingSnapshot.phase==='preparing' && analysisPreparingSnapshot.text.includes(`${analysisPreparingSnapshot.targetCount} câu`) && analysisPreparingSnapshot.spinner && analysisImmediateSnapshot.phase==='sending' && analysisImmediateSnapshot.disabled && analysisImmediateSnapshot.spinner)) throw new Error(`Analyze immediate state mismatch: ${JSON.stringify({analysisPreparingSnapshot,analysisImmediateSnapshot})}`);
  const analysisImmediate = true;
  await click('[data-generate-speaker-suggestions]');
  const analysisElapsed = await waitFor(`document.querySelector('[data-speaker-analysis-progress]')?.innerText.includes('3 giây')`, 7000);
  const analysisLongWait = await waitFor(`document.querySelector('[data-speaker-analysis-progress]')?.innerText.includes('Gemini vẫn đang phân tích. Bạn có thể tiếp tục chờ; không cần bấm lại.')`, 14000);
  const analysisVerificationSeen = await waitFor(`document.querySelector('[data-speaker-analysis-progress]')?.innerText.includes('Đang xác minh kết quả đã lưu')`, 5000);
  await waitFor(`window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.analysisProgress.phase==="complete"`, 20000);
  const analysisFinalSummary = await evaluate(`document.querySelector('[data-speaker-analysis-progress]')?.innerText||''`);
  const analysisCommandState = await evaluate(`fetch('/api/fixture/speaker-review-command-state').then(response=>response.json())`);
  const analysisCommands = analysisCommandState.commands.filter(command=>command.command_type==="GENERATE_SPEAKER_SUGGESTIONS"),analysisSingleCommand = analysisCommands.length>=1 && new Set(analysisCommands.map(command=>command.idempotency_key)).size===1 && analysisCommandState.command_count>analysisCommandsBefore;
  const analysisCardsRemainVisible = await evaluate(`document.querySelectorAll('[data-speaker-suggestion-card]').length===6`);
  await delay(300);
  const jobsPollingControlStates = await evaluate(`(async()=>{const inspect=async selector=>{const control=document.querySelector(selector);if(!control)throw new Error("Missing review control: "+selector);let blurCount=0;control.addEventListener("blur",()=>{blurCount+=1});control.focus();const selection=control.matches("input,textarea")?[control.selectionStart,control.selectionEnd]:null;for(let index=0;index<3;index+=1)await loadJobs();const current=document.querySelector(selector);return{sameNode:current===control,focused:document.activeElement===control,blurCount,value:current?.value,selection:current?.matches("input,textarea")?[current.selectionStart,current.selectionEnd]:null,selectionBefore:selection}};const states={};states.resolution=await inspect(${JSON.stringify(attr("data-speaker-suggestion-resolution", key2))});states.group=await inspect(${JSON.stringify(attr("data-speaker-suggestion-group", key5))});states.character=await inspect(${JSON.stringify(attr("data-speaker-suggestion-character", key1))});const name=document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-name", key2))});name.setSelectionRange(1,Math.min(4,name.value.length));states.name=await inspect(${JSON.stringify(attr("data-speaker-suggestion-name", key2))});states.aliases=await inspect(${JSON.stringify(attr("data-speaker-suggestion-aliases", key2))});states.voiceMode=await inspect(${JSON.stringify(attr("data-speaker-suggestion-voice-mode", key2))});const mode=document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-voice-mode", key2))});mode.value="exact";mode.dispatchEvent(new Event("change",{bubbles:true}));await new Promise(resolve=>requestAnimationFrame(()=>resolve()));states.voiceScope=await inspect(${JSON.stringify(attr("data-speaker-suggestion-voice-scope", key2))});states.voice=await inspect(${JSON.stringify(attr("data-speaker-suggestion-voice", key2))});states.filter=await inspect('[data-speaker-review-filter="confidence"]');const details=document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-context", key2))});details.open=true;const detailNode=details;for(let index=0;index<3;index+=1)await loadJobs();states.details={sameNode:document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-context", key2))})===detailNode,open:detailNode.open};detailNode.open=false;return states})()`);
  const queueRequestCountAfterJobsPolling = await evaluate(`fetch('/api/fixture/speaker-review-queue-count').then(response=>response.json()).then(payload=>payload.count)`);
  const deferredAuthoritativeUpdate = await evaluate(`(async()=>{const selector=${JSON.stringify(attr("data-speaker-suggestion-name", key2))},control=document.querySelector(selector);control.focus();control.value="Draft survives polling";control.dispatchEvent(new Event("input",{bubbles:true}));await fetch('/api/fixture/speaker-review-server-update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({unresolved_key:${JSON.stringify(key2)},annotation:' Server update arrived.'})});await loadSpeakerReviewSuggestions({force:true});const sameBeforeBlur=document.querySelector(selector)===control,valueBeforeBlur=control.value,notice=!!control.closest('[data-speaker-suggestion-card]')?.querySelector('[data-speaker-review-deferred-notice]');control.blur();await loadJobs();for(let index=0;index<60;index+=1){const updated=document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key2))});if(updated?.textContent.includes('Server update arrived.'))break;await new Promise(resolve=>setTimeout(resolve,50))}const updated=document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key2))}),queue=window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions||{};return{sameBeforeBlur,valueBeforeBlur,notice,applied:updated?.textContent.includes('Server update arrived.'),draftAfterBlur:document.querySelector(selector)?.value,deferredStored:!!queue.deferredResult,activeTag:document.activeElement?.tagName,activeKey:document.activeElement?.closest?.('[data-speaker-suggestion-card]')?.dataset?.speakerSuggestionCard||null}})()`);
  const labelsReadable = await evaluate(`[...document.querySelectorAll('[data-speaker-suggestion-card]')].every(card => card.querySelector('.status-symbol') && card.querySelector('.speaker-card-evidence') && card.querySelector('.speaker-card-decision') && card.querySelector('.speaker-card-actions'))`);
  const backgroundGroupVisible = await evaluate(`(() => { const card=document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key5))}); const group=card?.querySelector(${JSON.stringify(attr("data-speaker-suggestion-group", key5))}); return !!card && card.innerText.includes("Quần chúng nam") && group?.value==="MALE" && card.innerText.includes("Mặc định nam của sách") })()`);
  const invalidDecisionBlocked = await evaluate(`(() => { const card=document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key3))}); return !!card?.querySelector('[data-speaker-suggestion-submit]')?.disabled && card?.innerText.includes('Chọn một kết luận cụ thể') })()`);

  await click(`${attr("data-speaker-suggestion-context", key1)} > summary`);
  await click(`${attr("data-speaker-suggestion-context", key2)} > summary`);
  await setInput(attr("data-speaker-suggestion-name", key2), "Edited Sentinel");
  await click(attr("data-speaker-suggestion-select", key1));
  await setSelect('[data-speaker-review-filter="confidence"]', "HIGH");
  const beforeDraft = await evaluate(`document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-name", key2))}).value`);
  await evaluate(`(async()=>{for(let i=0;i<3;i+=1)await loadSpeakerReviewSuggestions({force:true})})()`);
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-name", key2))})?.value==="Edited Sentinel"`);
  const draftsPreserved = await evaluate(`document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-context", key1))})?.open && document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-context", key2))})?.open && document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-name", key2))})?.value===${JSON.stringify(beforeDraft)} && window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.filters.confidence==="HIGH"`);
  const pollingDecisionState = await evaluate(`(() => { const card=document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key2))}); return {dirty:card?.querySelector('[data-speaker-decision-state]')?.innerText||'',primary:card?.querySelector('[data-speaker-suggestion-submit]')?.innerText||'',details:card?.querySelector('[data-speaker-suggestion-context]')?.open,scrollY:window.scrollY} })()`);

  const discardCommandsBefore = await evaluate(`fetch('/api/fixture/speaker-review-command-state').then(response=>response.json()).then(payload=>payload.command_count)`);
  await click(attr("data-speaker-suggestion-discard", key2));
  const discardRestored = await waitFor(`(() => { const card=document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key2))}); return card?.querySelector(${JSON.stringify(attr("data-speaker-suggestion-name", key2))})?.value==="Outer Sentinel" && card?.querySelector('[data-speaker-suggestion-submit]')?.innerText==="Chấp nhận đề xuất Gemini" && card?.querySelector('[data-speaker-decision-state]')?.innerText.includes("Đang giữ nguyên đề xuất Gemini") })()`);
  const discardCommandsAfter = await evaluate(`fetch('/api/fixture/speaker-review-command-state').then(response=>response.json()).then(payload=>payload.command_count)`);
  const discardNoMutation = discardCommandsBefore===discardCommandsAfter;

  const shortcutCommandsBefore = discardCommandsAfter;
  await click(`${attr("data-speaker-suggestion-focus", key2)}[data-speaker-focus-target="character"]`);
  const characterFocus = await evaluate(`document.activeElement?.matches(${JSON.stringify(attr("data-speaker-suggestion-character", key2))})`);
  await click(`${attr("data-speaker-suggestion-focus", key2)}[data-speaker-focus-target="name"]`);
  const newCharacterFocus = await evaluate(`document.activeElement?.matches(${JSON.stringify(attr("data-speaker-suggestion-name", key2))})`);
  await click(`${attr("data-speaker-suggestion-focus", key2)}[data-speaker-focus-target="voice-mode"]`);
  const voiceFocus = await evaluate(`document.activeElement?.matches(${JSON.stringify(attr("data-speaker-suggestion-voice", key2))})`);
  const shortcutCommandsAfter = await evaluate(`fetch('/api/fixture/speaker-review-command-state').then(response=>response.json()).then(payload=>payload.command_count)`);
  const shortcutsNoMutation = shortcutCommandsBefore===shortcutCommandsAfter;
  await setSelect(attr("data-speaker-suggestion-resolution", key2), "EXISTING_CHARACTER");
  await setSelect(attr("data-speaker-suggestion-character", key2), "25");
  await setInput(attr("data-speaker-suggestion-name", key2), "Edited Sentinel");
  await setInput(attr("data-speaker-suggestion-aliases", key2), "edited alias");
  await setSelect(attr("data-speaker-suggestion-voice-mode", key2), "exact");
  await setSelect(attr("data-speaker-suggestion-voice", key2), "commander");
  await setSelect(attr("data-speaker-suggestion-voice-scope", key2), "range");
  const multiFieldDirty = await evaluate(`document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key2))})?.querySelector('[data-speaker-decision-state]')?.innerText||''`);
  await click(attr("data-speaker-suggestion-submit", key2));
  await waitFor(`window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions.find(item=>item.unresolved_key===${JSON.stringify(key2)}).review_state==="EDITED_AND_ACCEPTED"`);
  const editedDecisionSaved = await evaluate(`document.querySelector('[data-speaker-review-view="APPROVED"]')?.innerText.includes("1")`);
  const originalProposalRetained = await evaluate(`document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key2))})?.innerText.includes("Đề xuất của Gemini")`);

  await setInput(attr("data-speaker-suggestion-name", key6), "Edited Minor Character");
  const oneFieldDirty = await evaluate(`document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key6))})?.querySelector('[data-speaker-decision-state]')?.innerText.includes("Đã chỉnh sửa 1 trường")`);
  await click(attr("data-speaker-suggestion-submit", key6));
  await waitFor(`window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions.find(item=>item.unresolved_key===${JSON.stringify(key6)}).review_state==="EDITED_AND_ACCEPTED"`);
  const oneFieldAccepted = await evaluate(`(() => { const item=window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions.find(row=>row.unresolved_key===${JSON.stringify(key6)}); const payload=item?.human_review?.reviewer_payload||{}; return payload.proposed_resolution==="NEW_CHARACTER" && payload.proposed_character_name==="Edited Minor Character" })()`);

  await click(attr("data-speaker-suggestion-reanalyze", key3));
  await waitFor(`window.storyAudioAppState.productionCommand.commandType==="GENERATE_SPEAKER_SUGGESTIONS" && window.storyAudioAppState.productionCommand.status==="APPLIED"`);
  const reanalysisApplied = await evaluate(`window.storyAudioAppState.productionCommand.status==="APPLIED"`);
  await click(attr("data-speaker-suggestion-defer", key3));
  await waitFor(`window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions.find(item=>item.unresolved_key===${JSON.stringify(key3)}).review_state==="DEFERRED"`);
  const deferApplied = await evaluate(`window.storyAudioAppState.productionCommand.status==="APPLIED"`);

  const unchangedPrimary = await evaluate(`document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-submit", key1))})?.innerText==="Chấp nhận đề xuất Gemini"`);
  await click(attr("data-speaker-suggestion-submit", key1));
  const busyVisible = await poll(async () => evaluate(`!!document.querySelector('.command-spinner') && !!document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-submit", key1))})?.disabled`), 2000);
  await waitFor(`window.storyAudioAppState.productionCommand.status==="APPLIED"`);
  await waitFor(`document.querySelector('[data-speaker-review-view="NEEDS_REVIEW"]')`);
  await click('[data-speaker-review-view="NEEDS_REVIEW"]');
  const approvedMoved = await waitFor(`!document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key1))}) && [...document.querySelectorAll('[data-speaker-review-view]')].find(el=>el.dataset.speakerReviewView==="APPROVED")?.innerText.includes("3")`);
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
  const reloadPersisted = await waitFor(`document.querySelectorAll('[data-speaker-suggestion-card]').length===4 && document.querySelector(${JSON.stringify(attr("data-speaker-suggestion-card", key1))})?.innerText.includes("Đã thay thế quyết định")`);
  const horizontalOverflow1366 = await evaluate(`document.documentElement.scrollWidth>innerWidth+1`);
  await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  const horizontalOverflow1920 = await evaluate(`document.documentElement.scrollWidth>innerWidth+1`);
  const durableMutationCount = await evaluate(`new Set((window.storyAudioAppState.bookVoiceRegistry.speakerSuggestions.result.suggestions||[]).flatMap(item=>(item.review_history||[]).map(entry=>entry.idempotency_key))).size`);
  if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);
  process.stdout.write(JSON.stringify({
    ok: defaultView && labelsReadable && backgroundGroupVisible,
    allCardCount,
    initialQueueRequestCount,
    analysisImmediate: !!analysisImmediate,
    analysisElapsed: !!analysisElapsed,
    analysisLongWait: !!analysisLongWait,
    analysisVerificationSeen: !!analysisVerificationSeen,
    analysisFinalSummary,
    analysisSingleCommand,
    analysisCardsRemainVisible,
    jobsPollingControlStates,
    queueRequestCountAfterJobsPolling,
    deferredAuthoritativeUpdate,
    backgroundGroupVisible,
    invalidDecisionBlocked,
    busyVisible: !!busyVisible,
    characterFocus,
    newCharacterFocus,
    voiceFocus,
    editedDecisionSaved,
    originalProposalRetained,
    oneFieldAccepted,
    oneFieldDirty,
    multiFieldDirty,
    unchangedPrimary,
    reanalysisApplied,
    deferApplied,
    draftsPreserved: !!draftsPreserved,
    pollingDecisionState,
    discardRestored: !!discardRestored,
    discardNoMutation,
    shortcutsNoMutation,
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
