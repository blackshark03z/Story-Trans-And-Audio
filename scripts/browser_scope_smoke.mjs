import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const baseUrl = process.argv[2];
if (!baseUrl) throw new Error("Usage: node scripts/browser_scope_smoke.mjs <base-url>");

const candidates = [
  process.env.STORY_AUDIO_BROWSER_EXE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);
const browserExe = candidates.find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");

const profile = await mkdtemp(join(tmpdir(), "story-audio-browser-"));
const child = spawn(
  browserExe,
  [
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--remote-debugging-port=0",
    `--user-data-dir=${profile}`,
    `${baseUrl}/#/production`,
  ],
  { stdio: "ignore" },
);

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
  socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolve(message.result);
  });
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
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
        result.exceptionDetails.exception?.description || result.exceptionDetails.text,
      );
    }
    return result.result.value;
  };
  const waitFor = (expression, timeoutMs = 10000) =>
    poll(async () => (await evaluate(expression)) || null, timeoutMs);
  const click = selector =>
    evaluate(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); if(!el) throw new Error(${JSON.stringify(`Missing ${selector}`)}); el.click(); return true; })()`);
  const input = (selector, value) =>
    evaluate(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); if(!el) throw new Error(${JSON.stringify(`Missing ${selector}`)}); el.value=${JSON.stringify(value)}; el.dispatchEvent(new Event("input",{bubbles:true})); return true; })()`);

  const browserErrors = [];
  socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (message.method === "Runtime.exceptionThrown") {
      browserErrors.push(message.params?.exceptionDetails?.text || "runtime exception");
    }
    if (message.method === "Runtime.consoleAPICalled" && message.params?.type === "error") {
      browserErrors.push((message.params.args || []).map(item => item.value || item.description).join(" "));
    }
  });
  const key = (selector, keyboardKey) =>
    evaluate(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); if(!el) throw new Error(${JSON.stringify(`Missing ${selector}`)}); el.focus(); el.dispatchEvent(new KeyboardEvent("keydown",{key:${JSON.stringify(keyboardKey)},bubbles:true})); return true; })()`);

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
  await waitFor(`document.readyState==="complete"`);
  await waitFor(`document.querySelector("#productionPrimaryAction")?.textContent==="Chọn sách và chương"`);
  await waitFor(`!document.querySelector("#globalRuntimeState")?.textContent.includes("kiểm tra")`);
  const primaryLabelsAreHuman = await evaluate(`!document.body.innerText.includes("NO_SCOPE")&&!document.body.innerText.includes("AUTH_CONFIGURED")`);
  if (!primaryLabelsAreHuman) throw new Error("Raw runtime enums leaked into the primary UI.");

  await click("#productionPrimaryAction");
  await waitFor(`document.querySelector("#productionScopeDialog")?.open===true`);
  const bookCount = await evaluate(`document.querySelectorAll("#scopeBookList .scope-book-card").length`);
  if (bookCount !== 2) throw new Error(`Expected 2 books, received ${bookCount}.`);

  await input("#scopeBookSearch", "");
  await click('[data-scope-book-id="1"]');
  await waitFor(`document.querySelectorAll("#scopeChapterList .scope-chapter-card").length===6`);
  const firstPage = await evaluate(`document.querySelector("#scopeChapterPageInfo")?.textContent`);
  if (firstPage !== "1-6 / 45") throw new Error(`Unexpected pagination: ${firstPage}`);

  await input("#scopeFromChapter", "372");
  await waitFor(`document.querySelector("#scopeToChapter")?.value==="372"`);
  const oneChapterReady = await evaluate(`document.querySelector("#reviewProductionScope")?.disabled===false&&document.querySelector("#scopeSelectionSummary strong")?.textContent.includes("Chương 372")`);
  if (!oneChapterReady) throw new Error("Direct one-chapter entry was not ready.");

  await input("#scopeToChapter", "373");
  await waitFor(`document.querySelector("#scopeSingleChapter")?.checked===false`);
  await click("#scopeSkipCompleted");
  await click("#reviewProductionScope");
  await waitFor(`document.querySelector("#productionScopeDialog")?.open===false`);
  await waitFor(`location.hash.includes("book=1")&&location.hash.includes("from=372")&&location.hash.includes("to=373")`);
  const confirmedCount = 2;

  await click("#productionChangeScope");
  await waitFor(`document.querySelector("#productionScopeDialog")?.open===true`);
  await input("#scopeFromChapter", "372");
  await click('[data-scope-quick="5"]');
  await waitFor(`document.querySelector("#scopeToChapter")?.value==="376"`);
  await click('[data-scope-quick="10"]');
  await waitFor(`document.querySelector("#scopeToChapter")?.value==="381"`);
  await click('[data-scope-quick="1"]');
  await waitFor(`document.querySelector("#scopeToChapter")?.value==="372"&&document.querySelector("#scopeSingleChapter")?.checked===true`);

  await click("#scopeChapterBrowser summary");
  const browserOpenLayout = await evaluate(`(() => {
    const cta=document.querySelector("#reviewProductionScope").getBoundingClientRect();
    return {ctaVisible:cta.top>=0&&cta.bottom<=innerHeight,horizontal:document.documentElement.scrollWidth>innerWidth+1};
  })()`);
  if (!browserOpenLayout.ctaVisible || browserOpenLayout.horizontal) {
    throw new Error(`Open chapter browser hid the primary action: ${JSON.stringify(browserOpenLayout)}`);
  }
  await input("#scopeChapterSearch", "Chapter 372");
  await waitFor(`document.querySelector("#scopeChapterPageInfo")?.textContent==="1-1 / 1"`);
  await click('[data-scope-chapter-number="372"]');
  const rowSelectionWorks = await evaluate(`document.querySelector("#scopeFromChapter")?.value==="372"&&document.querySelector("#scopeToChapter")?.value==="372"`);
  if (!rowSelectionWorks) throw new Error("Clicking a chapter row did not select it.");

  await input("#scopeBookSearch", "");
  await click('[data-scope-book-id="2"]');
  await waitFor(`document.querySelector("#scopeChapterList .scope-chapter-card strong")?.textContent.includes("Pilot Chapter")===true`);
  const changedBook = await evaluate(`({
    chapters:[...document.querySelectorAll("#scopeChapterList .scope-chapter-card strong")].map(el=>el.textContent),
    from:document.querySelector("#scopeFromChapter")?.value,
    to:document.querySelector("#scopeToChapter")?.value
  })`);
  if (changedBook.chapters.some(text => text.includes("372")) || changedBook.from || changedBook.to) {
    throw new Error("Changing books leaked stale chapter state.");
  }

  await input("#scopeBookSearch", "");
  await click('[data-scope-book-id="1"]');
  await waitFor(`document.querySelector("#scopeChapterPageInfo")?.textContent==="1-6 / 45"`);
  await input("#scopeChapterSearch", "__slow__");
  await delay(240);
  await input("#scopeBookSearch", "");
  await click('[data-scope-book-id="2"]');
  await waitFor(`document.querySelector("#scopeChapterPageInfo")?.textContent==="1-1 / 1"`);
  await delay(450);
  const staleResponseIgnored = await evaluate(`document.querySelector("#scopeChapterList .scope-chapter-card strong")?.textContent.includes("Pilot Chapter")===true`);
  if (!staleResponseIgnored) throw new Error("A stale chapter response replaced the newly selected book.");

  await input("#scopeChapterSearch", "__fail__");
  await waitFor(`!document.querySelector("#scopeChaptersError")?.classList.contains("hidden")`);
  const apiErrorVisible = await evaluate(`document.querySelector("#scopeChaptersError")?.textContent.includes("Bạn vẫn có thể nhập số chương trực tiếp")`);
  const technicalErrorAvailable = await evaluate(`document.querySelector("#scopeTechnicalErrorText")?.textContent.includes("fixture chapter failure")`);
  if (!apiErrorVisible || !technicalErrorAvailable) throw new Error("Chapter API failure was not explained safely.");

  await input("#scopeBookSearch", "Fixture Book");
  await key("#scopeBookSearch", "Enter");
  await waitFor(`document.querySelector("#scopeChapterPageInfo")?.textContent==="1-6 / 45"`);
  const recoveredErrorHidden = await evaluate(`document.querySelector("#scopeChaptersError")?.classList.contains("hidden")===true`);
  if (!recoveredErrorHidden) throw new Error("A resolved chapter API error remained visible.");

  await input("#scopeFromChapter", "372");
  await input("#scopeToChapter", "373");
  await key("#scopeToChapter", "Enter");
  await waitFor(`document.querySelector("#productionScopeDialog")?.open===false`);
  await waitFor(`document.querySelector("#productionScopeSummary")?.textContent.includes("372-373")`);
  const keyboardWorkflow = true;

  await send("Page.reload", { ignoreCache: true });
  await waitFor(`document.readyState==="complete"`);
  await waitFor(`document.querySelector("#productionScopeSummary")?.textContent.includes("372-373")`);
  const skipCompletedRestored = await evaluate(`location.hash.includes("skip_completed=1")&&document.querySelector("#skipCompleted")?.checked===true`);
  if (!skipCompletedRestored) throw new Error("Skip-completed scope state was not restored.");

  await click("#productionChangeScope");
  await waitFor(`document.querySelector("#productionScopeDialog")?.open===true`);
  const layout1366 = await evaluate(`(() => {
    const cta=document.querySelector("#reviewProductionScope").getBoundingClientRect();
    const scrolling=[...document.querySelectorAll("#productionScopeDialog *")].filter(el=>{const s=getComputedStyle(el);return /(auto|scroll)/.test(s.overflowY)&&el.scrollHeight>el.clientHeight+2}).map(el=>el.id||el.className);
    return {ctaVisible:cta.top>=0&&cta.bottom<=innerHeight,horizontal:document.documentElement.scrollWidth>innerWidth+1,nestedScrolling:scrolling};
  })()`);
  if (!layout1366.ctaVisible || layout1366.horizontal || layout1366.nestedScrolling.length) {
    throw new Error(`1366 layout failed: ${JSON.stringify(layout1366)}`);
  }
  await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  const layout1920 = await evaluate(`(() => { const cta=document.querySelector("#reviewProductionScope").getBoundingClientRect(); return {ctaVisible:cta.top>=0&&cta.bottom<=innerHeight,horizontal:document.documentElement.scrollWidth>innerWidth+1}; })()`);
  if (!layout1920.ctaVisible || layout1920.horizontal) throw new Error(`1920 layout failed: ${JSON.stringify(layout1920)}`);

  await click("#clearProductionScope");
  await waitFor(`document.querySelector("#productionStateCard")?.dataset.productionState==="NO_SCOPE"`);
  if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);

  const evidence = await evaluate(`({
    state:document.querySelector("#productionStateCard")?.dataset.productionState,
    primaryAction:document.querySelector("#productionPrimaryAction")?.textContent,
    route:location.hash
  })`);
  process.stdout.write(JSON.stringify({
    ok: true,
    bookCount,
    firstPage,
    confirmedCount,
    oneChapterReady,
    rowSelectionWorks,
    keyboardWorkflow,
    quickRanges: ["372-372", "372-376", "372-381"],
    apiErrorVisible,
    technicalErrorAvailable,
    staleResponseIgnored,
    recoveredErrorHidden,
    skipCompletedRestored,
    primaryLabelsAreHuman,
    layout1366,
    layout1920,
    browserOpenLayout,
    interactionCounts: { oneChapter: 3, range: 3 },
    restoredRange: "372-373",
    final: evidence,
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
