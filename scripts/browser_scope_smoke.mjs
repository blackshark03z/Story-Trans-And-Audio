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

  await send("Runtime.enable");
  await send("Page.enable");
  await waitFor(`document.readyState==="complete"`);
  await waitFor(`document.querySelector("#productionStateBadge")?.textContent==="NO_SCOPE"`);

  await click("#productionPrimaryAction");
  await waitFor(`document.querySelector("#productionScopeDialog")?.open===true`);
  const bookCount = await evaluate(`document.querySelectorAll("#scopeBookList .scope-book-card").length`);
  if (bookCount !== 2) throw new Error(`Expected 2 books, received ${bookCount}.`);

  await click('[data-scope-book-id="1"]');
  await waitFor(`document.querySelectorAll("#scopeChapterList .scope-chapter-card").length===40`);
  const firstPage = await evaluate(`document.querySelector("#scopeChapterPageInfo")?.textContent`);
  if (firstPage !== "1-40 / 45") throw new Error(`Unexpected pagination: ${firstPage}`);

  await input("#scopeChapterSearch", "372");
  await waitFor(`document.querySelector("#scopeChapterPageInfo")?.textContent==="1-1 / 1"`);
  await click("#scopeChapterList .scope-chapter-card button:last-child");
  await input("#scopeFromChapter", "373");
  await input("#scopeToChapter", "372");
  await waitFor(`document.querySelector("#scopeSelectionValidation")?.textContent.includes("cannot be greater")`);

  await input("#scopeFromChapter", "372");
  await input("#scopeToChapter", "373");
  await click("#reviewProductionScope");
  await waitFor(`document.querySelector("#confirmProductionScope")?.disabled===false`);
  const confirmedCount = await evaluate(`Number(document.querySelector("#scopeSelectionSummary > div:nth-child(4) strong")?.textContent)`);
  if (confirmedCount !== 2) throw new Error(`Expected exact range count 2, received ${confirmedCount}.`);
  await click("#scopeSkipCompleted");
  await click("#confirmProductionScope");
  await waitFor(`document.querySelector("#productionScopeDialog")?.open===false`);
  await waitFor(`location.hash.includes("book=1")&&location.hash.includes("from=372")&&location.hash.includes("to=373")`);

  await click("#productionChangeScope");
  await waitFor(`document.querySelector("#productionScopeDialog")?.open===true`);
  await click('[data-scope-book-id="2"]');
  await waitFor(`document.querySelector("#scopeChapterPageInfo")?.textContent==="1-1 / 1"`);
  const changedBook = await evaluate(`({
    chapters:[...document.querySelectorAll("#scopeChapterList .scope-chapter-card strong")].map(el=>el.textContent),
    from:document.querySelector("#scopeFromChapter")?.value,
    to:document.querySelector("#scopeToChapter")?.value
  })`);
  if (changedBook.chapters.some(text => text.includes("372")) || changedBook.from || changedBook.to) {
    throw new Error("Changing books leaked stale chapter state.");
  }

  await click('[data-scope-book-id="1"]');
  await waitFor(`document.querySelector("#scopeChapterPageInfo")?.textContent==="1-40 / 45"`);
  await input("#scopeChapterSearch", "__slow__");
  await delay(240);
  await click('[data-scope-book-id="2"]');
  await waitFor(`document.querySelector("#scopeChapterPageInfo")?.textContent==="1-1 / 1"`);
  await delay(450);
  const staleResponseIgnored = await evaluate(`document.querySelector("#scopeChapterList .scope-chapter-card strong")?.textContent.includes("Pilot Chapter")===true`);
  if (!staleResponseIgnored) throw new Error("A stale chapter response replaced the newly selected book.");

  await input("#scopeChapterSearch", "__fail__");
  await waitFor(`!document.querySelector("#scopeChaptersError")?.classList.contains("hidden")`);
  const apiErrorVisible = await evaluate(`document.querySelector("#scopeChaptersError")?.textContent.includes("fixture chapter failure")`);
  if (!apiErrorVisible) throw new Error("Chapter API failure was not visible.");

  await click('[data-scope-book-id="1"]');
  await waitFor(`document.querySelector("#scopeChapterPageInfo")?.textContent==="1-40 / 45"`);
  const recoveredErrorHidden = await evaluate(`document.querySelector("#scopeChaptersError")?.classList.contains("hidden")===true`);
  if (!recoveredErrorHidden) throw new Error("A resolved chapter API error remained visible.");
  await input("#scopeFromChapter", "372");
  await input("#scopeToChapter", "373");
  await click("#reviewProductionScope");
  await waitFor(`document.querySelector("#confirmProductionScope")?.disabled===false`);
  await click("#confirmProductionScope");
  await waitFor(`document.querySelector("#productionScopeDialog")?.open===false`);
  await evaluate(`location.hash="#/assignment"`);
  await waitFor(`document.querySelector('[data-app-view="assignment"]')?.hidden===false`);
  await evaluate(`location.hash="#/production"`);
  await waitFor(`document.querySelector("#productionScopeSummary")?.textContent.includes("372-373")`);

  await send("Page.reload", { ignoreCache: true });
  await waitFor(`document.readyState==="complete"`);
  await waitFor(`document.querySelector("#productionScopeSummary")?.textContent.includes("372-373")`);
  const skipCompletedRestored = await evaluate(`location.hash.includes("skip_completed=1")&&document.querySelector("#skipCompleted")?.checked===true`);
  if (!skipCompletedRestored) throw new Error("Skip-completed scope state was not restored.");
  await click("#productionChangeScope");
  await waitFor(`document.querySelector("#productionScopeDialog")?.open===true`);
  await click("#clearProductionScope");
  await waitFor(`document.querySelector("#productionStateBadge")?.textContent==="NO_SCOPE"`);

  const evidence = await evaluate(`({
    state:document.querySelector("#productionStateBadge")?.textContent,
    route:location.hash,
    consoleReady:true
  })`);
  process.stdout.write(JSON.stringify({
    ok: true,
    bookCount,
    firstPage,
    confirmedCount,
    apiErrorVisible,
    staleResponseIgnored,
    recoveredErrorHidden,
    skipCompletedRestored,
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
