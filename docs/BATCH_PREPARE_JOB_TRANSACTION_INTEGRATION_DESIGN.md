# Batch PREPARE Job Transaction Integration Design

Status: `DESIGN_ONLY`

Required markers:

- `DESIGN_ONLY`
- `NO_PIPELINE_MODIFICATION`
- `NO_REAL_ADAPTER_IMPLEMENTATION`
- `NO_JOB_OR_JOB_CHAPTER_WRITE`
- `NO_LINKAGE_RUNTIME_INTEGRATION`
- `NO_API_ROUTE`
- `NO_CANONICAL_SCHEMA_ACTIVATION`
- `PREPARE_EXECUTION_NOT_AUTHORIZED`
- `START_RENDER_NOT_AUTHORIZED`

Authorization fields:

- `integration_implementation_authorized = false`
- `pipeline_modification_authorized = false`
- `real_job_execution = false`
- `mutation_authorized = false`
- `execution_endpoint_available = false`
- `prepare_starts_render = false`

## 1. Status And Authorization

Phase 8 defines the same-transaction boundary a future implementation must satisfy before batch PREPARE can create real prepared Jobs. It adds only pure models, protocol-shaped dependency interfaces, validators, recovery classifiers, and offline tests in:

- `story_audio/batch_prepare_job_transaction_integration_contract.py`
- `tests/test_batch_prepare_job_transaction_integration_contract.py`

This phase does not implement a runtime adapter and does not connect orchestration, pipeline, API, UI, schema activation, or render start.

## 2. Existing Transaction Evidence

| Question | Verified behavior | Source/test evidence | Integration implication |
| --- | --- | --- | --- |
| Who opens `db.transaction()` today? | Existing helpers own their own transactions. `Database.transaction()` opens a fresh connection, runs `BEGIN IMMEDIATE`, commits on normal exit, rolls back on exception, and closes. | `story_audio/db.py`; `story_audio/pipeline.py`; `story_audio/batch_prepare_store.py`; `story_audio/batch_prepare_job_link_store.py` | A future integration service must own the single transaction, and current helpers require refactor or transaction-scoped variants. |
| Does the Job creation helper accept a caller transaction? | No. It accepts `Database`, reads facts before the write transaction, performs Job and JobChapter inserts in its own `with db.transaction()`, then writes audit after commit. | `story_audio/pipeline.py` | Existing `create_job` / `prepare` helper cannot safely participate in same-transaction linkage as-is. |
| Is Job ID available before commit? | Yes, `lastrowid` is available inside the transaction, but the public helper returns only after commit and post-commit audit. | `story_audio/pipeline.py` | Pre-commit Job ID must not be treated as success evidence. |
| Do JobChapter inserts use the same connection? | Yes, current Job and all JobChapter inserts share the same internal transaction connection. | `story_audio/pipeline.py`; `tests/test_prepared_jobs.py` | The existing atomic write pattern is useful, but must be extracted behind caller-owned transaction interfaces. |
| When does conflict check run? | Conflict lookup runs before the Job insert transaction through `db.fetch_one`. | `story_audio/pipeline.py` | There is a check-then-insert race unless a future integration serializes scope or adds DB-enforced overlap protection. |
| Where are casting/text snapshots pinned? | Casting path validates approved plan and pins text revision, Casting Plan, plan hash, and voice snapshot into JobChapter rows. | `story_audio/pipeline.py`; `tests/test_prepared_jobs.py` | Future Job writer must preserve the same immutable pin semantics. |
| Does linkage store accept caller transaction? | No. The Phase 7 linkage store opens its own transaction in `create_or_replay`. | `story_audio/batch_prepare_job_link_store.py` | Runtime integration needs a transaction-scoped link writer or store refactor. |
| Does request store accept caller transaction? | No. It opens its own transactions for create, transition, and terminal result writes. | `story_audio/batch_prepare_store.py` | Runtime integration needs transaction-scoped request reload/verification, not terminal APPLIED inside Job transaction. |
| Are foreign keys visible in one transaction? | SQLite foreign keys are enabled on connections; rows inserted earlier in the same connection are visible to later statements. | `story_audio/db.py`; SQLite behavior; Phase 7 tests | Same-transaction Job, JobChapter, and linkage insert is viable if all writers share one connection. |
| Rollback semantics? | `Database.transaction()` rolls back on exception and closes connection. | `story_audio/db.py` | Failure before commit should leave no Job, JobChapter, or linkage if the future adapter uses one transaction. |
| SQLite lock mode? | Write transactions use `BEGIN IMMEDIATE` and `busy_timeout=30000`. | `story_audio/db.py` | A future integration should use equivalent write serialization, but this alone does not prove range-overlap uniqueness. |
| Commit evidence source? | Phase 7 linkage can reload durable linkage evidence; prepared Job and JobChapter rows can be verified after commit. | `story_audio/batch_prepare_job_link_store.py`; dormant schema 14 | Success requires post-commit reload and validation, not just no exception or returned Job ID. |

