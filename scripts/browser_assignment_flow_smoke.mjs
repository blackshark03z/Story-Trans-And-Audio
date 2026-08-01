import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";

const baseUrl = process.argv[2];
if (!baseUrl) throw new Error("Usage: node scripts/browser_assignment_flow_smoke.mjs <base-url>");

const browserExe = [
  process.env.STORY_AUDIO_BROWSER_EXE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");

const testRoot = process.env.STORY_AUDIO_ASSIGNMENT_TEST_ROOT;
if (!testRoot) throw new Error("STORY_AUDIO_ASSIGNMENT_TEST_ROOT is required.");
const profile = await mkdtemp(join(testRoot, "browser-"));
const child = spawn(browserExe, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--remote-debugging-port=0",
  `--user-data-dir=${profile}`,
  `${baseUrl}/#/assignment?book=1&from=1&to=10&skip_completed=1`,
], { stdio: "ignore" });

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function poll(callback, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const value = await callback();
      if (value) return value;
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
    (await readFile(join(profile, "DevToolsActivePort"), "utf8")).split(/\r?\n/)[0]
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
      browserErrors.push(
        message.params?.exceptionDetails?.exception?.description
        || message.params?.exceptionDetails?.text
        || "runtime exception"
      );
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
    const result = await send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    }
    return result.result.value;
  };
  const waitFor = (expression, timeoutMs = 15000) => poll(
    async () => (await evaluate(expression)) || null,
    timeoutMs,
  );
  const click = selector => evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) throw new Error(${JSON.stringify(`Missing ${selector}`)});
    el.click();
    return true;
  })()`);
  const setSelect = (selector, value) => evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) throw new Error(${JSON.stringify(`Missing ${selector}`)});
    el.value = ${JSON.stringify(value)};
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  })()`);

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1366,
    height: 768,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await waitFor(`document.readyState === "complete"`);
  await waitFor(`window.storyAudioAppState && document.querySelector('[data-speaker-suggestion-card]')`);

  const initial = await evaluate(`(() => {
    const review = document.querySelector('[data-assignment-section="review"]');
    const voices = document.querySelector('[data-assignment-section="voices"]');
    const steps = [...document.querySelectorAll('.assignment-workflow-steps > div')].map(row => row.innerText);
    return {
      hash: location.hash,
      steps,
      reviewOpen: !!review?.open,
      voicesOpen: !!voices?.open,
      sectionsSeparate: !!review && !!voices && review !== voices,
      unresolvedNotice: !!document.querySelector('[data-jump-to-speaker-review]'),
      unresolvedVoiceRows: [...document.querySelectorAll('[data-voice-library-row]')].filter(row => row.getAttribute('data-voice-library-row').startsWith('unresolved-dialogue:')).length,
      characterRows: document.querySelectorAll('[data-voice-library-row^="character:"]').length,
      preflightPrimaryCount: document.querySelectorAll('[data-open-production-preflight]').length,
      sectionTwoPreflightPrimaryCount: voices?.querySelectorAll('[data-open-production-preflight]').length || 0,
      sectionTwoConditionLink: voices?.querySelector('[data-jump-to-assignment-preflight]')?.textContent || '',
    };
  })()`);

  await evaluate(`(() => {
    const voices = document.querySelector('[data-assignment-section="voices"]');
    voices.open = true;
    return true;
  })()`);
  await setSelect('[data-speaker-review-filter="confidence"]', "HIGH");
  const filterBeforeJump = await evaluate(`document.querySelector('[data-speaker-review-filter="confidence"]').value`);
  await click('[data-jump-to-speaker-review]');
  const unresolvedNavigation = await waitFor(`(() => {
    const review = document.querySelector('[data-assignment-section="review"]');
    const active = document.activeElement;
    return review?.open && !!active?.closest('[data-speaker-suggestion-card]');
  })()`);
  const navigationState = await evaluate(`({
    hash: location.hash,
    filter: document.querySelector('[data-speaker-review-filter="confidence"]')?.value,
    activeCard: document.activeElement?.closest('[data-speaker-suggestion-card]')?.dataset?.speakerSuggestionCard || null,
  })`);

  const key = await evaluate(`document.querySelector('[data-speaker-suggestion-card]')?.dataset?.speakerSuggestionCard`);
  await click(`[data-speaker-suggestion-submit="${key}"]`);
  try {
    await waitFor(`document.querySelector('.assignment-workflow-steps > div:first-child')?.classList.contains('complete')
      && document.querySelector('[data-assignment-section="voices"]')?.open
      && !document.querySelector('[data-voice-library-row^="unresolved-dialogue:"]')`, 20000);
  } catch (error) {
    const diagnostic = await evaluate(`({
      steps: document.querySelector('.assignment-workflow-steps')?.innerText || '',
      voicesOpen: !!document.querySelector('[data-assignment-section="voices"]')?.open,
      unresolvedRows: document.querySelectorAll('[data-voice-library-row^="unresolved-dialogue:"]').length,
      registryStatus: window.storyAudioAppState?.bookVoiceRegistry?.status,
      commandActive: !!window.storyAudioAppState?.productionCommand?.active,
    })`);
    throw new Error(`${error.message} ${JSON.stringify(diagnostic)}`);
  }
  const reviewCompletion = await evaluate(`(() => {
    const rows = [...document.querySelectorAll('[data-voice-library-row="character:25"]')];
    return {
      reviewComplete: document.querySelector('.assignment-workflow-steps > div:first-child')?.classList.contains('complete'),
      voiceEmphasized: document.querySelector('[data-assignment-section="voices"]')?.classList.contains('is-current'),
      voiceOpen: document.querySelector('[data-assignment-section="voices"]')?.open,
      characterRows: rows.length,
      unresolvedRows: document.querySelectorAll('[data-voice-library-row^="unresolved-dialogue:"]').length,
    };
  })()`);

  await waitFor(`!window.storyAudioAppState.productionCommand?.active
    && !window.storyAudioAppState.bookVoiceRegistry?.loading
    && !window.storyAudioAppState.bookVoiceRegistry?.speakerSuggestions?.loading`);
  await evaluate(`Promise.all([
    loadBookVoiceRegistry(),
    loadSpeakerReviewSuggestions(),
    loadProductionTaskProjection({ silent: true }),
  ])`);

  const pollingStability = await evaluate(`(async () => {
    const voice = document.querySelector('[data-registry-voice-key="character:25"]');
    const scope = document.querySelector('[data-registry-scope-key="character:25"]');
    if (!voice || !scope) throw new Error('Character voice controls missing after review completion');
    scope.value = 'range';
    scope.dispatchEvent(new Event('change', { bubbles: true }));
    voice.value = 'commander';
    voice.dispatchEvent(new Event('change', { bubbles: true }));
    voice.focus();
    const node = voice;
    const scopeNode = scope;
    const scrollBefore = window.scrollY;
    for (let index = 0; index < 3; index += 1) await loadJobs();
    return {
      sameVoiceNode: document.querySelector('[data-registry-voice-key="character:25"]') === node,
      sameScopeNode: document.querySelector('[data-registry-scope-key="character:25"]') === scopeNode,
      focused: document.activeElement === node,
      voice: node.value,
      scope: scopeNode.value,
      sectionOpen: document.querySelector('[data-assignment-section="voices"]')?.open,
      scrollStable: Math.abs(window.scrollY - scrollBefore) <= 1,
      impact: document.querySelector('[data-registry-impact="character:25"]')?.innerText || '',
    };
  })()`);

  await click('[data-registry-apply="character:25"]');
  await waitFor(`!window.storyAudioAppState.productionCommand?.active
    && !window.storyAudioAppState.bookVoiceRegistry?.loading`, 20000);
  const voiceSaveState = await evaluate(`({
    command: window.storyAudioAppState.productionCommand,
    rowError: window.storyAudioAppState.bookVoiceRegistry?.rowErrors?.['character:25'] || null,
    rowResult: window.storyAudioAppState.bookVoiceRegistry?.rowResults?.['character:25'] || null,
    preflightEnabled: !!document.querySelector('[data-open-production-preflight]:not([disabled])'),
    commands: null,
  })`);
  voiceSaveState.commands = await evaluate(`fetch('/api/fixture/commands').then(response => response.json())`);
  if (!voiceSaveState.preflightEnabled) {
    throw new Error(`Voice save did not unlock preflight: ${JSON.stringify(voiceSaveState)}`);
  }

  const commandsBeforePreflight = await evaluate(`fetch('/api/fixture/commands').then(response => response.json())`);
  await click('[data-open-production-preflight]:not([disabled])');
  await waitFor(`location.hash.startsWith("#/production")`);
  const readyNavigation = await evaluate(`({
    hash: location.hash,
    workingContext: window.storyAudioAppState.productionWorkingContext,
  })`);
  const commandsAfterPreflight = await evaluate(`fetch('/api/fixture/commands').then(response => response.json())`);

  const repairBlocked = await evaluate(`(() => {
    const chapter={id:1001,number:1,title:'Chapter 1'};
    const details=[
      {code:'SPEAKER_DRAFT_NOT_APPROVED',title:'Bản xác định người nói mới nhất chưa được duyệt',explanation:'Cần xác nhận ai đang nói trước khi tạo bản audio thay thế.',action_label:'Duyệt người nói Chương 1',target:'assignment',assignment_focus:'review',technical_reason:'Latest Speaker Draft is not approved.'},
      {code:'VOICE_MAP_NOT_READY',title:'Chương 1 chưa có bản đồ giọng cuối cùng',explanation:'Cần hoàn tất người nói và giọng hiệu lực trước khi PREPARE bản thay thế.',action_label:'Hoàn tất giọng cho Chương 1',target:'assignment',assignment_focus:'voices',technical_reason:'Final Voice Map is missing.'},
    ];
    const phases=['Xác nhận nội dung và người nói','Hoàn tất cấu hình giọng','Chuẩn bị bản thay thế','Render bản thay thế','Nghe và duyệt bản mới'].map((label,index)=>({number:index+1,key:'repair-'+(index+1),label,current:index===0,complete:false,locked:index>0,state:index===0?'current':'locked',summary:index===0?'Đang thực hiện':'Sẽ thực hiện sau'}));
    const task={task_scope:'chapter',task_type:'REPAIR_REQUIRED',task_key:'chapter:1001:REPAIR_REQUIRED:artifact:39:plan:0',user_stage:5,title:'Cần sửa và tạo bản thay thế',summary:'Chương 1 có audio bị từ chối.',affected_chapter:chapter,primary_action:null,blocker:'Latest Speaker Draft is not approved.',next_task_hint:'Hoàn tất đầu vào.',technical_details:['artifact_id:39'],current_stage_key:'repair',input_summary:{},speaker:null,casting:null,range_prepare:null,render:null,qa:null,repair:{chapter_id:1001,artifact_id:39,job_id:14,duration_ms:294040,created_at:'2026-01-01T00:00:00Z',qa_note:'Đổi giọng narrator',qa_recorded_at:'2026-01-02T00:00:00Z',active_text_revision_id:3977,current_casting_plan_id:null,current_casting_plan_revision:null,current_casting_plan_status:null,prepare_ready:false,input_blockers:details.map(item=>item.technical_reason),input_blocker_details:details,effective_voice_map:[],voice_map_diff:[]}};
    window.__repairProjection={range_identity:'book:1:1-1',task_scope:'chapter',task_type:'REPAIR_REQUIRED',task_key:task.task_key,user_stage:5,title:task.title,summary:task.summary,task_title:task.title,task_summary:task.summary,affected_chapter:chapter,chapter_queue:[{chapter_id:1001,chapter_number:1,title:'Chapter 1',status:'current',state:'REPAIR_REQUIRED',user_stage:5,task_type:'REPAIR_REQUIRED',task_key:task.task_key,canonical_task:true,inspected:false}],queue:[],primary_action:null,secondary_actions:[],secondary_links:[],blocker:task.blocker,range_readiness:{scope:{book_id:1,from_chapter:1,to_chapter:1},summary:{}},next_task_hint:'',next_task_after_success:'',technical_details:task.technical_details,range_task:false,current_stage_key:'repair',conceptual_state:'REPAIR_REQUIRED',input_summary:{},phases,canonical_task:task,inspected_chapter:null,inspection_summary:null};
    state.productionRange={bookId:1,fromChapter:1,toChapter:1,skipCompleted:false};
    state.productionProjection=window.__repairProjection;
    state.productionRepair={taskKey:null,mode:null};
    setAppRoute('production');renderProductionShell();
    return {heading:document.querySelector('#productionCurrentStepHeading')?.textContent,badge:document.querySelector('#productionStateBadge')?.textContent,blockers:[...document.querySelectorAll('[data-repair-blocker]')].map(card=>card.innerText),sequence:[...document.querySelectorAll('.production-repair-sequence li')].map(item=>item.innerText),prepareEnabled:!!document.querySelector('#repairPrepare:not([disabled])'),qaControlsHidden:document.querySelector('#productionQaActions')?.classList.contains('hidden')};
  })()`);

  await click('[data-repair-blocker-action="0"]');
  await waitFor(`location.hash.startsWith('#/assignment?') && location.hash.includes('from=1') && location.hash.includes('to=1') && location.hash.includes('assignment_focus=review')`);
  await waitFor(`document.querySelector('[data-assignment-section="review"]')`);
  const speakerRepairNavigation = await evaluate(`({hash:location.hash,reviewOpen:document.querySelector('[data-assignment-section="review"]')?.open,returnTask:window.storyAudioAppState.productionWorkingContext?.returnTask,scope:document.querySelector('#assignmentScope')?.textContent})`);

  await evaluate(`(() => { state.productionProjection=window.__repairProjection; state.productionRange={bookId:1,fromChapter:1,toChapter:1,skipCompleted:false}; setAppRoute('production'); renderProductionShell(); return true })()`);
  await click('[data-repair-blocker-action="1"]');
  await waitFor(`location.hash.startsWith('#/assignment?') && location.hash.includes('assignment_focus=voices')`);
  await waitFor(`document.querySelector('[data-assignment-section="voices"]')`);
  const voiceRepairNavigation = await evaluate(`({hash:location.hash,voicesOpen:document.querySelector('[data-assignment-section="voices"]')?.open,returnTask:window.storyAudioAppState.productionWorkingContext?.returnTask,returnLabel:document.querySelector('[data-open-production-preflight]')?.textContent,unresolvedVoiceRows:document.querySelectorAll('[data-voice-library-row^="unresolved-dialogue:"]').length})`);

  const repairReady = await evaluate(`(() => {
    const projection=JSON.parse(JSON.stringify(window.__repairProjection)),task=projection.canonical_task;
    task.repair.input_blockers=[];task.repair.input_blocker_details=[];task.repair.prepare_ready=true;task.blocker=null;projection.blocker=null;
    projection.phases=projection.phases.map((phase,index)=>({...phase,current:index===2,complete:index<2,locked:index>2,state:index<2?'complete':index===2?'current':'locked'}));
    state.productionProjection=projection;state.productionRepair={taskKey:null,mode:null};state.productionRange={bookId:1,fromChapter:1,toChapter:1,skipCompleted:false};setAppRoute('production');renderProductionShell();
    return {blockers:document.querySelectorAll('[data-repair-blocker]').length,nextAction:document.querySelector('#repairSameData')?.textContent,prepareButton:!!document.querySelector('#repairPrepare'),commandsBefore:0};
  })()`);
  await waitFor(`(() => { const button=document.querySelector('#repairSameData'); if(!button)return false; button.click(); return true; })()`);
  const replacementPreflight = await waitFor(`(() => {
    const heading=document.querySelector('.production-repair-same-data h3')?.textContent;
    if(window.storyAudioAppState.productionRepair.mode !== "same_data" || !heading)return null;
    return {mode:window.storyAudioAppState.productionRepair.mode,heading,pins:document.querySelector('.production-repair-pins')?.innerText,prepareDisabled:document.querySelector('#repairPrepare')?.disabled};
  })()`);
  const commandsAfterRepairChecks = await evaluate(`fetch('/api/fixture/commands').then(response => response.json())`);

  if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);
  process.stdout.write(JSON.stringify({
    ok: true,
    initial,
    filterBeforeJump,
    unresolvedNavigation: !!unresolvedNavigation,
    navigationState,
    reviewCompletion,
    pollingStability,
    voiceSaveState,
    readyNavigation,
    commandsBeforePreflight,
    commandsAfterPreflight,
    repairBlocked,
    speakerRepairNavigation,
    voiceRepairNavigation,
    repairReady,
    replacementPreflight,
    repairCheckCommands: commandsAfterRepairChecks.slice(commandsAfterPreflight.length),
    renderCommands: commandsAfterPreflight.filter(command => /PREPARE|START_RENDER/.test(command.command_type || "")),
  }));
} finally {
  try {
    socket?.close();
  } catch {}
  const browserExited = new Promise(resolve => {
    if (child.exitCode !== null) resolve();
    else child.once("exit", resolve);
  });
  child.kill();
  await Promise.race([browserExited, delay(3000)]);
  let cleanupError = null;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      await rm(profile, { recursive: true, force: true });
      cleanupError = null;
      break;
    } catch (error) {
      cleanupError = error;
      if (!["EBUSY", "EPERM"].includes(error?.code) || attempt === 29) break;
      await delay(200);
    }
  }
  if (cleanupError) {
    process.stderr.write(`Warning: disposable browser profile cleanup deferred: ${cleanupError.message}\n`);
  }
}
