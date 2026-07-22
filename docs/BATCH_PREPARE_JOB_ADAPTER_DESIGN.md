# Batch PREPARE Job Adapter Design

Status: `DESIGN_ONLY`

Required markers:

- `NO_REAL_ADAPTER_IMPLEMENTATION`
- `NO_JOB_OR_JOB_CHAPTER_WRITE`
- `NO_PIPELINE_CALL`
- `NO_API_ROUTE`
- `NO_CANONICAL_SCHEMA_ACTIVATION`
- `PREPARE_EXECUTION_NOT_AUTHORIZED`
- `START_RENDER_NOT_AUTHORIZED`

Authorization fields:

- `adapter_implementation_authorized = false`
- `real_job_execution = false`
- `mutation_authorized = false`
- `execution_endpoint_available = false`
- `prepare_starts_render = false`

## 1. Status And Authorization

This document defines the design contract for the future boundary between a durable PREPARE request in `APPLYING`, the existing prepared-job creation lifecycle, and the durable terminal request result.

This phase does not implement that adapter. It adds only pure model definitions and tests in `story_audio/batch_prepare_job_adapter_contract.py` and `tests/test_batch_prepare_job_adapter_contract.py`.

## 2. Existing Lifecycle Evidence

| Question | Verified behavior | Source/test evidence | Adapter implication |
| --- | --- | --- | --- |
| Entry point creating a prepared Job | The supported prepared path delegates to the existing job creation path with `start_immediately=False`. | `story_audio/pipeline.py` lines 292-319; `tests/test_prepared_jobs.py` lines 91-104. | Future adapter may wrap this lifecycle only after separate implementation authorization. |
| Job fields required | The Job records book, status, chapter range, voice, repair mode, output format, settings, skip flag, selected count, schedule timestamps, optional Casting Plan ID, and optional casting snapshot. | `story_audio/pipeline.py` lines 218-245; `0001_initial.sql` lines 54-78; `0002_character_voice.sql` lines 33-34. | Adapter input must bind scope, phase, plan fingerprint, and chapter pins before transaction entry. |
| JobChapter fields required | One JobChapter is inserted per selected chapter with job, chapter, sequence, `pending` status, and for casting jobs pinned text revision, Casting Plan ID, plan hash, and voice snapshot. | `story_audio/pipeline.py` lines 248-265; `0001_initial.sql` lines 80-92; `0002_character_voice.sql` lines 36-38. | Success evidence must include exact JobChapter count and per-chapter references. |
| Job + JobChapter transaction | Job insert and all JobChapter inserts run inside `db.transaction()`, which uses `BEGIN IMMEDIATE`, commits after the block, and rolls back on exception. | `story_audio/pipeline.py` lines 218-265; `story_audio/db.py` lines 102-113. | Applied result cannot be recorded before durable commit evidence. |
| Prepared status value | Prepared jobs use `jobs.status = 'prepared'`. | `story_audio/pipeline.py` lines 75, 227-231, 283-287. | Adapter success requires prepared status exactly. |
| Worker eligible statuses | Worker picks only `scheduled`, `queued`, and `interrupted`. | `story_audio/pipeline.py` lines 86 and 446-458. | Prepared jobs are non-executable until a separate start transition. |
| Worker wake behavior | Prepare API does not wake the worker; start route wakes after transition. | `tests/test_prepared_jobs.py` lines 261-289. | Adapter evidence must require `worker_woken=false`. |
| Start transition separate | Start updates the same prepared Job to `scheduled` inside a transaction and rejects non-prepared or repeated starts. | `story_audio/pipeline.py` lines 322-361; `tests/test_prepared_jobs.py` lines 117-127. | PREPARE must not include render start semantics. |
| Existing conflict | Prepared and active jobs are conflict sources for overlapping chapters; same prepared plan raises a prepared-specific conflict. | `story_audio/pipeline.py` lines 93-118 and 203-217; `tests/test_prepared_jobs.py` lines 129-153. | Future adapter must map conflicts deterministically and not create duplicate Jobs. |
| Segment creation timing | Prepare creates no segments. Segments are created later inside worker chapter processing, after text preparation and before synthesis. | `tests/test_prepared_jobs.py` lines 101-104; `story_audio/pipeline.py` lines 552-572 and 981-1179. | Batch PREPARE adapter should bind immutable pins only; segmenting remains after START_RENDER. |
| Failure rollback | Transaction rollback covers Job and JobChapter inserts if any exception occurs in the transaction block. | `story_audio/db.py` lines 102-113. | Failure before commit is safe no-Job evidence; ambiguous connection/process outcomes need reconciliation. |
| Job identity returned | Existing lifecycle returns `job_id`, selected count, skipped count, status, and undo timestamp only for executable starts. | `story_audio/pipeline.py` lines 279-289. | A function return alone is not enough for APPLIED; durable linkage and commit evidence are required. |
| Retry behavior | Duplicate prepared or active work is rejected by conflict detection, not by a durable request idempotency link. | `story_audio/pipeline.py` lines 203-217; `tests/test_prepared_jobs.py` lines 129-134. | Batch idempotency must add durable request-to-Job linkage before real execution is allowed. |

