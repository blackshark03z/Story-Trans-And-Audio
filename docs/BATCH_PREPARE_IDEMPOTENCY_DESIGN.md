# Batch PREPARE Idempotency Design

Status markers:

- `SCHEMA_STORE_IMPLEMENTED_NO_EXECUTION`
- `MIGRATION_13_IMPLEMENTED_DORMANT`
- `NO_EXECUTION_ENDPOINT`
- `PREPARE_EXECUTION_NOT_AUTHORIZED`

## 1. Problem Statement

`DAILY-PROD-5B Phase 1` defined a pure PREPARE safety contract, but execution remains unsafe because the system has no durable request identity, no replayable result record, and no exact behavior for duplicate submits or ambiguous client timeouts.

This design defines the persistence and atomicity contract required before a later task may implement a PREPARE execution endpoint.

## 2. Existing Lifecycle Evidence

- `prepare_job(...)` delegates to `create_job(..., start_immediately=False)`.
- Prepared jobs use `jobs.status = 'prepared'`.
- `create_job(...)` inserts one `jobs` row and one `job_chapters` row per selected chapter inside `db.transaction()`.
- `POST /api/jobs/prepare` does not call `worker.wake()`.
- `POST /api/jobs/{job_id}/start` calls `start_prepared_job(...)`, then wakes the worker after the transition.
- Worker pickup statuses are only `scheduled`, `queued`, and `interrupted`; prepared jobs are not selected.
- Existing duplicate single-chapter prepare is guarded by `_find_conflicting_job(...)`, but that is not a durable batch idempotency record.

## 3. Schema And Migration Evidence

| Question | Existing convention | Source/test evidence | Design implication |
| --- | --- | --- | --- |
| Schema version stored where? | `schema_migrations(version,name,checksum,applied_at)` | `story_audio/migrations/__init__.py`, `tests/test_migrations.py` | Future PREPARE persistence requires next contiguous migration, proposed schema `12 -> 13`. |
| Migrations are atomic? | Each unapplied SQL migration is run under `BEGIN IMMEDIATE`; rollback on error | `MigrationRunner.apply(...)` | Request table must be added in one forward-only migration later. |
| Unique indexes naming? | Named indexes use `idx_<table>_<purpose>`; table constraints also use `UNIQUE(...)` | `0001_initial.sql`, `0011_audio_repair_blocks.sql`, `0012_speaker_draft_reviews.sql` | Use `UNIQUE(client_request_id)`, `UNIQUE(request_identity)`, and named lookup indexes. |
| Foreign-key behavior? | `Database.connect()` enables `PRAGMA foreign_keys=ON`; migrations use explicit references and occasional `ON DELETE CASCADE` / `RESTRICT` | `story_audio/db.py`, `tests/test_migrations.py` | Request `job_id` may reference `jobs(id)`; do not cascade-delete idempotency evidence. |
| Timestamp representation? | Text ISO timestamps from `utcnow()` or SQLite `datetime('now')` in tests | `story_audio/db.py`, table definitions | Use `created_at TEXT NOT NULL`, `updated_at TEXT NOT NULL`. |
| JSON fields used? | JSON is stored in `*_json` TEXT fields; immutable large payloads often live in blobs | `jobs.settings_json`, `jobs.casting_snapshot_json`, `audit_events.details_json`, `chapters.human_approval_json` | Store only bounded replay result JSON, not full text or full plan blobs. |
| Status values enforced where? | Mixed: many statuses are application-enforced; newer tables use `CHECK(status IN (...))` | `0011_audio_repair_blocks.sql`, `0012_speaker_draft_reviews.sql` | New request table should use a `CHECK` for request states. |
| Audit records retained how? | `audit_events` records event code, optional job/chapter, details JSON, timestamp; no general delete policy | `story_audio/db.py` | Request table is the durable replay source; `audit_events` can mirror lifecycle events later. |
| Job metadata linking? | `jobs` stores range/config; `job_chapters` stores per-chapter pins and snapshots | `0001_initial.sql`, `0007_voice_snapshot.sql`, `pipeline.py` | One PREPARE request should link to one `job_id` and replay per-chapter `job_chapter_id`s. |
| Cleanup convention? | Cleanup is targeted, explicit, and retention-based for segments/cache; not hard-delete of audit evidence | `PipelineWorker.cleanup_expired_segments`, docs | Initial request records should be retained indefinitely; cleanup is a later reviewed task. |

