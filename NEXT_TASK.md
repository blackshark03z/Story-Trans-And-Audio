# Next Task

Task classification:
SYSTEM_ROADMAP / MIGRATION_IMPLEMENTATION_AUTHORIZED / PREPARE_EXECUTION_NOT_AUTHORIZED

Active milestone:
DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout

Exact next task:
`DAILY-PROD-5B Phase 3` - Schema 13 Migration And Durable PREPARE Request Store

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-5A`, `DAILY-PROD-5B Phase 1`, and `DAILY-PROD-5B Phase 2` are complete. The PREPARE safety and persistence contracts are defined, but the system still lacks a durable request record capable of preventing duplicate mutation after client timeout or process interruption.

Current baseline for the next task:

- Branch `main`
- Last verified commit: `68f4f3d059f08004d6fcb4d4d06505ad802f3c11`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema: `12`
- Proposed future schema: `13`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Phase 2 validation baseline: pure persistence tests `50` pass; focused/affected tests `102` pass; full offline suite `1208` pass, `1` skipped; Doctor `critical_errors=0`.
- Canonical PREPARE batch-plan smoke for Book `1`, chapters `364-369`, returned included `0`, excluded `6`, authorization `MUTATION_NOT_AUTHORIZED`, execution endpoint unavailable, and unchanged sensitive counts.
- Chapter `369`: active Text Revision `738`, Casting Plan `24` revision `1` draft/unapproved, no Jobs, no JobChapters, no artifacts, no active audio, and audio status `not_created`.

Operator pain:
The PREPARE safety and persistence contracts are defined, but the system still lacks a durable request record capable of preventing duplicate mutation after client timeout or process interruption.

Allowed scope:

- Implement schema 13 migration.
- Add `batch_prepare_requests` persistence.
- Add unique request and canonical identity constraints.
- Add request state constraints.
- Add result schema/payload storage.
- Add applying reconciliation timestamps.
- Implement repository-level create-or-replay behavior.
- Implement payload-conflict detection.
- Implement atomic request state transitions.
- Implement historical result replay.
- Test only on temporary/isolated databases.
- Preserve schema 12 canonical production DB.

Excluded scope:

- Canonical DB migration.
- API route.
- PREPARE execution.
- `prepare_job`.
- Job/JobChapter creation.
- Start/resume render.
- UI.
- QA mutation.
- Provider/Gemini/TTS.
- Chapter `369` production action.

Acceptance criteria:

1. Migration upgrades a temporary schema-12 DB to schema 13.
2. Legacy data remains intact.
3. `batch_prepare_requests` table matches reviewed design.
4. Same request ID/same payload resolves same record.
5. Same request ID/different payload conflicts.
6. Duplicate `APPLYING` does not create a second record.
7. `APPLIED`/`REJECTED`/`FAILED` result can be replayed historically.
8. State transitions are atomic and allowlisted.
9. Applying reconciliation fields are queryable.
10. Result payload is bounded and versioned.
11. Migration is idempotent according to repository conventions.
12. Downgrade/partial migration failure behavior is tested or documented.
13. Canonical production DB remains schema 12.
14. No execution endpoint or Job mutation exists.

Safety gate:

- `SCHEMA_13_MIGRATION_IMPLEMENTATION_AUTHORIZED` applies only to repository migration code and isolated development/testing.
- `PREPARE_EXECUTION_NOT_AUTHORIZED` remains in force.
- `START_RENDER` remains separate and unauthorized.

Exact next action:

1. Implement schema 13 migration in isolated development.
2. Implement durable PREPARE request store.
3. Add repository-level persistence tests.
4. Keep canonical migration and PREPARE execution unauthorized.
