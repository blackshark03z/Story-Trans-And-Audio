# Next Task

Current Status:
Task 18X completed the same-job recovery for Chapter `367`. Job `20` and JobChapter `20` finished successfully after a single targeted retry of segment `573` / sequence `20`, and Chapter `367` now has active artifact `75`.

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
- Chapter `367` job state: Job `20`, JobChapter `20`, status `completed`, started_at `2026-07-16T08:51:31.019812+00:00`, finished_at `2026-07-16T09:38:49.583451+00:00`
- Chapter `367` downstream production state: Casting Plans `1` approved / `0` draft, jobs `1` completed, job_chapters `1` completed, segments `47` verified / `0` failed / `0` pending, segment attempt counters total `0`, legacy `segment_attempts` rows `0`, repair blocks `0`, artifacts `3` (`1` active), active audio `artifact 75`
- Segment 573 recovery: segment `573`, sequence `20`, utterance `20`, character `Hứa Thanh`, voice `custom:25`, retried once through `POST /api/segments/573/retry`, verified successfully at `2026-07-16T09:33:11.441592+00:00`

Next Recommended Task:
Task 18Y - Chapter 367 Human Audio QA and Targeted Remediation Review.

Why:
- Job `20` is now complete and active audio artifact `75` exists, so the next safe boundary is human audio QA rather than another render mutation.
- Chapter `367` should be listened to sequentially, with attention on the recovered segment `573` and the three remaining character lines.
- Creating another speaker draft, Casting Plan, approval, prepared job, or replacement render job would be a duplicate mutation and is no longer needed.

Scope:
1. Re-verify canonical runtime and Chapter `367` baseline before QA.
2. Inspect the final artifact, segment timeline, and recovered segment 573 placement.
3. Prepare the Human Audio QA checklist for chapter start, chapter end, recovered segment 573, and the remaining three character lines.
4. Stop before any additional remediation unless QA finds a real issue.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not generate another Chapter `367` speaker draft unless Draft `12` is proven absent or invalid.
- Do not create another Casting Plan, approval, prepared job, or replacement job during Task `18Y`.
- Do not start any other job during Task `18Y`.
- Do not mutate Chapter `366`.
- Keep Chapter `366` deferred and unchanged unless a later explicit targeted-remediation task selects it.
- Re-verify Git baseline before implementation.