## 4. Goals

- Require a durable client request ID before PREPARE execution can be authorized.
- Bind client request ID to target phase, book scope, and plan fingerprint.
- Replay duplicate completed results without creating another job.
- Return in-progress status for duplicate requests while work is applying.
- Define recovery for ambiguous timeout or stale `APPLYING` state.
- Preserve the existing separate START_RENDER boundary.

## 5. Non-Goals

- Schema 13 exists only as a dormant explicit-target artifact under
  `story_audio/migrations/dormant/0013_batch_prepare_requests.sql`.
- The default migration registry still auto-discovers only migrations through schema 12.
- The durable request store is implemented, but it does not auto-migrate and fails if the table is absent.
- No API route is registered.
- No call to `prepare_job`, `start_prepared_job`, provider, Gemini, or TTS is introduced.
- No UI is changed.
- No production data is mutated.

## 6. Request Identity

There are three separate identities:

- Database primary key: future integer `batch_prepare_requests.id`.
- Client request ID: operator/client-provided opaque token.
- Canonical request identity: server-computed deterministic SHA-256 over the normalized PREPARE payload.

The plan fingerprint is not a request ID. It is one bound input inside the request identity.

Client request ID rules:

- Required for any eventual mutation endpoint.
- Strip outer whitespace.
- Non-empty.
- Maximum length `200`, matching existing API `idempotency_key` bounds.
- Safe characters only: letters, numbers, dot, dash, underscore, and colon.
- Must not contain secrets.
- Must not be reused for a different phase, scope, or plan fingerprint.

Canonical request identity:

```text
sha256(canonical_json(
  request_schema,
  client_request_id,
  target_phase,
  book_id,
  from_chapter,
  to_chapter,
  plan_fingerprint
))
```

It does not include timestamp or random UUID.

## 7. Payload Binding

Same `client_request_id` plus same canonical payload resolves to the same request record.

Same `client_request_id` plus different phase, scope, or fingerprint returns `REQUEST_ID_CONFLICT`. The system must not overwrite the original request and must not use latest-request-wins semantics.

## 8. State Machine

States:

- `PLANNED`
- `APPLYING`
- `APPLIED`
- `REJECTED`
- `FAILED`

Allowed transitions:

| From | To |
| --- | --- |
| `PLANNED` | `APPLYING`, `REJECTED` |
| `APPLYING` | `APPLIED`, `REJECTED`, `FAILED` |
| `APPLIED` | terminal |
| `REJECTED` | terminal |
| `FAILED` | terminal |

`APPLIED` is valid only after the Job and all intended JobChapter rows are durably committed.

`FAILED` is replay-only. A new mutation attempt after review requires a new `client_request_id`; the old failure remains auditable.

## 9. Duplicate Behavior

| Existing state | Duplicate same request behavior |
| --- | --- |
| `PLANNED` | Return current request state; do not start a second operation. |
| `APPLYING` | Return in-progress response; do not mark failed solely because of timeout. |
| `APPLIED` | Replay stored result with original `job_id` and per-chapter results. |
| `REJECTED` | Replay stored deterministic rejection. |
| `FAILED` | Replay stored failure; require operator review and a new request ID for another attempt. |

Different payload with the same client request ID returns `REQUEST_ID_CONFLICT`.

## 10. Retry After Timeout

If a client sends PREPARE, times out before receiving a response, and retries with the same `client_request_id`:

- Lookup the durable request record.
- If `APPLYING`, return in-progress.
- If `APPLIED`, replay the stored result.
- If `REJECTED`, replay the rejection.
- If `FAILED`, replay failure and require review/new request ID.
- If payload differs, return `REQUEST_ID_CONFLICT`.

This is a hard gate before PREPARE execution authorization.

## 11. Atomicity Choice

Two options were considered.

Option A: request `APPLYING` committed before the Job transaction.

- Benefit: duplicate retries can see durable in-progress evidence.
- Risk: abandoned `APPLYING` can exist if the process dies before the Job transaction finishes.
- Required mitigation: stale `APPLYING` reconciliation and operator review; never auto-create a second job.

