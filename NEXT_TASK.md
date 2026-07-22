# Next Task

Task classification:
SYSTEM_ROADMAP / DORMANT_LINKAGE_PERSISTENCE_IMPLEMENTATION_AUTHORIZED / PIPELINE_INTEGRATION_NOT_AUTHORIZED / CANONICAL_ACTIVATION_NOT_AUTHORIZED / PREPARE_EXECUTION_NOT_AUTHORIZED

Active milestone:
DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout

Exact next task:
`DAILY-PROD-5B Phase 7` - Dormant Request-to-Job Linkage Persistence And Repository Contract

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-5A` and `DAILY-PROD-5B` Phases 1 through 6 are complete. Phase 6 accepted the PREPARE Job transaction adapter design contract: verified prepared-job lifecycle evidence, APPLYING adapter input, deterministic chapter snapshots, one-request/one-Job invariant, one Job/N JobChapter atomicity, committed-success evidence, duplicate invocation handling, interruption semantics, historical replay payload, and pure reconciliation evidence. Canonical/default runtime schema remains `12`; dormant request persistence schema remains `13`; proposed linkage schema `14` is not implemented.

Operator pain:
The Job adapter design requires database-enforced one-request/one-Job linkage, but the repository does not yet have a durable isolated linkage record. Without that record, duplicate adapter invocation and commit-before-request-result recovery cannot be enforced safely.

Current baseline for the next task:

- Branch `main`
- Last verified commit: `c1b3a40321aa783372751933fbec624b0a42ebb4`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema/latest schema: `12 / 12`
- Dormant request persistence schema: `13`
- Proposed dormant linkage schema: `14`
- Dormant request migration: `story_audio/migrations/dormant/0013_batch_prepare_requests.sql`
- Durable request store: `story_audio/batch_prepare_store.py`
- Job adapter contract: `story_audio/batch_prepare_job_adapter_contract.py`
- Phase 6 validation baseline: focused affected suite `169` pass; repeated adapter suite `72` pass; full offline suite `1337` pass, `1` skipped; Doctor `critical_errors=0`.
- Canonical DB has no `batch_prepare_requests` table, SHA-256 `dba41f6eb3eaba5de4a4d9964f41ee93bb730ac8c2d6fd47df202479ad203b23`, size `4009984` bytes, mtime `2026-07-20T12:31:47.429225`, and `quick_check=ok`.
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Allowed scope:

- inspect dormant migration conventions;
- create a dormant linkage migration after schema 13;
- create a pure linkage repository;
- enforce unique request and Job linkage;
- persist transaction evidence metadata;
- support create/replay/conflict lookup;
- test isolated schema upgrades;
- test concurrency and rollback;
- use temporary databases only;
- verify canonical DB remains unchanged.

Excluded scope:

- active migration registration;
- default/latest schema bump;
- canonical migration;
- pipeline modification;
- `prepare_job` or `create_job` invocation;
- real Job creation;
- orchestration integration;
- API route;
- UI;
- worker wake;
- START_RENDER;
- provider/Gemini/TTS;
- Chapter 369 production action.

Acceptance criteria:

1. Dormant migration upgrades isolated schema 13 to proposed schema 14.
2. Existing schema-13 request records are preserved.
3. Dedicated linkage table exists in the isolated upgraded schema.
4. One request maps to at most one Job.
5. One Job maps to at most one request.
6. Same request/same Job replays.
7. Same request/different Job conflicts.
8. Same Job/different request conflicts.
9. Transaction evidence fields are validated.
10. Uncommitted evidence cannot be stored as successful linkage.
11. Worker-woken or render-started evidence is rejected.
12. Lookup by request and Job is deterministic.
13. Concurrent inserts have one winner.
14. Failed migration rolls back and does not mark the next schema.
15. Store does not auto-migrate.
16. Store does not call pipeline or create Job rows.
17. Default/latest runtime schema remains 12.
18. Canonical DB remains byte-for-byte unchanged.

Safety gate:

- `ISOLATED_REQUEST_JOB_LINKAGE_PERSISTENCE_IMPLEMENTATION_AUTHORIZED` applies only to dormant schema artifacts, pure repository code, isolated/temporary database tests, migration rollback validation, and concurrency validation.
- `LINKAGE_PIPELINE_INTEGRATION_NOT_AUTHORIZED` remains in force.
- `REAL_JOB_ADAPTER_IMPLEMENTATION_NOT_AUTHORIZED` remains in force.
- `CANONICAL_SCHEMA_ACTIVATION_NOT_AUTHORIZED` remains in force.
- `PREPARE_EXECUTION_NOT_AUTHORIZED` remains in force.
- `API_INTEGRATION_NOT_AUTHORIZED` remains in force.
- `START_RENDER_NOT_AUTHORIZED` remains in force.

Exact next action:

1. Inspect dormant migration activation boundary.
2. Define isolated schema-13 to schema-14 linkage migration.
3. Enforce unique request and Job linkage.
4. Implement pure linkage repository create/replay/conflict behavior.
5. Validate concurrency and rollback on temporary databases.
6. Prove canonical schema and DB remain unchanged.
7. Stop before pipeline or orchestration integration.
