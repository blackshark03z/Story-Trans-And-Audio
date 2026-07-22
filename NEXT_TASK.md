# Next Task

Task classification:
SYSTEM_ROADMAP / JOB_ADAPTER_DESIGN_AUTHORIZED / ADAPTER_IMPLEMENTATION_NOT_AUTHORIZED / CANONICAL_ACTIVATION_NOT_AUTHORIZED / PREPARE_EXECUTION_NOT_AUTHORIZED

Active milestone:
DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout

Exact next task:
`DAILY-PROD-5B Phase 6` - Isolated PREPARE Job Transaction Adapter Design Contract

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-5A` and `DAILY-PROD-5B` Phases 1 through 5 are complete. Phase 5 accepted the isolated PREPARE orchestration contract for request intake, current-plan authority, durable create/replay, atomic ownership, second fingerprint validation, fake future transaction boundary, durable result ordering, timeout replay, and classify-only stale APPLYING reconciliation. Canonical/default runtime schema remains `12`; dormant proposed schema remains `13`.

Operator pain:
The durable request store and orchestration contract are complete, but the system still lacks a reviewed boundary between an APPLYING request and the existing Job/JobChapter transaction. Without that boundary, future integration could create duplicate Jobs or record APPLIED without durable transaction evidence.

Current baseline for the next task:

- Branch `main`
- Last verified commit: `306fd7d2d147ad0dc19e2c00a91cce94d9208ece`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema/latest schema: `12 / 12`
- Dormant proposed schema: `13`
- Dormant migration: `story_audio/migrations/dormant/0013_batch_prepare_requests.sql`
- Durable request store: `story_audio/batch_prepare_store.py`
- Orchestrator: `story_audio/batch_prepare_orchestrator.py`
- Phase 5 validation baseline: focused/affected suite `137` pass; repeated orchestrator suite `16` pass; full offline suite `1265` pass, `1` skipped; Doctor `critical_errors=0`.
- Canonical DB has no `batch_prepare_requests` table, SHA-256 `dba41f6eb3eaba5de4a4d9964f41ee93bb730ac8c2d6fd47df202479ad203b23`, size `4009984` bytes, mtime `2026-07-20T12:31:47.429225`, and `quick_check=ok`.
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Allowed scope:

- Inspect existing Job preparation lifecycle.
- Define adapter input/result contracts.
- Define one-request/one-Job invariant.
- Define Job/JobChapter atomic transaction evidence.
- Define request-to-Job linkage.
- Define conflict mapping.
- Define ambiguous-outcome handling.
- Define duplicate-Job prevention.
- Define historical replay evidence.
- Add pure design/model tests.
- Use fake adapters only.

Excluded scope:

- Real `prepare_job` or `create_job` call.
- Job/JobChapter write.
- Pipeline modification.
- API route.
- Canonical schema activation.
- UI.
- Worker wake.
- START_RENDER.
- Provider/Gemini/TTS.
- Chapter 369 production action.

Acceptance criteria:

1. Existing Job preparation lifecycle is documented from source/tests.
2. Adapter input binds request identity, scope, and plan fingerprint.
3. One request can produce at most one Job.
4. One Job contains all eligible JobChapter rows atomically.
5. Adapter success requires durable transaction evidence.
6. APPLIED cannot be recorded from an uncommitted result.
7. Existing prepared/active Job conflict maps deterministically.
8. Duplicate adapter invocation cannot be treated as safe without durable linkage.
9. Ambiguous outcomes require reconciliation/operator review.
10. Request-to-Job linkage fields are specified.
11. Historical replay fields are specified.
12. Adapter never wakes worker or starts render.
13. No real pipeline call or DB mutation is implemented.

Safety gate:

- `ISOLATED_JOB_TRANSACTION_ADAPTER_DESIGN_AUTHORIZED` applies only to pure design, fake dependencies, offline tests, and temporary/isolated databases when needed.
- `REAL_JOB_ADAPTER_IMPLEMENTATION_NOT_AUTHORIZED` remains in force.
- `CANONICAL_SCHEMA_13_ACTIVATION_NOT_AUTHORIZED` remains in force.
- `PREPARE_EXECUTION_NOT_AUTHORIZED` remains in force.
- `API_INTEGRATION_NOT_AUTHORIZED` remains in force.
- `START_RENDER` remains separate and unauthorized.

Exact next action:

1. Inspect existing Job/JobChapter preparation transaction.
2. Define adapter input and success evidence.
3. Define one-request/one-Job linkage.
4. Define duplicate and ambiguous-outcome behavior.
5. Define conflict and failure mapping.
6. Use only pure/fake adapter models.
7. Stop before pipeline integration or real Job writes.
