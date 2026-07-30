import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";

const baseUrl = process.argv[2];
if (!baseUrl) throw new Error("Usage: node scripts/browser_assignment_flow_smoke.mjs <base-url>");

const browserExe = [
  process.env.STORY_AUDIO_BROWSER_EXE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");

const testRoot = process.env.STORY_AUDIO_ASSIGNMENT_TEST_ROOT;
if (!testRoot) throw new Error("STORY_AUDIO_ASSIGNMENT_TEST_ROOT is required.");
const profile = await mkdtemp(join(testRoot, "browser-"));
const child = spawn(browserExe, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--remote-debugging-port=0",
  `--user-data-dir=${profile}`,
  `${baseUrl}/#/assignment?book=1&from=1&to=10&skip_completed=1`,
], { stdio: "ignore" });

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function poll(callback, timeoutMs = 15000) {
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
    if (message.method === "Runtime.consoleAPICalled" && message.params?.type === "error") {
      browserErrors.push((message.params.args || []).map(item => item.value || item.description).join(" "));
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
      throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    }
    return result.result.value;
  };
  const waitFor = (expression, timeoutMs = 15000) => poll(
    async () => (await evaluate(expression)) || null,
    timeoutMs,
  );
  const click = selector => evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) throw new Error(${JSON.stringify(`Missing ${selector}`)});
    el.click();
    return true;
  })()`);
  const setSelect = (selector, value) => evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) throw new Error(${JSON.stringify(`Missing ${selector}`)});
    el.value = ${JSON.stringify(value)};
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  })()`);

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1366,
    height: 768,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await waitFor(`document.readyState === "complete"`);
  await waitFor(`window.storyAudioAppState && document.querySelector('[data-speaker-suggestion-card]')`);

  const initial = await evaluate(`(() => {
    const review = document.querySelector('[data-assignment-section="review"]');
    const voices = document.querySelector('[data-assignment-section="voices"]');
    const steps = [...document.querySelectorAll('.assignment-workflow-steps > div')].map(row => row.innerText);
    return {
      hash: location.hash,
      steps,
      reviewOpen: !!review?.open,
      voicesOpen: !!voices?.open,
      sectionsSeparate: !!review && !!voices && review !== voices,
      unresolvedNotice: !!document.querySelector('[data-jump-to-speaker-review]'),
      unresolvedVoiceRows: [...document.querySelectorAll('[data-voice-library-row]')].filter(row => row.getAttribute('data-voice-library-row').startsWith('unresolved-dialogue:')).length,
      characterRows: document.querySelectorAll('[data-voice-library-row^="character:"]').length,
    };
  })()`);

  await evaluate(`(() => {
    const voices = document.querySelector('[data-assignment-section="voices"]');
    voices.open = true;
    return true;
  })()`);
  await setSelect('[data-speaker-review-filter="confidence"]', "HIGH");
  const filterBeforeJump = await evaluate(`document.querySelector('[data-speaker-review-filter="confidence"]').value`);
  await click('[data-jump-to-speaker-review]');
  const unresolvedNavigation = await waitFor(`(() => {
    const review = document.querySelector('[data-assignment-section="review"]');
    const active = document.activeElement;
    return review?.open && !!active?.closest('[data-speaker-suggestion-card]');
  })()`);
  const navigationState = await evaluate(`({
    hash: location.hash,
    filter: document.querySelector('[data-speaker-review-filter="confidence"]')?.value,
    activeCard: document.activeElement?.closest('[data-speaker-suggestion-card]')?.dataset?.speakerSuggestionCard || null,
  })`);

  const key = await evaluate(`document.querySelector('[data-speaker-suggestion-card]')?.dataset?.speakerSuggestionCard`);
  await click(`[data-speaker-suggestion-accept="${key}"]`);
  await waitFor(`document.querySelector('.assignment-workflow-steps')?.innerText.includes("Hoàn tất")
    && document.querySelector('[data-assignment-section="voices"]')?.open
    && !document.querySelector('[data-voice-library-row^="unresolved-dialogue:"]')`, 20000);
  const reviewCompletion = await evaluate(`(() => {
    const rows = [...document.querySelectorAll('[data-voice-library-row="character:25"]')];
    return {
      reviewComplete: document.querySelector('.assignment-workflow-steps')?.innerText.includes('Hoàn tất'),
      voiceEmphasized: document.querySelector('[data-assignment-section="voices"]')?.classList.contains('is-current'),
      voiceOpen: document.querySelector('[data-assignment-section="voices"]')?.open,
      characterRows: rows.length,
      unresolvedRows: document.querySelectorAll('[data-voice-library-row^="unresolved-dialogue:"]').length,
    };
  })()`);

  await waitFor(`!window.storyAudioAppState.productionCommand?.active
    && !window.storyAudioAppState.bookVoiceRegistry?.loading
    && !window.storyAudioAppState.bookVoiceRegistry?.speakerSuggestions?.loading`);
  await evaluate(`Promise.all([
    loadBookVoiceRegistry(),
    loadSpeakerReviewSuggestions(),
    loadProductionTaskProjection({ silent: true }),
  ])`);

  const pollingStability = await evaluate(`(async () => {
    const voice = document.querySelector('[data-registry-voice-key="character:25"]');
    const scope = document.querySelector('[data-registry-scope-key="character:25"]');
    if (!voice || !scope) throw new Error('Character voice controls missing after review completion');
    scope.value = 'range';
    scope.dispatchEvent(new Event('change', { bubbles: true }));
    voice.value = 'commander';
    voice.dispatchEvent(new Event('change', { bubbles: true }));
    voice.focus();
    const node = voice;
    const scopeNode = scope;
    const scrollBefore = window.scrollY;
    for (let index = 0; index < 3; index += 1) await loadJobs();
    return {
      sameVoiceNode: document.querySelector('[data-registry-voice-key="character:25"]') === node,
      sameScopeNode: document.querySelector('[data-registry-scope-key="character:25"]') === scopeNode,
      focused: document.activeElement === node,
      voice: node.value,
      scope: scopeNode.value,
      sectionOpen: document.querySelector('[data-assignment-section="voices"]')?.open,
      scrollStable: Math.abs(window.scrollY - scrollBefore) <= 1,
      impact: document.querySelector('[data-registry-impact="character:25"]')?.innerText || '',
    };
  })()`);

  const commandsBeforePreflight = await evaluate(`fetch('/api/fixture/commands').then(response => response.json())`);
  await click('[data-open-production-preflight]:not([disabled])');
  await waitFor(`location.hash.startsWith("#/production")`);
  const readyNavigation = await evaluate(`({
    hash: location.hash,
    workingContext: window.storyAudioAppState.productionWorkingContext,
  })`);
  const commandsAfterPreflight = await evaluate(`fetch('/api/fixture/commands').then(response => response.json())`);

  if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);
  process.stdout.write(JSON.stringify({
    ok: true,
    initial,
    filterBeforeJump,
    unresolvedNavigation: !!unresolvedNavigation,
    navigationState,
    reviewCompletion,
    pollingStability,
    readyNavigation,
    commandsBeforePreflight,
    commandsAfterPreflight,
    renderCommands: commandsAfterPreflight.filter(command => /PREPARE|START_RENDER/.test(command.command_type || "")),
  }));
} finally {
  try {
    socket?.close();
  } catch {}
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
