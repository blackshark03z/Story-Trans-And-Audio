# Next Task

Current Status:
Task 18AK inspected and approved the existing Chapter `368` narrator-only Final Voice Map. Casting Plan `23` revision `1` is now approved, sourced from zero-target Speaker Draft `14`, pinned to active Text Revision `736`, and ready for the prepare-only production-job boundary.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Completed chapters that must not be mutated:
  - Chapter `364`: `HUMAN_QA_PASS`, active artifact `69`
  - Chapter `365`: `HUMAN_QA_PASS`, active artifact `72`
  - Chapter `366`: `HUMAN_QA_PASS`, active artifact `78`
  - Chapter `367`: `HUMAN_QA_PASS`, active artifact `75`
- Chapter `368`: ID `368`, title `Chương 368`, active approved Text Revision `736`, parent/source Revision `735`, `kind = reflowed`, processor `lossless-reflow-v1`, content SHA-256 `c1e5c935f2df6e411086f87a6ff6c3b03795fe2005382a13cdde1c3376421564`, lexical SHA-256 `f5942c8d31af105fc39c7f0d03c9839d3f534559ee3cd6de56275fb90d230514`, char count `7831`
- Chapter `368` Speaker Assignment Draft: Draft `14`, `status = generated`, `stale = false`, `text_revision_id = 736`, `target_count = 0`, `valid_count = 0`, `invalid_count = 0`, `remaining_unreviewed_count = 0`, review rows `0`, assignments `[]`, invalid items `[]`, cache hit/miss `0/0`, created_at `2026-07-16T12:38:10.049602+00:00`
- Chapter `368` approved Final Voice Map / Casting Plan: Plan `23` revision `1`, `status = approved`, `approved_at = 2026-07-18T17:25:23.067196+00:00`, source speaker draft `14`, plan SHA-256 `493e1f39bd353657f6deee0a9ac1124ae3ad47160d5bf7b1b09657f1de1ee9c0`, assignment count `49`, narrator `49`, character `0`, unknown `0`, unresolved `0`, effective voice counts `custom:26 -> 49`
- Voice readiness: custom voice `26` remains active and resolves to canonical usable revision `6`, audio SHA-256 `b641e84e11583bfcbeb76f9a5615c605656e8151679d1286e8f4743c92218ace`
- Chapter `368` render-side state: audio status `not_created`, active audio artifact `none`, jobs for chapter `0`, JobChapters `0`, segments `0`, attempts `0`, artifacts `0`, output audio `none`
- UI/API state after Task 18AK: `/api/chapters/368/casting` returns approved Plan `23`; the next action is the separate `Chuẩn bị job audio` prepare step; that action has not been clicked
- Future observations that must remain untouched: Chapter `369` and Chapter `370` have text-remediation observations

Next Recommended Task:
Task 18AL - Prepare the Real Chapter 368 Narrator-Only Production Job Without Starting TTS.

Why:
- Chapter `368` now has an approved narrator-only Final Voice Map and is ready for durable job preparation.
- The prepared-job lifecycle requires creating a non-executable prepared job first, then starting render in a later explicit task.

Scope:
1. Re-verify canonical runtime, repository baseline, Chapter `368`, Draft `14`, and approved Casting Plan `23`.
2. Confirm Plan `23` is still approved, still pinned to Text Revision `736`, and still has `49` narrator/custom:26 assignments with `0` character, `0` unknown, and `0` unresolved.
3. Create exactly one prepared production job for Chapter `368` through `POST /api/jobs/prepare` or the supported UI prepare action.
4. Verify the prepared job pins Chapter `368`, Text Revision `736`, Casting Plan `23`, and the narrator-only voice snapshot.
5. Do not start the prepared job, call TTS, preview TTS, render audio, create segments, create attempts, create artifacts, or create output audio.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Create a pre-mutation SQLite backup before preparing the real job.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not modify Chapters `364`, `365`, `366`, or `367`.
- Do not mutate Chapters `369` or `370`.
- Do not create another Chapter `368` speaker draft or Casting Plan unless Plan `23` is proven absent/invalid.
- Do not approve, prepare, or start by direct database edit.
- Re-verify Git baseline before job preparation.
