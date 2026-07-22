# Next Task

Task classification:
`SYSTEM_ROADMAP / CANONICAL_CLONE_MIGRATION_REHEARSAL_AUTHORIZED / DISABLED_RUNTIME_WIRING_SKELETON_AUTHORIZED / CANONICAL_ACTIVATION_NOT_AUTHORIZED / PRODUCTION_PREPARE_NOT_AUTHORIZED / API_MUTATION_ROUTE_NOT_AUTHORIZED / START_RENDER_NOT_AUTHORIZED`

Active milestone:
`DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout`

Exact next task:
`DAILY-PROD-5B Phase 12 - Canonical Clone Migration Rehearsal And Disabled Runtime Wiring Skeleton`

## Operator Pain

The isolated adapter and runtime rollout design are complete, but schema activation
and rollback have not been rehearsed against a verified clone of the canonical
database, and runtime dependency wiring has not been proven to remain unreachable
and default-off inside the application process.

## Allowed Scope

- Make a verified read-only copy of canonical DB to an external temporary location.
- Verify clone provenance, hash, schema, and `quick_check`.
- Rehearse explicit schema 12 -> 13 -> 14 -> 15 on the clone only.
- Verify legacy data, protected Chapter 369 state, schema objects, and postflight.
- Rehearse clone rollback and prove original clone hash/schema are restored.
- Add a disabled runtime dependency wiring skeleton behind a hard-default-off flag.
- Prove disabled startup does not construct the mutation service.
- Keep read-only planning available and add model/startup tests and documentation.

## Excluded

- Canonical migration or canonical writable access.
- Enabled or registered PREPARE mutation endpoint.
- Production adapter invocation, Job, or JobChapter creation.
- UI mutation controls, worker wake, START_RENDER, provider, Gemini, or TTS.
- Beginning canary, limited/general rollout, or `DAILY-PROD-6`.

## Acceptance Criteria

1. Canonical source DB is never opened writable.
2. Clone source evidence matches the canonical baseline.
3. Clone migrates exactly 12 -> 13 -> 14 -> 15.
4. Clone legacy data and Chapter 369 remain unchanged.
5. Clone rollback restores the original hash and schema.
6. Runtime skeleton defaults off and is unreachable.
7. Disabled runtime does not construct a mutation service.
8. Read-only planning remains available.
9. No API mutation route is enabled.
10. No Job or JobChapter is created.
11. Canonical runtime remains schema 12.
12. Production PREPARE and START_RENDER remain unauthorized.
