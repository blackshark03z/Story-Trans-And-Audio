import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const baseUrl = process.argv[2];
if (!baseUrl) throw new Error("Usage: node scripts/browser_production_task_workbench_smoke.mjs <base-url>");

const browserExe = [
  process.env.STORY_AUDIO_BROWSER_EXE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");

const profile = await mkdtemp(join(tmpdir(), "story-audio-workbench-browser-"));
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
  await waitFor(`document.querySelector("#productionWorkbench")`);
  await waitFor(`window.storyAudioAppState`);
  await evaluate(`loadProductionTaskProjection=async()=>{renderProductionShell(state.productionProjection||undefined);return state.productionProjection}`);

  const fixture = {
    book: { id: 91, title: "Sách kiểm thử cô lập" },
    dialog: {
      chapter: { id: 9101, book_id: 91, chapter_number: 401, title: "Chương kiểm thử", active_text_revision_id: 8101, audio_status: "not_created" },
      revisions: [{ id: 8101, status: "approved", text: "Nội dung kiểm thử." }],
      qa_issues: [],
      active_output: {},
      audio_artifact: null,
      human_approval: null,
    },
    casting: {
      chapter: { id: 9101, book_id: 91, title: "Chương kiểm thử" },
      characters: [{ id: 7001, display_name: "Nhân vật A", gender: "unknown", voice_override_id: "voice:test" }],
      voice_profile: { profile: { narrator_voice_id: "voice:test", male_dialogue_voice_id: "voice:test", female_dialogue_voice_id: "voice:test", unknown_fallback: "narrator" }, validation: { valid: true } },
      casting: { id: 801, text_revision_id: 8101, plan_revision: 1, status: "draft", narrator_voice_id: "voice:test", plan: { utterances: [{ utterance_id: "u1", sequence: 1, role: "narrator", character_id: null, resolved_voice_id: "voice:test", resolution_source: "narrator", text: "Dòng kiểm thử." }] } },
    },
    draft: { id: 601, status: "approved", stale: false, remaining_unreviewed_count: 0, invalid_count: 0, review_rows: [], characters: [] },
    voiceCatalog: { items: [{ assignment_key: "voice:test", display_name: "Giọng kiểm thử", source_kind: "preset", selectable: true, active: true }] },
  };

  const show = async overrides => evaluate(`(() => {
    const base=${JSON.stringify(fixture)};
    const patch=${JSON.stringify(overrides || {})};
    state.book=base.book;
    state.dialog=structuredClone(patch.dialog||base.dialog);
    state.casting=structuredClone(patch.casting===null?null:(patch.casting||base.casting));
    state.voiceCatalog=base.voiceCatalog;
    state.jobs=structuredClone(patch.jobs||[]);
    state.speakerReview={chapterId:state.dialog?.chapter?.id||null,drafts:[],draft:structuredClone(patch.draft===null?null:(patch.draft||base.draft)),decisions:{},selected:{},generation:null};
    state.productionRange=patch.productionRange||{bookId:91,fromChapter:401,toChapter:401,chapterId:9101,skipCompleted:false,readiness:{scope:{book_id:91,book_title:"Sách kiểm thử cô lập",from_chapter:401,to_chapter:401,chapter_count:1},summary:{total:1,complete:0,needs_attention:1},chapters:[{chapter_id:9101,chapter_number:401,title:"Chương kiểm thử",state:patch.rangeState||"CASTING_REVIEW",requires_operator_action:true}]}};
    const rangeState=patch.rangeState||"CASTING_REVIEW",draft=state.speakerReview.draft,failedJob=state.jobs.find(item=>["failed","completed_with_errors","paused","interrupted"].includes(item.status));
    let taskType="REVIEW_CASTING_PLAN",actionKey="REVIEW_CASTING_PLAN",actionLabel="Kiểm tra bản đồ giọng",stage=3,stageKey="voice_map",rangeTask=false;
    if(rangeState==="RENDERED_NOT_QA"){taskType="HUMAN_QA";actionKey=null;actionLabel="";stage=5;stageKey="qa"}
    else if(!draft){taskType="CREATE_SPEAKER_PROPOSAL";actionKey=taskType;actionLabel="Tạo đề xuất người nói";stage=2;stageKey="speakers"}
    else if(draft.status!=="approved"&&Number(draft.remaining_unreviewed_count||0)>0){taskType="RESOLVE_SPEAKER";actionKey=taskType;actionLabel="Xác nhận và tiếp tục";stage=2;stageKey="speakers"}
    else if(draft.status!=="approved"){taskType="APPROVE_SPEAKER_DRAFT";actionKey=taskType;actionLabel="Duyệt Speaker Draft";stage=2;stageKey="speakers"}
    else if(rangeState==="VOICE_BLOCKED"){taskType="ASSIGN_VOICE";actionKey=taskType;actionLabel="Gán giọng";stage=3;stageKey="voices"}
    else if(rangeState==="READY_TO_PREPARE"){taskType="PREPARE_RANGE";actionKey=taskType;actionLabel="Chuẩn bị audio";stage=4;stageKey="prepare";rangeTask=true}
    else if(rangeState==="PREPARED"){taskType="START_RENDER_RANGE";actionKey=taskType;actionLabel="Bắt đầu render";stage=4;stageKey="render";rangeTask=true}
    else if(rangeState==="RENDERING_OR_PAUSED"&&failedJob){taskType="RECOVER_RENDER";actionKey=taskType;actionLabel="Xử lý render";stage=4;stageKey="render";rangeTask=true}
    else if(rangeState==="RENDERING_OR_PAUSED"){taskType="MONITOR_RENDER";actionKey=taskType;actionLabel="Theo dõi render";stage=4;stageKey="render";rangeTask=true}
    const queue=(state.productionRange.readiness?.chapters||[]).map((item,index)=>({chapter_id:item.chapter_id,chapter_number:item.chapter_number,title:item.title||"",status:index===0&&!rangeTask?"current":"ready",state:item.state,user_stage:stage,task_type:rangeTask?null:taskType,task_key:"chapter:"+item.chapter_id+":"+taskType}));
    state.productionProjection={range_identity:"book:91:401-401",task_scope:rangeTask?"range":"chapter",task_type:taskType,task_key:(rangeTask?"range:91:401-401:":"chapter:9101:")+taskType,user_stage:stage,title:actionLabel||"Nghe và duyệt",summary:"Trạng thái fixture",task_title:actionLabel||"Nghe và duyệt",task_summary:"Trạng thái fixture",affected_chapter:rangeTask?null:{id:9101,number:401,title:state.dialog?.chapter?.title||""},chapter_queue:queue,queue,primary_action:actionKey?{key:actionKey,label:actionLabel,target:stageKey}:null,secondary_actions:[],secondary_links:[],blocker:null,next_task_hint:"Bước tiếp theo",next_task_after_success:"Bước tiếp theo",technical_details:[],phases:[],conceptual_state:rangeState,current_stage_key:stageKey};
    state.runtimeIdentity={state:"isolated",label:"Dữ liệu kiểm thử"};
    state.runtimeIdentityResolved=true;
    renderProductionShell();
    const visible=element=>!!element&&getComputedStyle(element).display!=="none"&&element.getBoundingClientRect().width>0;
    const primary=[...document.querySelectorAll("#productionTaskWorkspace .primary")].filter(visible).map(element=>element.textContent.trim());
    const workspace=document.querySelector("#productionTaskWorkspace").getBoundingClientRect();
    const nested=[...document.querySelectorAll("#productionWorkbench *")].filter(element=>{const style=getComputedStyle(element);return /(auto|scroll)/.test(style.overflowY)&&element.scrollHeight>element.clientHeight+2}).map(element=>element.id||element.className);
    const primaryButton=document.querySelector("#productionPrimaryAction"),primaryRect=primaryButton.getBoundingClientRect();
    return {state:document.querySelector("#productionStateCard").dataset.productionState,title:document.querySelector("#productionCurrentStepHeading").textContent,primary,primaryViewport:!primary.includes(primaryButton.textContent.trim())||primaryRect.top>=0&&primaryRect.bottom<=innerHeight,body:document.querySelector("#productionTaskContent").innerText,queue:document.querySelectorAll(".production-queue-item").length,workspaceVisible:workspace.top>=0&&workspace.top<innerHeight,nested};
  })()`);

  const journeyA = await show({ rangeState: "CASTING_REVIEW" });
  const noDraftCasting = structuredClone(fixture.casting); noDraftCasting.casting = {};
  const journeyB = await show({ casting: noDraftCasting, draft: null, rangeState: "SPEAKER_EXCEPTIONS" });
  const unresolvedDraft = { id: 602, status: "draft", stale: false, remaining_unreviewed_count: 1, invalid_count: 0, characters: [{ id: 7001, display_name: "Nhân vật A" }], review_rows: [{ utterance_id: "u2", sequence: 2, text: "Ai đang nói?", reviewed: false, context: [{ text: "Ngữ cảnh trước" }, { text: "Ai đang nói?", is_target: true }, { text: "Ngữ cảnh sau" }], suggestion: { speaker_type: "character", character_id: 7001, confidence_level: "medium", confidence: 0.7, reason: "Có tên nhân vật gần câu thoại." } }] };
  const journeyC = await show({ casting: noDraftCasting, draft: unresolvedDraft, rangeState: "SPEAKER_EXCEPTIONS" });
  await waitFor(`document.querySelector("#productionSpeakerChoice")`);
  const pollingStability = await evaluate(`(async()=>{const details=document.querySelector(".production-advanced-options"),choice=document.querySelector("#productionSpeakerChoice");details.open=true;choice.value="unknown";choice.focus();const key=state.productionProjection.task_key;for(let index=0;index<5;index+=1){await new Promise(resolve=>setTimeout(resolve,2600));if(state.productionProjection.task_key!==key||!details.isConnected||!details.open||choice.value!=="unknown"||document.activeElement!==choice)return false}return true})()`);
  const voiceBlocked = structuredClone(fixture.casting); voiceBlocked.casting.plan.utterances[0].resolved_voice_id = null;
  const journeyDEdit = await show({ casting: voiceBlocked, rangeState: "VOICE_BLOCKED" });
  const journeyDReview = await show({ casting: fixture.casting, rangeState: "CASTING_REVIEW" });
  const approved = structuredClone(fixture.casting); approved.casting.status = "approved";
  const journeyEPrepare = await show({ casting: approved, rangeState: "READY_TO_PREPARE" });
  const journeyEStart = await show({ casting: approved, jobs: [{ id: 9001, book_id: 91, from_chapter: 401, to_chapter: 401, casting_plan_id: 801, status: "prepared" }], rangeState: "PREPARED" });
  const journeyERunning = await show({ casting: approved, jobs: [{ id: 9001, book_id: 91, from_chapter: 401, to_chapter: 401, casting_plan_id: 801, status: "running", total_chapters: 1, completed_chapters: 0, completed_segments: 3, failed_segments: 0, pending_segments: 5, actions: { can_retry: false } }], rangeState: "RENDERING_OR_PAUSED" });
  const journeyF = await show({ casting: approved, jobs: [{ id: 9001, book_id: 91, from_chapter: 401, to_chapter: 401, status: "failed", actions: { can_retry: true }, is_historical_output: false }], rangeState: "RENDERING_OR_PAUSED" });
  const qaDialog = structuredClone(fixture.dialog); qaDialog.chapter.audio_status = "completed"; qaDialog.active_output = { active_output_job_id: 9001, active_output_artifact_id: 9901 }; qaDialog.audio_artifact = { id: 9901, duration_ms: 60000, actual_size_bytes: 1024 };
  const journeyG = await show({ dialog: qaDialog, casting: approved, rangeState: "RENDERED_NOT_QA" });
  const qaNoteRequired = await evaluate(`(() => { document.querySelector("#productionQaNote").value=""; document.querySelector("#productionQaNeedsFixes").click(); return document.querySelector("#toast")?.textContent||document.querySelector(".toast")?.textContent||""; })()`);
  const rangeChapters = Array.from({ length: 10 }, (_, index) => ({ chapter_id: 9200 + index, chapter_number: 500 + index, title: `Chương ${500 + index}`, state: index < 3 ? "COMPLETE" : index === 3 ? "SPEAKER_EXCEPTIONS" : "READY_TO_PREPARE", requires_operator_action: index >= 3 }));
  const tenRange = { bookId: 91, fromChapter: 500, toChapter: 509, chapterId: null, skipCompleted: false, readiness: { scope: { book_id: 91, book_title: "Sách kiểm thử cô lập", from_chapter: 500, to_chapter: 509, chapter_count: 10 }, summary: { total: 10, complete: 3, needs_attention: 7 }, chapters: rangeChapters } };
  const journeyH = await evaluate(`(() => { state.dialog=null;state.casting=null;state.speakerReview=null;state.jobs=[];state.productionRange=${JSON.stringify(tenRange)};const queue=state.productionRange.readiness.chapters.map((item,index)=>({chapter_id:item.chapter_id,chapter_number:item.chapter_number,title:item.title,status:index<3?"complete":index===3?"current":"blocked",state:item.state,user_stage:index===3?2:4,task_type:index===3?"RESOLVE_SPEAKER":null,task_key:"chapter:"+item.chapter_id+":"+(index===3?"RESOLVE_SPEAKER":"READY")}));state.productionProjection={range_identity:"book:91:500-509",task_scope:"chapter",task_type:"RESOLVE_SPEAKER",task_key:"chapter:9203:RESOLVE_SPEAKER",user_stage:2,title:"Xác nhận người nói",summary:"Chương 503 còn dòng chưa xác nhận.",task_title:"Xác nhận người nói",task_summary:"Chương 503 còn dòng chưa xác nhận.",affected_chapter:{id:9203,number:503,title:"Chương 503"},chapter_queue:queue,queue,primary_action:{key:"RESOLVE_SPEAKER",label:"Xác nhận và tiếp tục",target:"speakers"},secondary_actions:[],secondary_links:[],blocker:null,next_task_hint:"Tiếp tục",next_task_after_success:"Tiếp tục",technical_details:[],phases:[],conceptual_state:"SPEAKER_EXCEPTIONS",current_stage_key:"speakers"};renderProductionShell();return {queue:document.querySelectorAll(".production-queue-item").length,current:document.querySelector(".production-queue-item.current")?.innerText||"",primary:document.querySelector("#productionPrimaryAction").textContent}; })()`);

  const expected = [
    [journeyB, "Tạo đề xuất người nói"],
    [journeyC, "Xác nhận và tiếp tục"],
    [journeyDEdit, "Gán giọng"],
    [journeyDReview, "Kiểm tra bản đồ giọng"],
    [journeyEPrepare, "Chuẩn bị 1 chương"],
    [journeyEStart, "Bắt đầu render 1 chương"],
    [journeyERunning, "Theo dõi render"],
    [journeyF, "Xử lý render"],
  ];
  for (const [journey, label] of expected) {
    if (journey.primary.length !== 1 || journey.primary[0] !== label) throw new Error(`Primary action mismatch for ${label}: ${JSON.stringify(journey)}`);
    if (!journey.primaryViewport) throw new Error(`Primary action fell below the 1366 viewport: ${JSON.stringify(journey)}`);
    if (journey.nested.length) throw new Error(`Nested operational scroll found: ${JSON.stringify(journey.nested)}`);
  }
  if (!journeyA.workspaceVisible) throw new Error("Journey A did not focus the current task.");
  if (!pollingStability) throw new Error("Advanced speaker controls did not survive five polling intervals.");
  if (journeyDReview.body.includes("Lưu bản nháp")) throw new Error("Voice save and approval competed on the review screen.");
  if (journeyERunning.body.includes("Bắt đầu render")) throw new Error("Running state exposed duplicate start.");
  if (journeyG.primary.length !== 1 || !journeyG.primary.includes("Chấp nhận") || !journeyG.body.includes("Ghi chú QA")) throw new Error(`QA controls are unclear: ${JSON.stringify(journeyG)}`);
  if (!qaNoteRequired.includes("ghi chú")) throw new Error("QA rejection did not require a note.");
  if (journeyH.queue !== 10 || !journeyH.current.includes("503")) throw new Error(`Ten-chapter queue did not focus the first action: ${JSON.stringify(journeyH)}`);

  await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  const desktop = await evaluate(`(() => ({horizontal:document.documentElement.scrollWidth>innerWidth+1,primaryVisible:document.querySelector("#productionPrimaryAction").getBoundingClientRect().top<innerHeight}))()`);
  if (desktop.horizontal || !desktop.primaryVisible) throw new Error(`1920 layout failed: ${JSON.stringify(desktop)}`);
  if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);

  process.stdout.write(JSON.stringify({ ok: true, journeyA, journeyB, journeyC, pollingStability, journeyDEdit, journeyDReview, journeyEPrepare, journeyEStart, journeyERunning, journeyF, journeyG, journeyH, desktop }));
} finally {
  try { socket?.close(); } catch {}
  const browserExited = new Promise(resolve => {
    if (child.exitCode !== null) resolve();
    else child.once("exit", resolve);
  });
  child.kill();
  await Promise.race([browserExited, delay(3000)]);
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try { await rm(profile, { recursive: true, force: true }); break; }
    catch (error) {
      if (!["EBUSY", "EPERM"].includes(error?.code) || attempt === 29) throw error;
      await delay(200);
    }
  }
}