## 3. Goals

- Bind one durable PREPARE request in `APPLYING` to zero or one prepared Job.
- Require one prepared Job to contain all eligible JobChapter rows atomically.
- Define committed-success evidence that is stronger than an in-memory return value.
- Define deterministic duplicate, conflict, failure, and reconciliation behavior.
- Preserve no-worker and no-render boundaries.

## 4. Non-Goals

- No production adapter implementation.
- No HTTP route.
- No canonical schema activation.
- No real Job or JobChapter creation.
- No worker wake.
- No segment, provider, Gemini, TTS, artifact, or audio work.
- No Chapter 369 production action.

## 5. Adapter Input

The future adapter input must be constructed only after the orchestrator has acquired `APPLYING` ownership and performed the second current-plan validation.

Minimum fields:

- `request_id`
- `client_request_id`
- `request_identity`
- `book_id`
- `from_chapter`
- `to_chapter`
- `target_phase = PREPARE`
- `plan_fingerprint`
- `request_state = APPLYING`
- `eligible_chapters`
- `orchestration_attempt`
- `explicit_no_render = true`
- source marker proving the input came from the second validated current plan snapshot

Client-provided included/excluded rows are never authority. The input must not contain full chapter text, full Casting Plan JSON, secrets, audio paths, or provider payloads.

## 6. Chapter Snapshot

Each eligible chapter snapshot must contain:

- `book_id`
- `chapter_id`
- `chapter_number`
- `text_revision_id`
- `casting_plan_id`
- `casting_plan_revision`
- `eligibility_evidence`
- `deterministic_order`

Snapshot rules:

- immutable and deterministic;
- sorted by deterministic order;
- no duplicate chapter IDs, chapter numbers, or order values;
- all chapters in the bound book;
- all chapters inside the requested range;
- no excluded chapter;
- no hard-coded chapter number.

The pure contract computes a deterministic `chapter_snapshot_digest` from these fields.

## 7. One-Request / One-Job Invariant

Required invariant:

```text
one durable PREPARE request -> zero or one durable prepared Job
```

Forbidden behavior:

- one request creates more than one Job;
- retry creates a second Job;
- latest Job fallback;
- unlinked legacy Job reuse without proof;
- APPLIED result from an allocated primary key before commit.

Required durable linkage evidence:

- request ID and request identity;
- job reference;
- committed timestamp;
- chapter count;
- chapter snapshot digest;
- plan fingerprint;
- transaction evidence version.

Current dormant `batch_prepare_requests.job_id` is useful as a replay pointer, but it is not sufficient by itself if it is written after the Job transaction commits.

## 8. Atomic Job/JobChapter Transaction

A successful future adapter invocation must create:

- exactly one Job;
- exactly one JobChapter for each eligible chapter;
- zero JobChapter rows for excluded chapters.

The transaction is all-or-nothing. There is no mixed durable success among eligible chapters. `APPLIED` can be recorded only after evidence confirms the Job and all JobChapter rows are committed.

Segmentation boundary: the chosen design keeps PREPARE to immutable pins only. Segment rows are not created during PREPARE; they are created later when the worker processes the started Job. This avoids silent divergence between preview/execution boundaries and matches the current runtime lifecycle.

## 9. Request-To-Job Linkage Options

Option A: use `batch_prepare_requests.job_id`.

- Benefit: already present in dormant schema.
- Weakness: if populated after the Job transaction, a process death can leave committed Job evidence without request linkage.
- Weakness: no separate evidence version, digest, or unique Job/request pair constraint beyond request uniqueness.

Option B: add request identity fields directly to `jobs`.

- Benefit: easy lookup from Job to request.
- Weakness: migration touches core Job table and mixes batch idempotency concerns into all Jobs.
- Weakness: legacy rows require null-handling and careful unique partial-index design.

