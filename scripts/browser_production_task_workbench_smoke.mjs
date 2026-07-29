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
  try {
    await waitFor(`window.storyAudioAppState`);
  } catch (error) {
    throw new Error(`${error.message} Browser errors: ${browserErrors.join(" | ")}`);
  }
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
    const sections={speaker:null,casting:null,range_prepare:null,render:null,qa:null};
    if(["CREATE_SPEAKER_PROPOSAL","RESOLVE_SPEAKER","APPROVE_SPEAKER_DRAFT"].includes(taskType))sections.speaker={chapter_id:9101,draft_id:draft?.id||null,draft_status:draft?.status||null,target_count:draft?.target_count||0,invalid_count:draft?.invalid_count||0,remaining_unreviewed_count:draft?.remaining_unreviewed_count||0,stale:!!draft?.stale};
    else if(["ASSIGN_VOICE","REVIEW_CASTING_PLAN"].includes(taskType))sections.casting={chapter_id:9101,plan_id:state.casting?.casting?.id||null,plan_revision:state.casting?.casting?.plan_revision||null,plan_status:state.casting?.casting?.status||null,voice_issues:[]};
    else if(taskType==="PREPARE_RANGE")sections.range_prepare={book_id:91,from_chapter:401,to_chapter:401,chapter_count:1};
    else if(["START_RENDER_RANGE","MONITOR_RENDER","RECOVER_RENDER"].includes(taskType))sections.render={job_id:state.jobs[0]?.id||null,job_status:state.jobs[0]?.status||null};
    else if(taskType==="HUMAN_QA")sections.qa={chapter_id:9101,artifact_id:state.dialog?.audio_artifact?.id||null,job_id:state.dialog?.active_output?.active_output_job_id||null,human_qa_status:null};
    state.productionProjection.canonical_task={task_scope:state.productionProjection.task_scope,task_type:taskType,task_key:state.productionProjection.task_key,user_stage:stage,title:state.productionProjection.title,summary:state.productionProjection.summary,affected_chapter:state.productionProjection.affected_chapter,primary_action:state.productionProjection.primary_action,blocker:null,next_task_hint:"Next",technical_details:[],current_stage_key:stageKey,...sections};
    state.productionProjection.chapter_queue.forEach(item=>{item.canonical_task=Number(item.chapter_id)===9101;item.inspected=false});
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
  const qaNullSafe = await evaluate(`(async()=>{const savedApi=api;state.casting=null;api=async()=>({chapter:state.dialog.chapter,active_output:state.dialog.active_output,human_approval:{status:"approved"}});try{await updateHumanApproval("approved");return{ok:true,casting:state.casting}}catch(error){return{ok:false,error:String(error?.message||error)}}finally{api=savedApi}})()`);
  const rangeChapters = Array.from({ length: 10 }, (_, index) => ({ chapter_id: 9200 + index, chapter_number: 500 + index, title: `Chương ${500 + index}`, state: index < 3 ? "COMPLETE" : index === 3 ? "SPEAKER_EXCEPTIONS" : "READY_TO_PREPARE", requires_operator_action: index >= 3 }));
  const tenRange = { bookId: 91, fromChapter: 500, toChapter: 509, chapterId: null, skipCompleted: false, readiness: { scope: { book_id: 91, book_title: "Sách kiểm thử cô lập", from_chapter: 500, to_chapter: 509, chapter_count: 10 }, summary: { total: 10, complete: 3, needs_attention: 7 }, chapters: rangeChapters } };
  const journeyH = await evaluate(`(() => { state.dialog=null;state.casting=null;state.speakerReview=null;state.jobs=[];state.productionRange=${JSON.stringify(tenRange)};const queue=state.productionRange.readiness.chapters.map((item,index)=>({chapter_id:item.chapter_id,chapter_number:item.chapter_number,title:item.title,status:index<3?"complete":index===3?"current":"blocked",state:item.state,user_stage:index===3?2:4,task_type:index===3?"RESOLVE_SPEAKER":null,task_key:"chapter:"+item.chapter_id+":"+(index===3?"RESOLVE_SPEAKER":"READY"),canonical_task:index===3,inspected:false}));const canonical={task_scope:"chapter",task_type:"RESOLVE_SPEAKER",task_key:"chapter:9203:RESOLVE_SPEAKER",user_stage:2,title:"Xác nhận người nói",summary:"Chương 503 còn dòng chưa xác nhận.",affected_chapter:{id:9203,number:503,title:"Chương 503"},primary_action:{key:"RESOLVE_SPEAKER",label:"Xác nhận và tiếp tục",target:"speakers"},blocker:null,next_task_hint:"Tiếp tục",technical_details:[],current_stage_key:"speakers",speaker:{chapter_id:9203,draft_id:null,draft_status:"draft",target_count:1,invalid_count:0,remaining_unreviewed_count:1,stale:false},casting:null,range_prepare:null,render:null,qa:null};state.productionProjection={range_identity:"book:91:500-509",chapter_queue:queue,queue,phases:[],canonical_task:canonical};renderProductionShell();return {queue:document.querySelectorAll(".production-queue-item").length,current:document.querySelector(".production-queue-item.current")?.innerText||"",primary:document.querySelector("#productionPrimaryAction").textContent}; })()`);
  const commandLifecycle = await evaluate(`(async()=>{const savedApi=api,savedPost=postProductionCommand,savedSync=syncCanonicalProductionContext,base=JSON.parse(JSON.stringify(state.productionProjection)),scope={range:{book_id:91,from_chapter:500,to_chapter:509}};syncCanonicalProductionContext=async()=>{};postProductionCommand=async(body)=>api("/api/production/commands",{method:"POST",body:JSON.stringify(body)});const projected=key=>{const copy=JSON.parse(JSON.stringify(base));copy.canonical_task.task_key=key;return copy},reply=(body,outcome="APPLIED",applied=[{chapter_number:500}],failed=[])=>({schema:"story-audio-production-command/v1",command_id:"pc-"+body.idempotency_key,command_type:body.command_type,idempotency_key:body.idempotency_key,scope:body.scope,outcome,submitted_count:applied.length+failed.length,applied_count:applied.length,failed_count:failed.length,applied_items:applied,failed_items:failed,operator_message:outcome==="PARTIAL"?"Đã duyệt một phần.":"Đã áp dụng thao tác.",resulting_task_projection:projected("command:"+body.command_type.toLowerCase()),resulting_preflight:null,asynchronous_reference:outcome==="ACCEPTED"?{type:"job",id:25,status:"queued",status_url:"/api/jobs/25"}:null,state_tokens:{task_projection:"token",preflight:null}});state.productionCommand={...state.productionCommand,status:"IDLE",active:false,keys:{}};let release,calls=[],gate=new Promise(resolve=>release=resolve);api=async(path,options)=>{const body=JSON.parse(options.body);calls.push(body);await gate;return reply(body)};const first=runProductionCommand({commandType:"APPROVE_SPEAKER_DRAFTS",scope,payload:{chapters:[1,2,3,4,5,6,7]},label:"Đang duyệt 7 chương…"}),second=runProductionCommand({commandType:"APPROVE_SPEAKER_DRAFTS",scope,payload:{chapters:[1,2,3,4,5,6,7]},label:"Đang duyệt 7 chương…"}),busy=state.productionCommand.status==="SUBMITTING";release();await Promise.all([first,second]);const A={calls:calls.length,busy,status:state.productionCommand.status};state.productionCommand.keys={};api=async(path,options)=>reply(JSON.parse(options.body),"PARTIAL",[{chapter_number:500},{chapter_number:501},{chapter_number:502},{chapter_number:503},{chapter_number:504}],[{chapter_number:505,reason:"Draft stale"},{chapter_number:506,reason:"Cần kiểm tra"}]);const partial=await runProductionCommand({commandType:"APPROVE_SPEAKER_DRAFTS",scope,payload:{chapters:[1,2,3,4,5,6,7]},label:"Đang duyệt 7 chương…"}),B={outcome:partial.outcome,applied:state.productionCommand.appliedItems.length,failed:state.productionCommand.failedItems.length};state.productionCommand.keys={};api=async(path,options)=>{const body=JSON.parse(options.body);return reply(body,body.command_type==="START_RENDER"?"ACCEPTED":"APPLIED")};const prepared=await runProductionCommand({commandType:"PREPARE",scope,payload:{book_id:91,from_chapter:500,to_chapter:509},label:"Đang chuẩn bị…"}),started=await runProductionCommand({commandType:"START_RENDER",scope:{job:{id:25}},payload:{job_id:25},label:"Đang bắt đầu…"}),accepted=await runProductionCommand({commandType:"HUMAN_QA_ACCEPT",scope:{artifact:{id:99}},payload:{chapter_id:9203,notes:"pass"},label:"Đang ghi QA…"}),rejected=await runProductionCommand({commandType:"HUMAN_QA_NEEDS_FIXES",scope:{artifact:{id:100}},payload:{chapter_id:9204,notes:"fix"},label:"Đang ghi QA…"}),EFGH={prepare:prepared.outcome,start:started.outcome,job:started.asynchronous_reference?.id,accept:accepted.outcome,reject:rejected.outcome};const epoch=state.productionInteractionEpoch,key=state.productionProjection.canonical_task.task_key,stale=await applyProductionCommandEnvelope(reply({command_type:"HUMAN_QA_ACCEPT",idempotency_key:"stale-key",scope:{artifact:{id:1}}}),epoch-1),I={discarded:stale===false,stable:state.productionProjection.canonical_task.task_key===key};state.productionCommand.keys={};calls=[];let lost=true;api=async(path,options)=>{const body=JSON.parse(options.body);calls.push(body);if(lost){lost=false;throw new Error("response lost")}return reply(body)};const verified=await runProductionCommand({commandType:"HUMAN_QA_ACCEPT",scope:{artifact:{id:101}},payload:{chapter_id:9205,notes:"pass"},label:"Đang ghi QA…"}),J={outcome:verified?.outcome,calls:calls.length,sameKey:calls.length===2&&calls[0].idempotency_key===calls[1].idempotency_key};const durable=projected("command:durable");state.productionProjection=null;await applyProductionCommandEnvelope({...reply(calls[1]),resulting_task_projection:durable},state.productionInteractionEpoch);const K={restored:state.productionProjection.canonical_task.task_key==="command:durable"};api=savedApi;postProductionCommand=savedPost;syncCanonicalProductionContext=savedSync;return{A,B,EFGH,I,J,K}})()`);
  const qaCommandReconcile = await evaluate(`(async()=>{const savedApi=api,savedPost=postProductionCommand,savedSync=syncCanonicalProductionContext,savedLoad=loadProductionTaskProjection,base=JSON.parse(JSON.stringify(state.productionProjection));syncCanonicalProductionContext=async()=>{};postProductionCommand=async(body)=>api("/api/production/commands",{method:"POST",body:JSON.stringify(body)});const repairProjection=()=>{const copy=JSON.parse(JSON.stringify(base)),task=copy.canonical_task,affected={id:9206,number:506,title:"Chapter 506"};copy.task_scope="chapter";copy.task_type="REPAIR_REQUIRED";copy.task_key="chapter:9206:REPAIR_REQUIRED:artifact:102:plan:88";copy.user_stage=5;copy.title="Bản audio này cần sửa";copy.summary="Chapter 506 đã được đánh dấu Cần sửa.";copy.affected_chapter=affected;copy.primary_action=null;copy.range_task=false;copy.current_stage_key="qa";copy.conceptual_state="REPAIR_REQUIRED";copy.chapter_queue=[{chapter_id:9206,chapter_number:506,title:"Chapter 506",status:"current",state:"REPAIR_REQUIRED",user_stage:5,task_type:"REPAIR_REQUIRED",task_key:"chapter:9206:REPAIR_REQUIRED",canonical_task:true,inspected:false}];copy.queue=copy.chapter_queue;Object.assign(task,{task_scope:"chapter",task_type:"REPAIR_REQUIRED",task_key:copy.task_key,user_stage:5,title:copy.title,summary:copy.summary,affected_chapter:affected,primary_action:null,blocker:null,next_task_hint:"Chọn hướng sửa.",technical_details:["chapter_state:REPAIR_REQUIRED","artifact_id:102"],current_stage_key:"qa",input_summary:{},speaker:null,casting:null,range_prepare:null,render:null,qa:null,repair:{artifact_id:102,qa_note:"fix",qa_recorded_at:"now",duration_ms:60000,prepare_ready:false,input_blockers:[]}});return copy};const reply=body=>({schema:"story-audio-production-command/v1",command_id:"pc-"+body.idempotency_key,command_type:body.command_type,idempotency_key:body.idempotency_key,scope:body.scope,outcome:"APPLIED",submitted_count:1,applied_count:1,failed_count:0,applied_items:[{chapter_number:506,artifact_id:102,qa_status:"needs_fixes"}],failed_items:[],operator_message:"Đã ghi Cần sửa cho Chương 506.",resulting_task_projection:repairProjection(),resulting_preflight:null,asynchronous_reference:null,state_tokens:{task_projection:"token",preflight:null}});state.productionCommand={...state.productionCommand,status:"IDLE",active:false,keys:{}};let calls=[];api=async(path,options)=>{const body=JSON.parse(options.body);calls.push(body);if(calls.length===1){const error=new Error("scope: invalid");error.status=422;throw error}return reply(body)};loadProductionTaskProjection=async()=>{state.productionProjection=repairProjection();renderProductionShell();return state.productionProjection};const args={commandType:"HUMAN_QA_NEEDS_FIXES",scope:{artifact:{id:102}},payload:{chapter_id:9206,notes:"fix"},label:"Đang ghi QA…"},first=await runProductionCommand(args),failedStatus=state.productionCommand.status,failedActive=state.productionCommand.active,firstKey=calls[0]?.idempotency_key,second=await runProductionCommand(args),secondKey=calls[1]?.idempotency_key;await new Promise(resolve=>setTimeout(resolve,320));const result={firstNull:first===null,failedStatus,failedActive,calls:calls.length,sameKey:firstKey===secondKey,secondOutcome:second?.outcome,task:state.productionProjection.canonical_task.task_type,qaHidden:document.querySelector("#productionQaActions").classList.contains("hidden"),primary:document.querySelector("#productionPrimaryAction").textContent,stayedRepair:currentProductionViewModel().task_type==="REPAIR_REQUIRED"};state.productionProjection=base;state.productionCommand={...state.productionCommand,status:"IDLE",active:false};renderProductionShell();api=savedApi;postProductionCommand=savedPost;syncCanonicalProductionContext=savedSync;loadProductionTaskProjection=savedLoad;return result})()`);
  const inspectionBC = await evaluate(`(()=>{const projection=state.productionProjection,canonicalKey=projection.canonical_task.task_key;projection.inspected_chapter={id:9200,number:500,title:"Chương 500"};projection.inspection_summary={read_only:true,task_type:"HUMAN_QA",title:"Đánh giá audio",summary:"Chương 500 có audio chờ nghe.",blocker:null};projection.chapter_queue.forEach(item=>item.inspected=Number(item.chapter_id)===9200);renderProductionShell();const inspected={taskKey:currentProductionViewModel().task_key,primary:document.querySelector("#productionPrimaryAction").textContent,qaHidden:document.querySelector("#productionQaActions").classList.contains("hidden"),labels:[...document.querySelectorAll(".production-queue-item small")].map(item=>item.textContent),summaryHidden:document.querySelector("#productionInspectionSummary").classList.contains("hidden")};projection.inspected_chapter=null;projection.inspection_summary=null;projection.chapter_queue.forEach(item=>item.inspected=false);renderProductionShell();return{canonicalKey,inspected,restoredKey:currentProductionViewModel().task_key,summaryRestored:document.querySelector("#productionInspectionSummary").classList.contains("hidden")}})()`);
  const malformedSafe = await evaluate(`(()=>{try{parseProductionProjection({canonical_task:{task_type:"HUMAN_QA",task_key:"bad",user_stage:5,technical_details:[],qa:null}});return{ok:false}}catch(error){state.productionProjection=productionProjectionFailure(error.message);renderProductionShell();return{ok:true,title:document.querySelector("#productionCurrentStepHeading").textContent,summary:document.querySelector("#productionStateExplanation").textContent,action:document.querySelector("#productionPrimaryAction").textContent,technical:document.querySelector("#productionTechnicalBody").textContent}}})()`);

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
  if (!qaNullSafe.ok || qaNullSafe.casting !== null) throw new Error(`QA renderer touched casting state: ${JSON.stringify(qaNullSafe)}`);
  if (!qaNoteRequired.includes("ghi chú")) throw new Error("QA rejection did not require a note.");
  if (journeyH.queue !== 10 || !journeyH.current.includes("503")) throw new Error(`Ten-chapter queue did not focus the first action: ${JSON.stringify(journeyH)}`);
  if (commandLifecycle.A.calls !== 1 || !commandLifecycle.A.busy || commandLifecycle.A.status !== "APPLIED") throw new Error(`Command A failed: ${JSON.stringify(commandLifecycle.A)}`);
  if (commandLifecycle.B.outcome !== "PARTIAL" || commandLifecycle.B.applied !== 5 || commandLifecycle.B.failed !== 2) throw new Error(`Command B failed: ${JSON.stringify(commandLifecycle.B)}`);
  if (commandLifecycle.EFGH.prepare !== "APPLIED" || commandLifecycle.EFGH.start !== "ACCEPTED" || commandLifecycle.EFGH.job !== 25 || commandLifecycle.EFGH.accept !== "APPLIED" || commandLifecycle.EFGH.reject !== "APPLIED") throw new Error(`Commands E-H failed: ${JSON.stringify(commandLifecycle.EFGH)}`);
  if (!commandLifecycle.I.discarded || !commandLifecycle.I.stable) throw new Error(`Command I failed: ${JSON.stringify(commandLifecycle.I)}`);
  if (commandLifecycle.J.outcome !== "APPLIED" || commandLifecycle.J.calls !== 2 || !commandLifecycle.J.sameKey) throw new Error(`Command J failed: ${JSON.stringify(commandLifecycle.J)}`);
  if (!commandLifecycle.K.restored) throw new Error(`Command K failed: ${JSON.stringify(commandLifecycle.K)}`);
  if (!qaCommandReconcile.firstNull || qaCommandReconcile.failedStatus !== "FAILED" || qaCommandReconcile.failedActive || qaCommandReconcile.calls !== 2 || !qaCommandReconcile.sameKey || qaCommandReconcile.secondOutcome !== "APPLIED" || qaCommandReconcile.task !== "REPAIR_REQUIRED" || !qaCommandReconcile.qaHidden || !qaCommandReconcile.stayedRepair) throw new Error(`QA command reconciliation failed: ${JSON.stringify(qaCommandReconcile)}`);
  if (inspectionBC.inspected.taskKey !== inspectionBC.canonicalKey || !inspectionBC.inspected.qaHidden || inspectionBC.inspected.summaryHidden || !inspectionBC.inspected.labels.some(label=>label.includes("Việc tiếp theo")) || !inspectionBC.inspected.labels.some(label=>label.includes("Đang xem")) || inspectionBC.restoredKey !== inspectionBC.canonicalKey || !inspectionBC.summaryRestored) throw new Error(`Inspection changed canonical task: ${JSON.stringify(inspectionBC)}`);
  if (!malformedSafe.ok || malformedSafe.title !== "Không thể tải việc tiếp theo" || malformedSafe.summary !== "Trạng thái sản xuất chưa đầy đủ. Hãy làm mới để hệ thống kiểm tra lại." || malformedSafe.action !== "Thử lại" || !malformedSafe.technical.includes("PROJECTION_CONTRACT_INVALID")) throw new Error(`Malformed projection was not fail-closed: ${JSON.stringify(malformedSafe)}`);

  await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  const desktop = await evaluate(`(() => ({horizontal:document.documentElement.scrollWidth>innerWidth+1,primaryVisible:document.querySelector("#productionPrimaryAction").getBoundingClientRect().top<innerHeight}))()`);
  if (desktop.horizontal || !desktop.primaryVisible) throw new Error(`1920 layout failed: ${JSON.stringify(desktop)}`);
  if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);

  process.stdout.write(JSON.stringify({ ok: true, journeyA, journeyB, journeyC, pollingStability, journeyDEdit, journeyDReview, journeyEPrepare, journeyEStart, journeyERunning, journeyF, journeyG, qaNullSafe, journeyH, commandLifecycle, qaCommandReconcile, inspectionBC, malformedSafe, desktop }));
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
