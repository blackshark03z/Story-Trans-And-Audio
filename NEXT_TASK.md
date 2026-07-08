# Next Task

Current Status:
Task 13C is complete locally on `main`. Chapter 357 canonical Job `17` remains the accepted production evidence, and the Character Voices operator UI now includes a step-by-step `Production Flow` wizard with explicit step status, blocker reasons, and `Back` / `Continue` / `Next` navigation before any production mutation.

Current Baseline:
- Branch `main`
- Current HEAD = `4b82cdd57c6626b03c086146c4e9a12e5543f60d`
- Task 11D2 acceptance evidence runtime: `D:\Youtube\StoryAudioAcceptanceRun1\data`
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Offline baseline last verified for this line of work: 907 tests passing, 1 skipped
- Official rollout verdict: `PRODUCTION_GO`
- Second acceptance chapter before rollout: not required
- Task 11B2 disposable smoke root: `D:\Youtube\StoryAudioTask11B2Smoke\data`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Next Task:
Task 13D - Live Canonical Operator Walkthrough for Step-by-Step Production Flow

Why:
- Task 13C now turns the operator path into a real stepper, but we should still verify live that a non-developer can follow it chapter-by-chapter without falling back to dashboard-style hunting.
- The next highest-value check is a canonical walkthrough of the new step flow, blocker messages, and step-to-section navigation: chapter CTA -> Production Flow stepper -> follow the next valid step -> review plan identity -> stop before any unintended production mutation.
- Chapter 357 remains the best reference chapter for this walkthrough because it already has accepted evidence and clear active-audio / historical-plan context.

Scope:
1. Restart only Story Audio on canonical production if needed and verify the runtime banner still shows `CANONICAL PRODUCTION`.
2. Walk the Chapter 357 `Production Flow` path live and confirm the stepper advances in the expected order: chapter selection -> text -> characters -> casting -> approval -> render -> QA -> human verdict.
3. Confirm blocker messages are understandable when a later step is not the valid next action, and that `Next` / `Continue` land on the intended existing UI section.
4. Confirm advanced/debug areas are still accessible but visually secondary to the main flow: AI Speaker Draft, historical jobs, segment attempts, and diagnostics should read as non-primary tooling.
5. Preserve Chapter 357 as the reference production-evidence chapter: Job `17`, Casting Plan `18`, active artifact `48`, final M4A SHA `024e9f8cc1a646095eb84fad71d532fc04875e9eb34609a397e44c6f3153b675`.
6. Do not mutate canonical production audio or submit any new render during the walkthrough unless a future explicit task authorizes it.

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
