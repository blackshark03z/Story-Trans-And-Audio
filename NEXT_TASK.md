# Next Task

Current Status:
Task 18K is complete on canonical production. Chapter 365 now has active approved Text Revision `3983`, stale historical speaker draft `10`, reviewed non-stale speaker draft `11`, and exactly one approved Final Voice Map / Casting Plan: plan `20` revision `1`, status `approved`, approved at `2026-07-15T13:39:48.199756+00:00`, with narrator resolving to `custom:26` and all five Hứa Thanh assignments resolving to `custom:25`.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Task 18K Outcome:
- Re-verified canonical runtime and confirmed Chapter 365 still matched the draft-only Task 18J state before mutation: Text Revision `3983`, reviewed speaker draft `11`, stale draft `10`, and exactly one unapproved Casting Plan `20` revision `1`.
- Verified the approval boundary in code before mutation: UI action `Duyệt bản đồ giọng cuối & tiếp tục tạo audio (v1)` uses `POST /api/casting/{casting_plan_id}/approve`, and backend `approve_plan(...)` only marks the existing draft plan approved plus voice validation. It does not create jobs, job_chapters, segments, TTS activity, artifacts, or manifests.
- Re-verified the Final Voice Map content: `47` total assignments, narrator `42`, Hứa Thanh `5`, unknown `0`, unresolved `0`, effective voices `custom:26 -> 42` and `custom:25 -> 5`, and no punctuation-only utterance.
- Approved exactly the existing Plan `20` revision `1` through the dedicated existing-plan approval route. No successor revision and no duplicate plan were created.
- Approval timestamp is `2026-07-15T13:39:48.199756+00:00`. Plan provenance remains Text Revision `3983` and source speaker-review draft `11`.
- Safety remained clean after approval: Chapter 365 jobs `0`, job_chapters `0`, segments `0`, segment attempts `0`, artifacts `0`, repair blocks `0`, manifests `0`, new text revisions `0`, and no provider/TTS/audio activity.
- Post-approval UI state is now render-ready by design: with `casting.status='approved'` and no active audio, the verified Production Flow advances to `Bước 5: Tạo audio chương`. No render action was invoked during Task 18K.

Next Recommended Task:
Task 18L - Chapter 365 Pre-Render Readiness and Production Job Preparation

Why:
- Chapter 365 now has the required approved Final Voice Map in canonical production, so the next safe step is a strict pre-render readiness pass before any job creation.
- The chapter still has zero job/audio state, which makes it the correct boundary to verify runtime identity, voice availability, immutable plan binding, and operator readiness without yet synthesizing audio.
- The Production Flow is now in the render-ready state, but job creation should remain a separately authorized step.

Scope:
1. Re-verify canonical runtime and confirm Chapter 365 still shows active Text Revision `3983` and approved Casting Plan `20` revision `1`.
2. Confirm the approved plan still resolves narrator `custom:26` and the five Hứa Thanh utterances to `custom:25`, with no assignment drift.
3. Perform pre-render checks only: runtime identity, plan approval state, voice availability, chapter/job duplication guard, and any required production-runner inputs.
4. Prepare the exact job-creation command or supported workflow path for Chapter 365 without executing it unless a later task explicitly authorizes rendering.
5. Stop before any provider call, TTS synthesis, segment creation, manifest creation, artifact creation, or audio output.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not reapply the Chapter 365 text correction, do not generate another speaker draft, and do not create another Casting Plan unless plan `20` is proven absent or invalid.
- Do not synthesize, preview TTS, queue a production job, or render audio during Task 18L unless the next task explicitly authorizes it.
- Re-verify Git baseline before implementation.
