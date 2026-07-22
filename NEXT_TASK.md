# Next Task

Task classification:
SYSTEM_ROADMAP / CONTRACT_READY / MUTATION_NOT_AUTHORIZED

Active milestone:
DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout

Completed:
DAILY-PROD-5A - Batch Scope Plan And Mutation Safety Contract

DAILY-PROD-5B Phase 1 - Pure PREPARE Mutation Safety Contract

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-1`, `DAILY-PROD-2`, `DAILY-PROD-3`, `DAILY-PROD-4`, `DAILY-PROD-5A`, and `DAILY-PROD-5B Phase 1` are complete. The system can inspect deterministic batch plans and validate a PREPARE request through a pure fail-closed contract, but PREPARE execution remains unauthorized.

Current baseline for the next task:
- Branch `main`
- Last verified commit: `a3d6f956a103ed563f5bd9ea6496ea0da307440c`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema: `12`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Pure PREPARE contract checkpoint: `a3d6f956a103ed563f5bd9ea6496ea0da307440c`
- Validation baseline: focused/affected tests `57` pass; full offline suite `1158` pass, `1` skipped; Doctor `critical_errors=0`.
- Canonical PREPARE contract smoke for Book `1`, chapters `364-369`, returned included `0`, excluded `6`, valid result `REJECTED_NO_ELIGIBLE_CHAPTERS`, stale result `REJECTED_STALE_PLAN`, missing-confirmation result `REJECTED_CONFIRMATION_REQUIRED`, and unchanged sensitive counts.
- Chapter `369`: active Text Revision `738`, Speaker Assignment Draft `15` approved, Casting Plan `24` revision `1` draft/unapproved, no Jobs, no JobChapters, no production segments, no production attempts, no artifacts, no active audio, and audio status `not_created`.

Execution authorization:
PREPARE_EXECUTION_NOT_AUTHORIZED

Exact next task:
`DAILY-PROD-5B Phase 2` - PREPARE Idempotency Persistence And Atomic Execution Design

Operator pain:
The system can validate a PREPARE request but cannot safely execute one after repeated submission, client timeout, or process interruption because there is no durable request identity, result replay, or batch-level retry contract.

Allowed scope:
- Inspect schema and migration conventions.
- Design durable PREPARE request identity.
- Define client request ID rules.
- Bind request to scope, target phase, and plan fingerprint.
- Define request state machine.
- Define duplicate request replay.
- Define in-progress duplicate response.
- Define completed duplicate response.
- Define failed request behavior.
- Define retry after client timeout.
- Define transaction and atomicity policy.
- Decide whether one batch creates one Job or multiple Jobs.
- Define per-chapter audit/result representation.
- Define migration requirements.
- Define retention and cleanup policy.
- Define exact authorization gates for later implementation.
- Add design/contract tests where possible.
- Perform no production mutation.

Excluded scope:
- Do not implement an execution endpoint.
- Do not create Jobs or JobChapters.
- Do not start or resume render.
- Do not mutate Human QA.
- Do not call provider, Gemini, VieNeu/TTS, or preview synthesis.
- Do not create artifacts or audio.
- Do not perform Chapter `369` production action.

Acceptance criteria:
1. Durable request identity is defined.
2. Same client request ID cannot bind to different scope or fingerprint.
3. Duplicate completed request returns the original result.
4. Duplicate in-progress request does not start a second mutation.
5. Stale fingerprint is rejected before mutation.
6. Request state machine is explicit.
7. Atomicity policy is explicit.
8. Retry-after-timeout behavior is explicit.
9. Per-chapter audit/result schema is explicit.
10. Migration requirement is documented.
11. PREPARE remains separate from START_RENDER.
12. No execution endpoint or production mutation is implemented.

Safety gate:
PREPARE execution remains unauthorized. Phase 2 may design persistence, request identity, replay, atomicity, and retry behavior, but must stop before migration implementation, execution endpoint, Job creation, or production mutation.

Exact next action:
1. Inspect schema and migration conventions.
2. Design durable PREPARE request identity.
3. Define request state machine and fingerprint binding.
4. Define duplicate replay and retry-after-timeout.
5. Define atomicity and per-chapter audit/result schema.
6. Stop before migration implementation or execution endpoint.
