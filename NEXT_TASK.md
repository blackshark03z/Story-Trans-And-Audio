# Next Task

Current Status:
Task 12C1 is complete locally on `main` and ready for final push verification. Production remains cleared for rollout (`PRODUCTION_GO`), and the unified workflow now has an explicit guarded canonical-production mode.

Current Baseline:
- Branch `main`
- Current HEAD = `d4a2afe455f2a9a2f7afaa689f2d9bc3243b249a`
- Task 11D2 acceptance evidence runtime: `D:\Youtube\StoryAudioAcceptanceRun1\data`
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Offline baseline last verified for this line of work: 887 tests passing, 1 skipped
- Official rollout verdict: `PRODUCTION_GO`
- Second acceptance chapter before rollout: not required
- Task 11B2 disposable smoke root: `D:\Youtube\StoryAudioTask11B2Smoke\data`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Next Task:
Task 12C - Run Canonical Production Job for Chapter 357

Why:
- Chapter 357 already has canonical approved Casting Plan `18`, but the unified workflow previously refused the canonical live root unconditionally.
- Task 12C1 adds an explicit opt-in guard `--allow-canonical-production` so the operator can submit one canonical production job only when they also pass `--submit`, exact casting-plan identity, and matching canonical `/api/runtime`.
- The immediate next step is to use that guarded path for the first canonical Chapter 357 production run without falling back to UI Render or ad hoc API calls.

Scope:
1. Verify canonical runtime on `http://127.0.0.1:8772` still points to `D:\Youtube\Story Trans And Audio\data`.
2. Re-verify approved Casting Plan `18` for Chapter 357: revision `1`, `utterance-v3`, 96 utterances, voice distribution `custom:26=90` / `custom:25=6`.
3. Run `scripts/run_production_workflow.py` with `--submit --through checklist --allow-canonical-production` and exact `--casting-plan-id 18`.
4. Require exactly one new canonical job, completed `96/96` verified, no open candidates, and matching manifest / QA / checklist bindings.
5. Do not regenerate, accept/reject, retry, or create replacement jobs unless a later explicit task authorizes it.

Prerequisites For Any Next Task:
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Use `.\run_app.ps1 --host 127.0.0.1 --port 8772 --no-browser` for canonical production startup and verify `GET /api/runtime` before mutating.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local via `run_app.ps1`; do not persist it at user or machine scope.
- Require an explicit isolated `STORY_AUDIO_DATA_DIR` / data root for any new smoke or production-style run.
- For unified canonical production workflow runs, require explicit `--allow-canonical-production` together with `--submit`; canonical mode must never auto-enable from environment alone.
- Preserve live DB guardrails.
- Do not stop or repurpose port `8765`; it belongs to YouTube Auto.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Re-verify Git baseline before implementation.
- Preserve Chapter 357 acceptance evidence:
  - Text Revision `714`
  - Casting Plan `#6`
  - Job `#2`
  - final M4A under `D:\Youtube\StoryAudioAcceptanceRun1\data\output\1-quang-am-chi-ngoai\chapter_0357\job_2\render_0001\`
