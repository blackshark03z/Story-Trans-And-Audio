# Next Task

Current Status:
Task 18M is complete in code and tests. The repository now supports a durable prepared-job lifecycle, while canonical Chapter 365 production data remains unchanged: active approved Text Revision `3983`, approved Casting Plan `20` revision `1`, and jobs / job_chapters / segments / attempts / artifacts / audio all remain `0`.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Task 18M Outcome:
- Confirmed the previous root cause: `POST /api/jobs` created a scheduled job and woke the live worker immediately, so there was no durable preparation-only state.
- Added explicit supported routes `POST /api/jobs/prepare` and `POST /api/jobs/{job_id}/start`.
- `prepare` now creates exactly one `jobs` row plus one `job_chapters` row, pins the active approved Text Revision plus approved Casting Plan, persists `status='prepared'`, and does not wake the worker or create any segment/attempt/artifact/audio state.
- `start` now reuses the same prepared job, atomically transitions it to the normal executable state, and wakes the worker only after the transition commits.
- Prepared jobs are now excluded from worker selection and survive app/worker restart unchanged.
- Legacy `POST /api/jobs` remains compatible by internally reusing the same job through prepare-then-start, without creating a duplicate job.
- Segmentation boundary is now explicit: prepare stores immutable pins only; deterministic segmentation still happens only after explicit start.
- Chapter 365 production data was not mutated during Task 18M.

Next Recommended Task:
Task 18N - Prepare the Real Chapter 365 Production Job Without Starting TTS

Why:
- Chapter 365 already has the correct approved Final Voice Map and now the codebase has the required durable preparation-only lifecycle.
- The next safe operational step is to exercise that lifecycle once on canonical production by preparing the real Chapter 365 job without starting render execution.
- This keeps the irreversible render boundary separate from the immutable identity-pinning step.

Scope:
1. Re-verify canonical runtime identity and Chapter 365 baseline before any mutation.
2. Use the supported `prepare` workflow only for Chapter 365 with approved Casting Plan `20` revision `1`.
3. Confirm the created prepared job pins the active approved Text Revision and approved Casting Plan exactly.
4. Confirm the prepared job does not wake the worker, does not create segments/attempts/artifacts/audio, and remains restart-safe.
5. Stop before `start`, before any Gemini/TTS call, and before any audio render activity.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not generate another speaker draft or another Casting Plan unless plan `20` is proven absent or invalid.
- Do not start render, preview TTS, synthesize audio, or create a second Chapter 365 prepared job during Task 18N.
- Re-verify Git baseline before implementation.
