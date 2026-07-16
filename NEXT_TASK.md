# Next Task

Current Status:
Task 18U is complete in canonical production. Chapter `367` now has exactly one approved Final Voice Map: Casting Plan `21` revision `1`, approved from speaker draft `12` on active approved Text Revision `734`. No job, TTS, segment, artifact, or audio state exists for Chapter `367`.

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
- Chapter `367` downstream production state: Casting Plans `1` approved / `0` draft, jobs `0`, job_chapters `0`, segments `0`, attempts `0`, artifacts `0`, active audio `none`

Next Recommended Task:
Task 18V - Prepare the Real Chapter 367 Production Job Without Starting TTS.

Why:
- Chapter `367` now has exactly one approved, voice-resolved Final Voice Map.
- The next workflow boundary is durable prepared-job creation, not rendering.
- Creating another speaker draft, Casting Plan, or approval would be a duplicate mutation and is no longer allowed unless the approved plan is proven absent or invalid.

Scope:
1. Re-verify canonical runtime and Chapter `367` baseline before mutation.
2. Re-verify Casting Plan `21` revision `1` is still approved, non-stale, voice-resolved, and pinned to active approved Text Revision `734`.
3. Create exactly one prepared Chapter `367` production job through the supported prepare-only workflow.
4. Confirm the prepared job pins Chapter `367`, Text Revision `734`, and Casting Plan `21` revision `1`.
5. Stop before job start, worker execution, TTS, segment creation, artifact creation, or audio render.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not generate another Chapter `367` speaker draft unless Draft `12` is proven absent or invalid.
- Do not create another Casting Plan or approve another plan during Task `18V`.
- Do not start rendering during Task `18V`.
- Do not create any Chapter `367` segment, attempt, artifact, TTS preview, TTS synthesis, or audio output during Task `18V`.
- Keep Chapter `366` deferred and unchanged unless a later explicit targeted-remediation task selects it.
- Re-verify Git baseline before implementation.