## 3. Goals

- Define one future same-transaction owner for request revalidation, conflict inspection, prepared Job creation, JobChapter creation, linkage insert, commit, and evidence reload.
- Require `APPLYING` request ownership to be revalidated inside the transaction.
- Require one prepared Job and exactly one JobChapter per eligible chapter.
- Require request-to-Job linkage to be inserted before commit in the same transaction.
- Define deterministic duplicate, recovery, failure, interruption, and orchestrator handoff decisions.
- Document implementation blockers honestly.

## 4. Non-Goals

- No production adapter implementation.
- No pipeline refactor.
- No API route.
- No canonical schema activation.
- No real Job or JobChapter creation.
- No request terminal APPLIED write inside the Job transaction.
- No worker wake.
- No START_RENDER.
- No segment, artifact, audio, provider, Gemini, or TTS work.

## 5. Current Abstraction Gaps

Current support is close but not implementation-ready:

- Job creation owns its transaction and cannot currently share it.
- Conflict detection runs before the transaction that inserts the Job.
- Request store operations own their own transactions.
- Linkage store operations own their own transactions.
- Chapter eligibility, active Text Revision, and approved Casting Plan facts are read before the Job transaction, leaving an authoritative-input TOCTOU window.
- Request ownership is represented by state and `attempt_count`, but there is no durable execution-owner token, fencing generation, lease, or execution-attempt row.
- Existing DB constraints prevent duplicate request linkage and duplicate Job linkage, but not two different requests preparing overlapping chapter ranges.
- Current audit persistence runs after the Job transaction; an audit failure can raise after the Job is already durable and must not be reported as rollback.

## 6. Transaction Owner

Preferred future design:

```text
FutureBatchPrepareJobIntegrationService
-> begin one isolated write transaction
-> call transaction-scoped repositories
-> commit
-> reload durable evidence
-> return adapter result to orchestrator
```

The integration service owns begin, commit, and rollback. Repositories must not commit, rollback, retry the whole body, open autonomous write transactions, or reuse the transaction object after commit or rollback.

## 7. Dependency Interfaces

Phase 8 models these future dependency interfaces:

- `TransactionManager`: begin isolated write transaction, commit, rollback; no hidden retry of transaction body.
- `RequestExecutionRepository`: reload request by ID/identity, verify `APPLYING`, `PREPARE`, fingerprint, owner token, fencing generation, active lease, and ownership attempt in caller-owned transaction; no state transition.
- `AuthoritativeInputRepository`: reload chapter eligibility, active Text Revision, approved Casting Plan, and immutable pin facts in the same caller-owned transaction.
- `JobConflictInspector`: inspect prepared/active overlap in the same transaction; no newest fallback.
- `PreparedJobWriter`: insert one prepared Job and all JobChapter rows in caller-owned transaction; no commit, no wake, no render.
- `RequestJobLinkWriter`: insert exact linkage in caller-owned transaction; rely on DB uniqueness as final guard.
- `CommitEvidenceReader`: after commit or during recovery, reload linkage, Job, JobChapter set, digest, fingerprint, and no-render evidence.

## 8. Required Operation Ordering

Future transaction ordering:

