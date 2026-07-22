# DAILY-PROD Checkpoint State

Updated: 2026-07-22 20:33:00 +07:00

## Current Phase

`DAILY-PROD-5B Phase 6 Closeout` - Full Validation And Job Adapter Design Checkpoint.

## Starting Commit

- `5701598ce2d769980471f4573ebbccb9664d5cf7`
- `docs: close phase 4 prepare persistence acceptance`

## Phase 5 Checkpoint

- `306fd7d2d147ad0dc19e2c00a91cce94d9208ece`
- `feat: define isolated PREPARE orchestration contract`

## Phase 5 Verdict

- `DAILY-PROD-5B_PHASE_5_COMPLETE`
- Isolated PREPARE orchestration contract acceptance: PASS.
- Focused/affected validation: `137` tests PASS.
- Repeated orchestrator suite: `16` tests PASS.
- Full offline validation: `1265` tests PASS, `1` skipped.
- Doctor: PASS, `critical_errors=0`.

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

API integration:

- `NOT_AUTHORIZED`

Job transaction adapter design:

- `AUTHORIZED`

Job transaction adapter implementation:

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

`DAILY-PROD-5B Phase 6` - Isolated PREPARE Job Transaction Adapter Design Contract.

## Phase 6 Adapter Design Checkpoint

- Starting commit: `85337ffef95cd280dc6176ddeb79dceefec7ecbb`.
- Authorization: `ISOLATED_JOB_TRANSACTION_ADAPTER_DESIGN_AUTHORIZED`.
- Adapter implementation: `NOT_AUTHORIZED`.
- Canonical activation: `NOT_AUTHORIZED`.
- PREPARE execution: `NOT_AUTHORIZED`.
- API integration: `NOT_AUTHORIZED`.
- START_RENDER: `NOT_AUTHORIZED`.
- Module: `story_audio/batch_prepare_job_adapter_contract.py`.
- Design document: `docs/BATCH_PREPARE_JOB_ADAPTER_DESIGN.md`.
- Test suite: `tests/test_batch_prepare_job_adapter_contract.py`.

Design coverage:

- Existing prepared-job lifecycle evidence from `story_audio/pipeline.py`, `story_audio/db.py`, migrations, and prepared-job tests.
- APPLYING adapter input contract bound to request identity, client request ID, scope, plan fingerprint, target phase, second validated current-plan snapshot, and no-render instruction.
- Eligible chapter snapshot contract bound to chapter, active Text Revision, approved Casting Plan identity, eligibility evidence, and deterministic order.
- One durable request to zero-or-one prepared Job invariant.
- One Job to all eligible JobChapter rows atomically.
- Committed-success evidence stronger than a function return.
- Duplicate invocation classification that never treats a second Job as safe.
- Existing prepared/active/legacy/conflicting Job mapping.
- Failure taxonomy for pre-transaction conflicts, rollback, ambiguous outcomes, invalid commit evidence, linkage conflict, and APPLIED-result recovery.
- Process interruption matrix.
- Historical replay payload fields and forbidden payload fields.
- Read-only reconciliation evidence classifier.
- No-worker/no-render boundary.

Recommended future linkage:

- A dedicated request-to-Job linkage table written in the same Job/JobChapter transaction.
- Database uniqueness on request identity and job reference.
- `batch_prepare_requests.job_id` remains useful as a replay pointer but is not sufficient alone if written after the Job transaction commits.
- Legacy Jobs without linkage require conservative conflict or operator review handling.

Remaining:

- Full closeout validation and commit are separate.
- Real adapter implementation and PREPARE execution still require separate authorization.

## Phase 6 Closeout

- Verdict: `DAILY-PROD-5B_PHASE_6_COMPLETE`.
- Adapter contract remains design/model only.
- Lifecycle evidence was reviewed against `story_audio/pipeline.py`, `story_audio/db.py`, migrations, and prepared-job tests.
- Dedicated request-to-Job linkage table remains the recommended future design because it can enforce one request/one Job and can be inserted in the same Job/JobChapter transaction.
- Future implementation requires database uniqueness on request identity and job reference.
- `batch_prepare_requests.job_id` remains a replay pointer, not sufficient same-transaction commit evidence by itself.
- Committed-success evidence rejects uncommitted Job references, mismatched request identity, mismatched plan fingerprint, mismatched chapter snapshot digest, non-prepared status, count mismatch, missing/extra chapter evidence, duplicate JobChapter references, worker wake, and render start.
- Duplicate invocation never claims a second Job is safe.
- Process interruption matrix requires no rerun after commit and committed-result recovery when the request result is missing.
- Reconciliation classifier remains pure/read-only and returns only deterministic decisions.
- No API route, real adapter implementation, real Job/JobChapter creation, canonical schema activation, UI integration, provider call, TTS call, worker wake, or START_RENDER was added.

