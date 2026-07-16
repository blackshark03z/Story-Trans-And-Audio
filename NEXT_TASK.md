# Next Task

Current Status:
Task 18V is complete in canonical production. Chapter `367` now has exactly one prepared production job: Job `20` / JobChapter `20`, pinned to active approved Text Revision `734` and approved Casting Plan `21` revision `1`. No TTS, segment, artifact, or audio state exists for Chapter `367`.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Chapter `367` active approved Text Revision: `734`
- Chapter `367` speaker draft state: exactly one draft, Draft `12`
- Chapter `367` approved Casting Plan: `21` revision `1`, approved at `2026-07-16T08:16:25.730916+00:00`
- Chapter `367` prepared job state: Job `20`, JobChapter `20`, status `prepared`, started_at `null`, finished_at `null`
- Chapter `367` downstream production state: Casting Plans `1` approved / `0` draft, jobs `1` prepared / `0` scheduled / `0` queued / `0` running, job_chapters `1`, segments `0`, attempts `0`, artifacts `0`, active audio `none`

Next Recommended Task:
Task 18W - Explicitly Start and Monitor the Existing Chapter 367 Prepared Job.

Why:
- Chapter `367` now has exactly one durable prepared job, and the next workflow boundary is explicit start + monitoring.
- The prepare-only lifecycle has already been validated on the real chapter, so the next safe step is to start the same prepared job rather than preparing a second one.
- Creating another speaker draft, Casting Plan, approval, or prepared job would be a duplicate mutation and is no longer allowed unless the current prepared job is proven absent or invalid.

Scope:
1. Re-verify canonical runtime and Chapter `367` baseline before mutation.
2. Re-verify Job `20` is still prepared, non-stale, and pinned to Chapter `367`, Text Revision `734`, and Casting Plan `21` revision `1`.
3. Start the existing prepared job through the supported start-only workflow.
4. Confirm the same job transitions exactly once and the worker wakes only after commit.
5. Stop before any render-side remediation or audio closeout work.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not generate another Chapter `367` speaker draft unless Draft `12` is proven absent or invalid.
- Do not create another Casting Plan, approval, or prepared job during Task `18W`.
- Do not start any other job during Task `18W`.
- Do not create any Chapter `367` segment, attempt, artifact, TTS preview, TTS synthesis, or audio output during Task `18W`.
- Keep Chapter `366` deferred and unchanged unless a later explicit targeted-remediation task selects it.
- Re-verify Git baseline before implementation.
