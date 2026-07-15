# Next Task

Current Status:
Task 18G is complete on canonical production. Chapter 365 was corrected exactly once through the supported targeted-correction API, active Text Revision moved from `730` to `3983`, stale speaker draft `10` remains intact, and fresh speaker draft `11` is now ready for operator review with exactly five clean targets.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Task 18G Outcome:
- Supported route `POST /api/chapters/{chapter_id}/text-revisions/targeted-correction` was used exactly once on canonical runtime after confirming the new code was loaded.
- Pre-mutation production backup: `backups\\task18g_pre_ch365_targeted_correction_20260715_191351.sqlite3`
- Chapter 365 active revision changed from `730` to `3983`
- Exact correction applied once:
  - Before: `"Không biết so với đội trưởng, sức mạnh của ta bây giờ đã như thế nào.... ."`
  - After: `"Không biết so với đội trưởng, sức mạnh của ta bây giờ đã như thế nào..."`
- New revision `3983` details:
  - `kind = repaired`
  - `status = approved`
  - `parent_revision_id = 730`
  - `processor_version = targeted-correction-v1`
  - `content_sha256 = e0e76f8d80a2c2fbee49676db4175cac1bb3e6e779d343021e8cfc3e174bd1a6`
  - `lexical_sha256 = 72115486b4e139682fc9388f48e58d39633a1c9475ceaf19e4a5f46efbb609cc`
  - `char_count = 6480`
- Minimal-diff validation passed: one changed block, lexical integrity preserved, punctuation-only orphan removed, and Chapter 365 quote/thought target count returned from `6` to `5`.
- Draft `10` remains immutable and stale on revision `730`.
- Exactly one new speaker draft `11` was created for revision `3983` with `target_count = 5`, `valid_count = 5`, `invalid_count = 0`, `remaining_unreviewed_count = 5`, `reused = false`, `cache_hit_count = 0`, and `cache_miss_count = 1`.
- Chapter 365 still has no Casting Plan, approved plan, job, segment, segment attempt, artifact, manifest, or audio output.

Next Recommended Task:
Task 18H - Review Chapter 365 Speaker Draft 11 and Create the First Casting Plan Through the Canonical Review Workflow

Why:
- The text-side blocker is now cleared: the malformed punctuation split is gone and the corrected internal-thought line rebuilds as one complete utterance.
- Draft `11` is the first valid Chapter 365 suggestion set bound to the corrected active Text Revision `3983`.
- The next useful production step is editorial review of those five rows and controlled progression into the first Casting Plan, without regenerating text or creating duplicate drafts.

Scope:
1. Re-verify canonical runtime, active Text Revision `3983`, and existence of speaker draft `11` before any further mutation.
2. Reuse existing draft `11`; do not regenerate a speaker draft and do not repeat the targeted correction.
3. Review the five reconstructed rows on draft `11`, including the corrected internal-thought utterance `u0032-fe2bc9743573`.
4. If editorial review agrees, use the supported speaker-review approval workflow to create the first Chapter 365 Casting Plan from draft `11`.
5. Stop after Casting Plan creation/approval scope defined by that task; do not render audio unless a later task explicitly authorizes it.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not reapply the Chapter 365 text correction and do not create another speaker draft unless draft `11` is proven unusable.
- Re-verify Git baseline before implementation.
