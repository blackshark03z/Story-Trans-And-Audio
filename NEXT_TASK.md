# Next Task

Current Status:
Task 13A is complete locally on `main`. Chapter 357 canonical Job `17` remains the accepted production evidence, and the Character Voices operator UI has been simplified so AI speaker drafts, Casting Plan review, and Render / Production Output are clearly separated before any production mutation.

Current Baseline:
- Branch `main`
- Current HEAD = `5220905394df1bf87c816f9a934d9794927a1580`
- Task 11D2 acceptance evidence runtime: `D:\Youtube\StoryAudioAcceptanceRun1\data`
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Offline baseline last verified for this line of work: 902 tests passing, 1 skipped
- Official rollout verdict: `PRODUCTION_GO`
- Second acceptance chapter before rollout: not required
- Task 11B2 disposable smoke root: `D:\Youtube\StoryAudioTask11B2Smoke\data`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Next Task:
Task 13B - Live Canonical Operator Walkthrough for Simplified Character Voices

Why:
- The confusing overlap between AI Speaker Draft review and Casting Plan approval was a real operator footgun; Task 13A removes most of that ambiguity in code, but the next highest-value check is a live canonical walkthrough on the real UI.
- We should verify the simplified panel works the way operators actually move: chapter CTA -> Character Voices -> review current plan -> render only from approved plan identity.
- Chapter 357 remains the best reference chapter for this walkthrough because it already has accepted evidence and clear active-audio / historical-plan context.

Scope:
1. Restart only Story Audio on canonical production if needed and verify the runtime banner still shows `CANONICAL PRODUCTION`.
2. Walk the Chapter 357 `Character Voices` path live and confirm the new production-step banner, the de-emphasized AI Draft area when a plan exists, and the exact `Approve Casting Plan vN` / render identity labels.
3. Confirm `Jump to Casting Plan approval` lands on the real plan-approval controls rather than the speaker-draft review controls.
4. Preserve Chapter 357 as the reference production-evidence chapter: Job `17`, Casting Plan `18`, active artifact `48`, final M4A SHA `024e9f8cc1a646095eb84fad71d532fc04875e9eb34609a397e44c6f3153b675`.
5. Do not mutate canonical production audio or submit any new render during the walkthrough unless a future explicit task authorizes it.

Prerequisites For Any Next Task:
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Use `.\run_app.ps1 --host 127.0.0.1 --port 8772 --no-browser` for canonical production startup and verify `GET /api/runtime` before mutating.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local via `run_app.ps1`; do not persist it at user or machine scope.
- Require an explicit isolated `STORY_AUDIO_DATA_DIR` / data root for any new smoke or production-style run.
- For unified canonical production workflow runs, require explicit `--allow-canonical-production`; creation of a new canonical job still requires `--submit`, while downstream-only canonical outputs require an exact `--job-id`.
- Custom voice bindings in approved canonical plans are now valid only when they resolve to active usable library entries with a preferred or latest usable revision; inactive or revision-less custom voices must still fail closed.
- Remember that checklist review state and detailed human notes are browser-local by default; use the checklist's `Export review JSON` if the notes need to become durable evidence outside the browser.
- Preserve live DB guardrails.
- Do not stop or repurpose port `8765`; it belongs to YouTube Auto.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Re-verify Git baseline before implementation.
- Preserve Chapter 357 acceptance evidence:
  - Text Revision `714`
  - Casting Plan `#6`
  - Job `#2`
  - final M4A under `D:\Youtube\StoryAudioAcceptanceRun1\data\output\1-quang-am-chi-ngoai\chapter_0357\job_2\render_0001\`
