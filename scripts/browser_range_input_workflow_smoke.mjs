import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const baseUrl = process.argv[2];
if (!baseUrl) throw new Error("Usage: node scripts/browser_range_input_workflow_smoke.mjs <base-url>");

const browserExe = [
  process.env.STORY_AUDIO_BROWSER_EXE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");

const profile = await mkdtemp(join(tmpdir(), "story-audio-range-input-browser-"));
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
    if (message.method === "Runtime.consoleAPICalled"
        && message.params?.type === "error") {
      browserErrors.push(
        (message.params.args || []).map(item => item.value || item.description).join(" ")
      );
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
      throw new Error(
        result.exceptionDetails.exception?.description || result.exceptionDetails.text
      );
    }
    return result.result.value;
  };
  const waitFor = (expression, timeoutMs = 10000) => poll(
    async () => (await evaluate(expression)) || null,
    timeoutMs,
  );

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1366,
    height: 768,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await waitFor(`document.readyState==="complete"`);
  await waitFor(`window.storyAudioAppState && document.querySelector("#productionWorkbench")`);
  await waitFor(`window.storyAudioAppState.config
    && window.storyAudioAppState.runtimeIdentityResolved
    && !document.querySelector("#homeAttention")?.textContent.includes("Đang tải")`);

  await evaluate(`(() => {
    const chapters=Array.from({length:10},(_,index)=>({
      chapter_id:7101+index,
      chapter_number:101+index,
      chapter_title:"Chương "+(101+index),
      title:"Chương "+(101+index),
      state:"SPEAKER_EXCEPTIONS",
      status:index===0?"current":"blocked",
      user_stage:2,
      task_type:null,
      task_key:"chapter:"+(7101+index)+":range",
      canonical_task:false,
      inspected:false,
    }));
    const exception=(chapterOffset,sequence)=>({
      chapter_id:7101+chapterOffset,
      chapter_number:101+chapterOffset,
      chapter_title:"Chương "+(101+chapterOffset),
      draft_id:8101+chapterOffset,
      draft_status:"generated",
      draft_fingerprint:"a".repeat(64),
      text_revision_id:9101+chapterOffset,
      utterance_id:"u"+String(sequence).padStart(4,"0")+"-fixture",
      sequence,
      source_text:"Câu thoại cần xác nhận "+sequence+".",
      context:[
        {text:"Ngữ cảnh trước."},
        {text:"Câu thoại cần xác nhận "+sequence+".",is_target:true},
        {text:"Ngữ cảnh sau."},
      ],
      detected_speaker:{speaker_type:"character",character_id:9901},
      suggested_character_id:9901,
      confidence:0.72,
      confidence_level:"medium",
      reason:"Có hai người nói hợp lý trong ngữ cảnh.",
      alternatives:[],
      current_decision:null,
      characters:[{id:9901,display_name:"Nhân vật A"},{id:9902,display_name:"Nhân vật B"}],
    });
    window.__rangeFixture={
      phase:"proposal",
      exceptions:[
        exception(0,1),exception(0,2),
        exception(1,1),exception(1,2),
        exception(2,1),
      ],
      voices:[
        {chapter_id:7101,chapter_number:101,chapter_title:"Chương 101",speaker_key:"character:9901",speaker_name:"Nhân vật A",character_id:9901,current_voice_id:null,reason:"Nhân vật mới cần chọn giọng.",chapter_ids:[7101,7102],chapter_numbers:[101,102]},
        {chapter_id:7103,chapter_number:103,chapter_title:"Chương 103",speaker_key:"character:9902",speaker_name:"Nhân vật B",character_id:9902,current_voice_id:null,reason:"Mapping hiện tại xung đột.",chapter_ids:[7103],chapter_numbers:[103]},
      ],
      calls:[],
      chapters,
      readyDrafts:Array.from({length:7},(_,index)=>({chapter_id:7104+index,chapter_number:104+index,chapter_title:"Chương "+(104+index),draft_id:8204+index,draft_revision:8204+index,unresolved_count:3,proposal_source:"Gemini speaker proposal"})),
      plans:Array.from({length:9},(_,index)=>({chapter_id:7101+index,chapter_number:101+index,chapter_title:"Chương "+(101+index),plan_id:8501+index,plan_revision:1,plan_status:"draft",narrator_voice_id:"voice:narrator",changed_character_voices:[],unresolved_count:0,changed_mapping_warning:index===0,effective_voice_map:[{speaker_name:"Người kể chuyện",effective_voice_name:"Giọng kể ấm",assignment_source:"book_default",line_count:12,affected_chapters:[101+index],available:true},{speaker_name:"Nhân vật A",effective_voice_name:"Giọng chỉ huy",assignment_source:"override",line_count:4,affected_chapters:[101+index],available:true}]})),
    };
    state.book={id:71,title:"Sách kiểm thử phạm vi"};
    state.books=[state.book];
    state.dialog=null;
    state.casting=null;
    state.speakerReview=null;
    state.voiceCatalog={items:[
      {assignment_key:"voice:a",display_name:"Giọng A",source_kind:"preset",selectable:true,active:true},
      {assignment_key:"voice:b",display_name:"Giọng B",source_kind:"preset",selectable:true,active:true},
    ]};
    state.productionRange={bookId:71,fromChapter:101,toChapter:110,skipCompleted:true,readiness:{scope:{book_id:71,book_title:"Sách kiểm thử phạm vi",from_chapter:101,to_chapter:110,chapter_count:10},summary:{total:10,complete:1,ready_to_prepare:0},chapters}};
    state.runtimeIdentity={state:"canonical",label:"Dữ liệu kiểm thử"};
    state.runtimeIdentityResolved=true;

    const summary=()=>({
      total_chapters:10,
      ready_chapters:window.__rangeFixture.phase==="ready"?9:0,
      blocked_chapters:0,
      proposal_required_chapters:window.__rangeFixture.phase==="proposal"?10:0,
      speaker_exception_count:window.__rangeFixture.phase==="exceptions"?window.__rangeFixture.exceptions.length:0,
      voice_exception_count:window.__rangeFixture.phase==="voices"?window.__rangeFixture.voices.length:0,
      chapters_awaiting_speaker_approval:window.__rangeFixture.phase==="speakerApproval"?7:0,
      chapters_awaiting_casting_approval:window.__rangeFixture.phase==="castingApproval"?9:0,
      casting_generation_ready_chapters:window.__rangeFixture.phase==="castingGeneration"?9:0,
      inherited_voice_count:16,
      skipped_chapters:1,
    });
    const sections=type=>{
      const result={speaker:null,casting:null,range_prepare:null,render:null,qa:null};
      if(["PREPARE_RANGE_INPUTS","REVIEW_RANGE_SPEAKER_EXCEPTIONS","APPROVE_READY_SPEAKER_DRAFTS"].includes(type))result.speaker={
        summary:summary(),
        proposal_chapters:window.__rangeFixture.phase==="proposal"?chapters:[],
        exception_queue:window.__rangeFixture.phase==="exceptions"?window.__rangeFixture.exceptions:[],
        ready_drafts:window.__rangeFixture.phase==="speakerApproval"?window.__rangeFixture.readyDrafts:[],
        casting_generation_ready:window.__rangeFixture.phase==="castingGeneration"?window.__rangeFixture.plans.map(item=>({...item,draft_id:item.plan_id-400})):[],
      };
      if(["REVIEW_RANGE_VOICE_EXCEPTIONS","APPROVE_RANGE_CASTING_PLANS"].includes(type))result.casting={
        summary:summary(),
        voice_exception_queue:window.__rangeFixture.phase==="voices"?window.__rangeFixture.voices:[],
        plans_awaiting_approval:window.__rangeFixture.phase==="castingApproval"?window.__rangeFixture.plans:[],
      };
      if(type==="PREPARE_RANGE")result.range_prepare={book_id:71,from_chapter:101,to_chapter:110,chapter_count:10};
      return result;
    };
    window.__buildRangeProjection=()=>{
      const fixture=window.__rangeFixture,phase=fixture.phase;
      let type,title,label,stage=2,stageKey="speakers",affected=null;
      if(phase==="proposal"){type="PREPARE_RANGE_INPUTS";title="Chuẩn bị dữ liệu đầu vào";label="Chuẩn bị dữ liệu cho 10 chương"}
      else if(phase==="exceptions"){const item=fixture.exceptions[0],remaining=fixture.exceptions.filter(row=>row.chapter_id===item.chapter_id).length;type="REVIEW_RANGE_SPEAKER_EXCEPTIONS";title="Kiểm tra ngoại lệ người nói";label=remaining===1?"Lưu và duyệt chương":"Lưu và sang câu tiếp theo";affected={id:item.chapter_id,number:item.chapter_number,title:item.chapter_title}}
      else if(phase==="speakerApproval"){type="APPROVE_READY_SPEAKER_DRAFTS";title="Duyệt chương không có ngoại lệ";label="Duyệt 7 chương"}
      else if(phase==="voices"){type="REVIEW_RANGE_VOICE_EXCEPTIONS";title="Gán giọng cho ngoại lệ";label="Gán giọng cho "+fixture.voices.length+" người";stage=3;stageKey="voices";const item=fixture.voices[0];affected={id:item.chapter_id,number:item.chapter_number,title:item.chapter_title}}
      else if(phase==="castingGeneration"){type="PREPARE_RANGE_INPUTS";title="Tạo bản đồ giọng theo phạm vi";label="Chuẩn bị bản đồ giọng cho 9 chương";stage=3;stageKey="voice_map"}
      else if(phase==="castingApproval"){type="APPROVE_RANGE_CASTING_PLANS";title="Duyệt bản đồ giọng";label="Duyệt bản đồ giọng cho 9 chương";stage=3;stageKey="voice_map"}
      else {type="PREPARE_RANGE";title="Sẵn sàng chuẩn bị";label="Chuẩn bị 9 chương";stage=4;stageKey="prepare"}
      const key="fixture:"+phase+":"+(fixture.exceptions[0]?.utterance_id||fixture.voices[0]?.speaker_key||"range");
      const task={task_scope:affected?"exception":"range",task_type:type,task_key:key,user_stage:stage,title,summary:title,affected_chapter:affected,primary_action:{key:type,label,target:stageKey},blocker:null,next_task_hint:"Tiếp tục theo phạm vi.",technical_details:[],current_stage_key:stageKey,input_summary:summary(),...sections(type)};
      const queue=fixture.chapters.map(item=>({...item,canonical_task:affected&&item.chapter_id===affected.id,inspected:false}));
      return{range_identity:"book:71:101-110",chapter_queue:queue,queue,range_readiness:{scope:state.productionRange.readiness.scope,summary:summary()},phases:[],canonical_task:task,inspected_chapter:null,inspection_summary:null};
    };
    loadProductionTaskProjection=async()=>{
      state.productionProjection=window.__buildRangeProjection();
      state.productionProjectionKey=state.productionProjection.canonical_task.task_key;
      renderProductionShell();
      return state.productionProjection;
    };
    api=async(path,options={})=>{
      const fixture=window.__rangeFixture;
      const requestBody=options.body?JSON.parse(options.body):{};
      fixture.calls.push({path,method:options.method||"GET",commandType:requestBody.command_type||null});
      if(path==="/api/production/commands"){
        const type=requestBody.command_type;
        if(type==="PREPARE_RANGE_INPUTS"){
          if(fixture.phase==="proposal")fixture.phase="exceptions";
          else if(fixture.phase==="castingGeneration")fixture.phase="castingApproval";
        }else if(type==="SAVE_SPEAKER_DECISION"){
          fixture.exceptions.shift();
          if(!fixture.exceptions.length)fixture.phase="speakerApproval";
        }else if(type==="SAVE_VOICE_ASSIGNMENT"){
          fixture.voices.shift();
          if(!fixture.voices.length)fixture.phase="castingGeneration";
        }else if(type==="APPROVE_CASTING_PLANS"){
          fixture.phase="ready";
        }
        const projection=window.__buildRangeProjection();
        return{
          schema:"story-audio-production-command/v1",
          command_id:"pc-fixture-"+type.toLowerCase(),
          command_type:type,
          idempotency_key:requestBody.idempotency_key,
          scope:requestBody.scope,
          outcome:"APPLIED",
          submitted_count:1,
          applied_count:1,
          failed_count:0,
          applied_items:[{chapter_id:7101}],
          failed_items:[],
          operator_message:"Đã áp dụng thao tác.",
          resulting_task_projection:projection,
          resulting_preflight:null,
          asynchronous_reference:null,
          state_tokens:{task_projection:"fixture",preflight:null},
        };
      }
      return{};
    };
    loadProductionTaskProjection();
  })()`);

  const primaryLabel = () => evaluate(
    `document.querySelector("#productionPrimaryAction")?.textContent.trim()`
  );
  const clickPrimary = async () => {
    await evaluate(
      `Promise.resolve(document.querySelector("#productionPrimaryAction").onclick())`
    );
  };

  const scenarioAStart = await primaryLabel();
  await clickPrimary();
  const scenarioA = await evaluate(`({
    phase:__rangeFixture.phase,
    prepareCalls:__rangeFixture.calls.filter(item=>item.commandType==="PREPARE_RANGE_INPUTS").length,
    chapterOpenCalls:__rangeFixture.calls.filter(item=>item.path.startsWith("/api/chapters/")&&!item.path.includes("/reviews/")).length,
    next:document.querySelector("#productionPrimaryAction").textContent.trim()
  })`);

  await evaluate(`__rangeFixture.phase="speakerApproval";loadProductionTaskProjection()`);
  const scenarioBStart = await primaryLabel();
  await clickPrimary();
  const scenarioB = await evaluate(`({
    approvals:__rangeFixture.calls.filter(item=>item.commandType==="APPROVE_SPEAKER_DRAFTS").length,
    chapterRows:document.querySelectorAll(".production-queue-item").length
  })`);

  await evaluate(`(() => {
    const exception=(chapterOffset,sequence)=>({
      chapter_id:7101+chapterOffset,chapter_number:101+chapterOffset,chapter_title:"Chương "+(101+chapterOffset),draft_id:8101+chapterOffset,draft_fingerprint:"a".repeat(64),text_revision_id:9101+chapterOffset,utterance_id:"u"+chapterOffset+"-"+sequence,sequence,source_text:"Ngoại lệ "+sequence,context:[{text:"Trước"},{text:"Mục tiêu",is_target:true},{text:"Sau"}],detected_speaker:{speaker_type:"character",character_id:9901},reason:"Cần kiểm tra.",characters:[{id:9901,display_name:"Nhân vật A"}]
    });
    __rangeFixture.exceptions=[exception(0,1),exception(0,2),exception(1,1),exception(1,2),exception(2,1)];
    __rangeFixture.phase="exceptions";loadProductionTaskProjection();
  })()`);
  const scenarioDStart = await primaryLabel();
  await evaluate(`document.querySelector("#productionRangeSpeakerChoice").value="narrator"`);
  await clickPrimary();
  const scenarioD = await evaluate(`({
    remaining:__rangeFixture.exceptions.length,
    visible:document.querySelector("[data-range-exception]")?.dataset.rangeException,
    label:document.querySelector("#productionPrimaryAction").textContent.trim()
  })`);
  await evaluate(`document.querySelector("#productionRangeSpeakerChoice").value="narrator"`);
  await clickPrimary();
  const scenarioE = await evaluate(`({
    remaining:__rangeFixture.exceptions.length,
    speakerApprovalCalls:__rangeFixture.calls.filter(item=>item.commandType==="APPROVE_SPEAKER_DRAFTS").length,
    visible:document.querySelector("[data-range-exception]")?.dataset.rangeException
  })`);
  let exceptionRounds = 0;
  while (await evaluate(`__rangeFixture.phase==="exceptions"`)) {
    if (exceptionRounds++ >= 10) {
      throw new Error("Speaker exception journey did not converge.");
    }
    const remainingBefore = await evaluate(`__rangeFixture.exceptions.length`);
    await evaluate(`document.querySelector("#productionRangeSpeakerChoice").value="narrator"`);
    await clickPrimary();
    try {
      await poll(async () => evaluate(
        `__rangeFixture.phase!=="exceptions"||__rangeFixture.exceptions.length<${remainingBefore}`
      ), 5000);
    } catch (error) {
      const stalled = await evaluate(`({
        phase:__rangeFixture.phase,
        remaining:__rangeFixture.exceptions.length,
        primary:document.querySelector("#productionPrimaryAction")?.textContent,
        selected:document.querySelector("#productionRangeSpeakerChoice")?.value,
        lastCalls:__rangeFixture.calls.slice(-5),
      })`);
      throw new Error(`Speaker exception stalled: ${JSON.stringify({ remainingBefore, stalled })}`);
    }
  }
  const scenarioC = await evaluate(`({
    remaining:__rangeFixture.exceptions.length,
    phase:__rangeFixture.phase,
    current:document.querySelector("#productionCurrentStepHeading").textContent
  })`);

  await evaluate(`__rangeFixture.phase="voices";__rangeFixture.voices=[
    {chapter_id:7101,chapter_number:101,chapter_title:"Chương 101",speaker_key:"character:9901",speaker_name:"Nhân vật A",character_id:9901,current_voice_id:null,reason:"Nhân vật mới cần chọn giọng.",chapter_ids:[7101,7102],chapter_numbers:[101,102]},
    {chapter_id:7103,chapter_number:103,chapter_title:"Chương 103",speaker_key:"character:9902",speaker_name:"Nhân vật B",character_id:9902,current_voice_id:null,reason:"Mapping xung đột.",chapter_ids:[7103],chapter_numbers:[103]}
  ];loadProductionTaskProjection()`);
  const scenarioFG = await evaluate(`({
    summary:document.querySelector("#productionStateExplanation").textContent,
    body:document.querySelector("#productionTaskContent").innerText,
    visibleVoiceRows:document.querySelectorAll("[data-range-voice]").length,
    options:document.querySelector("#productionRangeVoiceChoice").options.length
  })`);
  await evaluate(`document.querySelector("#productionRangeVoiceChoice").value="voice:a"`);
  await clickPrimary();
  await evaluate(`document.querySelector("#productionRangeVoiceChoice").value="voice:b"`);
  await clickPrimary();
  const scenarioGEnd = await evaluate(`({
    phase:__rangeFixture.phase,
    label:document.querySelector("#productionPrimaryAction").textContent.trim()
  })`);

  await clickPrimary();
  const scenarioHStart = await primaryLabel();
  const scenarioCastingEvidence = await evaluate(`document.querySelector("#productionTaskContent").innerText`);
  const prepareUnavailableBeforeH = await evaluate(
    `!document.querySelector("#productionPrimaryAction").textContent.includes("Chuẩn bị 9 chương")`
  );
  await clickPrimary();
  const scenarioH = await evaluate(`({
    phase:__rangeFixture.phase,
    castingApprovalCalls:__rangeFixture.calls.filter(item=>item.commandType==="APPROVE_CASTING_PLANS").length,
    label:document.querySelector("#productionPrimaryAction").textContent.trim()
  })`);

  await evaluate(`(() => {
    __rangeFixture.phase="exceptions";
    __rangeFixture.exceptions=[{chapter_id:7101,chapter_number:101,chapter_title:"Chương 101",draft_id:8101,draft_fingerprint:"a".repeat(64),text_revision_id:9101,utterance_id:"polling-item",sequence:1,source_text:"Giữ nguyên lựa chọn.",context:[],detected_speaker:{speaker_type:"character",character_id:9901},reason:"Cần kiểm tra.",characters:[{id:9901,display_name:"Nhân vật A"}]}];
    loadProductionTaskProjection();
  })()`);
  const scenarioJ = await evaluate(`(async()=>{
    const select=document.querySelector("#productionRangeSpeakerChoice");
    select.value="unknown";
    select.focus();
    const key=state.productionProjection.canonical_task.task_key;
    for(let index=0;index<5;index+=1){
      await loadProductionTaskProjection({silent:true});
      await new Promise(resolve=>setTimeout(resolve,30));
      const evidence={
        index,
        keyStable:state.productionProjection.canonical_task.task_key===key,
        connected:select.isConnected,
        valueStable:select.value==="unknown",
        focusStable:document.activeElement===select,
        activeElement:document.activeElement?.id||document.activeElement?.tagName||null,
      };
      if(!evidence.keyStable||!evidence.connected||!evidence.valueStable||!evidence.focusStable)return{ok:false,...evidence};
    }
    return{ok:true};
  })()`);

  const layout1366 = await evaluate(`(() => {
    const primary=document.querySelector("#productionPrimaryAction").getBoundingClientRect();
    const nested=[...document.querySelectorAll("#productionWorkbench *")].filter(element=>{
      const style=getComputedStyle(element);
      return /(auto|scroll)/.test(style.overflowY)&&element.scrollHeight>element.clientHeight+2;
    }).map(element=>element.id||element.className);
    return{primaryVisible:primary.top>=0&&primary.bottom<=innerHeight,horizontal:document.documentElement.scrollWidth>innerWidth+1,nested};
  })()`);
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1920,
    height: 1080,
    deviceScaleFactor: 1,
    mobile: false,
  });
  const layout1920 = await evaluate(`(() => {
    const primary=document.querySelector("#productionPrimaryAction").getBoundingClientRect();
    return{primaryVisible:primary.top>=0&&primary.bottom<=innerHeight,horizontal:document.documentElement.scrollWidth>innerWidth+1};
  })()`);

  if (scenarioAStart !== "Chuẩn bị dữ liệu cho 10 chương"
      || scenarioA.phase !== "exceptions"
      || scenarioA.prepareCalls !== 1
      || scenarioA.chapterOpenCalls !== 1) {
    throw new Error(`Scenario A failed: ${JSON.stringify({ scenarioAStart, scenarioA })}`);
  }
  if (scenarioBStart !== "Duyệt 7 chương" || scenarioB.approvals < 1) {
    throw new Error(`Scenario B failed: ${JSON.stringify({ scenarioBStart, scenarioB })}`);
  }
  if (scenarioDStart !== "Lưu và sang câu tiếp theo"
      || scenarioD.remaining !== 4
      || scenarioD.visible === "u0-1") {
    throw new Error(`Scenario D failed: ${JSON.stringify({ scenarioDStart, scenarioD })}`);
  }
  if (scenarioE.remaining !== 3 || scenarioE.speakerApprovalCalls < 2) {
    throw new Error(`Scenario E failed: ${JSON.stringify(scenarioE)}`);
  }
  if (scenarioC.remaining !== 0 || scenarioC.phase !== "speakerApproval") {
    throw new Error(`Scenario C failed: ${JSON.stringify(scenarioC)}`);
  }
  if (!scenarioFG.body.includes("16")
      || !scenarioFG.body.includes("2")
      || scenarioFG.visibleVoiceRows !== 1
      || scenarioFG.options < 2
      || scenarioGEnd.phase !== "castingGeneration") {
    throw new Error(`Scenarios F/G failed: ${JSON.stringify({ scenarioFG, scenarioGEnd })}`);
  }
  if (scenarioHStart !== "Duyệt bản đồ giọng cho 9 chương"
      || !prepareUnavailableBeforeH
      || scenarioH.phase !== "ready"
      || scenarioH.castingApprovalCalls !== 1
      || scenarioH.label !== "Chuẩn bị 9 chương") {
    throw new Error(`Scenarios H/I failed: ${JSON.stringify({ scenarioHStart, prepareUnavailableBeforeH, scenarioH })}`);
  }
  if (!scenarioCastingEvidence.includes("Nhân vật A")
      || !scenarioCastingEvidence.includes("Giọng chỉ huy")
      || !scenarioCastingEvidence.includes("override")
      || !scenarioCastingEvidence.toLocaleLowerCase("vi").includes("số câu")
      || !scenarioCastingEvidence.includes("thay thế mapping")) {
    throw new Error(`Casting approval evidence is incomplete: ${scenarioCastingEvidence}`);
  }
  if (!scenarioJ.ok) throw new Error(`Scenario J failed: ${JSON.stringify(scenarioJ)}`);
  if (!layout1366.primaryVisible || layout1366.horizontal || layout1366.nested.length) {
    throw new Error(`1366 layout failed: ${JSON.stringify(layout1366)}`);
  }
  if (!layout1920.primaryVisible || layout1920.horizontal) {
    throw new Error(`1920 layout failed: ${JSON.stringify(layout1920)}`);
  }
  if (browserErrors.length) {
    throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);
  }

  process.stdout.write(JSON.stringify({
    ok: true,
    scenarioA,
    scenarioB,
    scenarioC,
    scenarioD,
    scenarioE,
    scenarioFG,
    scenarioGEnd,
    scenarioCastingEvidence,
    scenarioH,
    scenarioJ,
    layout1366,
    layout1920,
  }));
} finally {
  try { socket?.close(); } catch {}
  const browserExited = new Promise(resolve => {
    if (child.exitCode !== null) resolve();
    else child.once("exit", resolve);
  });
  child.kill();
  await Promise.race([browserExited, delay(3000)]);
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      await rm(profile, { recursive: true, force: true });
      break;
    } catch (error) {
      if (!["EBUSY", "EPERM"].includes(error?.code) || attempt === 29) throw error;
      await delay(200);
    }
  }
}
