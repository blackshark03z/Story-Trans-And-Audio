# Next Task

Task classification:
SYSTEM_ROADMAP / ORCHESTRATION_DESIGN_AUTHORIZED / CANONICAL_ACTIVATION_NOT_AUTHORIZED / PREPARE_EXECUTION_NOT_AUTHORIZED

Active milestone:
DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout

Exact next task:
`DAILY-PROD-5B Phase 5` - Isolated PREPARE Orchestration And Reconciliation Contract

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-5A` and `DAILY-PROD-5B` Phases 1 through 4 are complete. Phase 4 accepted isolated schema-13 PREPARE request persistence with restart, replay, concurrency, race, rollback, stale APPLYING, and canonical path-safety evidence. Canonical/default runtime schema remains `12`; dormant proposed schema remains `13`.

Operator pain:
The plan contract, durable request store, and isolated persistence acceptance are complete, but the system still lacks a reviewed service-level contract that coordinates plan revalidation, durable ownership, timeout replay, future Job creation, and stale APPLYING reconciliation without double execution.

Current baseline for the next task:

- Branch `main`
- Last verified commit: `f650f6936f89d400579acb882f05704799f6c3c8`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema/latest schema: `12 / 12`
- Dormant proposed schema: `13`
- Dormant migration: `story_audio/migrations/dormant/0013_batch_prepare_requests.sql`
- Durable request store: `story_audio/batch_prepare_store.py`
- Phase 4 validation baseline: isolated suite `9` pass twice; affected suite `142` pass; full offline suite `1248` pass, `1` skipped; Doctor `critical_errors=0`.
- Canonical DB has no `batch_prepare_requests` table, SHA-256 `dba41f6eb3eaba5de4a4d9964f41ee93bb730ac8c2d6fd47df202479ad203b23`, size `4009984` bytes, mtime `2026-07-20T12:31:47.429225`, and `quick_check=ok`.
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Allowed scope:

- Inspect existing service/API conventions.
- Define pure orchestration state flow.
- Define request-store dependency interface.
- Define current-plan dependency interface.
- Define future Job-transaction dependency interface.
- Define durable ownership acquisition.
- Define pre-mutation fingerprint revalidation.
- Define result persistence ordering.
- Define timeout replay.
- Define stale APPLYING reconciliation decisions.
- Define operator-review outcomes.
- Add pure/offline orchestration tests.
- Use temporary or isolated databases only where needed.

Excluded scope:

- API route.
- Canonical schema activation.
- `prepare_job` or `create_job` invocation.
- Real Job/JobChapter creation.
- Production DB mutation.
- UI.
- START_RENDER.
- Provider/Gemini/TTS.
- Chapter 369 production action.

Acceptance criteria:

1. Request intake validates the Phase 1 contract.
2. Durable request record is created or replayed before ownership.
3. Same request never gains two execution owners.
4. Payload mismatch returns `REQUEST_ID_CONFLICT`.
5. APPLIED/REJECTED/FAILED requests replay historically.
6. `PLANNED -> APPLYING` ownership is atomic.
7. Fingerprint is revalidated immediately before the future mutation dependency.
8. Stale fingerprint records deterministic rejection without Job creation.
9. Future Job creation is represented only by an injected fake/interface.
10. APPLIED is recorded only after simulated future transaction success.
11. Failure before success cannot produce false APPLIED.
12. Ambiguous client timeout replays durable state.
13. Stale APPLYING records are classified for retry or operator review.
14. Reconciliation does not automatically execute PREPARE.
15. PREPARE never starts render.
16. No API or real mutation is implemented.

Safety gate:

- `ISOLATED_PREPARE_ORCHESTRATION_DESIGN_AUTHORIZED` applies only to pure design, fake dependencies, offline tests, and temporary/isolated databases when needed.
- `CANONICAL_SCHEMA_13_ACTIVATION_NOT_AUTHORIZED` remains in force.
- `PREPARE_EXECUTION_NOT_AUTHORIZED` remains in force.
- `START_RENDER` remains separate and unauthorized.

Exact next action:

1. Define the pure PREPARE orchestration contract.
2. Define atomic durable ownership and replay behavior.
3. Define pre-mutation fingerprint revalidation.
4. Define stale APPLYING reconciliation.
5. Add offline tests with fake/injected future Job dependencies.
6. Stop before canonical activation, API integration, real Job creation, UI, or START_RENDER.
