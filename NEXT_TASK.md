# Next Task

Current Status:
Task 18I implementation is complete in code. The canonical workflow now supports staged speaker review that creates a draft-only Final Voice Map/Casting Plan without auto-approval, and Chapter 365 production data remains unchanged from Task 18G: active Text Revision `3983`, stale speaker draft `10`, and fresh speaker draft `11` with five review targets.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Task 18I Outcome:
- Added staged backend service `create_casting_plan_draft_from_speaker_review(...)` that requires complete row review, creates a draft-only Casting Plan, verifies resolved voices, and never auto-approves.
- Added canonical staged API route `POST /api/chapters/{chapter_id}/speaker-review/casting-plan-draft`.
- Legacy one-step approval route stays available for compatibility, but the staged route is now the intended operator path.
- UI now labels the speaker-review action as `Tạo Final Voice Map draft` and only enables it when all review rows are covered locally.
- Focused verification passed: `node --check ui/app.js` and Python unittest suite `tests.test_speaker_assignment`, `tests.test_speaker_review_api`, `tests.test_speaker_review_ui` at `42/42`.
- No canonical runtime mutation was performed while implementing Task 18I. Chapter 365 still has no Casting Plan, approved plan, job, segment, attempt, artifact, manifest, or audio output.

Next Recommended Task:
Task 18J - Review Chapter 365 Speaker Draft 11 and Create the First Draft-Only Final Voice Map Through the Canonical Staged Workflow

Why:
- The text-side blocker is already cleared on canonical production: the malformed punctuation split is gone and the corrected internal-thought line rebuilds as one complete utterance on active Text Revision `3983`.
- Draft `11` is still the first valid Chapter 365 suggestion set bound to revision `3983`; it should be reused rather than regenerated.
- The codebase now supports the missing staged boundary, so the next useful production step is operator review of the five rows followed by creation of the first draft-only Final Voice Map, without approving it yet and without creating duplicate plans.

Scope:
1. Re-verify canonical runtime, active Text Revision `3983`, and existence of speaker draft `11` before any further mutation.
2. Reuse existing draft `11`; do not regenerate a speaker draft and do not repeat the targeted correction.
3. Review the five reconstructed rows on draft `11`, including the corrected internal-thought utterance `u0032-fe2bc9743573`.
4. If editorial review agrees, use the staged route `POST /api/chapters/{chapter_id}/speaker-review/casting-plan-draft` to create exactly one draft-only Final Voice Map from draft `11`.
5. Stop after draft creation and verification of its identity/state; do not approve the Final Voice Map and do not render audio unless a later task explicitly authorizes it.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not reapply the Chapter 365 text correction and do not create another speaker draft unless draft `11` is proven unusable.
- Do not auto-approve the resulting Final Voice Map; approval is now a separate later task by design.
- Re-verify Git baseline before implementation.
