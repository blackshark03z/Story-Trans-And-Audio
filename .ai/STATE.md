# DAILY-PROD Checkpoint State

Updated: 2026-07-22 18:17:10 +07:00

## Current Phase

`DAILY-PROD-5B Phase 5` - Isolated PREPARE Orchestration And Reconciliation Contract.

## Phase 4 Checkpoint

- `f650f6936f89d400579acb882f05704799f6c3c8`
- `test: validate isolated PREPARE request persistence`

## Phase 4 Verdict

- `DAILY-PROD-5B_PHASE_4_COMPLETE`
- Isolated schema-13 persistence acceptance: PASS.
- Full offline validation: `1248` tests PASS, `1` skipped.
- Doctor: PASS, `critical_errors=0`.

## Authorization Boundary

Isolated PREPARE orchestration design:

- `AUTHORIZED`

Isolated schema-13 activation:

- `AUTHORIZED_ONLY_FOR_TEMPORARY_OR_ISOLATED_DATABASES_WHEN_NEEDED`

Canonical schema activation:

- `NOT_AUTHORIZED`

PREPARE execution:

- `NOT_AUTHORIZED`

START_RENDER:

- `NOT_AUTHORIZED`

## Isolated Fixture And Migration

- Fixture type: synthetic production-like schema-12 database in a temporary directory outside the repository data root.
- Explicit migration: dormant `story_audio/migrations/dormant/0013_batch_prepare_requests.sql` applied only through explicit test runner composition.
- Starting schema: `12`
- Ending schema: `13`
- Legacy rows preserved: books, chapters, text revisions, casting plans, jobs, job chapters, and artifacts.
- Required table/columns/indexes verified for `batch_prepare_requests`.
- Connection restart verified with a fresh `Database`/store instance.
- Process restart verified through `tests/batch_prepare_isolated_worker.py`.
- Temporary resources are cleaned by `tempfile.TemporaryDirectory`.

## Persistence Acceptance

- Request restart persistence: PASS.
- Same-request replay after restart/process restart: PASS.
- Payload conflict after restart: PASS for scope, fingerprint, and unsupported phase reuse.
- APPLIED historical replay after restart: PASS.
- REJECTED historical replay after restart: PASS.
- FAILED historical replay after restart: PASS; same request remains replay-only and fresh retry requires a fresh `client_request_id`.
- Historical replay remains independent from changed current fixture facts.
- Concurrent same request creates exactly one durable row.
- Concurrent same ID/different payload persists one winner and returns `REQUEST_ID_CONFLICT` for the other caller.
- PLANNED -> APPLYING race has exactly one database winner.
- APPLYING terminal APPLIED/FAILED race has exactly one winner, and loser cannot overwrite terminal result.
- Terminal historical replay matches the committed final state.
- Stale APPLYING detection is deterministic, read-only, restart-stable, and does not mutate attempts/timestamps/state.

## Failure Recovery

- Injected migration failure rolls back and leaves schema version `12`.
- Failed migration leaves no `batch_prepare_requests` table or partial schema 13 evidence.
- Legacy fixture data remains intact after failed migration.
- Create failure before commit leaves no request row and a later retry can create normally.
- Transition failure leaves prior state unchanged.
- APPLIED result failure leaves no false success, no result payload, and no terminal timestamp.
- Invalid stored JSON fails closed through `BatchPrepareStoreDataError` and is not silently rewritten.

## Canonical Safety

- Existing runtime: `http://127.0.0.1:8772`
- Runtime identity: canonical data root and canonical DB are true.
- Runtime schema/latest schema: `12 / 12`
- Canonical DB opened writable by Phase 4: no.
- Canonical DB read-only quick_check: `ok`
- Canonical DB hash: `dba41f6eb3eaba5de4a4d9964f41ee93bb730ac8c2d6fd47df202479ad203b23`
- Canonical DB size: `4009984` bytes
- Canonical DB mtime: `2026-07-20T12:31:47.429225`
- Canonical `batch_prepare_requests` table: absent.
- Counts unchanged: speaker drafts `15`, casting plans `23`, jobs `21`, job chapters `21`, segments `688`, artifacts `84`.
- Chapter 369 unchanged: active Text Revision `738`, Casting Plan `24` revision `1` draft/unapproved, jobs `0`, artifacts `0`, active audio none, audio status `not_created`.

## Validation

- Syntax: PASS for `tests/batch_prepare_isolated_worker.py` and `tests/test_batch_prepare_isolated_integration.py`.
- Isolated integration suite: `9` tests PASS, repeated twice during closeout with the same count.
- Affected persistence/migration/prepared-job/DB suite: `142` tests PASS.
- Full offline suite: `1248` tests PASS, `1` skipped.
- Runtime check: PASS, canonical data root/db true and schema/latest `12 / 12`.
- Canonical byte-level recheck: PASS before and after Doctor, hash/size/mtime unchanged.
- Doctor: PASS, `critical_errors=0`; expected warning remains `speaker_assignment_drafts: drafts=15 invalid=9`.
- Doctor did not write canonical DB; post-Doctor hash/size/mtime remained unchanged.

## Files Changed

- `tests/batch_prepare_isolated_worker.py`
- `tests/test_batch_prepare_isolated_integration.py`
- `.ai/STATE.md`

No runtime source bug fixes were needed.

## Current Task

`DAILY-PROD-5B Phase 5` - Isolated PREPARE Orchestration And Reconciliation Contract.

## Next Exact Action

1. Define pure PREPARE orchestration flow.
2. Define atomic ownership acquisition.
3. Define fingerprint revalidation before the future mutation dependency.
4. Define durable result-recording order.
5. Define timeout replay and stale APPLYING reconciliation.
6. Use only fake or injected future Job dependencies.
7. Stop before API integration, canonical schema activation, real Job creation, PREPARE execution, or START_RENDER.
