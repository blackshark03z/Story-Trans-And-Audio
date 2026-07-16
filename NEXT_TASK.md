# Next Task

Current Status:
Task 18AI created exactly one provider-free zero-target Speaker Assignment Draft for Chapter `368`, Draft `14`, pinned to active Text Revision `736`. The draft is valid and review-complete under zero-row semantics, but the current UI/API cannot create a narrator-only Final Voice Map from an empty review-decision set.

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
- Chapter `368` text readiness: deterministic utterances `49`; sequence range `1-49`; all roles `narrator`; quote spans `0`; speaker targets `0`; empty utterances `0`; punctuation-only utterances `0`; malformed quote targets `0`; offset gaps/overlaps `0`; duplicate sequence/stable IDs `0`; utterance character counts min `15`, max `243`, median `175`
- Chapter `368` Speaker Assignment Draft: Draft `14`, `status = generated`, `stale = false`, `text_revision_id = 736`, `target_count = 0`, `valid_count = 0`, `invalid_count = 0`, `remaining_unreviewed_count = 0`, review rows `0`, assignments `[]`, invalid items `[]`, cache hit/miss `0/0`, created_at `2026-07-16T12:38:10.049602+00:00`
- Provider safety from Task `18AI`: provider call count `0`, Gemini call count `0`, provider cache writes `0`; provider cache file count stayed `88`
- Chapter `368` render-side state: Casting Plans `0`, jobs `0`, JobChapters `0`, segments `0`, attempts `0`, repair blocks `0`, artifacts `0`, active audio `none`, audio status `not_created`
- Expected narrator-only plan shape after workflow support exists: total assignments `49`, narrator `49`, character `0`, unknown `0`, unresolved `0`, `custom:26 -> 49`, `custom:25 -> 0`
- Current blocker: UI `reviewReadyForCastingPlan(review)` requires `reviewedDecisionCount(review) > 0`, `approveSpeakerReview()` refuses empty decisions, and backend `create_casting_plan_draft_from_speaker_review(...)` rejects `decisions = []` with `At least one reviewed decision is required`
- Future observations that must remain untouched: Chapter `369` and Chapter `370` have text-remediation observations

Next Recommended Task:
Task 18AJ - Implement and Validate Zero-Target Narrator-Only Final Voice Map Workflow for Chapter 368 Draft 14.

Why:
- Draft `14` correctly represents that Chapter `368` has zero speaker targets and zero review rows.
- The next safe workflow step should create an unapproved narrator-only Final Voice Map from Draft `14`, but the current UI/API requires at least one reviewed decision.
- Creating fake review rows, fabricating dialogue, skipping Draft `14`, or using direct DB edits would violate the canonical workflow.

Scope:
1. Re-verify canonical runtime, repository baseline, and Chapter `368` Draft `14`.
2. Update the supported zero-target speaker-review-to-casting-plan workflow so an empty, non-stale, review-complete draft can create one unapproved narrator-only Final Voice Map.
3. Ensure UI enables the safe zero-target next action without creating duplicate drafts or requiring fabricated decisions.
4. Add focused tests for zero-target draft review completion and narrator-only Casting Plan draft creation.
5. Do not approve the plan, prepare/start a job, call TTS, or render audio unless a later task explicitly authorizes it.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not modify Chapters `364`, `365`, `366`, or `367`.
- Do not mutate Chapters `369` or `370`.
- Do not create another Chapter `368` speaker draft unless Draft `14` is proven absent or invalid.
- Do not create a fake speaker target or convert narrator utterances into dialogue.
- Re-verify Git baseline before implementation.
