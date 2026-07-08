# Next Task

Current Status:
Task 12D is complete locally on `main`. Chapter 357 canonical Job `17` is now officially recorded as `HUMAN_QA_PASS_WITH_MINOR_PRONUNCIATION_NOTES`; downstream manifest / QA / checklist evidence exists, active artifact `48` remains unchanged, and no production audio or DB mutation was needed beyond the existing Job 17 evidence.

Current Baseline:
- Branch `main`
- Current HEAD = `f6200797ab270a0bcd3a5ddec55bcc9de9610dba`
- Task 11D2 acceptance evidence runtime: `D:\Youtube\StoryAudioAcceptanceRun1\data`
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Offline baseline last verified for this line of work: 898 tests passing, 1 skipped
- Official rollout verdict: `PRODUCTION_GO`
- Second acceptance chapter before rollout: not required
- Task 11B2 disposable smoke root: `D:\Youtube\StoryAudioTask11B2Smoke\data`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Next Task:
Task 12E - Capture Detailed Pronunciation Notes or Select the Next Routine Canonical Production Chapter

Why:
- Chapter 357 canonical Job `17` has now been listened to end-to-end and accepted overall, with only minor pronunciation notes.
- The canonical downstream evidence package already exists, but detailed human notes are not persisted unless the operator exports review JSON or pastes the notes separately.
- The next highest-value step is either to preserve those detailed pronunciation notes explicitly, or move on to the first routine canonical production chapter with the now-validated workflow.

Scope:
1. If the operator wants the minor pronunciation notes preserved, export the Chapter 357 checklist review JSON or paste the note text into the task thread so it can be recorded explicitly.
2. If no detailed note capture is needed, select the next routine canonical production chapter using the production-go workflow and existing rollout guardrails.
3. Preserve Chapter 357 as the first canonical human-QA-passed production evidence set: Job `17`, Casting Plan `18`, active artifact `48`, final M4A SHA `024e9f8cc1a646095eb84fad71d532fc04875e9eb34609a397e44c6f3153b675`.
4. Do not mutate canonical production audio for Chapter 357 unless a future explicit task requests a corrective rerender.

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
