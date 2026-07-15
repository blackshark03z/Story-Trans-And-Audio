# Next Task

Current Status:
Task 18F is complete locally. Story Audio now has a supported backend/API workflow for exact immutable targeted text correction on the active approved chapter revision, and no real Chapter 365 production data was mutated during implementation.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Task 18F Outcome:
- Added `POST /api/chapters/{chapter_id}/text-revisions/targeted-correction`
- Added service `story_audio.text_correction.apply_targeted_text_correction(...)`
- Correction path creates exactly one new immutable approved TextRevision and activates it atomically
- Existing speaker drafts remain immutable and become stale through normal active-revision mismatch rules
- UI support was deferred intentionally to keep the change focused
- No real Chapter 365 correction was executed during Task 18F

Next Recommended Task:
Task 18G - Apply the Canonical Targeted Text Correction Workflow to Chapter 365 and Regenerate Exactly One Speaker Draft

Why:
- Chapter 365 remains blocked before casting because approved Text Revision `730` still contains malformed punctuation that splits one internal-thought span into a standalone punctuation utterance.
- Task 18F delivered the missing supported workflow needed to fix that issue safely without going through the Gemini repair/render pipeline.
- The next highest-value step is to use the new canonical correction route operationally on Chapter 365, verify one corrected active revision, and regenerate exactly one fresh speaker-assignment draft bound to that new revision.

Scope:
1. Re-verify Git and canonical runtime baseline before any mutation.
2. Read Chapter 365 active approved Text Revision `730` through the supported workflow only.
3. Apply the exact one-match targeted correction that removes the malformed extra punctuation.
4. Verify one new immutable approved active revision is created and that draft `10` remains immutable but stale.
5. Generate exactly one new Chapter 365 speaker-assignment draft from the corrected active revision.
6. Verify the corrected internal-thought span rebuilds as one utterance and that target count returns from `6` to `5`.
7. Stop before reviewing assignments, creating a Casting Plan, rendering audio, or creating any job/artifact state.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Re-verify Git baseline before implementation.
