# Batch PREPARE Phase 9 Transaction Infrastructure

Status: `PHASE_9_IMPLEMENTED_ISOLATED_ONLY`

Authorization labels:

- `ISOLATED_ONLY`
- `DORMANT_SCHEMA_ONLY`
- `NO_RUNTIME_WIRING`
- `NO_CANONICAL_ACTIVATION`
- `NO_PRODUCTION_JOB_CREATION`
- `PREPARE_EXECUTION_NOT_AUTHORIZED`
- `API_INTEGRATION_NOT_AUTHORIZED`
- `START_RENDER_NOT_AUTHORIZED`

## Scope And Authorization

Phase 9 implements and tests the prerequisites for one caller-owned PREPARE transaction only on disposable databases. Nothing imports this infrastructure from the runtime pipeline, orchestrator, API, worker, or UI. The production database remains schema 12 and does not contain the dormant request, linkage, or execution-attempt tables.

Synthetic `Job` and `JobChapter` rows are test evidence only. The service does not call `prepare_job()`, `create_job()`, worker wake, START_RENDER, provider, Gemini, TTS, segmentation, artifact creation, or audio creation.

## Resolved Blockers

| Blocker | Exact previous evidence | Failure scenario | Phase 9 resolution | Acceptance evidence |
| --- | --- | --- | --- | --- |
| `BLOCKED_BY_TRANSACTION_ABSTRACTION` | Production `create_job()` owned its transaction; linkage store owned another | Job commits without linkage or linkage observes a different transaction | One-shot transaction manager plus connection-scoped Job/JobChapter and linkage writers | Caller-commit, caller-rollback, partial-write injection, and connection-state tests |
| `BLOCKED_BY_AUTHORITATIVE_INPUT_REVALIDATION` | Plan validation happened before the future write boundary | Text Revision, Casting Plan, approval, voice pin, or eligible set changes before insert | Transaction revalidator reloads request, owner, book/range, exact eligible set, active revision, latest approved plan, hash, narrator, and pins under `BEGIN IMMEDIATE` | Stale revision/plan/approval/voice/digest/order/scope tests |
| `BLOCKED_BY_OWNERSHIP_EVIDENCE` | `APPLYING` and `attempt_count` had no durable executor identity | A stale process can execute after another process takes over | Dormant execution-attempt row stores a token hash, monotonic generation, lease, transaction reference, immutable fingerprints, and terminal outcome | Wrong-token, stale-generation, expiry, renew, restart, and concurrent-acquire tests |
| `BLOCKED_BY_CONFLICT_RACE` | Production conflict lookup used a separate connection before Job transaction | Two overlapping requests both pass the lookup and create two prepared Jobs | Conflict lookup and all inserts execute after one database-wide `BEGIN IMMEDIATE` reservation | Same-request and overlapping-request concurrency tests prove one Job; non-overlap commits sequentially |

## Dormant Schema 15

Artifact: `story_audio/migrations/dormant/0015_batch_prepare_execution_attempts.sql`.

Table: `batch_prepare_execution_attempts`.

The table binds `(batch_prepare_request_id, request_identity)` to the schema-13 parent, and optionally binds a committed attempt to one schema-14 linkage. It stores generation, token hash, lease timestamps, transaction reference, plan fingerprint, chapter snapshot digest, state, and terminal evidence.

Allowed states are bounded:

- `OWNED`
- `COMMITTED`
- `ROLLBACK_CONFIRMED`
- `OUTCOME_AMBIGUOUS`
- `EXPIRED`

Constraints enforce positive generation, lowercase 64-character digests, lease ordering, unique request/generation, unique transaction reference, one live owner through a partial unique index, and state-specific terminal columns. A committed state requires linkage plus commit time. Rollback-confirmed requires rollback time and forbids linkage. Ambiguous requires a bounded reason code and forbids false commit evidence.

The migration is below `migrations/dormant/`, is not recursively discovered, and does not change `LATEST_SCHEMA_VERSION = 12`. Explicit isolated tests cover 14 -> 15, the complete 12 -> 13 -> 14 -> 15 chain, reopen, legacy preservation, constraints, indexes, foreign keys, and migration rollback without false schema 15.

