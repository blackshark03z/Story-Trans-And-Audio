# Next Task

Current Status:
Task 18J is complete on canonical production. Chapter 365 now has active approved Text Revision `3983`, stale historical speaker draft `10`, reviewed speaker draft `11`, and exactly one unapproved Final Voice Map / Casting Plan draft: plan `20` revision `1`, status `draft`, approved `false`, provenance `source_speaker_draft_id = 11`, with narrator resolving to `custom:26` and all five Hứa Thanh assignments resolving to `custom:25`.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Task 18J Outcome:
- Recovered canonical runtime on `http://127.0.0.1:8772` to the Task 18I-capable app build before mutation, then confirmed the staged route `POST /api/chapters/{chapter_id}/speaker-review/casting-plan-draft` was live.
- Reused existing speaker draft `11` bound to Text Revision `3983`; no new speaker draft was generated and stale draft `10` remained unchanged on revision `730`.
- Reviewed and accepted all five Draft `11` targets as Hứa Thanh / `character_id 42`: `u0017-d3809b48d599`, `u0032-fe2bc9743573`, `u0034-9634d7a009f0`, `u0039-99e8b095900e`, and `u0046-8cad60adce11`.
- Created exactly one unapproved Final Voice Map through the staged workflow: Casting Plan `20` revision `1`, `status = draft`, `approved_at = null`, `text_revision_id = 3983`, `source_speaker_draft_id = 11`.
- Verified final counts: `47` total assignments, narrator `42`, Hứa Thanh `5`, unknown `0`, effective voices `custom:26 -> 42` and `custom:25 -> 5`, unresolved `0`.
- Verified UI readiness in Chapter 365 Production Flow: the Character Voices / Final Voice Map screen now opens the existing unapproved plan instead of prompting to regenerate speaker assignments, and the separate approval action label is `Duyệt bản đồ giọng cuối & tiếp tục tạo audio (v1)`.
- Safety remained clean after Task 18J: approved Casting Plans `0`, jobs `0`, job_chapters `0`, segments `0`, segment attempts `0`, artifacts `0`, repair blocks `0`, and no TTS preview/synthesis or audio output for Chapter 365.

Next Recommended Task:
Task 18K - Operator Inspect and Approve the Existing Chapter 365 Final Voice Map

Why:
- The production-side review step is already finished: the Chapter 365 Final Voice Map draft exists as Casting Plan `20` revision `1`, pinned to Text Revision `3983`, with the five Hứa Thanh assignments resolved to `custom:25`.
- The UI now exposes the plan through the canonical Production Flow and provides a separate explicit approval action, so the next authorized operator move is to inspect that existing plan and approve it without regenerating anything.
- No render/job/audio state exists yet for Chapter 365, so approval is the remaining gateway before any later audio task can proceed.

Scope:
1. Re-verify canonical runtime and confirm Chapter 365 still shows active Text Revision `3983`, speaker draft `11`, and draft Casting Plan `20` revision `1`.
2. Open Chapter 365 Production Flow and inspect the existing Final Voice Map draft, especially narrator `custom:26` and the five Hứa Thanh utterances on `custom:25`.
3. Use the dedicated approval action `Duyệt bản đồ giọng cuối & tiếp tục tạo audio (v1)` to approve the existing plan only; do not regenerate the speaker draft and do not create a second plan.
4. Verify the plan becomes approved while Chapter 365 still has no job, no segment, no artifact, and no audio output immediately after approval.
5. Stop after approval-state verification; rendering audio belongs to a later explicitly authorized task.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not reapply the Chapter 365 text correction, do not generate another speaker draft, and do not create another Casting Plan unless plan `20` is proven absent.
- Do not synthesize, preview TTS, queue a job, or render audio during the approval task unless a later task explicitly authorizes it.
- Re-verify Git baseline before implementation.