1. Orchestrator has already acquired `APPLYING` ownership.
2. Second current-plan validation has passed.
3. Begin one write transaction.
4. Reload request row in transaction.
5. Verify request ID, request identity, state, phase, fingerprint, owner token, fencing generation, active lease, and ownership attempt.
6. Reload and verify chapter eligibility, active Text Revisions, approved Casting Plans, and immutable pins.
7. Check existing exact linkage.
8. If exact committed linkage exists, do not insert a Job; return recovery/replay evidence.
9. Check conflicting linkage.
10. Check prepared/active overlapping Jobs.
11. Insert one prepared Job.
12. Insert all expected JobChapter rows.
13. Insert request-to-Job linkage with one shared transaction reference.
14. Validate expected counts, pins, bindings, and transaction reference.
15. Commit transaction.
16. Reload committed evidence from durable state and match the same transaction reference.
17. Return validated evidence to orchestrator.
18. Orchestrator separately records terminal `APPLIED`.

Forbidden orderings:

- Job commit before linkage.
- Linkage commit before all JobChapter rows.
- APPLIED request persistence inside the Job transaction under the current contract.
- Durable success based on pre-commit Job ID.

## 9. Request Ownership Revalidation

The transaction must fail closed if the request:

- does not exist;
- has identity mismatch;
- is not `PREPARE`;
- is not `APPLYING`;
- has fingerprint mismatch;
- has ownership attempt mismatch;
- has missing or mismatched owner token;
- has stale fencing generation;
- has expired ownership lease;
- has changed eligibility, active Text Revision, or approved Casting Plan facts;
- is already linked to conflicting Job evidence.

Current request schema does not contain durable ownership beyond `state` and `attempt_count`. `attempt_count` remains audit metadata, not an execution token. A future dormant migration must add an unguessable owner token, monotonic fencing generation, and lease (or an equivalent execution-attempt record); transaction revalidation and terminal writes must guard on token plus generation. Process-local ownership is not enough, and a reclaimed request must fence out the previous owner.

## 10. Job Conflict Race Analysis

Current conflict behavior is not sufficient as a final concurrency guard:

- `_find_conflicting_job` queries prepared/active overlaps before the existing Job insert transaction.
- Two concurrent transactions for different request identities could both observe no conflict before either inserts.
- Dormant linkage uniqueness prevents one request from creating multiple Jobs and one Job from linking to multiple requests, but it does not prevent different requests from creating overlapping Jobs for the same chapter range.
- `BEGIN IMMEDIATE` serializes SQLite writers once a transaction begins, but current conflict check occurs before the write transaction.

Future mitigation must include one of:

- move conflict check into the same `BEGIN IMMEDIATE` transaction immediately before insert and rely on serialized writers for the local SQLite deployment;
- add a DB-enforced per-chapter prepared binding/unique active guard;
- introduce a durable serialized lock per book/chapter range.

Until that mitigation is implemented and tested, real adapter implementation is blocked by conflict-race risk.

## 11. Job And JobChapter Writes

Future writer contract:

- exactly one Job insert;
- Job status exactly `prepared`;
- correct book and requested range;
- correct voice/config/casting/text snapshot identities;
- exactly one JobChapter for each eligible snapshot;
- zero JobChapter rows for excluded chapters;
- deterministic chapter order;
- pinned active approved Text Revision;
- pinned approved Casting Plan evidence when applicable;
- each JobChapter status exactly `pending`;
- positive chapter identity, Text Revision pin, and Casting Plan pin for every included chapter;
- no duplicate chapter binding;
- no partial success.

No Segment, Artifact, audio, worker wake, or render start is allowed during PREPARE.

## 12. Same-Transaction Linkage Insert

The linkage insert must bind:

- request row ID;
- request identity;
- Job ID;
- plan fingerprint;
- chapter snapshot digest;
- expected chapter count;
- actual chapter count;
- prepared status;
- transaction evidence version;
- timestamp or transaction reference terminology;
- one non-empty transaction reference shared by Job write evidence, linkage evidence, and post-commit reload;
- `worker_woken=false`;
- `render_started=false`.

Schema 14 currently uses `transaction_committed_at`. The design limitation is explicit: the timestamp value is recorded in a row that only becomes visible after commit, but the timestamp alone is not independent proof of commit. Future evidence must rely on durable post-commit visibility and verification of linkage, Job, and JobChapter rows.

