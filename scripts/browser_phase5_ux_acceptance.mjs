import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const baseUrl = process.argv[2];
const evidenceDir = process.argv[3] || process.env.STORY_AUDIO_PHASE5_EVIDENCE_DIR || null;
if (!baseUrl) throw new Error("Usage: node scripts/browser_phase5_ux_acceptance.mjs <base-url> [evidence-dir]");

const browserExe = [
  process.env.STORY_AUDIO_BROWSER_EXE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");

const profile = await mkdtemp(join(tmpdir(), "story-audio-phase5-browser-"));
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
    if (message.method === "Runtime.consoleAPICalled" && message.params?.type === "error") browserErrors.push((message.params.args || []).map(item => item.value || item.description).join(" "));
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

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
  await waitFor(`document.readyState==="complete"`);
  await waitFor(`window.storyAudioAppState&&document.querySelector("#productionTaskWorkspace")`);
  await evaluate(`(()=>{
    window.__phase5MutationCalls=[];
    const originalApi=api;
    api=async(path,options={})=>{
      const method=String(options?.method||'GET').toUpperCase();
      if(method!=='GET'){
        window.__phase5MutationCalls.push({path:String(path),method});
        throw new Error('PHASE5_READ_ONLY_FIXTURE_BLOCKED_MUTATION');
      }
      return originalApi(path,options);
    };
    loadProductionTaskProjection=async()=>state.productionProjection;
    history.replaceState(null,'','#/production?book=91&from=401&to=401');
    state.currentRoute='production';
    return true;
  })()`);

  const show = async (taskType, width = 1366, height = 768) => {
    await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
    return evaluate(`(()=>{
      const taskType=${JSON.stringify(taskType)};
      const viewportWidth=${JSON.stringify(width)},viewportHeight=${JSON.stringify(height)};
      const chapter={id:9101,number:401,title:'Chương kiểm thử'};
      const repair={chapter_id:9101,artifact_id:9901,job_id:9001,duration_ms:60000,created_at:'2026-09-03T08:00:00Z',qa_note:'Đoạn mở đầu bị lặp chữ và nhịp kể quá chậm.',qa_recorded_at:'2026-09-03T09:00:00Z',qa_evidence_id:77,active_text_revision_id:401,current_casting_plan_id:51,current_casting_plan_revision:3,current_casting_plan_status:'approved',prepare_ready:false,input_blockers:[],effective_voice_map:[{speaker_name:'Người kể chuyện',voice_name:'Giọng kiểm thử',line_count:12,assignment_source:'book_default',available:true}],voice_map_diff:[],repair_plan:null,repair_draft:null,repair_draft_review:null};
      const qa={chapter_id:9101,artifact_id:9901,job_id:9001,human_qa_status:null,duration_ms:60000,size_bytes:2048,created_at:'2026-09-03T08:00:00Z',replacement:false,previous_artifact:null,repair_goals:{}};
      const currentStageKey=taskType==='REPAIR_REQUIRED'?'repair':taskType==='HUMAN_QA'?'qa':'complete';
      const section={speaker:null,casting:null,range_prepare:null,render:null,qa:taskType==='HUMAN_QA'?qa:null,repair:taskType==='REPAIR_REQUIRED'?repair:null};
      const canonical={task_scope:'chapter',task_type:taskType,task_key:'chapter:9101:'+taskType,user_stage:5,title:taskType==='HUMAN_QA'?'Nghe và duyệt':taskType==='REPAIR_REQUIRED'?'Sửa audio':'Hoàn tất',summary:'Trạng thái fixture chỉ đọc.',affected_chapter:chapter,primary_action:null,blocker:null,next_task_hint:'',technical_details:['artifact_id:9901','revision_id:401','evidence_id:77'],current_stage_key:currentStageKey,...section};
      const readiness={scope:{book_id:91,from_chapter:401,to_chapter:401},summary:{total:1,complete:taskType==='COMPLETE'?1:0},chapters:[{chapter_id:9101,chapter_number:401,title:chapter.title,state:taskType,active_artifact_id:9901}]};
      state.book={id:91,title:'Sách kiểm thử cô lập'};
      state.currentRoute='production';history.replaceState(null,'','#/production?book=91&from=401&to=401');
      state.dialog={chapter:{id:9101,book_id:91,chapter_number:401,title:chapter.title,audio_status:'completed'},revisions:[],qa_issues:[],active_output:{active_output_job_id:9001,active_output_artifact_id:9901},audio_artifact:{id:9901,duration_ms:60000,actual_size_bytes:2048},human_approval:null};
      state.casting=null;state.speakerReview=null;state.productionPreflight=null;state.productionQaNoteDraft='';state.productionQaComparisonArtifactId=null;state.productionRepair={taskKey:null,mode:null,markers:[]};
      state.productionRange={bookId:91,fromChapter:401,toChapter:401,chapterId:9101,skipCompleted:false,readiness};
      state.productionProjection={range_identity:'book:91:401-401',task_scope:'chapter',task_type:taskType,task_key:canonical.task_key,user_stage:5,title:canonical.title,summary:canonical.summary,task_title:canonical.title,task_summary:canonical.summary,affected_chapter:chapter,chapter_queue:[{chapter_id:9101,chapter_number:401,title:chapter.title,status:'current',state:taskType,user_stage:5,task_type:taskType,task_key:canonical.task_key,canonical_task:true,inspected:false}],queue:[],primary_action:null,secondary_actions:[],secondary_links:[],blocker:null,range_readiness:readiness,next_task_hint:'',next_task_after_success:'',technical_details:canonical.technical_details,range_task:false,current_stage_key:currentStageKey,conceptual_state:taskType,canonical_task:canonical,inspected_chapter:null,inspection_summary:null};
      state.runtimeIdentity={state:'isolated',label:'Dữ liệu kiểm thử'};state.runtimeIdentityResolved=true;
      const toast=document.querySelector('#toast');if(toast){toast.textContent='';toast.className='toast hidden'}
      const taskContent=document.querySelector('#productionTaskContent');if(taskContent)taskContent.dataset.productionTaskKey='';
      renderProductionShell();
      window.scrollTo(0,0);
      const visible=element=>!!element&&getComputedStyle(element).display!=='none'&&element.getBoundingClientRect().width>0&&element.getBoundingClientRect().height>0;
      const text=taskContent?.innerText||'',qaActions=document.querySelector('#productionQaActions'),player=document.querySelector('#productionQaAudio'),decision=document.querySelector('.production-result-note'),technical=document.querySelector('#productionTechnicalDetails'),repairDetails=document.querySelector('.owner-advanced-details'),primary=document.querySelector('#productionPrimaryAction'),download=document.querySelector('#ownerCompleteDownload');
      const playerRect=player?.getBoundingClientRect(),decisionRect=decision?.getBoundingClientRect(),qaRect=qaActions?.getBoundingClientRect();
      return{taskType,width:viewportWidth,height:viewportHeight,stage:document.querySelector('#productionStateBadge')?.textContent.trim(),heading:document.querySelector('#productionCurrentStepHeading')?.textContent.trim(),text,playerVisible:visible(player),qaActionsVisible:visible(qaActions),qaActionsAfterContext:!!(playerRect&&decisionRect&&qaRect&&qaRect.top>=playerRect.bottom&&qaRect.top>=decisionRect.bottom),qaLabels:[...document.querySelectorAll('#productionQaActions button')].filter(visible).map(item=>item.textContent.trim()),technicalOpen:!!technical?.open,repairDetailsOpen:!!repairDetails?.open,problemBeforePlan:text.indexOf('Ghi chú QA')>=0&&text.indexOf('Ghi chú QA')<text.indexOf('Xem kế hoạch sửa'),repairAction:document.querySelector('#repairOpenPlan')?.textContent.trim()||null,historyVisible:text.includes('Bản cũ được giữ nguyên'),rawTechnicalVisible:/Revision 401|Artifact #?9901|evidence_id:77/.test(text),completePrimaryVisible:visible(primary),completePrimaryLabel:primary?.textContent.trim()||null,downloadVisible:visible(download),downloadHref:download?.getAttribute('href')||null,legacyVisible:['#flowView','#productionLegacyJobPanel','#preRenderConfigurationPanel'].some(selector=>visible(document.querySelector(selector))),horizontal:document.documentElement.scrollWidth>innerWidth+1,mutations:window.__phase5MutationCalls.slice()};
    })()`);
  };

  const humanQa = await show("HUMAN_QA");
  const humanQaScreenshot = await screenshot("phase5-human-qa-1366x768");
  const emptyNeedsFix = await evaluate(`(()=>{document.querySelector('#productionQaNote').value='';document.querySelector('#productionQaNeedsFixes').click();return{toast:document.querySelector('#toast')?.textContent||document.querySelector('.toast')?.textContent||'',mutations:window.__phase5MutationCalls.slice()}})()`);
  const repairRequired = await show("REPAIR_REQUIRED");
  const repairScreenshot = await screenshot("phase5-repair-required-1366x768");
  const complete = await show("COMPLETE");
  const completeScreenshot = await screenshot("phase5-complete-1366x768");
  const completeNavigation = await evaluate(`(()=>{ensureAudioLibraryLoaded=()=>{};document.querySelector('#productionPrimaryAction').click();return{route:state.currentRoute,hash:window.location.hash,mutations:window.__phase5MutationCalls.slice()}})()`);
  const narrow = {
    humanQa: await show("HUMAN_QA", 820, 900),
    repairRequired: await show("REPAIR_REQUIRED", 820, 900),
    complete: await show("COMPLETE", 820, 900),
  };

  if (humanQa.stage !== "Giai đoạn 5 / 5" || !humanQa.playerVisible || !humanQa.qaActionsVisible || !humanQa.qaActionsAfterContext || humanQa.qaLabels.join("|") !== "Cần sửa|Chấp nhận" || humanQa.technicalOpen || humanQa.legacyVisible) throw new Error(`HUMAN_QA failed: ${JSON.stringify(humanQa)}`);
  if (!emptyNeedsFix.toast.includes("ghi chú") || emptyNeedsFix.mutations.length) throw new Error(`HUMAN_QA note gate failed: ${JSON.stringify(emptyNeedsFix)}`);
  if (repairRequired.stage !== "Giai đoạn 5 / 5" || !repairRequired.problemBeforePlan || repairRequired.repairAction !== "Xem kế hoạch sửa" || !repairRequired.historyVisible || repairRequired.technicalOpen || repairRequired.repairDetailsOpen || repairRequired.rawTechnicalVisible || repairRequired.legacyVisible || repairRequired.mutations.length) throw new Error(`REPAIR_REQUIRED failed: ${JSON.stringify(repairRequired)}`);
  if (complete.stage !== "Giai đoạn 5 / 5" || !complete.completePrimaryVisible || complete.completePrimaryLabel !== "Mở audio đã hoàn tất" || !complete.downloadVisible || complete.downloadHref !== "/api/artifacts/9901/file" || complete.legacyVisible || complete.mutations.length || completeNavigation.route !== "audio" || !completeNavigation.hash.includes("#/audio?book=91&from=401&to=401") || completeNavigation.mutations.length) throw new Error(`COMPLETE failed: ${JSON.stringify({complete,completeNavigation})}`);
  if ([humanQa, repairRequired, complete, ...Object.values(narrow)].some(item => item.horizontal)) throw new Error(`Responsive layout failed: ${JSON.stringify(narrow)}`);
  if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);

  process.stdout.write(JSON.stringify({ok:true,humanQa,emptyNeedsFix,repairRequired,complete,completeNavigation,narrow:{humanQa:{horizontal:narrow.humanQa.horizontal},repairRequired:{horizontal:narrow.repairRequired.horizontal},complete:{horizontal:narrow.complete.horizontal}},screenshots:{humanQa:humanQaScreenshot,repairRequired:repairScreenshot,complete:completeScreenshot}}));
} finally {
  try { socket?.close(); } catch {}
  const browserExited = new Promise(resolve => child.exitCode !== null ? resolve() : child.once("exit", resolve));
  child.kill();
  await Promise.race([browserExited, delay(3000)]);
  let cleanupError = null;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try { await rm(profile, { recursive: true, force: true }); cleanupError = null; break; }
    catch (error) { cleanupError = error; if (!["EBUSY", "EPERM"].includes(error?.code) || attempt === 29) break; await delay(200); }
  }
  if (cleanupError) process.stderr.write(`Warning: disposable browser profile cleanup deferred: ${cleanupError.message}\n`);
}