## Orchestration Checkpoint

- Module: `story_audio/batch_prepare_orchestrator.py`
- Design document: `docs/BATCH_PREPARE_ORCHESTRATION_DESIGN.md`
- Test suite: `tests/test_batch_prepare_orchestrator.py`
- Request validation uses the current pure PREPARE contract.
- Current plan is recomputed at intake and again before the future transaction boundary.
- Durable request is created or replayed before ownership.
- Ownership uses store `PLANNED -> APPLYING` compare-and-transition.
- Valid no-eligible requests persist deterministic `REJECTED` directly from `PLANNED`.
- Future transaction is injected/fake-only and records APPLIED with `job_id = null`.
- APPLIED is returned only after durable result persistence.
- Timeout replay is durable-record based.
- Stale APPLYING reconciliation is classification-only and non-mutating.
- Operator actions are deterministic.
- Authorization fields remain false: mutation, endpoint availability, real job execution, and render start.
- No API route, real Job/JobChapter creation, canonical schema activation, UI integration, provider call, TTS call, or render start was added.
- Phase 5 closeout review verified store/orchestrator transition consistency with the pure persistence contract.
- Fake dependency cannot reach the existing execution lifecycle; API, pipeline, schema, migrations, and UI diffs are empty.

## Validation

- Syntax: PASS for `story_audio/batch_prepare_orchestrator.py` and `tests/test_batch_prepare_orchestrator.py`.
- Focused orchestrator suite: `16` tests PASS.
- Affected contract/store/integration/prepared-job suite: `137` tests PASS.
- Isolated orchestration smoke: PASS through orchestrator tests for success, lost-response replay, stale-before-transaction, concurrent owner, ambiguous reconciliation, no real Job/JobChapter creation, and no production mutation.
- Repeated orchestrator suite: `16` tests PASS.
- Full offline suite: `1265` tests PASS, `1` skipped.
- Runtime check: PASS, canonical data root/db true and schema/latest `12 / 12`.
- Canonical read-only safety check: PASS; hash/size/mtime unchanged, `batch_prepare_requests` absent, Chapter 369 unchanged.
- Doctor: PASS, `critical_errors=0`; expected warning remains `speaker_assignment_drafts: drafts=15 invalid=9`.
- Post-Doctor canonical byte-level recheck: PASS; hash/size/mtime unchanged.

Remaining validation:

- Phase 6 adapter design contract remains pure/fake-only until a later explicit implementation authorization.

## Phase 6 Validation

- Syntax: PASS for `story_audio/batch_prepare_job_adapter_contract.py`.
- Focused adapter/orchestrator/prepared-job/store/persistence suite: `169` tests PASS.
- Repeated adapter contract suite: `72` tests PASS.
- Full offline suite: `1337` tests PASS, `1` skipped.
- Pure model smoke: PASS for valid committed success, uncommitted reference rejection, duplicate committed linkage replay, multiple matching Jobs operator review, and commit-before-request-result recovery.
- Runtime check: PASS, canonical data root/db true and schema/latest `12 / 12`.
- Canonical DB opened writable by Phase 6: no.
- Canonical DB read-only quick_check: `ok`.
- Canonical DB hash: `dba41f6eb3eaba5de4a4d9964f41ee93bb730ac8c2d6fd47df202479ad203b23`.
- Canonical DB size: `4009984` bytes.
- Canonical DB mtime ns: `1784525507429225500`.
- Canonical `batch_prepare_requests` table: absent.
- Counts unchanged: speaker drafts `15`, casting plans `23`, jobs `21`, job chapters `21`, segments `688`, artifacts `84`.
- Chapter 369 unchanged: active Text Revision `738`, Casting Plan `24` revision `1` draft/unapproved, jobs `0`, artifacts `0`, active audio none, audio status `not_created`.
- Doctor: PASS, `critical_errors=0`; expected warning remains `speaker_assignment_drafts: drafts=15 invalid=9`.
- Post-Doctor canonical byte-level recheck: PASS; hash/size/mtime unchanged.

## Next Exact Action

1. Reconcile DAILY-PROD-5B Phase 6 canonical documentation.
2. Assess isolated linkage/schema implementation authorization.
3. Keep pipeline integration, canonical activation, and real execution unauthorized.
4. Keep START_RENDER separate.