Preferred terminology for future refactor is either:

- rename future public evidence semantics to `transaction_recorded_at`, or
- keep `transaction_committed_at` with documentation that commit proof is durable visibility after commit, not the timestamp alone.

## 13. Commit Evidence Contract

Committed success is valid only after commit and reload confirms:

- linkage row visible;
- request identity matches;
- Job row visible;
- Job status `prepared`;
- JobChapter count matches expected count;
- chapter snapshot digest matches;
- plan fingerprint matches;
- worker not woken;
- render not started;
- evidence version supported;
- no conflicting linkage.
- the same transaction reference is present on Job/linkage evidence and the post-commit reload;
- every JobChapter identity, status, Text Revision pin, and Casting Plan pin matches the revalidated authoritative snapshot.

Returned Job ID before commit and a lack of thrown exception are not enough.

## 14. Duplicate Invocation

Duplicate and recovery rules:

- Exact committed linkage exists: validate durable state and return recovered committed evidence; do not insert Job.
- Same request with different Job/evidence: deterministic conflict.
- Same Job linked to different request: deterministic conflict.
- No linkage and confirmed rollback: safe no-commit result; later retry requires orchestration policy.
- No linkage and unknown outcome: ambiguous; do not rerun transaction automatically.
- Multiple matching Jobs without linkage: operator review.
- Never choose newest Job.

## 15. Failure And Interruption Matrix

| Point | Transaction state | Durable state | Safe result | Rerun allowed |
| --- | --- | --- | --- | --- |
| Before begin | no transaction | no Job/linkage | `ROLLBACK_CONFIRMED` | yes, after orchestration policy |
| After request revalidation | open transaction | rollback not yet proven | `ROLLBACK_REQUIRED` | no, until rollback/absence observed |
| After Job insert | uncommitted | rollback not yet proven | `ROLLBACK_REQUIRED` | no, until rollback/absence observed |
| After partial JobChapter inserts | uncommitted | rollback not yet proven | `ROLLBACK_REQUIRED` | no, until rollback/absence observed |
| After all JobChapter inserts | uncommitted | rollback not yet proven | `ROLLBACK_REQUIRED` | no, until rollback/absence observed |
| After linkage insert | uncommitted | rollback not yet proven | `ROLLBACK_REQUIRED` | no, until rollback/absence observed |
| During commit | uncertain | unknown until evidence reload | `OUTCOME_AMBIGUOUS` | no |
| Commit response lost | uncertain until reload | linkage and prepared Job must be verified | `OUTCOME_AMBIGUOUS`, then `REPLAYED_COMMITTED` only with valid evidence | no |
| Commit evidence reload failed | uncertain | operator evidence required | `OUTCOME_AMBIGUOUS` | no |
| APPLIED persistence failed | commit must be independently verified | linkage/Job visible, request may remain `APPLYING` | `COMMITTED` only with valid evidence | no |

Key conclusions:

- Failures before commit are expected to roll back Job, JobChapter, and linkage together, but `ROLLBACK_CONFIRMED` requires observed rollback and durable absence.
- Uncertain commit outcome must not rerun immediately.
- Committed linkage recovery must happen before retry.
- Response loss after commit replays committed evidence.
- APPLIED persistence failure does not rerun the Job transaction.

## 16. Ambiguous Commit Recovery

Recovery query order:

1. Lookup linkage by request identity.
2. If none, decide whether absence is reliable; otherwise classify ambiguous.
3. If one linkage, verify Job, JobChapter set, digest, fingerprint, prepared status, and no-render flags.
4. If corrupt linkage/Job state, require operator review.
5. If multiple matching Jobs without linkage, require operator review.
6. Never select newest Job.
7. Never create a second Job during recovery.

Recovery decisions:

- `RECOVER_COMMITTED_TRANSACTION`
- `CONFIRMED_ROLLBACK_NO_COMMIT`
- `TRANSACTION_OUTCOME_AMBIGUOUS`
- `REQUEST_JOB_CONFLICT`
- `CORRUPT_COMMITTED_STATE`
- `OPERATOR_REVIEW_REQUIRED`

## 17. Orchestrator Handoff

