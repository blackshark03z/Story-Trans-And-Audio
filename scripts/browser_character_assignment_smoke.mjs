import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";

const baseUrl = process.argv[2];
if (!baseUrl) throw new Error("Usage: node scripts/browser_character_assignment_smoke.mjs <base-url>");

const browserExe = [
  process.env.STORY_AUDIO_BROWSER_EXE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");

const testRoot = "C:\\StoryAudio_CharacterAssignment_Test";
await mkdir(testRoot, { recursive: true });
const profile = await mkdtemp(join(testRoot, "browser-profile-"));
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
    (await readFile(join(profile, "DevToolsActivePort"), "utf8")).split(/\r?\n/)[0],
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
        || "runtime exception",
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
  const attr = (name, value) => `[${name}="${value}"]`;

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1366,
    height: 768,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await waitFor(`document.readyState === "complete"`);
  await waitFor(`window.storyAudioAppState && document.querySelector("#assignmentRows")`);
  await waitFor(`window.storyAudioAppState.bookVoiceRegistry?.status === "ready"
    && document.querySelector('[data-assignment-section="review"]')
    && document.querySelector('[data-generate-speaker-suggestions]')`);

  const initial = await evaluate(`(() => {
    const review = document.querySelector('[data-assignment-section="review"]');
    const voices = document.querySelector('[data-assignment-section="voices"]');
    const voiceRows = [...document.querySelectorAll('[data-voice-library-row]')];
    return {
      hash: location.hash,
      stepCount: document.querySelectorAll('.assignment-workflow-steps > div').length,
      reviewOpen: !!review?.open,
      voicesOpen: !!voices?.open,
      unresolvedNotice: !!document.querySelector('[data-jump-to-speaker-review]'),
      unresolvedVoiceRows: voiceRows.filter(row => /unresolved|unknown/i.test(row.dataset.voiceLibraryRow || "")).length,
      characterRows: voiceRows.filter(row => (row.dataset.voiceLibraryRow || "").startsWith("character:")).length,
    };
  })()`);

  await evaluate(`(() => {
    window.__characterAssignmentCommands = [];
    const originalPost = postProductionCommand;
    postProductionCommand = async (request, token = null) => {
      const response = await originalPost(request, token);
      window.__characterAssignmentCommands.push({
        type: request.command_type,
        key: request.idempotency_key,
        applied: response.applied_count || 0,
      });
      return response;
    };
    return true;
  })()`);

  const generateEnabled = await evaluate(`!document.querySelector('[data-generate-speaker-suggestions]')?.disabled`);
  if (generateEnabled) {
    await click("[data-generate-speaker-suggestions]");
  } else {
    await evaluate(`generateSpeakerSuggestions(false)`);
  }
  await waitFor(`document.querySelectorAll('[data-speaker-suggestion-card]').length === 3`);
  const reviewQueue = await evaluate(`(() => {
    const cards = [...document.querySelectorAll('[data-speaker-suggestion-card]')];
    return {
      count: cards.length,
      existingCharacterVisible: cards.some(card => card.textContent.includes("Existing Commander")),
      sourceLineVisible: cards.some(card => card.textContent.includes("- Hold the gate")),
      noAutomaticApproval: cards.every(card => !!card.querySelector('[data-speaker-suggestion-submit]')),
    };
  })()`);

  await evaluate(`document.querySelector('[data-assignment-section="voices"]').open = true`);
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-apply", "character:25"))})
    && !document.querySelector(${JSON.stringify(attr("data-registry-apply", "character:25"))}).disabled`);
  await setSelect(attr("data-registry-scope-key", "character:25"), "range");
  await setSelect(attr("data-registry-voice-key", "character:25"), "commander");
  await click(attr("data-registry-apply", "character:25"));
  await waitFor(`(window.__characterAssignmentCommands || []).some(command => command.type === "SET_RANGE_VOICE_OVERRIDE")`);
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-editor", "character:25"))})?.closest("tr")?.textContent.includes("Commander Voice")`);
  const voiceAssigned = await evaluate(`document.querySelector(${JSON.stringify(attr("data-registry-editor", "character:25"))})?.closest("tr")?.textContent.includes("Commander Voice")`);

  await send("Emulation.setDeviceMetricsOverride", {
    width: 1920,
    height: 1080,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await evaluate(`document.querySelector(${JSON.stringify(attr("data-registry-apply", "character:25"))})?.scrollIntoView({ block: "center" })`);
  const layout1920 = await evaluate(`(() => {
    const action = document.querySelector(${JSON.stringify(attr("data-registry-apply", "character:25"))})?.getBoundingClientRect();
    return {
      primaryVisible: !!action && action.top >= 0 && action.bottom <= innerHeight,
      horizontal: document.documentElement.scrollWidth > innerWidth + 1,
    };
  })()`);
  if (!layout1920.primaryVisible || layout1920.horizontal) {
    throw new Error(`Character assignment layout failed: ${JSON.stringify(layout1920)}`);
  }
  if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);

  const commands = await evaluate(`window.__characterAssignmentCommands || []`);
  process.stdout.write(JSON.stringify({
    ok: true,
    initial,
    reviewQueue,
    voiceAssigned,
    commands,
    renderCommands: commands.filter(command => /PREPARE|START_RENDER/.test(command.type)),
    layout1920,
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
