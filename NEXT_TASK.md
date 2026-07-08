# Next Task

Current Status:
Task 12C3 is complete locally on `main` and ready for final push verification. Production remains cleared for rollout (`PRODUCTION_GO`), canonical production still fail-closes by default, preflight now accepts active usable custom voice IDs, and downstream canonical QA/checklist can now be explicitly authorized for an existing completed job.

Current Baseline:
- Branch `main`
- Current HEAD = `760d1f193933731fa1dfe3d17d098502127217a7`
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
Task 12C - Resume Canonical Downstream Outputs for Chapter 357 Job 17

Why:
- Chapter 357 already has canonical completed Job `17`, active artifact `48`, and final M4A SHA `024e9f8cc1a646095eb84fad71d532fc04875e9eb34609a397e44c6f3153b675`.
- Task 12C3 removes the remaining blocker after submit: downstream `audio_qa` and `listening_checklist` can now run against canonical production only when the operator passes explicit canonical approval and an exact `--job-id`.
- The immediate next step is to rerun the unified workflow in downstream-only mode for Job `17` so canonical manifest / QA JSON / listening checklist can be generated without creating any new job.

Scope:
1. Verify canonical runtime on `http://127.0.0.1:8772` still points to `D:\Youtube\Story Trans And Audio\data`.
2. Re-verify existing canonical Job `17` bindings: Chapter `357`, Text Revision `714`, Casting Plan `18`, active artifact `48`, final M4A SHA `024e9f8cc1a646095eb84fad71d532fc04875e9eb34609a397e44c6f3153b675`.
3. Run `scripts/run_production_workflow.py` with `--job-id 17 --through checklist --allow-canonical-production` and exact `--casting-plan-id 18`.
4. Require canonical manifest / QA / checklist outputs under `D:\Youtube\Story Trans And Audio\data\workflow\job_17_chapter_357\` with no new job, no new audio artifact, and matching Job / Text Revision / Casting Plan / active artifact bindings.
5. Do not submit, render, retry, regenerate, accept/reject, or create replacement jobs unless a later explicit task authorizes it.

Prerequisites For Any Next Task:
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Use `.\run_app.ps1 --host 127.0.0.1 --port 8772 --no-browser` for canonical production startup and verify `GET /api/runtime` before mutating.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local via `run_app.ps1`; do not persist it at user or machine scope.
- Require an explicit isolated `STORY_AUDIO_DATA_DIR` / data root for any new smoke or production-style run.
- For unified canonical production workflow runs, require explicit `--allow-canonical-production`; creation of a new canonical job still requires `--submit`, while downstream-only canonical outputs require an exact `--job-id`.
- Custom voice bindings in approved canonical plans are now valid only when they resolve to active usable library entries with a preferred or latest usable revision; inactive or revision-less custom voices must still fail closed.
- Preserve live DB guardrails.
- Do not stop or repurpose port `8765`; it belongs to YouTube Auto.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Re-verify Git baseline before implementation.
- Preserve Chapter 357 acceptance evidence:
  - Text Revision `714`
  - Casting Plan `#6`
  - Job `#2`
  - final M4A under `D:\Youtube\StoryAudioAcceptanceRun1\data\output\1-quang-am-chi-ngoai\chapter_0357\job_2\render_0001\`