Adapter results map to orchestrator permissions:

- `COMMITTED`: output of the commit-evidence validator, not a caller-supplied status string; orchestrator may persist `APPLIED`.
- `REPLAYED_COMMITTED`: output of deterministic durable-linkage recovery, not a caller-supplied status string; orchestrator may persist/replay `APPLIED`.
- `DETERMINISTIC_CONFLICT`: no new Job; orchestrator records rejected/failed by existing contract.
- `ROLLBACK_CONFIRMED`: no durable Job; orchestrator may record safe failure according to reviewed workflow.
- `OUTCOME_AMBIGUOUS`: orchestrator must not persist `APPLIED`, must not rerun, and must route to operator review.
- `CORRUPT_STATE`: fail closed and require operator review.

No adapter result may start render.

## 18. Response Terminology

Forbidden model-only claims:

- `job_created = true`
- `execution_completed = true`
- `production_committed = true`

Preferred fields:

- `transaction_decision`
- `future_job_reference`
- `durable_linkage_verified`
- `committed_evidence_valid`
- `eligible_for_applied_record`
- `requires_operator_review`

All authorization fields remain false.

## 19. Implementation Prerequisites

| Gate | Current support | Required change | Blocks implementation |
| --- | --- | --- | --- |
| Caller-owned DB transaction | `Database` supports `BEGIN IMMEDIATE`, but current helpers own transactions | Introduce integration-owned transaction boundary | yes |
| Transaction-scoped Job writer | Current job creation opens its own transaction | Extract writer accepting caller transaction | yes |
| Transaction-scoped linkage writer | Current linkage store opens its own transaction | Extract writer accepting caller transaction | yes |
| Request reload in transaction | Current request store opens its own transaction | Add read/verify using caller transaction | yes |
| Authoritative input revalidation | Eligibility, active revisions, and approved plans are read before the Job transaction | Reload and verify all immutable pins inside caller transaction | yes |
| Durable ownership evidence | State and `attempt_count` exist; no durable owner token | Add owner token, monotonic fencing generation, lease, and guarded terminal writes | yes |
| Conflict race protection | Existing overlap check is query-based before insert | Serialize per scope or add DB-enforced overlap protection | yes |
| Linkage uniqueness | Dormant schema 14 enforces request identity and Job uniqueness | Activate only after separate canonical approval | no |
| Commit evidence reload | Linkage store can build evidence after commit | Expose transaction-safe post-commit reader | no |
| Failure injection points | Pure/fake tests exist | Add isolated failure injection around each operation | yes |
| Post-commit audit semantics | Current audit is a separate transaction and can fail after Job commit | Make audit failure non-authoritative or persist audit in the owning transaction | yes |
| No-worker/no-render guarantee | Prepared lifecycle and worker exclusion exist | Carry assertions into real adapter tests | no |

Overall implementation readiness: `IMPLEMENTATION_NOT_READY`.

Blocker codes:

- `BLOCKED_BY_TRANSACTION_ABSTRACTION`
- `BLOCKED_BY_OWNERSHIP_EVIDENCE`
- `BLOCKED_BY_CONFLICT_RACE`
- `BLOCKED_BY_AUTHORITATIVE_INPUT_REVALIDATION`

## 20. Authorization Gates

Separate future authorization is required before:

1. Pipeline refactor.
2. Real adapter implementation.
3. Canonical schema 13/14 activation.
4. Runtime linkage integration.
5. PREPARE execution endpoint.
6. API/UI integration.
7. Any real Job/JobChapter creation.
8. START_RENDER integration.

## 21. Open Risks

- Existing transaction abstraction is not caller-owned.
- Authoritative chapter/revision/plan facts are not revalidated inside the Job transaction.
- Durable request ownership evidence is insufficient without owner token, fencing generation, and lease/execution-attempt record.
- Existing overlap conflict detection may race for different request identities.
- Post-commit audit failure can currently look like a failed Job creation even though the Job committed.
- Commit recovery must distinguish reliable rollback from unknown commit outcome.
- Legacy prepared Jobs without linkage remain conservative conflict/operator-review evidence.
- Canonical activation remains separate and unauthorized.
- Real execution remains separate and unauthorized.
