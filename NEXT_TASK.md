# Next Task

Task classification:
SYSTEM_ROADMAP / CONTRACT_READY / MUTATION_NOT_AUTHORIZED

Active milestone:
DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-1`, `DAILY-PROD-2`, `DAILY-PROD-3`, and `DAILY-PROD-4` are complete. Production has a modular shell, read-only state resolver, isolated current-step panels, shared preset/custom voice selectors, contextual Voice Library detour/return, a read-only completed-output Audio Library, and a read-only range readiness/exception queue.

Current baseline for the next task:
- Branch `main`
- Last verified commit: `537af32ab83e8d369dea954c787192f2d032681f`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema: `12`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- `DAILY-PROD-4A` backend checkpoint: `eaffadb5d56411c15fdeeb969361eb97a5cbfb8f`
- `DAILY-PROD-4A` UI checkpoint: `537af32ab83e8d369dea954c787192f2d032681f`
- Range readiness for Book `1`, chapters `364-369`, was verified as total `6`, complete `1`, ready_to_prepare `0`, needs_attention `5`, prepared/rendering/paused `0`.
- Runtime states from the range smoke were `364-367 RENDERED_NOT_QA`, `368 COMPLETE`, and `369 CASTING_REVIEW`.
- Chapter `369`: active Text Revision `738`, Speaker Assignment Draft `15` approved, Casting Plan `24` revision `1` draft/unapproved, no Jobs, no JobChapters, no production segments, no production attempts, no artifacts, no active audio, and audio status `not_created`.

Exact next task:
`DAILY-PROD-5A` - Batch Scope Plan And Mutation Safety Contract

Operator pain:
Operators can now inspect a range and see which chapters are complete, blocked, QA-needed, or casting-needed, but batch actions are still intentionally unavailable. Before any batch approval/prepare/render/QA work is implemented, the system needs a deterministic plan contract that says exactly what would happen, what is excluded, how repeated actions behave, and where partial failures stop.

Allowed scope:
- Design a read-only batch scope plan contract that consumes existing range readiness results.
- Define batch eligibility and exclusion rules for complete, QA-needed, blocked, unresolved, prepared, running/paused, ready-to-prepare, and casting-review chapters.
- Define the operator confirmation model required before any future batch mutation.
- Define idempotency, retry, partial-failure, and recovery semantics.
- Define how future batch prepare/start/render/QA actions must preserve existing single-chapter lifecycle boundaries.
- Add documentation and tests for the read-only contract if implementation is authorized inside this task.

Excluded scope:
- Do not approve Speaker Drafts or Casting Plans.
- Do not prepare or start jobs.
- Do not render, regenerate, retry, assemble, or mutate audio/artifacts.
- Do not perform Human QA mutation.
- Do not call provider, Gemini, VieNeu/TTS, or preview synthesis.
- Do not implement batch mutation endpoints.
- Do not perform batch approval, batch prepare, batch render, or batch QA closeout.
- Do not resolve Chapter `369` production/editorial work unless a later task explicitly selects it.

Acceptance criteria:
- The next batch direction is described as a deterministic read-only plan before mutation.
- Eligibility and exclusion rules are explicit for each range readiness state.
- Already completed chapters are skipped from active artifact state, not newest-job heuristics.
- Chapters requiring operator review remain routed to existing single-chapter workflows.
- Repeated future batch actions have defined idempotency and conflict behavior.
- Partial failure behavior is defined before any render or provider/TTS boundary.
- Future batch mutation remains gated behind explicit operator confirmation.
- Validation confirms no production data, job, artifact, audio, provider, or protected-path mutation occurred.

Safety gate:
Batch mutation is not authorized yet. The next task must stop before approving plans, preparing jobs, starting renders, generating audio, or changing QA state.

Exact next action:
1. Open existing range-readiness contract and job lifecycle documentation.
2. Define deterministic batch-plan eligibility and exclusions.
3. Define idempotency, retry and partial-failure semantics.
4. Implement only a read-only plan contract in the next phase.
5. Stop before any batch mutation endpoint.
