import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";

const baseUrl = process.argv[2];
const runRoot = process.argv[3];
const fixture = JSON.parse(process.argv[4] || "{}");
if (!baseUrl || !runRoot || !fixture.book_id) {
  throw new Error("Usage: node scripts/browser_golden_journey_certification.mjs <base-url> <run-root> <fixture-json>");
}

const browserExe = [
  process.env.STORY_AUDIO_BROWSER_EXE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");

const profile = join(runRoot, "browser-profile");
const downloads = join(runRoot, "downloads");
await rm(profile, { recursive: true, force: true });
await mkdir(profile, { recursive: true });
await mkdir(downloads, { recursive: true });

const child = spawn(browserExe, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--remote-debugging-port=0",
  `--user-data-dir=${profile}`,
  `${baseUrl}/#/production`,
], { stdio: "ignore" });

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function poll(callback, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const value = await callback();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await delay(80);
  }
  throw lastError || new Error("Timed out waiting for browser state.");
}

let socket;
try {
  const port = await poll(async () => Number((await readFile(join(profile, "DevToolsActivePort"), "utf8")).split(/\r?\n/)[0]) || null);
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
    if (message.method === "Runtime.consoleAPICalled" && message.params?.type === "error") {
      browserErrors.push((message.params.args || []).map(item => item.value || item.description).join(" "));
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
    const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  };
  const waitFor = (expression, timeoutMs = 20000) => poll(async () => (await evaluate(expression)) || null, timeoutMs);
  const click = selector => evaluate(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); if(!el) throw new Error(${JSON.stringify(`Missing ${selector}`)}); el.click(); return true; })()`);
  const input = (selector, value) => evaluate(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); if(!el) throw new Error(${JSON.stringify(`Missing ${selector}`)}); el.value=${JSON.stringify(value)}; el.dispatchEvent(new Event("input",{bubbles:true})); el.dispatchEvent(new Event("change",{bubbles:true})); return true; })()`);

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
  await waitFor(`document.readyState==="complete"`);
  await waitFor(`window.storyAudioAppState&&document.querySelector("#productionPrimaryAction")`);

  const evidence = {
    stages: [],
    commandInjections: {},
    accessibility: {},
    downloads: {},
  };

  // Stage A: visible scope selection, durable URL/context, refresh/navigation stability.
  await click("#productionPrimaryAction");
  await waitFor(`document.querySelector("#productionScopeDialog")?.open===true`);
  await click(`[data-scope-book-id="${fixture.book_id}"]`);
  await waitFor(`document.querySelector("#scopeChapterList .scope-chapter-card")`);
  await input("#scopeFromChapter", String(fixture.chapter_number));
  await input("#scopeToChapter", String(fixture.chapter_number));
  await waitFor(`document.querySelector("#reviewProductionScope")?.disabled===false`, 10000);
  await click("#reviewProductionScope");
  await waitFor(`location.hash.includes("book=${fixture.book_id}")&&location.hash.includes("from=${fixture.chapter_number}")&&location.hash.includes("to=${fixture.chapter_number}")`);
  await waitFor(`window.storyAudioAppState.productionRange?.fromChapter===${fixture.chapter_number}`);
  await send("Page.reload", { ignoreCache: true });
  await waitFor(`document.readyState==="complete"`);
  await waitFor(`window.storyAudioAppState?.productionRange?.fromChapter===${fixture.chapter_number}`);
  await evaluate(`location.hash="#/jobs"`);
  await waitFor(`window.storyAudioAppState.currentRoute==="jobs"`);
  await evaluate(`history.back()`);
  await waitFor(`window.storyAudioAppState.currentRoute==="production"`);
  await evaluate(`history.forward()`);
  await waitFor(`window.storyAudioAppState.currentRoute==="jobs"`);
  await evaluate(`location.hash=${JSON.stringify(`#/production?book=${fixture.book_id}&from=${fixture.chapter_number}&to=${fixture.chapter_number}`)}`);
  await waitFor(`window.storyAudioAppState.productionProjection?.canonical_task&&window.storyAudioAppState.productionRange?.fromChapter===${fixture.chapter_number}`);
  evidence.stages.push("scope_selection");

  // Stage B: visible book-centric voice assignment and blocker clearance.
  await evaluate(`location.hash=${JSON.stringify(`#/assignment?book=${fixture.book_id}&from=${fixture.chapter_number}&to=${fixture.chapter_number}`)}`);
  await waitFor(`window.storyAudioAppState.currentRoute==="assignment"`);
  await waitFor(`document.querySelector(${JSON.stringify(`#assignmentVoice-${fixture.character_id}`)})`);
  const assignmentBefore = await evaluate(`document.querySelector("#assignmentRows")?.innerText || ""`);
  await evaluate(`(() => { const select=document.querySelector(${JSON.stringify(`#assignmentVoice-${fixture.character_id}`)}); select.value="fixture_character"; select.dispatchEvent(new Event("change",{bubbles:true})); return true; })()`);
  const saveSelector = `[data-book-registry-save="${fixture.character_id}"]`;
  await click(saveSelector);
  await click(saveSelector);
  await waitFor(`!window.storyAudioAppState.productionCommand.active`, 20000);
  await waitFor(`window.storyAudioAppState.bookVoiceRegistry?.loading===false&&document.querySelector(${JSON.stringify(`#assignmentVoice-${fixture.character_id}`)})`, 20000);
  await waitFor(`!document.querySelector("#assignmentRows")?.innerText.includes("fixture_missing")`, 20000);
  const assignmentAfter = await evaluate(`document.querySelector("#assignmentRows")?.innerText || ""`);
  if (!await evaluate(`!!document.querySelector(${JSON.stringify(`#assignmentVoice-${fixture.character_id}`)})`)) {
    throw new Error(`Assignment registry lost the character selector. Before=${assignmentBefore} After=${assignmentAfter}`);
  }
  evidence.assignment = { before: assignmentBefore, after: assignmentAfter };
  evidence.stages.push("voice_assignment");

  // Create a new plan after the voice fix, then approve it through the visible production primary action.
  const newPlan = await evaluate(`(async()=> {
    const context = await api("/api/chapters/${fixture.chapter_id}/casting");
    const assignments = context.casting.plan.utterances.map(u => ({utterance_id:u.utterance_id, role:u.role, character_id:u.character_id ?? null}));
    const draft = await api("/api/chapters/${fixture.chapter_id}/casting/draft", {
      method:"POST",
      body:JSON.stringify({text_revision_id:${fixture.revision_id}, narrator_voice_id:"fixture_narrator", assignments})
    });
    await openChapter(${fixture.chapter_id});
    await openCasting();
    return {id:draft.id,status:draft.status,revision:draft.plan_revision};
  })()`);
  await evaluate(`(async()=>{setAppRoute("production"); await loadProductionTaskProjection(); return window.storyAudioAppState.currentRoute})()`);
  await waitFor(`window.storyAudioAppState.currentRoute==="production"`);
  await waitFor(`["REVIEW_CASTING_PLAN","APPROVE_RANGE_CASTING_PLANS"].includes(window.storyAudioAppState.productionProjection?.canonical_task?.task_type)`);
  await click("#productionPrimaryAction");
  await waitFor(`!window.storyAudioAppState.productionCommand.active`, 20000);
  await waitFor(`window.storyAudioAppState.productionProjection?.canonical_task?.task_type==="PREPARE_RANGE"`, 20000);
  evidence.stages.push("preflight_ready");

  // Failure injection matrix around the command coordinator, provider-free.
  evidence.commandInjections = await evaluate(`(async()=> {
    const savedApi=api, savedPost=postProductionCommand, savedSync=syncCanonicalProductionContext;
    syncCanonicalProductionContext=async()=>{};
    postProductionCommand=async(commandRequest,authorizationToken=null)=>api("/api/production/commands",{method:"POST",headers:{"Content-Type":"application/json",...(authorizationToken?{"Authorization":"Bearer "+authorizationToken}:{})},body:JSON.stringify(commandRequest)});
    const scope={range:{book_id:${fixture.book_id},from_chapter:${fixture.chapter_number},to_chapter:${fixture.chapter_number}}};
    const baseProjection=JSON.parse(JSON.stringify(window.storyAudioAppState.productionProjection));
    const reply=(body,outcome="APPLIED")=>({schema:"story-audio-production-command/v1",command_id:"pc-"+body.idempotency_key,command_type:body.command_type,idempotency_key:body.idempotency_key,scope:body.scope,outcome,submitted_count:1,applied_count:outcome==="APPLIED"?1:0,failed_count:outcome==="APPLIED"?0:1,applied_items:outcome==="APPLIED"?[{chapter_number:${fixture.chapter_number}}]:[],failed_items:outcome==="APPLIED"?[]:[{chapter_number:${fixture.chapter_number},reason:"fixture failure"}],operator_message:"fixture",resulting_task_projection:baseProjection,resulting_preflight:null,state_tokens:{task_projection:"fixture"}});
    const cases={};
    for (const code of [400,409,422,500]) {
      window.storyAudioAppState.productionCommand.keys={};
      api=async()=>{const error=new Error("HTTP "+code); error.status=code; throw error};
      const result=await runProductionCommand({commandType:"SAVE_VOICE_ASSIGNMENT",scope,payload:{character_id:${fixture.character_id},voice_override_id:"fixture_character"},label:"fixture"});
      cases["http_"+code]={result:result===null,status:window.storyAudioAppState.productionCommand.status,active:window.storyAudioAppState.productionCommand.active};
    }
    let calls=[],release;
    window.storyAudioAppState.productionCommand.keys={};
    api=async(_path,options)=>{calls.push(JSON.parse(options.body)); await new Promise(resolve=>release=resolve); return reply(calls[0]);};
    const first=runProductionCommand({commandType:"SAVE_VOICE_ASSIGNMENT",scope,payload:{character_id:${fixture.character_id},voice_override_id:"fixture_character"},label:"fixture delayed"});
    const second=runProductionCommand({commandType:"SAVE_VOICE_ASSIGNMENT",scope,payload:{character_id:${fixture.character_id},voice_override_id:"fixture_character"},label:"fixture delayed"});
    const busy=window.storyAudioAppState.productionCommand.active;
    for(let i=0;i<20&&!release;i+=1) await new Promise(resolve=>setTimeout(resolve,10));
    if(typeof release!=="function") throw new Error("delayed fake API was not invoked");
    release();
    await Promise.all([first,second]);
    cases.duplicate_delayed={calls:calls.length,busy,status:window.storyAudioAppState.productionCommand.status};
    window.storyAudioAppState.productionCommand.keys={};
    let lost=true; calls=[];
    api=async(_path,options)=>{const body=JSON.parse(options.body); calls.push(body); if(lost){lost=false; throw new Error("connection closed after apply")} return reply(body)};
    const verified=await runProductionCommand({commandType:"HUMAN_QA_ACCEPT",scope:{artifact:{id:999}},payload:{chapter_id:${fixture.chapter_id},notes:"fixture"},label:"fixture lost"});
    cases.response_lost={outcome:verified?.outcome,calls:calls.length,sameKey:calls.length===2&&calls[0].idempotency_key===calls[1].idempotency_key};
    api=savedApi; postProductionCommand=savedPost; syncCanonicalProductionContext=savedSync; return cases;
  })()`);

  // Stage D: PREPARE through visible UI.
  await click("#productionPrimaryAction");
  await waitFor(`document.querySelector("#productionPrepareAuthDialog")?.open===true`);
  await click("#productionPrepareDialogConfirmation");
  await evaluate(`(() => { const dialog=document.querySelector("#productionPrepareAuthDialog"),el=dialog?.querySelector("#productionTaskOperatorToken"); if(!el) throw new Error("Missing PREPARE dialog token"); el.value="fixture-token"; el.dispatchEvent(new Event("input",{bubbles:true})); el.dispatchEvent(new Event("change",{bubbles:true})); return true; })()`);
  await evaluate(`updateProductionPrepareDialog(); true`);
  try {
    await waitFor(`(()=>{updateProductionPrepareDialog();return document.querySelector("#productionPrepareDialogSubmit")?.disabled===false})()`, 5000);
  } catch (error) {
    const diagnostic = await evaluate(`({
      task: window.storyAudioAppState.productionProjection?.canonical_task?.task_type,
      action: window.storyAudioAppState.productionProjection?.canonical_task?.primary_action?.key,
      preflight: window.storyAudioAppState.productionPreflight?.execution_readiness,
      readiness: window.storyAudioAppState.productionPrepare?.readiness,
      dialogOpen: document.querySelector("#productionPrepareAuthDialog")?.open,
      checked: document.querySelector("#productionPrepareDialogConfirmation")?.checked,
      tokenLength: document.querySelector("#productionPrepareAuthDialog")?.querySelector("#productionTaskOperatorToken")?.value?.length || 0,
      disabled: document.querySelector("#productionPrepareDialogSubmit")?.disabled,
      status: document.querySelector("#productionPrepareDialogStatus")?.textContent || "",
      updateSource: String(updateProductionPrepareDialog).slice(0, 360),
      scripts: [...document.scripts].map(script => script.src || "inline")
    })`);
    throw new Error(`PREPARE submit stayed disabled: ${JSON.stringify(diagnostic)}`);
  }
  await click("#productionPrepareDialogSubmit");
  await waitFor(`!window.storyAudioAppState.productionCommand.active`, 20000);
  try {
    await waitFor(`window.storyAudioAppState.productionProjection?.canonical_task?.task_type==="START_RENDER_RANGE"`, 20000);
  } catch (error) {
    const diagnostic = await evaluate(`({
      task: window.storyAudioAppState.productionProjection?.canonical_task?.task_type,
      action: window.storyAudioAppState.productionProjection?.canonical_task?.primary_action?.key,
      command: window.storyAudioAppState.productionCommand,
      preflight: window.storyAudioAppState.productionPreflight?.execution_readiness,
      readiness: window.storyAudioAppState.productionPrepare?.readiness,
      body: document.body.innerText.slice(0, 1200)
    })`);
    throw new Error(`PREPARE did not reach START_RENDER_RANGE: ${JSON.stringify(diagnostic)}`);
  }
  const preparedJob = await evaluate(`window.storyAudioAppState.productionProjection?.canonical_task?.render?.job_id || window.storyAudioAppState.productionPreflight?.execution_readiness?.prepared_job?.job_id || 0`);
  if (!preparedJob) throw new Error("PREPARE did not expose a prepared job.");
  evidence.stages.push("prepare");

  // Stage E: START_RENDER and wait for Human QA target.
  await waitFor(`window.storyAudioAppState.productionProjection?.canonical_task?.task_type==="START_RENDER_RANGE"&&document.querySelector("#productionPrimaryAction")?.disabled===false`, 10000);
  await click("#productionPrimaryAction");
  try {
    await waitFor(`window.storyAudioAppState.productionProjection?.canonical_task?.task_type==="HUMAN_QA"`, 45000);
  } catch (error) {
    const diagnostic = await evaluate(`({
      task: window.storyAudioAppState.productionProjection?.canonical_task?.task_type,
      action: window.storyAudioAppState.productionProjection?.canonical_task?.primary_action?.key,
      command: window.storyAudioAppState.productionCommand,
      render: window.storyAudioAppState.productionProjection?.canonical_task?.render,
      primaryDisabled: document.querySelector("#productionPrimaryAction")?.disabled,
      body: document.body.innerText.slice(0, 1200)
    })`);
    throw new Error(`START_RENDER did not reach HUMAN_QA: ${JSON.stringify(diagnostic)}`);
  }
  await waitFor(`document.querySelector("#productionQaAudio")`);
  const firstArtifact = await evaluate(`window.storyAudioAppState.dialog?.audio_artifact?.id || window.storyAudioAppState.productionProjection?.canonical_task?.qa?.artifact_id`);
  if (!firstArtifact) throw new Error("First render did not create a QA artifact.");
  evidence.firstArtifact = firstArtifact;
  evidence.stages.push("first_render");

  // Stage F: needs_fixes with one click, then authoritative REPAIR_REQUIRED.
  await evaluate(`document.querySelector("#productionQaAudio").currentTime = 0.2`);
  await input("#productionQaNote", "Fixture defect at marker; needs same-data rerender.");
  await click("#productionQaNeedsFixes");
  await waitFor(`!window.storyAudioAppState.productionCommand.active`, 20000);
  await waitFor(`window.storyAudioAppState.productionProjection?.canonical_task?.task_type==="REPAIR_REQUIRED"`, 20000);
  const repairState = await evaluate(`({
    qaActionsHidden: document.querySelector("#productionQaActions")?.classList.contains("hidden"),
    buttons: ["repairSameData","repairVoice","repairTextSpeaker"].every(id=>!!document.getElementById(id)),
    body: document.querySelector("#productionTaskContent")?.innerText || ""
  })`);
  if (!repairState.buttons) throw new Error(`Repair routes missing: ${JSON.stringify(repairState)}`);
  evidence.stages.push("needs_fixes");

  // Stage G: exercise repair routes, then choose same-data repair.
  await click("#repairVoice");
  await waitFor(`window.storyAudioAppState.currentRoute==="assignment"`);
  await evaluate(`location.hash=${JSON.stringify(`#/production?book=${fixture.book_id}&from=${fixture.chapter_number}&to=${fixture.chapter_number}`)}`);
  await waitFor(`window.storyAudioAppState.currentRoute==="production"`);
  await waitFor(`window.storyAudioAppState.productionProjection?.canonical_task?.task_type==="REPAIR_REQUIRED"`, 20000);
  await waitFor(`document.querySelector("#repairTextSpeaker")`);
  await click("#repairTextSpeaker");
  await waitFor(`window.storyAudioAppState.currentRoute==="production"`);
  await waitFor(`document.querySelector("#repairSameData")`);
  await click("#repairSameData");
  await waitFor(`document.querySelector("#repairPrepare")`);
  await evaluate(`(() => { const el=document.querySelector("#repairOperatorToken"); if(el){ el.value="fixture-token"; el.dispatchEvent(new Event("input",{bubbles:true})); el.dispatchEvent(new Event("change",{bubbles:true})); } return true; })()`);
  evidence.stages.push("repair_routes");

  // Stage H: replacement PREPARE and replacement START_RENDER.
  await click("#repairPrepare");
  await waitFor(`!window.storyAudioAppState.productionCommand.active`, 20000);
  try {
    await waitFor(`window.storyAudioAppState.productionProjection?.canonical_task?.task_type==="START_RENDER_RANGE"`, 20000);
  } catch (error) {
    const diagnostic = await evaluate(`({
      task: window.storyAudioAppState.productionProjection?.canonical_task?.task_type,
      command: window.storyAudioAppState.productionCommand,
      repair: window.storyAudioAppState.productionProjection?.canonical_task?.repair,
      preflight: window.storyAudioAppState.productionPreflight?.execution_readiness,
      tokenLength: document.querySelector("#repairOperatorToken")?.value?.length || 0,
      body: document.body.innerText.slice(0, 1200)
    })`);
    throw new Error(`Replacement PREPARE did not reach START_RENDER_RANGE: ${JSON.stringify(diagnostic)}`);
  }
  await waitFor(`window.storyAudioAppState.productionProjection?.canonical_task?.task_type==="START_RENDER_RANGE"&&document.querySelector("#productionPrimaryAction")?.disabled===false`, 10000);
  await click("#productionPrimaryAction");
  try {
    await waitFor(`window.storyAudioAppState.productionProjection?.canonical_task?.task_type==="HUMAN_QA"`, 45000);
  } catch (error) {
    const diagnostic = await evaluate(`({
      task: window.storyAudioAppState.productionProjection?.canonical_task?.task_type,
      action: window.storyAudioAppState.productionProjection?.canonical_task?.primary_action?.key,
      command: window.storyAudioAppState.productionCommand,
      render: window.storyAudioAppState.productionProjection?.canonical_task?.render,
      primaryDisabled: document.querySelector("#productionPrimaryAction")?.disabled,
      body: document.body.innerText.slice(0, 1200)
    })`);
    throw new Error(`Replacement START_RENDER did not reach HUMAN_QA: ${JSON.stringify(diagnostic)}`);
  }
  const replacementArtifact = await evaluate(`window.storyAudioAppState.dialog?.audio_artifact?.id || window.storyAudioAppState.productionProjection?.canonical_task?.qa?.artifact_id`);
  if (!replacementArtifact || Number(replacementArtifact) === Number(firstArtifact)) throw new Error("Replacement artifact did not replace QA target.");
  evidence.replacementArtifact = replacementArtifact;
  evidence.stages.push("replacement_render");

  // Stage I: accept replacement with one click and verify COMPLETE.
  await evaluate(`document.querySelector("#productionQaAudio").currentTime = 0.2`);
  await click("#productionQaAccept");
  await waitFor(`!window.storyAudioAppState.productionCommand.active`, 20000);
  await waitFor(`window.storyAudioAppState.productionProjection?.canonical_task?.task_type==="COMPLETE"`, 20000);
  const completion = await evaluate(`({
    task: window.storyAudioAppState.productionProjection?.canonical_task?.task_type,
    qaActionsHidden: document.querySelector("#productionQaActions")?.classList.contains("hidden"),
    downloadHref: document.querySelector("#productionCompleteDownload")?.href || "",
    openAudio: !!document.querySelector("#productionCompleteOpenAudio")
  })`);
  if (completion.task !== "COMPLETE" || !completion.openAudio) throw new Error(`Completion screen failed: ${JSON.stringify(completion)}`);
  evidence.stages.push("accept_replacement");

  // Stage J: open Audio and verify active replacement selection/playback URL.
  await click("#productionCompleteOpenAudio");
  await waitFor(`window.storyAudioAppState.currentRoute==="audio"`);
  await waitFor(`window.storyAudioAppState.audioLibrary.loaded===true`);
  await waitFor(`Number(window.storyAudioAppState.audioLibrary.selectedArtifactId)===Number(${replacementArtifact})`);
  const audioState = await evaluate(`(() => {
    const audio=document.querySelector("#audioLibraryAudio");
    audio.currentTime=0;
    return {
      selected: window.storyAudioAppState.audioLibrary.selectedArtifactId,
      src: audio?.src || "",
      durationText: document.querySelector("#audioLibraryPlayerMeta")?.textContent || "",
      rejectedVisible: document.body.innerText.includes(String(${firstArtifact}))
    };
  })()`);
  if (!audioState.src.includes(`/api/artifacts/${replacementArtifact}/file`)) throw new Error(`Audio route selected stale source: ${JSON.stringify(audioState)}`);
  evidence.audioState = audioState;
  evidence.stages.push("audio_playback");

  // Stage K: visible chapter download URL and range ZIP from C: downloads.
  const activeDownload = await fetch(`${baseUrl}/api/artifacts/${replacementArtifact}/file`);
  if (!activeDownload.ok) throw new Error(`Active artifact download failed: ${activeDownload.status}`);
  const activeBytes = Buffer.from(await activeDownload.arrayBuffer());
  const activeHash = createHash("sha256").update(activeBytes).digest("hex");
  await writeFile(join(downloads, `artifact_${replacementArtifact}.m4a`), activeBytes);
  const zipUrl = `${baseUrl}/api/audio-library/range-archive?book_id=${fixture.book_id}&from_chapter=${fixture.chapter_number}&to_chapter=${fixture.chapter_number + 1}`;
  const zipResponse = await fetch(zipUrl);
  if (!zipResponse.ok) throw new Error(`Range ZIP failed: ${zipResponse.status}`);
  const zipBytes = Buffer.from(await zipResponse.arrayBuffer());
  const zipHash = createHash("sha256").update(zipBytes).digest("hex");
  await writeFile(join(downloads, "range_372_373.zip"), zipBytes);
  evidence.downloads = { activeHash, activeBytes: activeBytes.length, zipHash, zipBytes: zipBytes.length };
  evidence.stages.push("download");

  // Stage L: refresh/persistent routing plus accessibility basics.
  await evaluate(`location.hash=${JSON.stringify(`#/production?book=${fixture.book_id}&from=${fixture.chapter_number}&to=${fixture.chapter_number}`)}`);
  await waitFor(`window.storyAudioAppState.currentRoute==="production"`);
  await waitFor(`window.storyAudioAppState.productionProjection?.canonical_task?.task_type==="COMPLETE"`);
  await send("Page.reload", { ignoreCache: true });
  await waitFor(`document.readyState==="complete"`);
  await waitFor(`window.storyAudioAppState.productionProjection?.canonical_task?.task_type==="COMPLETE"`, 20000);
  await evaluate(`setAppRoute("assignment")`);
  await waitFor(`window.storyAudioAppState.currentRoute==="assignment"`);
  await evaluate(`setAppRoute("jobs")`);
  await waitFor(`window.storyAudioAppState.currentRoute==="jobs"`);
  await evaluate(`setAppRoute("audio")`);
  await waitFor(`window.storyAudioAppState.currentRoute==="audio"`);
  await evaluate(`setAppRoute("production")`);
  await waitFor(`window.storyAudioAppState.productionProjection?.canonical_task?.task_type==="COMPLETE"`);
  await delay(2600);
  const finalState = await evaluate(`({
    task: window.storyAudioAppState.productionProjection?.canonical_task?.task_type,
    route: location.hash,
    state: document.querySelector("#productionStateCard")?.dataset.productionState,
    selected: window.storyAudioAppState.audioLibrary.selectedArtifactId || null,
    noMojibake: !/[ÃÂÆ]/.test(document.body.innerText),
    buttonsNamed: [...document.querySelectorAll("button")].every(button => button.textContent.trim() || button.getAttribute("aria-label")),
    disabledProgrammatic: [...document.querySelectorAll("button:disabled")].every(button => button.disabled === true),
    hiddenPrimary: !document.querySelector("#productionPrimaryAction") || document.querySelector("#productionPrimaryAction").getBoundingClientRect().bottom <= innerHeight
  })`);
  evidence.accessibility = {
    buttonsNamed: finalState.buttonsNamed,
    disabledProgrammatic: finalState.disabledProgrammatic,
    primaryInViewport: finalState.hiddenPrimary,
    noMojibake: finalState.noMojibake,
  };
  if (!finalState.buttonsNamed || !finalState.disabledProgrammatic || !finalState.hiddenPrimary) {
    throw new Error(`Accessibility/interaction check failed: ${JSON.stringify(finalState)}`);
  }
  if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);

  await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  const desktop = await evaluate(`({horizontal:document.documentElement.scrollWidth>innerWidth+1,primaryVisible:!document.querySelector("#productionPrimaryAction")||document.querySelector("#productionPrimaryAction").getBoundingClientRect().top<innerHeight})`);
  if (desktop.horizontal || !desktop.primaryVisible) throw new Error(`1920 layout failed: ${JSON.stringify(desktop)}`);
  evidence.layout1920 = desktop;
  evidence.newPlan = newPlan;
  evidence.ok = true;
  process.stdout.write(JSON.stringify(evidence));
} finally {
  try { socket?.close(); } catch {}
  child.kill();
}
