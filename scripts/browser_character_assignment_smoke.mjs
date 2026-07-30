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
  const waitFor = (expression, timeoutMs = 10000) => poll(
    async () => (await evaluate(expression)) || null,
    timeoutMs,
  );
  const attr = (name, value) => `[${name}="${value}"]`;
  const click = selector => evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) throw new Error(${JSON.stringify(`Missing ${selector}`)});
    el.click();
    return true;
  })()`);
  const setInput = (selector, value) => evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) throw new Error(${JSON.stringify(`Missing ${selector}`)});
    el.value = ${JSON.stringify(value)};
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  })()`);
  const setSelect = (selector, value) => evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) throw new Error(${JSON.stringify(`Missing ${selector}`)});
    el.value = ${JSON.stringify(value)};
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  })()`);
  const rowText = speaker => evaluate(`(() => {
    const editor = document.querySelector(${JSON.stringify(attr("data-registry-editor", speaker))});
    return editor?.closest("tr")?.innerText || "";
  })()`);
  const rowContent = speaker => evaluate(`(() => {
    const editor = document.querySelector(${JSON.stringify(attr("data-registry-editor", speaker))});
    return editor?.closest("tr")?.textContent || "";
  })()`);
  const waitMapReady = async speaker => {
    await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-map", speaker))}) && !document.querySelector(${JSON.stringify(attr("data-registry-map", speaker))}).disabled`);
  };
  const waitVoiceReady = async speaker => {
    await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-apply", speaker))}) && !document.querySelector(${JSON.stringify(attr("data-registry-apply", speaker))}).disabled`);
  };
  const installCommandRecorder = async (existing = []) => evaluate(`(() => {
    window.__characterAssignmentCommands = ${JSON.stringify(existing)};
    const originalPost = window.__characterAssignmentOriginalPost || postProductionCommand;
    window.__characterAssignmentOriginalPost = originalPost;
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

  const unresolvedNew = "unresolved-dialogue:1002:u0002-deadbeef0000";
  const unresolvedExisting = "unresolved-dialogue:1003:u0002-feedface0000";
  const unresolvedThird = "unresolved-dialogue:1004:u0002-cafebabe0000";

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
  await waitFor(`document.readyState === "complete"`);
  await waitFor(`window.storyAudioAppState && document.querySelector("#assignmentRows")`);
  await waitMapReady(unresolvedNew);
  await installCommandRecorder([]);

  const detailSelectors = [unresolvedNew, unresolvedExisting, unresolvedThird].map(key => attr("data-registry-detail", key));
  for (const selector of detailSelectors) {
    await click(`${selector} > summary`);
  }
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-detail", unresolvedNew))})?.open && document.querySelector(${JSON.stringify(attr("data-registry-detail", unresolvedExisting))})?.open && document.querySelector(${JSON.stringify(attr("data-registry-detail", unresolvedThird))})?.open`);

  const openBeforeRefresh = await evaluate(`(() => ({
    newRow: document.querySelector(${JSON.stringify(attr("data-registry-detail", unresolvedNew))})?.open || false,
    existingRow: document.querySelector(${JSON.stringify(attr("data-registry-detail", unresolvedExisting))})?.open || false,
    thirdRow: document.querySelector(${JSON.stringify(attr("data-registry-detail", unresolvedThird))})?.open || false,
  }))()`);
  await evaluate(`loadBookVoiceRegistry({force:true})`);
  await waitFor(`window.storyAudioAppState.bookVoiceRegistry?.status === "ready"`);
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-detail", unresolvedNew))})?.open && document.querySelector(${JSON.stringify(attr("data-registry-detail", unresolvedExisting))})?.open && document.querySelector(${JSON.stringify(attr("data-registry-detail", unresolvedThird))})?.open`);

  await setInput(attr("data-registry-new-character", unresolvedNew), "Gate Captain");
  await setInput(attr("data-registry-alias-key", unresolvedNew), "front gate voice");
  await setInput(attr("data-registry-new-character", unresolvedExisting), "Existing Commander");
  await setInput(attr("data-registry-alias-key", unresolvedExisting), "red command voice");
  await setInput(attr("data-registry-new-character", unresolvedThird), "Scout Caller");
  await setInput(attr("data-registry-alias-key", unresolvedThird), "outer scout voice");
  await setSelect(attr("data-registry-character-key", unresolvedThird), "25");

  const draftsBeforeRefresh = await evaluate(`(() => ({
    newRow: document.querySelector(${JSON.stringify(attr("data-registry-new-character", unresolvedNew))})?.value || "",
    existingRow: document.querySelector(${JSON.stringify(attr("data-registry-new-character", unresolvedExisting))})?.value || "",
    thirdRow: document.querySelector(${JSON.stringify(attr("data-registry-new-character", unresolvedThird))})?.value || "",
  }))()`);
  await evaluate(`loadBookVoiceRegistry({force:true})`);
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-new-character", unresolvedNew))})?.value === "Gate Captain"`);
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-new-character", unresolvedExisting))})?.value === "Existing Commander"`);
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-new-character", unresolvedThird))})?.value === "Scout Caller"`);
  const draftsAfterRefresh = await evaluate(`(() => ({
    newRow: document.querySelector(${JSON.stringify(attr("data-registry-new-character", unresolvedNew))})?.value || "",
    existingRow: document.querySelector(${JSON.stringify(attr("data-registry-new-character", unresolvedExisting))})?.value || "",
    thirdRow: document.querySelector(${JSON.stringify(attr("data-registry-new-character", unresolvedThird))})?.value || "",
  }))()`);

  const generateButtonEnabled = await evaluate(`!document.querySelector('[data-generate-speaker-suggestions]')?.disabled`);
  if (generateButtonEnabled) {
    await click('[data-generate-speaker-suggestions]');
  } else {
    await evaluate(`generateSpeakerSuggestions(false)`);
  }
  await waitFor(`document.querySelector('[data-speaker-suggestion-card]') && document.querySelector('[data-speaker-suggestion-card]').innerText.includes("Existing Commander")`, 15000);
  const suggestionVisible = await evaluate(`(() => {
    const card = document.querySelector('[data-speaker-suggestion-card]');
    return !!card && card.innerText.includes('Existing Commander') && card.innerText.includes('Giọng hiệu lực');
  })()`);
  await click(`${attr("data-registry-map", unresolvedThird)}`);
  const thirdRowRemoved = await waitFor(`(() => {
    const third = document.querySelector(${JSON.stringify(attr("data-registry-editor", unresolvedThird))});
    return !third && !!document.querySelector(${JSON.stringify(attr("data-registry-detail", unresolvedNew))})?.open && !!document.querySelector(${JSON.stringify(attr("data-registry-detail", unresolvedExisting))})?.open;
  })()`, 15000);

  const exactState = await evaluate(`(() => {
    const body = document.querySelector("#assignmentRows")?.innerText || "";
    return {
      hash: location.hash,
      body: body.slice(0, 1200),
      hasBook: location.hash.includes("book=1"),
      hasFrom: location.hash.includes("from=1"),
      hasTo: location.hash.includes("to=10"),
      hasExisting: body.includes("Existing Commander"),
      hasMap: !!document.querySelector(${JSON.stringify(attr("data-registry-map", unresolvedNew))}),
      hasCreateTop: !!document.querySelector('[data-create-character-top]'),
    };
  })()`);
  const exactUrlHasRealRows = exactState.hasBook
    && exactState.hasFrom
    && exactState.hasTo
    && exactState.hasExisting
    && exactState.hasMap
    && exactState.hasCreateTop;
  const sampleVisible = (await rowContent(unresolvedNew)).includes("- Hold the gate");
  if (!exactUrlHasRealRows || !sampleVisible) {
    throw new Error(`Exact assignment URL did not expose real named/unresolved rows: ${JSON.stringify({ exactState, sampleVisible })}`);
  }

  await setInput(attr("data-registry-new-character", unresolvedNew), "Gate Captain");
  await setInput(attr("data-registry-alias-key", unresolvedNew), "front gate voice");
  await click(attr("data-registry-map", unresolvedNew));
  await waitFor(`!!document.querySelector(${JSON.stringify(attr("data-registry-editor", "character:31"))})`, 12000);
  await waitVoiceReady("character:31");
  const newCharacterMapped = (await rowText("character:31")).includes("Gate Captain")
    && !(await evaluate(`!!document.querySelector(${JSON.stringify(attr("data-registry-map", unresolvedNew))})`));

  await waitMapReady(unresolvedExisting);
  await setSelect(attr("data-registry-character-key", unresolvedExisting), "25");
  await setInput(attr("data-registry-alias-key", unresolvedExisting), "red command voice");
  await click(attr("data-registry-map", unresolvedExisting));
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-editor", "character:25"))})?.closest("tr")?.innerText.includes("red command voice")`, 12000);
  const existingCharacterMapped = (await rowText("character:25")).includes("Existing Commander")
    && (await rowText("character:25")).includes("red command voice");

  await waitVoiceReady("character:31");
  const beforeVoiceCommands = await evaluate(`(window.__characterAssignmentCommands || []).length`);
  await setSelect(attr("data-registry-scope-key", "character:31"), "range");
  await setSelect(attr("data-registry-voice-key", "character:31"), "commander");
  await click(attr("data-registry-apply", "character:31"));
  await waitFor(`(window.__characterAssignmentCommands || []).length > ${beforeVoiceCommands}`, 12000);
  await waitFor(`(window.__characterAssignmentCommands || []).some(command => command.type === "SET_RANGE_VOICE_OVERRIDE")`, 12000);
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-editor", "character:31"))})?.closest("tr")?.innerText.includes("Commander Voice")`, 12000);
  const voiceAssigned = (await rowText("character:31")).includes("Commander Voice")
    && await evaluate(`(window.__characterAssignmentCommands || []).some(command => command.type === "SET_RANGE_VOICE_OVERRIDE")`);

  await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  await evaluate(`document.querySelector(${JSON.stringify(attr("data-registry-apply", "character:31"))})?.scrollIntoView({ block: "center" })`);
  const layout1920 = await evaluate(`(() => {
    const action = document.querySelector(${JSON.stringify(attr("data-registry-apply", "character:31"))})?.getBoundingClientRect();
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
    exactUrlHasRealRows,
    sampleVisible,
    openBeforeRefresh,
    draftsBeforeRefresh,
    draftsAfterRefresh,
    suggestionVisible,
    thirdRowRemoved,
    newCharacterMapped,
    existingCharacterMapped,
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