Option B: request and Job creation in one transaction.

- Benefit: simpler database atomicity.
- Risk: duplicate retry during an uncommitted transaction cannot see the request record, making timeout semantics weaker.

Recommended design: Option A.

Option A safety contract:

- Future schema must enforce unique `client_request_id` and unique `request_identity`.
- Future implementation must not rely on application-level check-then-insert alone.
- Transition to `APPLYING` must use a transactional compare-and-transition, for example a guarded `WHERE state = 'PLANNED'` update. Zero changed rows means another request already owns the execution boundary or the request is no longer executable.
- Duplicate requests that observe `APPLYING` return in-progress and must not start mutation again.
- `APPLIED` is written only after the all-or-nothing Job/JobChapter transaction commits.
- Stale `APPLYING` rows older than the review threshold are never auto-run again.

Abandoned `APPLYING` reconciliation:

1. Read the request row and its bound `client_request_id`, `request_identity`, scope, and plan fingerprint.
2. Check whether `job_id` is populated and whether that Job has the expected JobChapter rows.
3. Check audit metadata, if the future implementation writes it, for a matching request identity.
4. If matching Job/JobChapter evidence exists, write or replay the `APPLIED` result from that durable evidence.
5. If no Job exists, recompute the PREPARE plan for the bound scope.
6. If the current fingerprint still matches and no conflicting prepared/active Job exists, mark the request `FAILED` with `FAILED_RETRYABLE`; the operator may submit a new client request ID after review.
7. If facts changed, a conflict exists, or evidence is ambiguous, mark the request `FAILED` with `FAILED_REVIEW_REQUIRED`.
8. Never create a Job while reconciling an existing stale `APPLYING` row.

Future sequence:

1. Insert or reuse request row in `PLANNED`.
2. Revalidate current plan fingerprint.
3. Transition `PLANNED -> APPLYING` and commit.
4. In a protected execution boundary, revalidate fingerprint/facts again.
5. Create one Job and all JobChapter rows in one all-or-nothing transaction.
6. Store bounded result payload and transition to `APPLIED`.
7. If safe validation rejects before mutation, transition to `REJECTED`.
8. If mutation fails, transition to `FAILED` or leave stale `APPLYING` for reconciliation if the process dies.

## 12. One Request / One Job Decision

Recommended model:

```text
one PREPARE request
-> one durable request record
-> one Job
-> one JobChapter per eligible chapter
```

This matches the existing lifecycle and lets START_RENDER remain a separate action for the same prepared Job.

## 13. Per-Chapter Results

Replay result payload stores bounded chapter rows:

- `chapter_id`
- `chapter_number`
- `plan_eligibility`
- `result_status`
- `job_chapter_id`
- `reason_codes`
- `created_or_reused`

Allowed chapter statuses:

- `PREPARED`
- `EXCLUDED`
- `CONFLICT`
- `FAILED`

Because the Job/JobChapter creation transaction is all-or-nothing, an applied request must not claim mixed durable success among eligible chapters. Excluded chapters can be reported as pre-execution plan evidence, but eligible chapter durable creation is batch-atomic. Excluded chapters do not receive JobChapter rows and are not mutation failures.

## 14. Result Replay

Recommended approach: store bounded `result_payload_json` on the request row.

Reasons:

- Duplicate `APPLIED` replay does not depend on current readiness changing later.
- The public response can be versioned.
- It avoids recomputing an old result from mutable current facts.

The stored payload must not contain:

- full approved text;
- full Casting Plan blob;
- provider credentials;
- absolute paths;
- tracebacks;
- audio bytes;
- voice snapshot JSON blobs.

## 15. Fingerprint Race Protection

The plan fingerprint must be verified:

1. during request validation;
2. immediately before transition to `APPLYING`;
3. inside or equivalent to the protected execution boundary before Job creation.

If canonical facts change after validation but before mutation, the request must transition to `REJECTED` with `STALE_PLAN` and must not create a Job.

## 16. Failure Taxonomy

Public failure codes:

- `INVALID_REQUEST`
- `UNSUPPORTED_PHASE`
- `CONFIRMATION_REQUIRED`
- `STALE_PLAN`
- `NO_ELIGIBLE_CHAPTERS`
- `REQUEST_ID_CONFLICT`
- `PREPARE_CONFLICT`
- `APPLYING`
- `APPLIED`
- `FAILED_RETRYABLE`
- `FAILED_REVIEW_REQUIRED`

Public errors must not expose tracebacks.

## 17. Proposed Schema

Schema 13 is implemented as a dormant explicit-target migration artifact.

Migration proposal:

- Current schema: `12`
- Future schema: `13`
- Table: `batch_prepare_requests`
- Activation: `DORMANT_EXPLICIT_TARGET_ONLY`
- Default auto-discovery: disabled; routine canonical startup remains schema 12.

Proposed columns:

| Column | Type |
| --- | --- |
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` |
| `client_request_id` | `TEXT NOT NULL` |
| `request_identity` | `TEXT NOT NULL` |
| `book_id` | `INTEGER NOT NULL REFERENCES books(id)` |
| `from_chapter` | `INTEGER NOT NULL` |
| `to_chapter` | `INTEGER NOT NULL` |
| `target_phase` | `TEXT NOT NULL CHECK(target_phase IN ('PREPARE'))` |
| `plan_fingerprint` | `TEXT NOT NULL` |
| `state` | `TEXT NOT NULL CHECK(state IN ('PLANNED','APPLYING','APPLIED','REJECTED','FAILED'))` |
| `job_id` | `INTEGER REFERENCES jobs(id)` |
| `result_schema_version` | `INTEGER` |
| `result_payload_json` | `TEXT` |
| `error_code` | `TEXT` |
| `error_message` | `TEXT` |
| `attempt_count` | `INTEGER NOT NULL DEFAULT 0` |
| `applying_started_at` | `TEXT` |
| `completed_at` | `TEXT` |
| `created_at` | `TEXT NOT NULL` |
| `updated_at` | `TEXT NOT NULL` |

Proposed constraints:

- `UNIQUE(client_request_id)`
- `UNIQUE(request_identity)`
- `CHECK(target_phase IN ('PREPARE'))`
- `CHECK(state IN ('PLANNED','APPLYING','APPLIED','REJECTED','FAILED'))`
- `CHECK(from_chapter <= to_chapter)`

Proposed indexes:

- `idx_batch_prepare_requests_state_updated`
- `idx_batch_prepare_requests_job`
- `idx_batch_prepare_requests_scope`

## 18. Retention

Initial policy:

- Retain `APPLIED` indefinitely.
- Retain `REJECTED` at least through the retry/replay window; initial implementation should retain indefinitely.
- Retain `FAILED` indefinitely for audit and review.
- Retain `APPLYING`; stale rows require reconciliation.
- Do not hard-delete request rows in the first implementation.
- Cleanup is a separate future task.

Recommended stale `APPLYING` review threshold: `30` minutes.

## 19. Migration And Testing Plan

Implementation must:

- Keep migration `0013_batch_prepare_requests.sql` dormant until canonical activation is separately authorized.
- Update migration tests from schema `12 -> 13`.
- Test unique `client_request_id` and `request_identity`.
- Test `CHECK` constraints for request state and target phase.
- Test all-or-nothing Job/JobChapter creation with isolated temporary DB.
- Test duplicate completed replay and duplicate in-progress behavior.
- Test no worker wake on PREPARE.
- Test START_RENDER remains separate.

This phase creates only the dormant migration artifact and repository store/tests. It does not register a production-active migration, add an API route, or execute PREPARE.

## 20. Authorization Gates

PREPARE execution remains unauthorized until a later task implements and validates:

- migration and upgrade tests;
- persisted request table;
- execution endpoint;
- request lookup/replay behavior;
- stale fingerprint revalidation inside the execution boundary;
- all-or-nothing Job/JobChapter transaction;
- same Job reuse on duplicate replay;
- no worker wake on PREPARE;
- separate START_RENDER action.

## 21. Open Risks

- Abandoned `APPLYING` reconciliation must be implemented carefully so it never creates a duplicate Job.
- Result payload size should be bounded after real batch sizes are known.
- SQLite concurrency behavior must be validated with isolated timeout/duplicate-submit tests in the implementation phase.
- The future API must choose a user-facing way to create and persist `client_request_id` without exposing technical burden to the operator.
