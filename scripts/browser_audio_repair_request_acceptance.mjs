import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const baseUrl = process.argv[2];
const evidenceDir = process.argv[3] || null;
if (!baseUrl) throw new Error("Usage: node scripts/browser_audio_repair_request_acceptance.mjs <base-url> [evidence-dir]");

const browserExe = [
  process.env.STORY_AUDIO_BROWSER_EXE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");

const profile = await mkdtemp(join(tmpdir(), "story-audio-repair-request-browser-"));
const child = spawn(browserExe, [
  "--headless=new",
  "--disable-gpu",
  "--disable-breakpad",
  "--disable-crash-reporter",
  "--no-first-run",
  "--no-default-browser-check",
  "--remote-debugging-port=0",
  `--user-data-dir=${profile}`,
  `${baseUrl}/#/audio?book=1&from=2&to=2&focus=102`,
], { stdio: "ignore" });

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function poll(callback, timeoutMs = 12000) {
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
    if (message.method === "Runtime.exceptionThrown") browserErrors.push(message.params?.exceptionDetails?.exception?.description || message.params?.exceptionDetails?.text || "runtime exception");
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
  const waitFor = (expression, timeoutMs = 10000) => poll(async () => (await evaluate(expression)) || null, timeoutMs);
  const screenshot = async name => {
    if (!evidenceDir) return null;
    await mkdir(evidenceDir, { recursive: true });
    const capture = await send("Page.captureScreenshot", { format: "png", fromSurface: true, captureBeyondViewport: false });
    const path = join(evidenceDir, `${name}.png`);
    await writeFile(path, Buffer.from(capture.data, "base64"));
    return path;
  };
  const inspect = () => evaluate(`(()=>{
    const visible=element=>!!element&&getComputedStyle(element).display!=='none'&&!element.classList.contains('hidden');
    const choices=[...document.querySelectorAll('.automated-audio-qa-repair-choice input')];
    return {
      choiceCount:choices.length,
      selectedCount:choices.filter(item=>item.checked).length,
      perFindingCreateCount:[...document.querySelectorAll('.automated-audio-qa-point-row button')].filter(item=>/Tạo bản sửa thử|Đưa vào yêu cầu sửa/.test(item.textContent)).length,
      cta:document.querySelector('#automatedAudioQaCreateRepairRequest')?.textContent.trim()||'',
      barVisible:visible(document.querySelector('#automatedAudioQaRepairBar')),
      horizontal:document.documentElement.scrollWidth>innerWidth+1,
    };
  })()`);

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
  await waitFor(`document.readyState==='complete'`);
  await waitFor(`document.querySelectorAll('.automated-audio-qa-repair-choice input').length===4`);
  await evaluate(`(()=>{window.__repairRequestMutations=[];const originalApi=api;api=async(path,options={})=>{const method=String(options?.method||'GET').toUpperCase();if(method!=='GET')window.__repairRequestMutations.push({path:String(path),method});return originalApi(path,options)};return true})()`);

  const desktop = await inspect();
  await evaluate(`document.querySelector('.automated-audio-qa-repair-choice input').click()`);
  const afterDeselect = await inspect();
  await evaluate(`(()=>{document.querySelector('#audioQaRepeatedWords').checked=true;document.querySelector('#audioQaReplacementSpeed').value='1.5';return true})()`);
  await evaluate(`document.querySelector('#automatedAudioQaCreateRepairRequest').click()`);
  await waitFor(`document.querySelector('#audioQaRepairDetails')?.open&&document.querySelector('#audioQaNote')?.value.includes('đã gom 3 điểm')`);
  const review = await evaluate(`(()=>({
    detailsOpen:!!document.querySelector('#audioQaRepairDetails')?.open,
    noteFindingCount:(document.querySelector('#audioQaNote')?.value.match(/^- /gm)||[]).length,
    markerText:document.querySelector('#audioQaMarkerList')?.textContent||'',
    manualRepeatedPreserved:!!document.querySelector('#audioQaRepeatedWords')?.checked,
    manualSpeedPreserved:document.querySelector('#audioQaReplacementSpeed')?.value||'',
    boundMarkerCount:(state.audioQa?.markers||[]).length,
    automaticMarkerCount:(state.audioQa?.markers||[]).filter(marker=>marker.repair_kind).length,
    allMarkersHaveSegmentSha:(state.audioQa?.markers||[]).every(marker=>/^[0-9a-f]{64}$/.test(marker.segment_audio_sha256||'')),
    mutations:window.__repairRequestMutations,
  }))()`);
  const desktopPath = await screenshot("audio-repair-request-desktop");

  await send("Emulation.setDeviceMetricsOverride", { width: 700, height: 900, deviceScaleFactor: 1, mobile: false });
  await evaluate(`document.querySelector('#automatedAudioQaRepairBar')?.scrollIntoView({block:'center'})`);
  const narrow = await inspect();
  const narrowPath = await screenshot("audio-repair-request-narrow");
  await send("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
  await evaluate(`(()=>{
    const item=selectedAudioLibraryItem(),markers=(state.audioQa.markers||[]).map(marker=>({timestamp_seconds:marker.timestamp,segment_id:marker.segment_id,segment_audio_sha256:marker.segment_audio_sha256,risk_kind:marker.risk_kind,repair_kind:marker.repair_kind,machine_finding_key:marker.machine_finding_key,issue:repairIssueFromRisk(marker.risk_kind),note:marker.note||'',nearest_utterance:'',local_pace:null}));
    state.productionRange={bookId:1,fromChapter:2,toChapter:2,chapterId:102,skipCompleted:false};
    state.productionRepair={taskKey:null,mode:'review',markers};
    state.productionProjection={canonical_task:{task_type:'REPAIR_REQUIRED',task_key:'chapter:102:REPAIR_REQUIRED:artifact:5001',user_stage:5,title:'Sửa audio Chương 2',summary:'Yêu cầu sửa đã được lưu. Kiểm tra toàn bộ trước khi chuẩn bị.',task_title:'Sửa audio Chương 2',task_summary:'Yêu cầu sửa đã được lưu. Kiểm tra toàn bộ trước khi chuẩn bị.',current_stage_key:'repair',affected_chapter:{id:102,number:2,title:'Chương 2'},primary_action:null,secondary_links:[],technical_details:[],phases:[],repair:{artifact_id:Number(item.artifact_id),chapter_id:102,qa_evidence_id:9001,qa_note:document.querySelector('#audioQaNote')?.value||'',qa_recorded_at:'2026-09-13T01:40:00+07:00',duration_ms:369000,input_blockers:[],qa_feedback:{repeated_words:true,global_speed_target:1.5,local_pacing_adjustment_required:false,operator_note:document.querySelector('#audioQaNote')?.value||'',position_markers:markers},repair_plan:{},repair_draft:{},repair_draft_review:{},effective_voice_map:[{speaker_name:'Người kể chuyện',voice_name:'Quang Âm Chi Ngoại',available:true,line_count:53}],current_casting_plan_revision:1,current_casting_plan_status:'approved'}},chapter_queue:[],phases:[]};
    setAppRoute('production');renderProductionShell();return true;
  })()`);
  await waitFor(`document.querySelector('#repairConfirmUnified')&&document.querySelectorAll('[data-repair-marker]').length===3`);
  const unifiedDesktop = await evaluate(`(()=>(()=>{const primaries=[...document.querySelectorAll('#productionTaskContent .primary')].filter(el=>getComputedStyle(el).display!=='none');return{route:state.currentRoute,heading:document.querySelector('#productionTaskContent h3')?.textContent.trim()||'',primaryIds:primaries.map(el=>el.id),legacyControls:document.querySelectorAll('#repairOpenPlan,#repairConfirmPlan,#repairApplyPlan,#repairReviewDraft,#repairConfirmDraft').length,markerCount:document.querySelectorAll('[data-repair-marker]').length,stepCount:document.querySelectorAll('.production-repair-sequence li').length,horizontal:document.documentElement.scrollWidth>innerWidth+1}})())()`);
  const unifiedDesktopPath = await screenshot("audio-repair-unified-desktop");
  await send("Emulation.setDeviceMetricsOverride", { width: 700, height: 900, deviceScaleFactor: 1, mobile: false });
  await evaluate(`document.querySelector('#repairConfirmUnified')?.scrollIntoView({block:'center'})`);
  const unifiedNarrow = await evaluate(`(()=>({horizontal:document.documentElement.scrollWidth>innerWidth+1,primaryVisible:!!document.querySelector('#repairConfirmUnified')&&getComputedStyle(document.querySelector('#repairConfirmUnified')).display!=='none'}))()`);
  const unifiedNarrowPath = await screenshot("audio-repair-unified-narrow");
  const unifiedCommit = await evaluate(`(async()=>{
    const originalRun=runProductionCommand,originalRefresh=refreshUnifiedRepairView,calls=[];
    document.querySelector('#repairPlanRepeatedWords').checked=false;
    runProductionCommand=async options=>{
      calls.push(options.commandType);
      const repair=state.productionProjection.canonical_task.repair;
      if(options.commandType==='CONFIRM_REPAIR_PLAN')repair.repair_plan={evidence_id:9101,qa_evidence_id:9001,artifact_id:5001,repeated_words:false,global_speed_target:1.5,local_pacing_adjustment_required:false,operator_note:'fixture'};
      if(options.commandType==='APPLY_REPAIR_PLAN')repair.repair_draft={evidence_id:9102,qa_evidence_id:9001,artifact_id:5001,repair_plan_evidence_id:9101,repeated_words:false,global_speed_target:1.5,local_pacing_adjustment_required:false,position_markers:[...state.productionRepair.markers]};
      if(options.commandType==='CONFIRM_REPAIR_DRAFT'){repair.repair_draft_review={evidence_id:9103,qa_evidence_id:9001,artifact_id:5001,repair_plan_evidence_id:9101,marker_count:state.productionRepair.markers.length,repeated_words:false,global_speed_target:1.5,local_pacing_adjustment_required:false};repair.prepare_ready=true;repair.storage={prepare_allowed:true,free_bytes:50*1024**3,required_free_bytes:10*1024**3}}
      return{outcome:'APPLIED'};
    };
    refreshUnifiedRepairView=async()=>currentProductionViewModel();
    await confirmUnifiedRepair(currentProductionViewModel());
    const result={calls,reviewedHeading:document.querySelector('#productionTaskContent h3')?.textContent.trim()||'',prepareVisible:!!document.querySelector('#repairPrepareReplacement'),confirmVisible:!!document.querySelector('#repairConfirmUnified')};
    runProductionCommand=originalRun;refreshUnifiedRepairView=originalRefresh;return result;
  })()`);
  if (browserErrors.length) throw new Error(`Browser errors: ${JSON.stringify(browserErrors)}`);
  if (!desktop.barVisible || desktop.choiceCount !== 4 || desktop.perFindingCreateCount !== 0 || afterDeselect.selectedCount !== 3 || review.noteFindingCount !== 3 || review.boundMarkerCount !== 3 || review.automaticMarkerCount !== 3 || !review.allMarkersHaveSegmentSha || !review.manualRepeatedPreserved || review.manualSpeedPreserved !== '1.5' || desktop.horizontal || narrow.horizontal || review.mutations.length || unifiedDesktop.route !== 'production' || unifiedDesktop.heading !== 'Kiểm tra toàn bộ bản sửa' || unifiedDesktop.primaryIds.join(',') !== 'repairConfirmUnified' || unifiedDesktop.legacyControls !== 0 || unifiedDesktop.markerCount !== 3 || unifiedDesktop.stepCount !== 4 || unifiedDesktop.horizontal || unifiedNarrow.horizontal || !unifiedNarrow.primaryVisible || unifiedCommit.calls.join(',') !== 'CONFIRM_REPAIR_PLAN,APPLY_REPAIR_PLAN,CONFIRM_REPAIR_DRAFT' || unifiedCommit.reviewedHeading !== 'Đã xác nhận toàn bộ bản sửa' || !unifiedCommit.prepareVisible || unifiedCommit.confirmVisible) throw new Error(`Acceptance failed: ${JSON.stringify({desktop,afterDeselect,review,narrow,unifiedDesktop,unifiedNarrow,unifiedCommit})}`);
  process.stdout.write(JSON.stringify({ ok: true, desktop, afterDeselect, review, narrow, unifiedDesktop, unifiedNarrow, unifiedCommit, screenshots: { desktop: desktopPath, narrow: narrowPath, unifiedDesktop: unifiedDesktopPath, unifiedNarrow: unifiedNarrowPath } }));
} finally {
  if (socket?.readyState === WebSocket.OPEN) socket.close();
  child.kill();
  await Promise.race([
    new Promise(resolve => child.once("exit", resolve)),
    delay(2000),
  ]);
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      await rm(profile, { recursive: true, force: true });
      break;
    } catch (error) {
      if (!["EBUSY", "ENOTEMPTY", "EPERM"].includes(error?.code) || attempt === 29) throw error;
      await delay(200);
    }
  }
}
