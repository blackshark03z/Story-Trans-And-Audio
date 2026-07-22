# Next Task

Task classification:
SYSTEM_ROADMAP / CONTRACT_READY / MUTATION_NOT_AUTHORIZED

Active milestone:
DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout

Completed:
DAILY-PROD-5A - Batch Scope Plan And Mutation Safety Contract

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-1`, `DAILY-PROD-2`, `DAILY-PROD-3`, `DAILY-PROD-4`, and `DAILY-PROD-5A` are complete. Production has a modular shell, read-only state resolver, isolated current-step panels, shared preset/custom voice selectors, contextual Voice Library detour/return, a read-only completed-output Audio Library, a read-only range readiness/exception queue, and a read-only batch scope plan.

Current baseline for the next task:
- Branch `main`
- Last verified commit: `b364b51ed72a4c1e506de12e368a6b5a69a3356e`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema: `12`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- `DAILY-PROD-5A` backend checkpoint: `4784c16c69fbfc6d714c1a636068e35ab41e3bb1`
- `DAILY-PROD-5A` UI checkpoint: `b364b51ed72a4c1e506de12e368a6b5a69a3356e`
- Batch plan for Book `1`, chapters `364-369`, target `PREPARE`, was verified as included `0`, excluded `6`, authorization `MUTATION_NOT_AUTHORIZED`, and execution endpoint unavailable.
- Runtime exclusions from the batch-plan smoke were chapters `364-367` `HUMAN_QA_NOT_ACCEPTED`, chapter `368` `ACTIVE_OUTPUT_COMPLETE`, and chapter `369` `CASTING_PLAN_NOT_APPROVED`.
- Chapter `369`: active Text Revision `738`, Speaker Assignment Draft `15` approved, Casting Plan `24` revision `1` draft/unapproved, no Jobs, no JobChapters, no production segments, no production attempts, no artifacts, no active audio, and audio status `not_created`.

Exact next task:
`DAILY-PROD-5B` - Batch Prepare Mutation Contract And Stale-Plan Guard

Operator pain:
Operators can inspect a deterministic batch plan but cannot yet safely authorize preparation. The system lacks a reviewed mutation contract for stale-plan rejection, duplicate requests, partial failure, per-chapter execution evidence, and retry behavior.

Allowed scope:
- Inspect the existing single-chapter `prepare_job` lifecycle.
- Define the PREPARE-only batch request/response contract.
- Require the deterministic plan fingerprint from `GET /api/production/batch-plan`.
- Define stale-plan rejection.
- Define explicit operator confirmation.
- Define idempotency behavior.
- Define existing prepared Job behavior.
- Define duplicate-request behavior.
- Define per-chapter success/failure result shape.
- Define partial-failure boundaries.
- Define retry behavior.
- Define audit/evidence fields.
- Add contract-focused offline tests.
- Stop before implementation of any mutation endpoint or production mutation.

Excluded scope:
- Do not implement an execution endpoint.
- Do not mutate the database or runtime state.
- Do not approve Speaker Drafts or Casting Plans.
- Do not prepare or start jobs.
- Do not render, regenerate, retry, assemble, or mutate audio/artifacts.
- Do not perform Human QA mutation.
- Do not call provider, Gemini, VieNeu/TTS, or preview synthesis.
- Do not perform batch approval, batch prepare, batch render, or batch QA closeout.
- Do not resolve Chapter `369` production/editorial work unless a later task explicitly selects it.

Acceptance criteria:
1. PREPARE is the only mutation phase considered.
2. Request must include the deterministic plan fingerprint.
3. Stale fingerprint must be rejected.
4. Explicit confirmation is mandatory.
5. Duplicate submission behavior is defined.
6. Existing prepared Job is not duplicated.
7. Per-chapter results are deterministic.
8. Partial failure semantics are explicit.
9. Prepare never starts synthesis.
10. Initial task performs no production mutation.
11. Actual mutation implementation requires a separate review.

Safety gate:
Batch mutation remains unauthorized. The next task must stop before approving plans, preparing jobs, starting renders, generating audio, changing QA state, or implementing a live execution endpoint.

Exact next action:
1. Inspect the existing single-job PREPARE lifecycle.
2. Define the PREPARE-only batch mutation contract.
3. Define plan fingerprint and stale-plan rejection.
4. Define duplicate-request, partial-failure and retry semantics.
5. Add contract-focused tests.
6. Stop before implementation of any mutation endpoint.
