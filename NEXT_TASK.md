# Next Task

Current Status:
Task 18W reached a meaningful terminal blocker. Chapter `367` Job `20` was started exactly once through the canonical start route and ran on the same prepared Job/JobChapter, but render stopped at segment `573` / sequence `20` / utterance `20` (`"Quá ít."`) after 3 failed synthesis QA attempts for excessive silence. No final artifact and no active audio were created.

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
- Chapter `367` job state: Job `20`, JobChapter `20`, status `completed_with_errors` / `failed`, started_at `2026-07-16T08:51:31.019812+00:00`, finished_at `2026-07-16T08:57:28.266916+00:00`
- Chapter `367` downstream production state: Casting Plans `1` approved / `0` draft, jobs `1` completed_with_errors, job_chapters `1` failed, segments `47` (`19` verified / `1` failed / `27` pending), segment attempt counters total `22`, legacy `segment_attempts` rows `0`, repair blocks `0`, artifacts `0`, active audio `none`
- Failed segment: segment `573`, sequence `20`, utterance `20`, character `Hứa Thanh`, voice `custom:25`, text `"Quá ít."`, error `Excessive silence in synthesized audio: 83.0% silent (16.1s of 19.4s total), longest continuous silence: 10.1s`

Next Recommended Task:
Task 18X - Recover Chapter 367 Job 20 Segment 20 Silence Failure Without Creating a Replacement Job.

Why:
- Job `20` already contains the canonical production identity and 19 verified segment files, so recovery must preserve successful work rather than create a duplicate production job.
- The blocker is narrow and diagnostic: segment `573` / sequence `20` failed synthesis QA because the generated audio was mostly silence for the short text `"Quá ít."`.
- Creating another speaker draft, Casting Plan, approval, prepared job, or replacement render job would be a duplicate mutation and is no longer allowed unless same-job recovery is proven unsupported.

Scope:
1. Re-verify canonical runtime and Chapter `367` baseline before mutation.
2. Re-verify Job `20` / JobChapter `20` are still the only Chapter `367` production job rows and remain pinned to Text Revision `734` and Casting Plan `21` revision `1`.
3. Inspect the supported diagnostics/retry/resume API surface for failed segment `573`; do not call a broad full-job replacement workflow.
4. Recover only through the canonical same-job path, preserving verified segments `1-19`.
5. Do not switch provider, voice, text, casting, character identity, or Book Voice Profile without explicit authorization.
6. If recovery completes the render, validate the final artifact and stop at Human Audio QA. If same-job recovery is unsupported, report the blocker without creating a replacement job.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not generate another Chapter `367` speaker draft unless Draft `12` is proven absent or invalid.
- Do not create another Casting Plan, approval, prepared job, or replacement job during Task `18X`.
- Do not start any other job during Task `18X`.
- Do not regenerate all segments unless a later explicit operator task authorizes it after same-job recovery is proven impossible.
- Keep Chapter `366` deferred and unchanged unless a later explicit targeted-remediation task selects it.
- Re-verify Git baseline before implementation.
