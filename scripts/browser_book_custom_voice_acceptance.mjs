import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";

const baseUrl = process.argv[2];
const bookA = Number(process.argv[3]);
const bookB = Number(process.argv[4]);
function assertNonCanonicalUrl(value) {
  const parsed = new URL(value);
  if (["127.0.0.1", "localhost", "::1"].includes(parsed.hostname) && parsed.port === "8772") {
    throw new Error("Refusing canonical Story Audio runtime (:8772).");
  }
  return parsed;
}
if (baseUrl === "--self-check-canonical-url") {
  try { assertNonCanonicalUrl("http://127.0.0.1:8772"); } catch (error) { console.log(JSON.stringify({ ok: true, rejected: error.message })); process.exit(0); }
  throw new Error("Canonical URL isolation self-check failed.");
}
if (!baseUrl || !bookA || !bookB) throw new Error("Usage: STORY_AUDIO_ISOLATED_ACCEPTANCE=1 node scripts/browser_book_custom_voice_acceptance.mjs <base-url> <book-a-id> <book-b-id>");
assertNonCanonicalUrl(baseUrl);
if (process.env.STORY_AUDIO_ISOLATED_ACCEPTANCE !== "1") throw new Error("Isolated acceptance marker is required.");
const runtime = await (await fetch(`${baseUrl}/api/runtime`)).json();
if (runtime.is_canonical_live_db || runtime.is_canonical_live_data_root || !runtime.db_path || !runtime.data_root) {
  throw new Error("Runtime did not prove an isolated non-canonical database.");
}
const browserExe = [process.env.STORY_AUDIO_BROWSER_EXE, "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"].filter(Boolean).find(existsSync);
if (!browserExe) throw new Error("No supported Chromium browser was found.");
const profile = await mkdtemp(join(process.env.TEMP || process.cwd(), "story-audio-book-voice-browser-"));
const child = spawn(browserExe, ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--remote-debugging-port=0", `--user-data-dir=${profile}`, `${baseUrl}/#/voices`], { stdio: "ignore" });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function poll(fn, timeout = 20000) { const end = Date.now() + timeout; let last; while (Date.now() < end) { try { const value = await fn(); if (value) return value; } catch (error) { last = error; } await delay(75); } throw last || new Error("Timed out waiting for browser state."); }
let socket;
try {
  const port = await poll(async () => Number((await readFile(join(profile, "DevToolsActivePort"), "utf8")).split(/\r?\n/)[0]) || null);
  const page = await poll(async () => (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(item => item.type === "page" && item.url.startsWith(baseUrl)));
  socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.addEventListener("open", resolve, { once: true }); socket.addEventListener("error", reject, { once: true }); });
  let next = 1; const pending = new Map();
  socket.addEventListener("message", event => { const message = JSON.parse(event.data); if (!message.id || !pending.has(message.id)) return; const waiter = pending.get(message.id); pending.delete(message.id); message.error ? waiter.reject(new Error(message.error.message)) : waiter.resolve(message.result); });
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = next++; pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params })); });
  const evaluate = async expression => { const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }); if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text); return result.result.value; };
  const wait = expression => poll(async () => (await evaluate(expression)) || null);
  await send("Runtime.enable"); await send("Page.enable"); await wait("document.readyState === 'complete' && document.querySelector('#libraryBookSelect')");
  const waitForBooks = () => wait(`[...document.querySelector('#libraryBookSelect').options].some(option=>option.value===${JSON.stringify(String(bookA))}) && [...document.querySelector('#libraryBookSelect').options].some(option=>option.value===${JSON.stringify(String(bookB))})`);
  await evaluate("document.querySelector('#refreshLibrary').click()");
  await waitForBooks();
  await wait("!document.querySelector('#refreshLibrary').disabled");
  const voiceName = `Book A Acceptance ${Date.now()}`;
  const setBook = async id => evaluate(`(() => { const el=document.querySelector('#libraryBookSelect'); el.value=${JSON.stringify(String(id))}; el.dispatchEvent(new Event('change',{bubbles:true})); return el.value; })()`);
  const refreshFor = async id => { await setBook(id); await wait(`document.querySelector('#libraryBookSelect').value===${JSON.stringify(String(id))}`); await evaluate("document.querySelector('#refreshLibrary').click()"); await wait("!document.querySelector('#refreshLibrary').disabled"); };
  await refreshFor(bookA);
  await evaluate(`(() => { document.querySelector('.create-voice-section').open=true; document.querySelector('#libraryNewName').value=${JSON.stringify(voiceName)}; document.querySelector('#libraryNewTranscript').value='Disposable isolated acceptance sample.'; const bytes=new Uint8Array([82,73,70,70,36,0,0,0,87,65,86,69,102,109,116,32,16,0,0,0,1,0,1,0,128,187,0,0,0,119,1,0,2,0,16,0,100,97,116,97,0,0,0,0]); const file=new File([bytes],'sample.wav',{type:'audio/wav'}); const transfer=new DataTransfer(); transfer.items.add(file); Object.defineProperty(document.querySelector('#libraryNewAudioFile'),'files',{value:transfer.files}); document.querySelector('#libraryCreate').click(); return true; })()`);
  await wait(`[...document.querySelectorAll('.voice-library-row strong')].some(x=>x.textContent===${JSON.stringify(voiceName)})`);
  const previousPage = await evaluate("performance.timeOrigin");
  await evaluate("location.reload()");
  await wait(`performance.timeOrigin!==${JSON.stringify(previousPage)} && document.readyState==='complete' && document.querySelector('#libraryBookSelect')`);
  await evaluate("document.querySelector('#refreshLibrary').click()"); await waitForBooks(); await wait("!document.querySelector('#refreshLibrary').disabled"); await refreshFor(bookA); await wait(`[...document.querySelectorAll('.voice-library-row strong')].some(x=>x.textContent===${JSON.stringify(voiceName)})`);
  await refreshFor(bookB); await wait(`![...document.querySelectorAll('.voice-library-row strong')].some(x=>x.textContent===${JSON.stringify(voiceName)})`);
  const evidence = await evaluate(`(async () => { const rows=[...document.querySelectorAll('.voice-library-row strong')].map(x=>x.textContent); const a=await (await fetch('/api/voice-catalog?book_id=${bookA}')).json(); const b=await (await fetch('/api/voice-catalog?book_id=${bookB}')).json(); const legacy=await (await fetch('/api/voice-catalog')).json(); const aFound=a.items.some(x=>x.display_name===${JSON.stringify(voiceName)}); const bFound=b.items.some(x=>x.display_name===${JSON.stringify(voiceName)}); const legacyAvailable=legacy.items.some(x=>x.book_id===null); return {voiceName:${JSON.stringify(voiceName)}, bookAVisible:aFound, bookBVisible:bFound||rows.includes(${JSON.stringify(voiceName)}), legacyAvailable}; })()`);
  if (!evidence.bookAVisible || evidence.bookBVisible || !evidence.legacyAvailable) throw new Error(`Book scope acceptance failed: ${JSON.stringify(evidence)}`);
  console.log(JSON.stringify({ ok: true, ...evidence }));
} finally { try { socket?.close(); } catch {} child.kill(); await new Promise(resolve => child.once("exit", resolve)); await rm(profile, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 }); }
