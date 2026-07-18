# Next Task

Current Status:
Task 18AL prepared the real Chapter `368` narrator-only production job without starting TTS. Job `22` and JobChapter `22` are durable, non-executable prepared state, pinned to active Text Revision `736` and approved Casting Plan `23` revision `1`.

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
- Chapter `368` Speaker Assignment Draft: Draft `14`, `status = generated`, `stale = false`, `text_revision_id = 736`, `target_count = 0`, `valid_count = 0`, `invalid_count = 0`, remaining unreviewed `0`, review rows `0`, assignments `[]`, invalid items `[]`, cache hit/miss `0/0`
- Chapter `368` approved Final Voice Map / Casting Plan: Plan `23` revision `1`, `status = approved`, `approved_at = 2026-07-18T17:25:23.067196+00:00`, source speaker draft `14`, plan SHA-256 `493e1f39bd353657f6deee0a9ac1124ae3ad47160d5bf7b1b09657f1de1ee9c0`, assignment count `49`, narrator `49`, character `0`, unknown `0`, unresolved `0`, effective voice counts `custom:26 -> 49`
- Voice readiness: custom voice `26` remains active and resolves to canonical usable revision `6`, audio SHA-256 `b641e84e11583bfcbeb76f9a5615c605656e8151679d1286e8f4743c92218ace`
- Chapter `368` prepared job: Job `22`, `status = prepared`, `created_at = 2026-07-18T17:39:08.259402+00:00`, `started_at = null`, `finished_at = null`, `voice_name = custom:26`, `repair_mode = off`, `output_format = m4a`, `skip_completed = true`, `casting_plan_id = 23`
- Chapter `368` prepared JobChapter: JobChapter `22`, `status = pending`, `chapter_id = 368`, `text_revision_id = 736`, `casting_plan_id = 23`, `casting_plan_sha256 = 493e1f39bd353657f6deee0a9ac1124ae3ad47160d5bf7b1b09657f1de1ee9c0`, `artifact_id = null`, `started_at = null`, `finished_at = null`
- Prepared snapshot: Text Revision `736`, Plan `23`, narrator voice `custom:26`, utterances `49`, narrator `49`, character `0`, unknown `0`, unresolved `0`, `custom:26 -> 49`, custom voice revision `6 -> 49`, `resolved_character_voices = {}`
- Chapter `368` execution state: active audio `none`, audio status `not_created`, segments `0`, attempts `0`, repair blocks `0`, artifacts `0`, output/work Chapter `368` paths `0`
- UI/API state after Task 18AL: queue shows Job `#22` as `Đã chuẩn bị`, `0/1` chapters and `0/0` segments, with next explicit action `Bắt đầu render`; that action has not been clicked
- Pre-mutation backup for Task 18AL: `D:\Youtube\Story Trans And Audio\backups\task18al_pre_ch368_prepare_20260718T173847Z.sqlite3`, size `3809280` bytes, SHA-256 `8f48663faa68b744df0cd642879028989edf28ae9cab7e2ad85d9a3756fcac5d`, quick_check `ok`
- Future observations that must remain untouched: Chapter `369` and Chapter `370` have text-remediation observations

Next Recommended Task:
Task 18AM - Explicitly Start and Monitor the Existing Chapter 368 Narrator-Only Prepared Job.

Why:
- Chapter `368` now has the required durable prepared job boundary.
- The next safe workflow boundary is the explicit start action for the existing prepared Job `22`; no second prepare job should be created.

Scope:
1. Re-verify canonical runtime, repository baseline, Chapter `368`, approved Plan `23`, and prepared Job `22`.
2. Confirm Job `22` is still `prepared`, JobChapter `22` is still `pending`, and immutable pins still reference Text Revision `736` and Casting Plan `23`.
3. Start only Job `22` through `POST /api/jobs/22/start` or the supported UI `Bắt đầu render` action.
4. Monitor the same job through render completion or a supported recoverable blocker.
5. Do not call `POST /api/jobs/prepare`, do not create another job, do not create another Text Revision, speaker draft, Casting Plan, or review row.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not modify Chapters `364`, `365`, `366`, or `367`.
- Do not mutate Chapters `369` or `370`.
- Do not prepare another Chapter `368` job unless Job `22` is proven absent by authoritative state.
- Do not start by direct database edit.
- Re-verify Git baseline before starting Job `22`.
