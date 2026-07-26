import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const baseUrl = process.argv[2];
if (!baseUrl) throw new Error("Usage: node scripts/browser_production_workflow_smoke.mjs <base-url>");

const browserExe = [
  process.env.STORY_AUDIO_BROWSER_EXE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");

const profile = await mkdtemp(join(tmpdir(), "story-audio-workflow-browser-"));
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
  const port = await poll(async () => {
    const content = await readFile(join(profile, "DevToolsActivePort"), "utf8");
    return Number(content.split(/\r?\n/)[0]) || null;
  });
  const page = await poll(async () => {
    const response = await fetch(`http://127.0.0.1:${port}/json/list`);
    const pages = await response.json();
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
      browserErrors.push(message.params?.exceptionDetails?.text || "runtime exception");
    }
    if (message.method === "Runtime.consoleAPICalled" && message.params?.type === "error") {
      browserErrors.push((message.params.args || []).map(item => item.value || item.description).join(" "));
    }
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolve(message.result);
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
  const waitFor = (expression, timeoutMs = 10000) =>
    poll(async () => (await evaluate(expression)) || null, timeoutMs);

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1366,
    height: 768,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await waitFor(`document.readyState==="complete"`);
  await waitFor(`document.querySelector("#productionStateCard")?.dataset.productionState==="NO_SCOPE"`);

  const baseFixture = {
    book: { id: 1, title: "Sách kiểm thử" },
    dialog: {
      chapter: {
        id: 1401,
        book_id: 1,
        chapter_number: 401,
        title: "Chương kiểm thử",
        active_text_revision_id: 9001,
        audio_status: "not_created",
      },
      revisions: [{ id: 9001, status: "approved", kind: "reflowed", char_count: 240, text: "Nội dung kiểm thử." }],
      qa_issues: [],
      active_output: {},
      audio_artifact: null,
      human_approval: null,
    },
    casting: {
      chapter: { id: 1401, book_id: 1, title: "Chương kiểm thử" },
      characters: [],
      voice_profile: {
        profile: { narrator_voice_id: "voice:test" },
        validation: { valid: true },
        narrator_resolution: { resolved_voice_id: "voice:test", resolution_source: "narrator", needs_review: false },
      },
      casting: {
        id: 31,
        chapter_id: 1401,
        text_revision_id: 9001,
        plan_revision: 1,
        status: "approved",
        narrator_voice_id: "voice:test",
        plan: {
          source_metadata: { review: { review_completed: true, remaining_unreviewed_count: 0 } },
          utterances: [
            { utterance_id: "u1", sequence: 1, role: "narrator", character_id: null, resolved_voice_id: "voice:test", resolution_source: "narrator", resolved_gender: "unknown", needs_review: false, text: "Dòng thứ nhất." },
            { utterance_id: "u2", sequence: 2, role: "narrator", character_id: null, resolved_voice_id: "voice:test", resolution_source: "narrator", resolved_gender: "unknown", needs_review: false, text: "Dòng thứ hai." },
          ],
        },
      },
    },
    voiceCatalog: {
      items: [{
        assignment_key: "voice:test",
        display_name: "Giọng chỉ huy",
        source_kind: "preset",
        selectable: true,
        active: true,
        provenance_summary: "Giọng kiểm thử cô lập",
      }],
    },
  };

  async function showScenario(name, overrides = {}) {
    const fixture = structuredClone(baseFixture);
    fixture.name = name;
    Object.assign(fixture, overrides);
    return evaluate(`(() => {
      const fixture=${JSON.stringify(fixture)};
      state.book=fixture.book;
      state.dialog=fixture.dialog;
      state.casting=fixture.casting;
      state.voiceCatalog=fixture.voiceCatalog;
      state.jobs=fixture.jobs||[];
      state.speakerReview={chapterId:fixture.dialog.chapter.id,drafts:[],draft:null,decisions:{},selected:{},generation:null};
      state.productionRange={bookId:1,fromChapter:fixture.dialog.chapter.chapter_number,toChapter:fixture.dialog.chapter.chapter_number,chapterId:fixture.dialog.chapter.id,skipCompleted:false};
      state.runtimeIdentity={state:"isolated",label:"Dữ liệu kiểm thử"};
      state.runtimeIdentityResolved=true;
      setupProductionWorkspace();
      document.querySelector("#castingPanel")?.classList.remove("hidden");
      renderProductionShell();
      applyCastingOperatorSummary();
      const body=document.querySelector('[data-app-view="production"]').innerText;
      const primary=document.querySelector("#productionPrimaryAction");
      const rect=primary.getBoundingClientRect();
      const nested=[...document.querySelectorAll("#productionPhaseWorkspace *")].filter(el=>{
        const style=getComputedStyle(el);
        return /(auto|scroll)/.test(style.overflowY)&&el.scrollHeight>el.clientHeight+2;
      }).map(el=>el.id||el.className);
      return {
        name:fixture.name,
        state:document.querySelector("#productionStateCard")?.dataset.productionState,
        phase:document.querySelector("#productionStateBadge")?.textContent,
        primary:primary?.textContent,
        primaryVisible:rect.top>=0&&rect.bottom<=innerHeight,
        summary:document.querySelector("#productionStateExplanation")?.textContent,
        renderStatus:document.querySelector("#flowRenderStatus")?.textContent,
        renderSummary:document.querySelector("#flowRenderSummary")?.innerText,
        qaStatus:document.querySelector("#flowAudioStatus")?.textContent,
        accept:document.querySelector("#flowFinalizeOutput")?.textContent,
        needsFixes:document.querySelector("#flowNeedsFixes")?.textContent,
        audioVisible:!document.querySelector("#audioBox")?.classList.contains("hidden"),
        dialogOpen:document.querySelector("#textDialog")?.open===true,
        nested,
        body,
      };
    })()`);
  }

  const draftFixture = structuredClone(baseFixture.casting);
  draftFixture.casting.status = "draft";
  const castingReview = await showScenario("casting-review", { casting: draftFixture });
  const ready = await showScenario("ready-to-prepare");
  const prepared = await showScenario("prepared", {
    jobs: [{ id: 501, book_id: 1, from_chapter: 401, to_chapter: 401, casting_plan_id: 31, status: "prepared" }],
  });
  const running = await showScenario("running", {
    jobs: [{ id: 502, book_id: 1, from_chapter: 401, to_chapter: 401, casting_plan_id: 31, status: "running", total_chapters: 1, completed_chapters: 0, total_segments: 8, completed_segments: 3, failed_segments: 0, pending_segments: 5, current_stage: "synthesizing", actions: { can_retry: false, can_resume: false } }],
  });
  const failed = await showScenario("failed", {
    jobs: [{ id: 503, book_id: 1, from_chapter: 401, to_chapter: 401, casting_plan_id: 31, status: "failed", total_chapters: 1, completed_chapters: 0, total_segments: 8, completed_segments: 6, failed_segments: 1, pending_segments: 1, current_stage: "synthesizing", error_message: "sqlite traceback secret=do-not-render", actions: { can_retry: true, can_resume: false }, is_historical_output: false }],
  });
  const qaDialog = structuredClone(baseFixture.dialog);
  qaDialog.chapter.audio_status = "completed";
  qaDialog.chapter.active_audio_artifact_id = 701;
  qaDialog.active_output = { active_output_job_id: 504, active_output_artifact_id: 701, active_output_casting_plan_revision: 1 };
  qaDialog.audio_artifact = { id: 701, duration_ms: 65432, path: "fixture/chapter.m4a" };
  const qa = await showScenario("qa", { dialog: qaDialog });

  const expected = [
    [castingReview, "CASTING_REVIEW", "Duyệt và tiếp tục"],
    [ready, "READY_TO_PREPARE", "Chuẩn bị"],
    [prepared, "PREPARED", "Bắt đầu render"],
    [running, "RENDERING_OR_PAUSED", "Theo dõi tiến độ"],
    [failed, "RENDERING_OR_PAUSED", "Theo dõi tiến độ"],
    [qa, "RENDERED_NOT_QA", "Cần nghe và duyệt"],
  ];
  for (const [scenario, stateName, primary] of expected) {
    if (scenario.state !== stateName || scenario.primary !== primary || !scenario.primaryVisible) {
      throw new Error(`Unexpected ${scenario.name} state: ${JSON.stringify(scenario)}`);
    }
    if (scenario.dialogOpen || scenario.nested.length) {
      throw new Error(`Long modal or nested scroll found in ${scenario.name}: ${JSON.stringify(scenario.nested)}`);
    }
  }
  if (!ready.body.includes("Đã duyệt") || !ready.summary.includes("Chưa gọi TTS")) {
    throw new Error("Approved casting did not explain the safe preparation boundary.");
  }
  if (prepared.renderStatus !== "Sẵn sàng render" || !prepared.body.includes("Bắt đầu render")) {
    throw new Error("Prepared state did not expose the separate render action.");
  }
  if (!running.renderSummary.includes("3") || !running.renderSummary.includes("5")) {
    throw new Error("Running progress did not show completed and pending segment counts.");
  }
  if (!failed.body.includes("có thể tiếp tục") || /sqlite|traceback|do-not-render/i.test(failed.body)) {
    throw new Error("Failed state exposed raw diagnostics or omitted its recoverable action.");
  }
  if (!qa.audioVisible || qa.accept !== "Chấp nhận" || qa.needsFixes !== "Cần sửa") {
    throw new Error("QA controls were not clear.");
  }
  const mojibake = /Ãƒ|Ã„|Ã¡Â»|Ã¡Âº|Ã†|\uFFFD/;
  if (expected.some(([scenario]) => mojibake.test(scenario.body))) {
    throw new Error("Rendered Production UI contains mojibake.");
  }

  await send("Emulation.setDeviceMetricsOverride", {
    width: 1920,
    height: 1080,
    deviceScaleFactor: 1,
    mobile: false,
  });
  const layout1920 = await evaluate(`(() => {
    const cta=document.querySelector("#productionPrimaryAction").getBoundingClientRect();
    return {primaryVisible:cta.top>=0&&cta.bottom<=innerHeight,horizontal:document.documentElement.scrollWidth>innerWidth+1};
  })()`);
  if (!layout1920.primaryVisible || layout1920.horizontal) {
    throw new Error(`1920 workflow layout failed: ${JSON.stringify(layout1920)}`);
  }
  if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);

  process.stdout.write(JSON.stringify({
    ok: true,
    castingReview,
    ready,
    prepared,
    running,
    failed,
    qa,
    layout1920,
  }));
} finally {
  try {
    socket?.close();
  } catch {}
  child.kill();
  for (let attempt = 0; attempt < 10; attempt += 1) {
    try {
      await rm(profile, { recursive: true, force: true });
      break;
    } catch (error) {
      if (error?.code !== "EBUSY" || attempt === 9) throw error;
      await delay(100);
    }
  }
}