Option C: add a dedicated linkage table.

- Benefit: can be inserted in the same transaction as Job and JobChapter rows.
- Benefit: can enforce `UNIQUE(request_identity)` and `UNIQUE(job_id)`.
- Benefit: can store digest, fingerprint, evidence version, and committed timestamp without rewriting legacy Job semantics.
- Cost: requires a later migration and adapter refactor.

## 10. Recommended Linkage Design

Recommended future design: Option C, a dedicated request-to-Job linkage table written inside the same Job transaction.

Required properties:

- database-enforced uniqueness on `request_identity`;
- database-enforced uniqueness on `job_id`;
- linkage inserted in the same transaction as Job and JobChapter rows;
- stored `chapter_snapshot_digest`, `plan_fingerprint`, and evidence version;
- legacy Jobs without linkage are treated as conflicts or operator-review evidence, not auto-reused.

After commit, the orchestrator may record `batch_prepare_requests.job_id` and result payload from the linkage evidence. If that request update fails, reconciliation can recover from the durable linkage table instead of rerunning the transaction.

## 11. Success Evidence

Committed success evidence must include:

- transaction evidence version;
- request identity;
- job reference;
- committed flag and committed timestamp;
- prepared Job status;
- expected and actual JobChapter counts;
- chapter snapshot digest;
- plan fingerprint;
- worker-woken flag;
- render-started flag;
- per-chapter JobChapter references.

APPLIED eligibility is true only when all fields match the adapter input, the transaction is committed, the status is `prepared`, counts match, worker wake is false, render start is false, and per-chapter evidence matches the snapshot.

## 12. Duplicate Invocation

Duplicate invocation behavior:

- Existing committed same linkage: replay/recover success; do not create another Job.
- Existing linkage with wrong request, fingerprint, or snapshot: conflict; no overwrite.
- Job reference without commit evidence: ambiguous; no retry transaction.
- No linkage/evidence: do not claim safe retry automatically.
- Multiple matching Jobs: operator review.
- Legacy unlinked Job: operator review unless a later migration provides explicit proof.

Duplicate invocation never makes a second Job safe.

## 13. Existing Job Conflicts

Conflict codes:

- `EXISTING_PREPARED_JOB`
- `EXISTING_ACTIVE_JOB`
- `REQUEST_JOB_LINK_CONFLICT`
- `CHAPTER_ALREADY_BOUND`
- `PLAN_SNAPSHOT_CONFLICT`
- `TRANSACTION_EVIDENCE_MISSING`

Prepared or active work for the same chapter blocks future batch PREPARE. Completed historical Jobs are not executable conflicts, but they can still indicate stale assumptions and must not be silently reused as batch idempotency evidence.

## 14. Failure Taxonomy

Minimum public codes:

- `ADAPTER_INPUT_INVALID`
- `REQUEST_STATE_NOT_APPLYING`
- `REQUEST_BINDING_MISMATCH`
- `PLAN_SNAPSHOT_MISMATCH`
- `EXISTING_JOB_CONFLICT`
- `TRANSACTION_FAILED_ROLLED_BACK`
- `TRANSACTION_OUTCOME_AMBIGUOUS`
- `COMMIT_EVIDENCE_INVALID`
- `LINKAGE_CONFLICT`
- `RESULT_PERSISTENCE_REQUIRED`
- `OPERATOR_REVIEW_REQUIRED`

Failure categories:

- Deterministic pre-transaction conflict: no transaction starts, no Job is created.
- Confirmed rollback: no durable Job or JobChapter rows; request can later be failed according to reviewed workflow.
- Ambiguous outcome: do not invoke the transaction again; inspect and reconcile first.
- Commit confirmed but request APPLIED persistence failed: recover result from durable transaction/linkage evidence; do not rerun.

## 15. Process Interruption Matrix