## Owner Token Security

Acquisition uses `secrets.token_urlsafe(32)`. The raw token is returned to the owner and is never written to SQLite, logs, public evidence, exceptions, documentation, or handoff capsules. SQLite stores only lowercase SHA-256. Validation uses `hmac.compare_digest`.

An exact replay may present the token it already owns and recover the same generation while the lease is live. It does not allocate another generation. A terminal attempt cannot acquire another generation; historical recovery or a fresh request identity is required.

## Generation, Fencing, And Lease

Generation starts at one and increases only after a prior owner expires. The active owner is identified by request ID, request identity, generation, raw-token proof, plan fingerprint, chapter digest, transaction reference, `OWNED` state, and unexpired lease.

Renewal is accepted only from the current unexpired owner. Wrong token, wrong generation, stale generation, terminal generation, and expired owner fail closed. Expiry is durable and a replacement generation fences the old process after restart.

## Transaction-Scoped Request Verification

The revalidator accepts the caller's existing SQLite connection and performs no commit, rollback, migration, or autonomous read. It requires:

- request row present;
- exact request identity and numeric ID;
- `APPLYING` state;
- `PREPARE` target;
- exact book/range and plan fingerprint;
- exact owner token, generation, lease, and transaction reference;
- explicit no-render input.

## Authoritative Snapshot Validation

The same write transaction reloads:

- book and deterministic chapter range;
- exact current eligible chapter set;
- no active output and `audio_status = not_created`;
- no prepared or active overlapping Job;
- chapter ID, number, and book;
- active Text Revision and revision ownership;
- latest Casting Plan identity/revision;
- `approved` status and approval timestamp;
- plan SHA-256, content-path presence, narrator voice, and pinned casting/voice JSON;
- deterministic order and full chapter snapshot digest.

The validator does not silently select a newer revision or plan. The input digest includes all immutable per-chapter pins. Excluded chapters cannot enter the write set because the recomputed ready IDs must exactly equal the snapshot IDs.

## Transaction-Scoped Prepared Job Writer

`PreparedJobTransactionRepository` requires an active `IsolatedWriteTransaction`. It does not open, begin, commit, rollback, or close a connection. It inserts exactly one `prepared` Job and one pending JobChapter per validated chapter.

JobChapter rows pin Text Revision ID, Casting Plan ID, Casting Plan SHA-256, sequence, and voice snapshot JSON. The Job stores no scheduled/running status, no start or finish evidence, and a deterministic batch casting snapshot. The writer cannot create segments, attempts, artifacts, active audio, or worker actions. Returned IDs are explicitly provisional until commit and post-commit reload.

## Transaction-Scoped Linkage Writer

`BatchPrepareJobLinkStore.create_or_replay_in_connection()` is the narrow caller-owned seam. Existing autonomous `create_or_replay()` behavior remains compatible and delegates to the seam.

The seam requires an active connection, inserts on that connection, and never commits. Request uniqueness, identity uniqueness, Job uniqueness, exact evidence replay, request/Job conflict, and no-newest-fallback semantics remain unchanged.

## BEGIN IMMEDIATE Serialization

`BatchPrepareTransactionManager` guards the canonical path before opening a writable connection, configures a bounded busy timeout, and executes exactly one `BEGIN IMMEDIATE`. There is no hidden retry of the body and no nested transaction.

SQLite therefore serializes local writers database-wide. This is intentionally conservative. A second overlapping writer waits within the bound, reloads facts after the winner commits, and receives a deterministic conflict/eligibility rejection. Non-overlapping requests may both commit sequentially. Range-level parallel writes are not claimed.

## Exact Transaction Ordering

The isolated service executes:

1. guard isolated path;
2. open connection and `BEGIN IMMEDIATE`;
3. reload request;
4. validate owner token, fence, lease, and transaction reference;
5. revalidate authoritative inputs and exact eligible set;
6. inspect exact existing linkage;
7. inspect overlapping prepared/active Jobs;
8. insert one prepared Job;
9. insert all JobChapter rows;
10. insert request-to-Job linkage;
11. mark execution attempt `COMMITTED` on the same connection;
12. commit once;
13. close the transaction connection;
14. reload durable attempt/linkage/Job/JobChapter evidence on a new connection;
15. return evidence eligible for a future orchestrator `APPLIED` recording.

