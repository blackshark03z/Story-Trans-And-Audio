import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const base = process.argv[2];
if (!base) throw new Error("Usage: node scripts/browser_repeat_use_lifecycle_smoke.mjs <base-url>");
const evidenceDir = process.argv[3] || null;

const executable = [
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].find(existsSync);
if (!executable) throw new Error("No Chromium browser found");

const profile = await mkdtemp(join(tmpdir(), "story-audio-repeat-use-"));
const child = spawn(executable, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--remote-debugging-port=0",
  `--user-data-dir=${profile}`,
  `${base}/#/production?book=1&from=3&to=8&skip_completed=1`,
], { stdio: "ignore" });

const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
async function poll(fn, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const value = await fn();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await sleep(100);
  }
  throw lastError || new Error("timeout");
}

let socket;
try {
  const port = await poll(async () => Number((await readFile(join(profile, "DevToolsActivePort"), "utf8")).split(/\r?\n/)[0]) || null);
  const page = await poll(async () => {
    const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    return pages.find(item => item.type === "page" && item.url.startsWith(base));
  });
  socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  let nextId = 1;
  const pending = new Map();
  const browserErrors = [];
  const mutatingRequests = [];
  let recordMutations = false;
  socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (message.method === "Runtime.exceptionThrown") {
      browserErrors.push(message.params?.exceptionDetails?.exception?.description || message.params?.exceptionDetails?.text || "exception");
    }
    if (message.method === "Runtime.consoleAPICalled" && message.params?.type === "error") {
      browserErrors.push((message.params.args || []).map(arg => arg.value || arg.description || "").join(" "));
    }
    if (message.method === "Network.requestWillBeSent" && recordMutations) {
      const request = message.params?.request || {};
      if (!["GET", "HEAD", "OPTIONS"].includes(String(request.method || "").toUpperCase())) {
        mutatingRequests.push({ method: request.method, url: request.url });
      }
    }
    if (!message.id || !pending.has(message.id)) return;
    const waiter = pending.get(message.id);
    pending.delete(message.id);
    message.error ? waiter.reject(new Error(message.error.message)) : waiter.resolve(message.result);
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
  const screenshot = async (name, width, height) => {
    if (!evidenceDir) return null;
    await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
    const result = await send("Page.captureScreenshot", { format: "png", fromSurface: true });
    await mkdir(evidenceDir, { recursive: true });
    const path = join(evidenceDir, `${name}.png`);
    await writeFile(path, Buffer.from(result.data, "base64"));
    return path;
  };

  await send("Runtime.enable");
  await send("Network.enable");
  await poll(() => evaluate("document.readyState === 'complete' && !!window.storyAudioAppState"));
  await poll(() => evaluate("state.productionProjection?.canonical_task?.task_type === 'COMPLETE' && state.productionRange?.readiness?.chapters?.length === 6 && state.productionRange.readiness.chapters.every(row => row.state === 'COMPLETE')"));

  const snapshot = () => evaluate(`(async () => {
    const readiness = await fetch('/api/production/range-readiness?book_id=1&from_chapter=3&to_chapter=8').then(response => response.json());
    const library = await fetch('/api/audio-library').then(response => response.json());
    const rows = (readiness.chapters || []).map(row => ({
      chapter: row.chapter_number,
      state: row.state,
      artifact: row.active_artifact_id || row.active_output_artifact_id || null,
    }));
    const identities = new Map((library.items || []).map(item => [Number(item.artifact_id), {
      artifact: Number(item.artifact_id),
      sha256: item.sha256,
      sizeBytes: Number(item.size_bytes),
    }]));
    return rows.map(row => ({ ...row, ...identities.get(Number(row.artifact)) }));
  })()`);

  const before = {
    hash: await evaluate("location.hash"),
    context: await evaluate("currentProductionWorkingContext()"),
    task: await evaluate("state.productionProjection?.canonical_task?.task_type"),
    nextVisible: await evaluate("document.querySelector('#ownerStartNextProduction')?.offsetParent !== null"),
    artifacts: await snapshot(),
  };

  await evaluate("document.querySelector('[data-app-route=\"assignment\"]').click()");
  await poll(() => evaluate("state.currentRoute === 'assignment'"));
  await poll(() => evaluate("document.querySelector('#assignmentLifecycleNotice')?.offsetParent !== null"));
  const assignment = await evaluate(`({
    hash: location.hash,
    notice: document.querySelector('#assignmentLifecycleNotice')?.innerText?.trim(),
    startVisible: document.querySelector('#assignmentStartNextProduction')?.offsetParent !== null,
  })`);

  await send("Page.reload", { ignoreCache: true });
  await poll(() => evaluate("document.readyState === 'complete' && document.querySelector('#assignmentLifecycleNotice')?.offsetParent !== null"));
  await poll(() => evaluate("state.bookVoiceRegistry?.status === 'ready'"));
  const assignmentAfterReload = await evaluate(`({
    hash: location.hash,
    notice: document.querySelector('#assignmentLifecycleNotice')?.innerText?.trim(),
    startVisible: document.querySelector('#assignmentStartNextProduction')?.offsetParent !== null,
    registryStatus: state.bookVoiceRegistry?.status,
    registryError: state.bookVoiceRegistry?.error,
  })`);
  const assignmentScreenshot = await screenshot("repeat-use-assignment-complete-1366x768", 1366, 768);

  await evaluate(`(()=>{state.productionPreflight={stale:true};state.productionPrepare={readiness:{stale:true},status:'ready',result:{stale:true},error:'old',clientRequestId:'old',submitting:false};state.productionRepair={taskKey:'old',mode:'plan',markers:[{time:1}]};state.productionQaNoteDraft='old qa note';state.productionQaComparisonArtifactId=999;state.audioQa={history:[{id:1}],loading:false,markers:[{time:2}]};state.audioArchive.selectedChapterIds=[77];state.audioLibrary.selectedArtifactId=88;state.audioLibrary.videoExports={88:{stale:true}};sessionStorage.setItem(REPAIR_PLAN_OPEN_STORAGE_KEY,'777')})()`);
  recordMutations = true;
  await evaluate("document.querySelector('#assignmentStartNextProduction').click()");
  await poll(() => evaluate("state.currentRoute === 'production' && document.querySelector('#productionScopeDialog')?.open === true"));
  await poll(() => evaluate("state.productionScopeSelection?.loadingChapters === false"));
  const afterStart = await evaluate(`({
    hash: location.hash,
    context: currentProductionWorkingContext(),
    range: state.productionRange,
    bookId: state.book?.id,
    selection: {
      bookId: state.productionScopeSelection?.bookId,
      from: state.productionScopeSelection?.fromChapter,
      to: state.productionScopeSelection?.toChapter,
      skipCompleted: state.productionScopeSelection?.skipCompleted,
    },
    storage: {
      range: localStorage.getItem(PRODUCTION_RANGE_SCOPE_STORAGE_KEY),
      working: localStorage.getItem(PRODUCTION_WORKING_CONTEXT_STORAGE_KEY),
      assignment: localStorage.getItem(ASSIGNMENT_CONTEXT_STORAGE_KEY),
      sessionWorking: sessionStorage.getItem(PRODUCTION_WORKING_CONTEXT_STORAGE_KEY),
      repairOpen: sessionStorage.getItem(REPAIR_PLAN_OPEN_STORAGE_KEY),
    },
    transient: {
      preflight: state.productionPreflight,
      prepareResult: state.productionPrepare?.result,
      repairMarkers: state.productionRepair?.markers?.length,
      qaNote: state.productionQaNoteDraft,
      qaComparison: state.productionQaComparisonArtifactId,
      qaHistory: state.audioQa?.history?.length,
      qaMarkers: state.audioQa?.markers?.length,
      archiveSelection: state.audioArchive?.selectedChapterIds?.length,
      selectedArtifactId: state.audioLibrary?.selectedArtifactId,
      videoExports: Object.keys(state.audioLibrary?.videoExports||{}).length,
    },
  })`);
  const nextScopeScreenshot = await screenshot("repeat-use-next-scope-820x900", 820, 900);

  await evaluate("document.querySelector('#cancelProductionScope').click()");
  await poll(() => evaluate("document.querySelector('#productionScopeDialog')?.open === false"));
  await evaluate("document.querySelector('[data-app-route=\"audio\"]').click()");
  await poll(() => evaluate("state.currentRoute === 'audio'"));
  await evaluate("document.querySelector('[data-app-route=\"assignment\"]').click()");
  await poll(() => evaluate("state.currentRoute === 'assignment'"));
  const assignmentAfterCancel = await evaluate(`({
    hash: location.hash,
    context: currentProductionWorkingContext(),
    range: state.productionRange,
    scope: document.querySelector('#assignmentScope')?.textContent?.trim(),
  })`);
  await evaluate("document.querySelector('[data-app-route=\"production\"]').click()");
  await poll(() => evaluate("state.currentRoute === 'production'"));
  await send("Page.reload", { ignoreCache: true });
  await poll(() => evaluate("document.readyState === 'complete' && !!window.storyAudioAppState"));
  await sleep(500);
  const afterReentry = await evaluate(`({
    hash: location.hash,
    context: currentProductionWorkingContext(),
    range: state.productionRange,
    storage: {
      range: localStorage.getItem(PRODUCTION_RANGE_SCOPE_STORAGE_KEY),
      working: localStorage.getItem(PRODUCTION_WORKING_CONTEXT_STORAGE_KEY),
      assignment: localStorage.getItem(ASSIGNMENT_CONTEXT_STORAGE_KEY),
      sessionWorking: sessionStorage.getItem(PRODUCTION_WORKING_CONTEXT_STORAGE_KEY),
    },
  })`);
  const artifactsAfter = await snapshot();
  recordMutations = false;

  const artifactsUnchanged = JSON.stringify(before.artifacts) === JSON.stringify(artifactsAfter);
  const storageCleared = values => Object.values(values).every(value => value === null);
  const transientCleared = value => value.preflight === null && value.prepareResult === null && value.repairMarkers === 0 && value.qaNote === '' && value.qaComparison === null && value.qaHistory === 0 && value.qaMarkers === 0 && value.archiveSelection === 0 && value.selectedArtifactId === null && value.videoExports === 0;
  const ok = before.task === "COMPLETE" && before.nextVisible &&
    assignment.startVisible && assignment.notice.includes("snapshot giọng của Job cũ không thay đổi") &&
    assignmentAfterReload.startVisible && assignmentAfterReload.registryStatus === "ready" && !assignmentAfterReload.registryError &&
    afterStart.hash === "#/production" && afterStart.context === null && afterStart.range === null &&
    Number(afterStart.bookId) === 1 && Number(afterStart.selection.bookId) === 1 &&
    Number(afterStart.selection.from) === 9 && Number(afterStart.selection.to) === 14 &&
    afterStart.selection.skipCompleted === true && storageCleared(afterStart.storage) && transientCleared(afterStart.transient) &&
    assignmentAfterCancel.hash === "#/assignment" && assignmentAfterCancel.context === null && assignmentAfterCancel.range === null &&
    afterReentry.hash === "#/production" && afterReentry.context === null && afterReentry.range === null &&
    storageCleared(afterReentry.storage) && artifactsUnchanged &&
    mutatingRequests.length === 0 && browserErrors.length === 0;

  console.log(JSON.stringify({
    ok,
    before,
    assignment,
    assignmentAfterReload,
    screenshots: { assignmentScreenshot, nextScopeScreenshot },
    afterStart,
    assignmentAfterCancel,
    afterReentry,
    artifactsAfter,
    artifactsUnchanged,
    mutatingRequests,
    browserErrors,
  }, null, 2));
  if (!ok) process.exitCode = 2;
} finally {
  try { socket?.close(); } catch {}
  try { child.kill("SIGKILL"); } catch {}
  await sleep(300);
  await rm(profile, { recursive: true, force: true }).catch(() => {});
}
