# Next Task

Current Status:
Task 18AJ implemented and validated the zero-target narrator-only Final Voice Map workflow, then created exactly one live unapproved narrator-only Casting Plan draft for Chapter `368`: Casting Plan `23` revision `1`, sourced from Speaker Assignment Draft `14` and active Text Revision `736`.

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
- Chapter `368` Final Voice Map / Casting Plan: Plan `23` revision `1`, `status = draft`, `approved = false`, `approved_at = null`, source speaker draft `14`, `remaining_unreviewed_count = 0`, assignment count `49`, narrator `49`, character `0`, unknown `0`, unresolved `0`, effective voice counts `custom:26 -> 49`
- Chapter `368` render-side state: audio status `not_created`, active audio artifact `none`, jobs for chapter `0`, JobChapters `0`, segments `0`, attempts `0`, artifacts `0`, output audio `none`
- UI state after Task 18AJ: Chapter `368` shows `CASTING REVIEW NEEDED` and `NOT RENDERED`; the workflow dialog shows `Technical: Casting Plan #23 / v1`, current step `Bước 4: Duyệt bản đồ giọng cuối`, approve-plan enabled, and `Chuẩn bị job audio` disabled until approval
- Pre-mutation backup from Task 18AJ: `D:\Youtube\Story Trans And Audio\backups\task18aj_pre_ch368_zero_target_plan\app_20260716T132510Z.db`, SHA-256 `c34df076a0aa353d174e9b3a111c508328b618ddc466063b018868069d61d947`, quick_check `ok`
- Future observations that must remain untouched: Chapter `369` and Chapter `370` have text-remediation observations

Next Recommended Task:
Task 18AK - Inspect and Approve Existing Chapter 368 Narrator-Only Final Voice Map 23.

Why:
- Plan `23` revision `1` is a valid unapproved narrator-only Final Voice Map for Chapter `368`.
- The next safe workflow boundary is operator inspection and explicit approval of that existing plan.
- Approval must remain separate from job preparation and render start.

Scope:
1. Re-verify canonical runtime, repository baseline, Chapter `368`, Draft `14`, and Casting Plan `23`.
2. Inspect Plan `23` revision `1` for narrator-only correctness: `49` assignments, narrator `49`, character `0`, unknown `0`, unresolved `0`, `custom:26 -> 49`.
3. If still valid, approve the existing plan through `POST /api/casting/23/approve` or the supported UI approval action.
4. Do not prepare a job, start a job, call TTS, preview TTS, render audio, create another plan, create another speaker draft, or edit Text Revision `736`.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not modify Chapters `364`, `365`, `366`, or `367`.
- Do not mutate Chapters `369` or `370`.
- Do not create another Chapter `368` speaker draft or Casting Plan unless Plan `23` is proven absent/invalid.
- Do not approve by direct database edit.
- Re-verify Git baseline before approval.