The request remains `APPLYING` in Phase 9. Updating it to `APPLIED` belongs to the not-yet-assembled Phase 10 adapter.

## Commit Evidence

A return value or allocated Job ID is not commit proof. Accepted evidence requires a committed execution attempt linked to the exact request linkage, exact request identity, plan fingerprint, chapter digest, transaction reference, prepared Job, exact ordered JobChapter IDs/pins, `worker_woken = 0`, and `render_started = 0` after a new connection reload.

## Rollback Behavior

Failures after request validation, conflict inspection, Job insert, any JobChapter insert, linkage insert, attempt update, or immediately before commit roll back the caller-owned transaction. The service verifies absence of both provisional Job and request linkage before it records `ROLLBACK_CONFIRMED` in a later transaction. A caller that never proves owner identity cannot terminalize the real owner's attempt.

Rollback-confirmed attempts are immutable and are not automatically rerun. A fresh request is required unless a future reviewed contract explicitly permits another policy.

## Ambiguous Commit Recovery

A commit exception never reruns the body. The service closes the uncertain connection and reloads durable evidence:

- exact committed evidence -> recover the same Job;
- no provable committed evidence -> mark `OUTCOME_AMBIGUOUS` when safe and require reconciliation;
- mismatched/partial evidence -> fail closed as corrupt committed state.

An exception raised after the real commit is treated as response loss and recovers the committed Job. Post-commit evidence/audit failure does not roll back and does not create a second Job.

## Process Restart Recovery

Raw-token proof held by the caller remains valid across process restart because hash, generation, lease, digest, and transaction reference are durable. Subprocess tests create the transaction in one process, recover it in another, verify the same Job/linkage, and reject a wrong token without printing the valid token.

## Canonical Path Protection

Every Phase 9 writable entry point resolves and normalizes the requested path and compares it to the canonical production DB, including `samefile` when both files exist. Exact, relative, normalized, case/slash-equivalent, and resolvable alias paths fail before opening a writable connection.

This guard complements, rather than replaces, the repository-wide `Database.initialize()` live-DB guard.

## Tests

Phase 9 adds isolated migration, ownership, revalidation, writer, service, concurrency, failure-injection, busy-timeout, and subprocess-restart coverage. Existing linkage, adapter-contract, transaction-design, orchestrator, prepared-job/API, and DB-guard suites remain part of the focused acceptance set.

All fixtures use `TemporaryDirectory`, synthetic text metadata, explicit dormant migrations, and `STORY_AUDIO_TESTING=1`. They do not copy chapter content or call a provider.

## No-Runtime-Wiring Boundary

The following remain unchanged and must show an empty diff:

- `story_audio/pipeline.py`
- `story_audio/api.py`
- `story_audio/db.py`
- `story_audio/batch_prepare_orchestrator.py`
- active migration discovery
- `ui/`

Phase 9 modules are dormant because no production module imports or instantiates the isolated service.

## Phase 10 Prerequisites

Phase 10 may be considered only after repeated focused tests, full offline tests, Doctor, diff inspection, canonical byte-level verification, and the Phase 9 implementation checkpoint all pass.

Its maximum boundary is isolated end-to-end adapter assembly: inject these modules into the existing orchestrator on schema-15 temporary databases, record durable request outcomes, and prove full replay/recovery. Runtime wiring, canonical activation, production PREPARE, API/UI, worker wake, provider work, and START_RENDER remain unauthorized.

## Open Risks

- SQLite writer serialization is database-wide. This is acceptable for the current local isolated proof but is not range-level concurrency.
- Casting content is represented by its immutable database SHA/path and caller-provided pinned JSON. Phase 10 must preserve the second validated current-plan snapshot and must not substitute current plan content after ownership.
- `APPLIED`, `REJECTED`, and `FAILED` orchestration persistence is deliberately outside this transaction and must be assembled and accepted in Phase 10.
- The service is not production hardened or reachable. Its canonical guard is a defense-in-depth boundary, not authorization to activate it.
