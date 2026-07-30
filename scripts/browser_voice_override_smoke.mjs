import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const baseUrl = process.argv[2];
if (!baseUrl) throw new Error("Usage: node scripts/browser_voice_override_smoke.mjs <base-url>");

const browserExe = [
  process.env.STORY_AUDIO_BROWSER_EXE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");

const profile = await mkdtemp(join(tmpdir(), "story-audio-voice-override-browser-"));
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
  const waitFor = (expression, timeoutMs = 10000) => poll(
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
  const route = async hash => {
    const params = new URLSearchParams(hash.split("?")[1] || "");
    const fromChapter = Number(params.get("from"));
    const toChapter = Number(params.get("to"));
    await evaluate(`(() => { location.hash = ${JSON.stringify(hash)}; return true; })()`);
    await waitFor(`location.hash === ${JSON.stringify(hash)}
      && Number(window.storyAudioAppState?.bookVoiceRegistry?.result?.range?.from_chapter) === ${fromChapter}
      && Number(window.storyAudioAppState?.bookVoiceRegistry?.result?.range?.to_chapter) === ${toChapter}
      && !window.storyAudioAppState?.bookVoiceRegistry?.loading`);
    await evaluate(`(() => {
      const section = document.querySelector('[data-assignment-section="voices"]');
      if (section) section.open = true;
      return true;
    })()`);
  };
  const attr = (name, value) => `[${name}="${value}"]`;
  const rowText = speaker => evaluate(`(() => {
    const editor = document.querySelector(${JSON.stringify(attr("data-registry-editor", speaker))});
    return editor?.closest("tr")?.textContent || "";
  })()`);
  const rowHasVoice = async (speaker, text) => (await rowText(speaker)).includes(text);
  const waitAssignmentReady = async speaker => {
    await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-apply", speaker))}) && !document.querySelector(${JSON.stringify(attr("data-registry-apply", speaker))}).disabled`);
  };
  const applyVoice = async (speaker, voice, scope = null) => {
    if (scope) await setSelect(attr("data-registry-scope-key", speaker), scope);
    await setSelect(attr("data-registry-voice-key", speaker), voice);
    await click(attr("data-registry-apply", speaker));
    const busySeen = await waitFor(`!!document.querySelector(".assignment-saving")`, 5000);
    await waitFor(`!document.querySelector(".assignment-saving")`, 20000);
    return !!busySeen;
  };
  const installCommandRecorder = async (existing = []) => evaluate(`(() => {
    window.__voiceOverrideCommands = ${JSON.stringify(existing)};
    const originalPost = window.__voiceOverrideOriginalPost || postProductionCommand;
    window.__voiceOverrideOriginalPost = originalPost;
    postProductionCommand = async (request, token = null) => {
      const response = await originalPost(request, token);
      window.__voiceOverrideCommands.push({
        type: request.command_type,
        key: request.idempotency_key,
        applied: response.applied_count || 0,
      });
      return response;
    };
    return true;
  })()`);
  const clearVoice = async (speaker, scope = null) => {
    if (scope) await setSelect(attr("data-registry-scope-key", speaker), scope);
    await click(attr("data-registry-clear", speaker));
    await waitFor(`!!document.querySelector(".assignment-saving")`, 5000);
    await waitFor(`!document.querySelector(".assignment-saving")`, 20000);
  };

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
  await waitFor(`document.readyState === "complete"`);
  await waitFor(`window.storyAudioAppState && document.querySelector("#assignmentRows")`);
  await evaluate(`(() => {
    const section = document.querySelector('[data-assignment-section="voices"]');
    if (section) section.open = true;
    return !!section;
  })()`);
  await waitAssignmentReady("narrator");
  await installCommandRecorder([]);

  const exactUrlNotReadOnly = await evaluate(`(() => {
    const body = document.querySelector("#assignmentRows")?.innerText || "";
    return location.hash.includes("book=1")
      && location.hash.includes("from=1")
      && location.hash.includes("to=10")
      && !!document.querySelector('[data-registry-scope-key="narrator"]')
      && !!document.querySelector('[data-registry-voice-key="narrator"]')
      && !!document.querySelector('[data-registry-apply="narrator"]')
      && !!document.querySelector('[data-registry-clear="narrator"]')
      && !document.querySelector('[data-voice-library-row="unknown"]')
      && !body.includes("Narrator/unknown");
  })()`);
  if (!exactUrlNotReadOnly) throw new Error("Exact assignment URL is still read-only.");

  await route("#/assignment?book=1&from=5&to=5&skip_completed=1");
  await waitAssignmentReady("narrator");
  const oneBusy = await applyVoice("narrator", "male", "chapter");
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-editor", "narrator"))})?.closest("tr")?.textContent.includes("Male Default")`);
  const commandsBeforeReload = await evaluate(`window.__voiceOverrideCommands || []`);
  await evaluate(`window.__voiceOverrideReloadMarker = "before-reload"`);
  await send("Page.reload", { ignoreCache: true });
  await waitFor(`document.readyState === "complete" && window.__voiceOverrideReloadMarker !== "before-reload"`);
  await evaluate(`(() => {
    const section = document.querySelector('[data-assignment-section="voices"]');
    if (section) section.open = true;
    return !!section;
  })()`);
  await waitAssignmentReady("narrator");
  await installCommandRecorder(commandsBeforeReload);
  const oneChapterNarratorText = await rowText("narrator");
  const oneChapterNarrator = oneBusy && oneChapterNarratorText.includes("Male Default");

  await route("#/assignment?book=1&from=4&to=4&skip_completed=1");
  await waitAssignmentReady("narrator");
  const chapter4Unchanged = await rowHasVoice("narrator", "Narrator Default");
  await route("#/assignment?book=1&from=6&to=6&skip_completed=1");
  await waitAssignmentReady("narrator");
  const chapter6UnchangedBeforeRange = await rowHasVoice("narrator", "Narrator Default");

  await route("#/assignment?book=1&from=6&to=8&skip_completed=1");
  await waitAssignmentReady("narrator");
  await applyVoice("narrator", "female", "range");
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-editor", "narrator"))})?.closest("tr")?.textContent.includes("Female Range")`);
  const rangeNarrator = await rowHasVoice("narrator", "Female Range")
    && (await rowText("narrator")).includes("6")
    && (await rowText("narrator")).includes("8");

  await route("#/assignment?book=1&from=9&to=9&skip_completed=1");
  await waitAssignmentReady("narrator");
  const chapter9Unchanged = await rowHasVoice("narrator", "Narrator Default");

  await route("#/assignment?book=1&from=2&to=4&skip_completed=1");
  await waitAssignmentReady("character:25");
  await applyVoice("character:25", "character-alt", "range");
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-editor", "character:25"))})?.closest("tr")?.textContent.includes("Character Alt")`);
  const characterRange = await rowHasVoice("character:25", "Character Alt");

  await route("#/assignment?book=1&from=3&to=3&skip_completed=1");
  await waitAssignmentReady("character:25");
  await clearVoice("character:25", "chapter");
  await waitFor(`document.querySelector(${JSON.stringify(attr("data-registry-editor", "character:25"))})?.closest("tr")?.textContent.includes("Male Default")`);
  const clearRestoresDefault = await rowHasVoice("character:25", "Male Default");

  await route("#/assignment?book=1&from=2&to=4&skip_completed=1");
  await waitAssignmentReady("character:25");
  const mixedVisible = await rowHasVoice("character:25", "Xung đột giọng")
    || await evaluate(`document.querySelector(${JSON.stringify(attr("data-registry-editor", "character:25"))})?.textContent.includes("nhiều giọng")`);
  await applyVoice("character:25", "character-alt", "range");
  const mixedResolved = await rowHasVoice("character:25", "Character Alt");

  await route("#/assignment?book=1&from=1&to=1&skip_completed=1");
  const unidentifiedSpeakerHidden = await evaluate(`!document.querySelector('[data-voice-library-row="unknown"]')`);

  const beforeUnavailableCommands = await evaluate(`window.__voiceOverrideCommands.length`);
  await evaluate(`(() => {
    const select = document.querySelector('[data-registry-voice-key="narrator"]');
    select.insertAdjacentHTML("beforeend", '<option value="legacy">Legacy Unavailable</option>');
    select.value = "legacy";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  })()`);
  await click(attr("data-registry-apply", "narrator"));
  await waitFor(`!!document.querySelector('[data-registry-editor="narrator"] .assignment-row-error')`);
  const unavailableBlocked = await evaluate(`(() => {
    const select = document.querySelector('[data-registry-voice-key="narrator"]');
    const error = document.querySelector('[data-registry-editor="narrator"] .assignment-row-error');
    return select?.value === "legacy" && !!error && window.__voiceOverrideCommands.length === ${beforeUnavailableCommands};
  })()`);

  await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  await evaluate(`document.querySelector('[data-registry-apply="narrator"]')?.scrollIntoView({ block: "center" })`);
  const layout1920 = await evaluate(`(() => {
    const action = document.querySelector('[data-registry-apply="narrator"]')?.getBoundingClientRect();
    return {
      primaryVisible: !!action && action.top >= 0 && action.bottom <= innerHeight,
      horizontal: document.documentElement.scrollWidth > innerWidth + 1,
    };
  })()`);
  if (!layout1920.primaryVisible || layout1920.horizontal) {
    throw new Error(`Voice override layout failed: ${JSON.stringify(layout1920)}`);
  }

  if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);
  const commands = await evaluate(`window.__voiceOverrideCommands`);
  process.stdout.write(JSON.stringify({
    ok: true,
    exactUrlNotReadOnly,
    oneChapterNarrator,
    oneBusy,
    oneChapterNarratorText,
    rangeNarrator: rangeNarrator && chapter4Unchanged && chapter6UnchangedBeforeRange && chapter9Unchanged,
    characterRange,
    clearRestoresDefault,
    mixedVisible,
    mixedResolved,
    unidentifiedSpeakerHidden,
    unavailableBlocked,
    commands,
    renderCommands: commands.filter(command => /PREPARE|START_RENDER/.test(command.type)),
    mutationCount: commands.reduce((total, command) => total + Number(command.applied || 0), 0),
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
