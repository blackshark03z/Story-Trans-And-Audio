# Next Task

Task classification:
SYSTEM_ROADMAP / ISOLATED_SCHEMA_13_TESTING_AUTHORIZED / CANONICAL_ACTIVATION_NOT_AUTHORIZED / PREPARE_EXECUTION_NOT_AUTHORIZED

Active milestone:
DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout

Exact next task:
`DAILY-PROD-5B Phase 4` - Isolated Schema 13 Activation And Request Store Integration Validation

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-5A`, `DAILY-PROD-5B Phase 1`, `DAILY-PROD-5B Phase 2`, and `DAILY-PROD-5B Phase 3` are complete. Phase 3 added a dormant schema-13 migration artifact and durable PREPARE request store in repository code, while canonical/default runtime schema remains `12`.

Operator pain:
The dormant migration and request store pass unit and repository tests, but the complete persistence lifecycle has not yet been validated across explicit migration, process restart, concurrent connections, and failure recovery in a production-like isolated database.

Current baseline for the next task:

- Branch `main`
- Last verified commit: `e4684905c6e7b3efd23cfef89a7da9dadf0f75e1`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema/latest schema: `12 / 12`
- Dormant proposed schema: `13`
- Dormant migration: `story_audio/migrations/dormant/0013_batch_prepare_requests.sql`
- Durable request store: `story_audio/batch_prepare_store.py`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Phase 3 validation baseline: focused/affected tests `133` pass; full offline suite `1239` pass, `1` skipped; Doctor `critical_errors=0`.
- Canonical DB has no `batch_prepare_requests` table, SHA-256 `dba41f6eb3eaba5de4a4d9964f41ee93bb730ac8c2d6fd47df202479ad203b23`, size `4009984` bytes, mtime `2026-07-20T12:31:47.429225`, and `quick_check=ok`.
- Chapter `369`: active Text Revision `738`, Casting Plan `24` revision `1` draft/unapproved, no Jobs, no JobChapters, no artifacts, no active audio, and audio status `not_created`.

Allowed scope:

- Temporary schema-12 production-like fixtures.
- Explicit dormant migration activation.
- Process/connection restart.
- Create-or-replay persistence.
- Historical replay after restart.
- Concurrent request creation.
- State transition races.
- Stale APPLYING simulation.
- Failure injection.
- Isolated acceptance harness and tests.
- Canonical byte-level safety verification.

Excluded scope:

- Top-level migration registration.
- Default/latest schema bump.
- Canonical migration.
- API route.
- `prepare_job`.
- Job/JobChapter execution.
- Render start.
- UI.
- Provider/Gemini/TTS.
- Chapter `369` production mutation.

Acceptance criteria:

1. Temporary schema-12 fixture upgrades explicitly to schema 13.
2. Legacy rows and counts survive upgrade.
3. Reopened DB remains schema 13.
4. Request records survive process/connection restart.
5. Same request replays after restart.
6. Different payload remains a conflict after restart.
7. APPLIED result replays historically after restart.
8. REJECTED result replays historically after restart.
9. FAILED result replays historically after restart.
10. Concurrent same request creates one durable row.
11. Concurrent different payload same ID conflicts.
12. State-transition races have one winner.
13. Stale APPLYING records are detected without mutation.
14. Injected failures do not leave false APPLIED state.
15. Failed migration does not leave schema marked 13.
16. Default/latest runtime schema remains 12.
17. Canonical DB remains byte-for-byte unchanged.
18. No PREPARE execution or Job creation occurs.

Safety gate:

- `ISOLATED_SCHEMA_13_INTEGRATION_VALIDATION_AUTHORIZED` applies only to temporary or isolated databases.
- `CANONICAL_SCHEMA_13_ACTIVATION_NOT_AUTHORIZED` remains in force.
- `PREPARE_EXECUTION_NOT_AUTHORIZED` remains in force.
- `START_RENDER` remains separate and unauthorized.

Exact next action:

1. Build a production-like temporary schema-12 fixture.
2. Explicitly activate dormant schema 13 on that temporary database.
3. Validate restart persistence, historical replay, concurrency, stale APPLYING, and failure recovery.
4. Prove canonical DB remains byte-for-byte unchanged.
5. Stop before canonical activation, API execution, `prepare_job`, UI, or START_RENDER.