| Interruption point | Durable DB state | Safe adapter response | Reconciliation action |
| --- | --- | --- | --- |
| Before Job transaction | Request may remain `APPLYING`; no Job evidence. | Do not retry automatically. | If stale and no commit evidence exists, classify as no-commit confirmed or failed-retryable in a later mutation workflow. |
| After Job insert before JobChapter inserts | SQLite transaction is uncommitted; rollback on exception/connection close is expected. | If no committed evidence exists, no APPLIED. | Inspect for partial/corrupt committed rows only if process outcome is unclear. |
| After some JobChapter inserts | Same transaction remains uncommitted until commit. | No APPLIED without full count and commit evidence. | Partial committed state is corrupt and requires operator review. |
| Before transaction commit | No durable success claim. | Return or record rollback/ambiguous depending on observed evidence. | Check linkage/evidence before any new request. |
| After commit before adapter response | Job, JobChapters, and same-transaction linkage should exist. | Recover committed success from evidence. | Record/replay APPLIED from linkage evidence. |
| After adapter response before request APPLIED | Transaction committed, request still `APPLYING`. | Do not rerun transaction. | Classify `RESULT_PERSISTENCE_REQUIRED` and recover APPLIED result. |
| After request APPLIED | Request stores terminal replay payload. | Replay historical payload. | No mutation. |

The design does not claim exactly-once execution until database uniqueness/linkage enforcement exists.

## 16. Historical Replay Payload

Stored `result_payload_json` after adapter success should contain:

- `result_schema_version`
- `request_identity`
- `job_reference`
- `job_status`
- `chapter_count`
- `chapters`
- `chapter_snapshot_digest`
- `plan_fingerprint`
- `committed_at`
- `worker_woken`
- `render_started`
- `replay_source`

Per-chapter fields:

- `chapter_id`
- `chapter_number`
- `job_chapter_reference`
- `status`

Forbidden fields:

- full text;
- full Casting Plan blob;
- voice snapshot JSON;
- filesystem paths;
- provider payloads;
- tracebacks;
- audio details.

## 17. Reconciliation Evidence

External evidence states:

- `NONE`
- `TRANSACTION_NOT_FOUND`
- `PREPARED_JOB_COMMITTED`
- `JOB_PARTIAL_OR_CORRUPT`
- `ACTIVE_JOB_FOUND`
- `COMPLETED_JOB_FOUND`
- `MULTIPLE_MATCHING_JOBS`
- `LINKAGE_MISMATCH`
- `UNKNOWN`

Classifier decisions:

- `SAFE_NO_COMMIT_CONFIRMED`
- `RECOVER_COMMITTED_RESULT`
- `OPERATOR_REVIEW_REQUIRED`
- `REQUEST_JOB_CONFLICT`
- `CORRUPT_TRANSACTION_STATE`

The classifier is pure, deterministic, read-only, and never retries or mutates.

## 18. No-Worker / No-Render Boundary

PREPARE remains non-executable. Future adapter success must report:

- `worker_woken = false`
- `render_started = false`
- `prepared_status = prepared`

Any evidence of worker wake or render start invalidates APPLIED eligibility for the PREPARE adapter contract.

## 19. Migration / Refactor Requirements

Before real adapter execution can be authorized, a later task must provide:

- canonical schema activation approval;
- a same-transaction request-to-Job linkage mechanism, preferably a dedicated linkage table;
- database uniqueness for request identity and Job linkage;
- adapter implementation that can participate in the Job transaction;
- isolated tests for commit, rollback, ambiguous outcome, and duplicate invocation;
- API and UI tasks kept separate from START_RENDER.

## 20. Implementation Authorization Gates

Before real adapter implementation can be authorized, a later reviewed task must provide:

1. Request-to-Job DB linkage schema review.
2. Unique request-to-Job constraint review.
3. Same-transaction Job, JobChapter, and linkage insertion design review.
4. Legacy prepared/active/completed Job conflict behavior review.
5. Committed-evidence query and recovery design.
6. Pipeline transaction integration point identification.
7. Failure-injection tests for rollback, ambiguous outcome, and commit-before-result persistence.
8. No-worker/no-render behavior tests against the real adapter boundary.
9. Canonical schema activation decision kept separate.
10. PREPARE API/execution decision kept separate.
11. Full isolated implementation acceptance before any canonical production execution.

Still unauthorized in this design checkpoint:

- production adapter implementation;
- canonical schema 13 activation;
- PREPARE execution endpoint;
- API integration;
- worker wake;
- START_RENDER;
- provider/Gemini/TTS calls;
- real Job/JobChapter creation from batch PREPARE.

## 21. Open Risks

- Current dormant request row `job_id` alone cannot prove a committed transaction if written after commit.
- Existing prepared/active conflict detection is chapter-based, not request-identity-based.
- Legacy prepared Jobs lack batch request linkage and must be handled conservatively.
- Audit is written after the Job transaction, so audit alone is not commit evidence.
- The future adapter must be able to share a transaction boundary or write durable linkage before commit.
- Canonical activation and real execution remain separate reviewed tasks.
