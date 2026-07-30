import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const baseUrl = process.argv[2];
if (!baseUrl) throw new Error("Usage: node scripts/browser_production_preflight_smoke.mjs <base-url>");

const browserExe = [
  process.env.STORY_AUDIO_BROWSER_EXE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");

const profile = await mkdtemp(join(tmpdir(), "story-audio-preflight-browser-"));
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

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
  await waitFor(`document.readyState==="complete"`);
  await waitFor(`window.storyAudioAppState&&document.querySelector("#productionTaskWorkspace")`);
  await evaluate(`loadProductionTaskProjection=async()=>{renderProductionShell();return state.productionProjection}`);

  const show = async options => evaluate(`(() => {
    const options=${JSON.stringify(options)};
    const taskType=options.taskType||"PREPARE_RANGE",prepared=taskType==="START_RENDER_RANGE",running=taskType==="MONITOR_RENDER";
    const chapters=[{chapter_id:7001,chapter_number:372,chapter_title:"Chương 372",state:prepared?"PREPARED":running?"RENDERING_OR_PAUSED":"READY_TO_PREPARE"},{chapter_id:7002,chapter_number:373,chapter_title:"Chương 373",state:"READY_TO_PREPARE"}];
    state.productionRange={bookId:8,fromChapter:372,toChapter:373,skipCompleted:true,readiness:{scope:{book_id:8,book_title:"Sách kiểm thử",from_chapter:372,to_chapter:373,chapter_count:2},summary:{total:2,ready_to_prepare:2},chapters}};
    state.jobs=prepared?[{id:81,status:"prepared",total_chapters:2}]:running?[{id:81,status:"running",total_chapters:2,completed_chapters:1,completed_segments:12,failed_segments:0,pending_segments:7}]:[];
    const renderSection=["START_RENDER_RANGE","MONITOR_RENDER"].includes(taskType)?{job_id:81,job_status:prepared?"prepared":"running"}:null;
    const canonical={task_scope:"range",task_type:taskType,task_key:"range:8:372-373:"+taskType,user_stage:4,title:"Kiểm tra trước khi sản xuất",summary:"Xác nhận dữ liệu và hành động tiếp theo.",affected_chapter:null,primary_action:{key:taskType,label:"Canonical",target:taskType==="PREPARE_RANGE"?"prepare":"render"},blocker:null,next_task_hint:"",technical_details:[],current_stage_key:"prepare",speaker:null,casting:null,range_prepare:taskType==="PREPARE_RANGE"?{book_id:8,from_chapter:372,to_chapter:373,chapter_count:2}:null,render:renderSection,qa:null};
    state.productionProjection={range_identity:"book:8:372-373",chapter_queue:chapters.map(row=>({chapter_id:row.chapter_id,chapter_number:row.chapter_number,title:row.chapter_title,status:"ready",state:row.state,user_stage:4,task_type:null,task_key:"ready:"+row.chapter_id,canonical_task:false,inspected:false})),range_readiness:state.productionRange.readiness,phases:[],canonical_task:canonical};
    const blocked=!!options.blocked,voiceUnavailable=!!options.voiceUnavailable,authorized=options.authorized!==false;
    const blocker=blocked||voiceUnavailable?{chapter_id:7002,chapter_number:373,chapter_title:"Chương 373",state:voiceUnavailable?"VOICE_BLOCKED":"SPEAKER_EXCEPTIONS",reason:voiceUnavailable?"Giọng nhân vật không khả dụng.":"Cần xác nhận người nói.",next_task:voiceUnavailable?"ASSIGN_VOICE":"RESOLVE_SPEAKER",action_label:voiceUnavailable?"Gán lại giọng Chương 373":"Xử lý Chương 373",target:voiceUnavailable?"voices":"speakers"}:null;
    const ready=!blocker;
    const checks={
      text:{label:"Văn bản",passed:2,total:2,failed_chapters:[]},
      speaker:{label:"Người nói",passed:blocked?1:2,total:2,failed_chapters:blocked?[373]:[]},
      casting:{label:"Bản đồ giọng",passed:blocked?1:2,total:2,failed_chapters:blocked?[373]:[]},
      voice:{label:"Giọng khả dụng",passed:voiceUnavailable?1:blocked?1:2,total:2,failed_chapters:blocker?[373]:[]},
      conflict:{label:"Job xung đột",passed:2,total:2,failed_chapters:[]},
    };
    const action=taskType==="START_RENDER_RANGE"?{key:"START_RENDER_RANGE",label:"Bắt đầu render phạm vi",target:"render"}:taskType==="MONITOR_RENDER"?{key:"MONITOR_RENDER",label:"Theo dõi render",target:"render"}:!ready?{key:blocker.next_task,label:blocker.action_label,target:blocker.target}:!authorized?{key:"AUTHENTICATE_EXECUTION",label:"Xác thực để chuẩn bị",target:"authentication"}:{key:"PREPARE_RANGE",label:"Chuẩn bị phạm vi",target:"prepare"};
    state.productionPreflight={schema:"story-audio-production-preflight/v1",range:{book:{id:8,title:"Sách kiểm thử"},from_chapter:372,to_chapter:373,selected_chapter_count:2,included_chapters:ready?[{chapter_number:372},{chapter_number:373}]:[{chapter_number:372}],excluded_chapters:blocker?[{chapter_number:373,reason:blocker.reason,reason_codes:["BLOCKED"]}]:[],skip_completed:true},data_readiness:{ready,...checks,ordered_blockers:blocker?[blocker]:[]},effective_voice_map:[{speaker_name:"Người kể chuyện",role:"narrator",effective_voice_name:"Chanlee",assignment_source:"book_default",affected_chapters:[372,373],line_count:38,available:true,warning:null},{speaker_name:"Hứa Thanh",role:"character",effective_voice_name:voiceUnavailable?"Giọng không khả dụng":"Hứa Thanh",assignment_source:"override",affected_chapters:[373],line_count:4,available:!voiceUnavailable,warning:voiceUnavailable?"Giọng đã lưu không còn khả dụng.":null}],execution_readiness:{prepare_allowed:ready&&authorized&&taskType==="PREPARE_RANGE",render_allowed:prepared&&authorized,authorization_ready:authorized,schema_ready:true,kill_switch_clear:true,conflict_free:true,prepared_job:prepared?{job_id:81,status:"prepared",chapter_count:2}:null},execution_preview:{chapter_count:ready?2:1,estimated_segment_count:42,voice_count:2,prepare_effect:"Pins inputs",tts_called:false,next_action:action},technical_details:{range_identity:"book:8:372-373",task_key:canonical.task_key,task_type:taskType,plan_fingerprint:"abc123secretfingerprint",included_chapter_ids:[7001,7002],casting_plan_ids:[91,92],voice_ids:["custom:25","custom:26"],authentication_state:authorized?"AUTH_CONFIGURED":"AUTH_NOT_CONFIGURED",runtime_status:"READY",runtime_reasons:[],voice_warnings:voiceUnavailable?["VOICE_UNAVAILABLE"]:[]}};
    renderProductionShell();
    const primary=document.querySelector("#productionPrimaryAction"),review=document.querySelector("[data-production-preflight]"),details=document.querySelector("#productionTechnicalDetails"),voice=document.querySelector(".production-preflight-table"),verdict=document.querySelector(".production-preflight-verdict"),checklist=document.querySelector(".production-preflight-checklist");
    const rect=element=>{const value=element?.getBoundingClientRect();return value?{top:value.top,bottom:value.bottom,left:value.left,right:value.right,width:value.width,height:value.height}:null};
    const legacy=document.querySelector("#productionLegacyJobPanel");
    return{primary:primary.textContent.trim(),body:review?.innerText||"",detailsOpen:details.open,rawIdsVisible:(review?.innerText||"").includes("custom:")||(review?.innerText||"").includes("abc123"),rawAuthVisible:document.body.innerText.includes("AUTH_CONFIGURED"),legacyVisible:!!legacy&&!legacy.hidden,get legacyInert(){return legacy?.hasAttribute("inert")||false},dialogOpen:document.querySelector("#productionPrepareAuthDialog").open,positions:{primary:rect(primary),verdict:rect(verdict),checklist:rect(checklist),voice:rect(voice)},horizontal:document.documentElement.scrollWidth>innerWidth+1};
  })()`);

  const scenarioA = await show({ blocked: true });
  const blockerNavigation = await evaluate(`(async()=>{const saved=focusProductionTarget;let target=null;focusProductionTarget=async value=>{target=value};try{await navigateProductionPreflightBlocker(0);return{chapterId:state.productionInspectedChapterId,target}}finally{focusProductionTarget=saved;state.productionInspectedChapterId=null}})()`);
  const scenarioB = await show({});
  await evaluate(`document.querySelector("#productionPrimaryAction").click()`);
  const readyDialog = await evaluate(`({open:document.querySelector("#productionPrepareAuthDialog").open,confirm:document.querySelector("#productionPrepareConfirmationCopy").textContent,submitDisabled:document.querySelector("#productionPrepareDialogSubmit").disabled})`);
  const readyDialogEnabled = await evaluate(`(()=>{document.querySelector("#productionPrepareDialogConfirmation").checked=true;document.querySelector("#productionTaskOperatorToken").value="synthetic-browser-token";updateProductionPrepareDialog();return !document.querySelector("#productionPrepareDialogSubmit").disabled})()`);
  await evaluate(`document.querySelector("#productionPrepareAuthDialog").close()`);
  const scenarioC = await show({ authorized: false });
  await evaluate(`document.querySelector("#productionPrimaryAction").click()`);
  const authDialog = await evaluate(`({open:document.querySelector("#productionPrepareAuthDialog").open,status:document.querySelector("#productionPrepareDialogStatus").textContent,submitDisabled:document.querySelector("#productionPrepareDialogSubmit").disabled})`);
  await evaluate(`document.querySelector("#productionPrepareAuthDialog").close()`);
  const scenarioD = await show({ voiceUnavailable: true });
  const scenarioE = await show({ taskType: "START_RENDER_RANGE" });
  const scenarioRunning = await show({ taskType: "MONITOR_RENDER" });
  const scenarioF = await evaluate(`({open:document.querySelector("#productionTechnicalDetails").open,technical:document.querySelector("#productionTechnicalBody").textContent})`);
  const scenarioG = await show({});
  const scenarioH = await evaluate(`(async()=>{const details=document.querySelector("#productionTechnicalDetails"),primary=document.querySelector("#productionPrimaryAction");details.open=true;primary.focus();const key=currentProductionViewModel().task_key;for(let i=0;i<4;i+=1){await new Promise(resolve=>setTimeout(resolve,80));renderProductionShell()}return{detailsOpen:details.open,focus:document.activeElement===primary,keyStable:currentProductionViewModel().task_key===key}})()`);

  const visibleAt1366 = ["primary", "verdict", "checklist", "voice"].every(key => {
    const rect = scenarioG.positions[key];
    return rect && rect.top < 768 && rect.bottom > 0;
  });
  if (!scenarioA.body.includes("Chưa thể chuẩn bị audio") || !scenarioA.body.includes("Chương 373") || scenarioA.primary.includes("Chuẩn bị")) throw new Error(`Scenario A failed: ${JSON.stringify(scenarioA)}`);
  if (blockerNavigation.chapterId !== 7002 || blockerNavigation.target !== "speakers") throw new Error(`Blocker navigation failed: ${JSON.stringify(blockerNavigation)}`);
  if (!scenarioB.body.includes("Sẵn sàng chuẩn bị") || !scenarioB.body.includes("Chanlee") || scenarioB.primary !== "Chuẩn bị 2 chương") throw new Error(`Scenario B failed: ${JSON.stringify(scenarioB)}`);
  if (!readyDialog.open || !readyDialog.confirm.includes("372–373") || !readyDialog.submitDisabled || !readyDialogEnabled) throw new Error(`Ready confirmation failed: ${JSON.stringify({ readyDialog, readyDialogEnabled })}`);
  if (!scenarioC.body.includes("Sẵn sàng chuẩn bị") || scenarioC.primary !== "Xác thực để chuẩn bị" || !authDialog.open || !authDialog.submitDisabled) throw new Error(`Scenario C failed: ${JSON.stringify({ scenarioC, authDialog })}`);
  if (!scenarioD.body.includes("Giọng không khả dụng") || scenarioD.primary.includes("Chuẩn bị")) throw new Error(`Scenario D failed: ${JSON.stringify(scenarioD)}`);
  if (scenarioE.primary !== "Bắt đầu render 2 chương" || scenarioE.body.includes("Chuẩn bị 2 chương")) throw new Error(`Scenario E failed: ${JSON.stringify(scenarioE)}`);
  if (scenarioRunning.primary !== "Theo dõi render" || !scenarioRunning.body.includes("đoạn hoàn tất")) throw new Error(`Running state failed: ${JSON.stringify(scenarioRunning)}`);
  if (scenarioF.open || !scenarioF.technical.includes("plan_fingerprint")) throw new Error(`Scenario F failed: ${JSON.stringify(scenarioF)}`);
  if (!visibleAt1366 || scenarioG.horizontal || scenarioG.rawIdsVisible || scenarioG.rawAuthVisible || scenarioG.legacyVisible || !scenarioG.legacyInert) throw new Error(`Scenario G failed: ${JSON.stringify(scenarioG)}`);
  if (!scenarioH.detailsOpen || !scenarioH.focus || !scenarioH.keyStable) throw new Error(`Scenario H failed: ${JSON.stringify(scenarioH)}`);

  await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  const desktop = await evaluate(`({horizontal:document.documentElement.scrollWidth>innerWidth+1,primaryVisible:document.querySelector("#productionPrimaryAction").getBoundingClientRect().top<innerHeight})`);
  if (desktop.horizontal || !desktop.primaryVisible) throw new Error(`1920 layout failed: ${JSON.stringify(desktop)}`);
  if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);

  process.stdout.write(JSON.stringify({ ok: true, scenarioA, blockerNavigation, scenarioB, readyDialog, readyDialogEnabled, scenarioC, authDialog, scenarioD, scenarioE, scenarioRunning, scenarioF, scenarioG: { visibleAt1366, horizontal: scenarioG.horizontal, rawIdsVisible: scenarioG.rawIdsVisible }, scenarioH, desktop }));
} finally {
  try { socket?.close(); } catch {}
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
