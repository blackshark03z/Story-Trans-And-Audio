# Next Task

Current Status:
Task 18O is complete in canonical production. Chapter 365 render Job `19` has finished successfully and produced active artifact `72` from approved Text Revision `3983` and approved Casting Plan `20` revision `1`. The output is now at the Human Audio QA boundary: no duplicate job was created, no render retry was needed, and no text/casting/voice identity changed during execution.

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

Task 18O Outcome:
- Re-verified canonical runtime identity and exact prepared state for Job `19`, then created one immediate pre-start SQLite backup at `backups\\task18o_pre_ch365_start_20260716_132718.sqlite3` with SHA-256 `de2ab05faa6b4ee60dfc33f94a4988d2e94e060ae5178c77f54e0966b46c7e0e`.
- Issued exactly one supported `POST /api/jobs/19/start` call. No new job or replacement job was created.
- Canonical lifecycle progressed cleanly as `prepared -> scheduled -> synthesizing -> assembling -> completed`.
- Job `19` started at `2026-07-16T06:27:33.334422+00:00` and finished at `2026-07-16T06:38:14.802745+00:00`; JobChapter `19` finished at `2026-07-16T06:38:14.776740+00:00`.
- Rendered exactly `47` utterance segments with no empty segments, no punctuation-only segments, and no invalid offsets.
- Voice routing stayed correct: narrator `42` via `custom:26`, Hứa Thanh `5` via `custom:25`, unresolved `0`.
- Segment rows show `attempt_count = 1` for all `47` segments, so the run completed in one pass with no retry/failure path; the legacy `segment_attempts` table still has `0` Chapter 365 rows for this successful render.
- Final artifact set is `70` master WAV, `71` segment timeline JSON, and active artifact `72` M4A.
- Final Chapter 365 audio is `D:\\Youtube\\Story Trans And Audio\\data\\output\\1-quang-am-chi-ngoai\\chapter_0365\\job_19\\render_0001\\chapter.m4a`, SHA-256 `4bc75234a5ff804f9dc985af2e46fff2d440f78a061ca749b12e9adcf0375f83`, size `6647393` bytes, duration `408980 ms`, `48000` Hz, mono, AAC-LC in M4A.
- Chapter `365` now has `audio_status = completed` and `active_audio_artifact_id = 72`; Chapter `364` remained unchanged at active artifact `69`.
- Prepared Human Audio QA markers for chapter start/end, all five Hứa Thanh lines, and several duration/loudness outliers that deserve listening review before any targeted remediation.

Next Recommended Task:
Task 18P - Chapter 365 Human Audio QA and Targeted Remediation Review

Why:
- The render boundary is complete and Chapter 365 now has one active production artifact from the canonical pinned inputs.
- The next safe step is human listening review, not another render mutation.
- Any remediation decision should now be based on the produced artifact, the prepared QA markers, and the existing targeted recovery workflow rather than creating a replacement job preemptively.

Scope:
1. Perform a complete Human Audio QA pass on Chapter 365 active artifact `72`.
2. Use the prepared checklist markers: chapter start/end, all five Hứa Thanh lines, and the recorded duration/loudness outliers.
3. Decide whether the artifact is an immediate `HUMAN_QA_PASS` or whether any specific segment needs targeted remediation.
4. If remediation is needed, use only the canonical targeted recovery path on the existing Job `19` / segment identity; do not create a replacement job.
5. Keep Text Revision `3983`, Casting Plan `20`, and speaker draft provenance unchanged unless a separate authorized workflow explicitly changes them.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not generate another speaker draft or another Casting Plan unless plan `20` is proven absent or invalid.
- Do not create another Chapter 365 job.
- Do not rerender the whole chapter if review finds only localized issues.
- Use the existing Job `19` artifact and provenance as the canonical basis for QA or targeted recovery.
- Re-verify Git baseline before implementation.
