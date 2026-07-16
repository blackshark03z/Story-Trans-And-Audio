# Next Task

Current Status:
Task 18N is complete in canonical production. Chapter 365 now has exactly one real prepared job: Job `19` on approved Text Revision `3983` and approved Casting Plan `20` revision `1`. The worker has not started it, and render-side state remains untouched: segments `0`, attempts `0`, repair blocks `0`, artifacts `0`, audio `0`.

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

Task 18N Outcome:
- Re-verified canonical runtime identity on `http://127.0.0.1:8772` and replaced a stale pre-Task-18M listener through the supported repository launcher before any mutation.
- Re-verified Chapter 365 baseline: active approved Text Revision `3983`, approved Casting Plan `20` revision `1`, Book Voice Profile narrator `custom:26` / male dialogue `custom:25`, and no pre-existing Chapter 365 job.
- Created one pre-mutation SQLite online backup at `backups\\task18n_pre_ch365_prepare_20260716_131349.sqlite3` with SHA-256 `463711f9cde945d7adc9b32d584afb92c69a989cffd5c160af445ff16959744e` and `quick_check = ok`.
- Issued exactly one supported `POST /api/jobs/prepare` call and created exactly one real Chapter 365 prepared job: Job `19`.
- Verified immutable prepared pins on the committed row: Chapter `365`, Text Revision `3983`, Casting Plan `20`, `voice_name = custom:26`, `repair_mode = off`, `output_format = m4a`.
- Verified non-execution boundary held after prepare: job stayed `prepared`, no worker pickup, no segments, no attempts, no repair blocks, no artifacts, and no active audio.
- Verified live UI now shows the prepared Chapter 365 queue item with the separate `Bắt đầu render` action.

Next Recommended Task:
Task 18O - Start the Existing Prepared Chapter 365 Production Job

Why:
- Chapter 365 already has the correct approved Final Voice Map and now also has the correct prepared production job pinned in canonical production.
- The remaining production step is no longer preparation. It is the explicit render-start transition for the already-existing prepared Job `19`.
- Starting the existing prepared job preserves the two-stage boundary and avoids any duplicate prepare or duplicate job creation.

Scope:
1. Re-verify canonical runtime identity and confirm Job `19` is still `prepared`.
2. Re-verify Job `19` still pins Chapter `365`, Text Revision `3983`, and approved Casting Plan `20` revision `1`.
3. Start the existing prepared job through the supported `POST /api/jobs/{job_id}/start` route only.
4. Confirm the same job transitions to the normal executable state exactly once and that the worker begins from that existing pinned identity.
5. Track render execution and downstream QA only after the explicit start boundary is crossed; do not create another prepared job.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not generate another speaker draft or another Casting Plan unless plan `20` is proven absent or invalid.
- Do not call `POST /api/jobs/prepare` again for Chapter 365 unless Job `19` is proven absent and no prepared/live Chapter 365 job exists.
- Use the existing prepared Job `19`; do not create a second Chapter 365 prepared job.
- Re-verify Git baseline before implementation.
