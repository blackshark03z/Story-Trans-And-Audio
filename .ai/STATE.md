# DAILY-PROD Checkpoint State

Updated: 2026-07-22 15:15:13 +07:00

## Current Phase

`DAILY-PROD-5B Phase 2` - PREPARE Idempotency Persistence And Atomic Execution Design.

Starting commit:
`f0d78ca9718c0d1648a209cd5d38bec3ece18ccc`

## Execution Authorization

`PREPARE_EXECUTION_NOT_AUTHORIZED`

No batch execution endpoint, execution control, approval, prepare, start, resume, render, QA mutation, provider call, Gemini call, or TTS action is authorized in Phase 2.

All Phase 2 contract output must keep:

- `mutation_authorized = false`
- `execution_endpoint_available = false`
- `prepare_starts_render = false`

## Design Artifacts

Added pure persistence contract module:

- `story_audio/batch_prepare_persistence_contract.py`

Added design document:

- `docs/BATCH_PREPARE_IDEMPOTENCY_DESIGN.md`

Added focused tests:

- `tests/test_batch_prepare_persistence_contract.py`

Current schema:

- `12`

Proposed future schema:

- `13`, design only

Migration:

- not implemented

Execution endpoint:

- none

## Persistence Design

The design defines:

- durable client request ID;
- canonical request identity;
- payload and plan-fingerprint binding;
- request state machine;
- duplicate replay;
- retry-after-timeout behavior;
- atomicity policy;
- one PREPARE request to one Job;
- one JobChapter per eligible chapter;
- per-chapter result contract;
- historical result replay;
- public failure taxonomy;
- retention policy;
- proposed migration metadata.

Request identity:

- `client_request_id` is required for any future mutation endpoint.
- Maximum length is `200`, matching existing API idempotency-key bounds.
- Allowed characters are letters, numbers, dot, dash, underscore, and colon.
- Same `client_request_id` cannot bind to a different phase, scope, or plan fingerprint.
- Canonical request identity is SHA-256 over canonical JSON of request schema, normalized client request ID, `PREPARE`, `book_id`, `from_chapter`, `to_chapter`, and `plan_fingerprint`.
- The canonical request identity is distinct from the plan fingerprint and does not include timestamp or random UUID.

State machine:

- `PLANNED -> APPLYING`
- `PLANNED -> REJECTED`
- `APPLYING -> APPLIED`
- `APPLYING -> REJECTED`
- `APPLYING -> FAILED`
- `APPLIED`, `REJECTED`, and `FAILED` are terminal.

Duplicate behavior:

- `PLANNED`: return current request state; no second operation.
- `APPLYING`: return in-progress response; do not mark failed solely because of timeout.
- `APPLIED`: replay original durable result.
- `REJECTED`: replay deterministic rejection.
- `FAILED`: replay failure; operator review and a new `client_request_id` are required for another attempt.
- Same `client_request_id` with different payload returns `REQUEST_ID_CONFLICT`.

Atomicity recommendation:

- Use Option A: commit request `APPLYING` before the Job transaction.
- Create one Job and all JobChapter rows in one all-or-nothing database transaction.
- Store bounded `result_payload_json` and transition to `APPLIED` only after Job/JobChapter creation commits.
- Stale `APPLYING` requires reconciliation/review; never auto-create a duplicate Job.

Result replay:

- Use bounded, versioned `result_payload_json`.
- Replay must not depend on current readiness after `APPLIED`.
- Payload must not contain paths, secrets, full text, full Casting Plan blobs, voice snapshot blobs, audio bytes, or tracebacks.

Retention:

- Initial implementation should retain request records indefinitely.
- Cleanup is a separate future task.
- Stale `APPLYING` threshold recommendation: `30` minutes, requiring explicit reconciliation.

## Schema And Migration Conventions Verified

- Migration files are contiguous numbered SQL files under `story_audio/migrations/`.
- `MigrationRunner` stores version, name, checksum, and applied timestamp in `schema_migrations`.
- Unapplied migrations run with `BEGIN IMMEDIATE` and rollback on error.
- `Database.connect()` enables foreign keys, WAL, and busy timeout.
- Timestamps are text ISO strings from `utcnow()` or SQLite `datetime('now')` in tests.
- JSON fields are stored as TEXT `*_json` columns or immutable blobs.
- Newer status tables use `CHECK(status IN (...))`; older job statuses remain application-enforced.
- Audit records use `audit_events(event_code, job_id, chapter_id, details_json, created_at)`.
- Cleanup is targeted and retention-based; no general hard-delete pattern exists for audit evidence.

## Validation

Syntax:

- `python -m py_compile story_audio\batch_prepare_persistence_contract.py`: PASS

Focused contract tests:

- `python -m unittest tests.test_batch_prepare_persistence_contract -v`: PASS, 50 tests

Focused Phase 2 suite:

- `python -m unittest tests.test_batch_prepare_persistence_contract tests.test_batch_prepare_contract tests.test_prepared_jobs tests.test_migrations -v`: PASS, 102 tests

Full offline suite:

- `python -m unittest discover -s tests -v`: PASS, 1208 tests, 1 skip

Canonical read-only verification:

- Runtime: `http://127.0.0.1:8772`
- Canonical live root/db: true
- Schema: `12`
- Batch plan Book `1`, chapters `364-369`, target `PREPARE`: included `0`, excluded `6`
- Authorization: `MUTATION_NOT_AUTHORIZED`
- `execution_endpoint_available = false`
- Plan fingerprint: `3ecbe9c69353157f2e0f6e4af48ec21616891469ef2c7c704bfe0f69dcc211b1`

Sensitive table counts before and after read-only smoke:

- `speaker_assignment_drafts`: `15 -> 15`
- `casting_plans`: `23 -> 23`
- `jobs`: `21 -> 21`
- `job_chapters`: `21 -> 21`
- `segments`: `688 -> 688`
- `artifacts`: `84 -> 84`

Chapter 369 after read-only smoke:

- Active Text Revision `738`
- Casting Plan `24` revision `1` remains draft/unapproved
- Jobs: `0`
- Artifacts: `0`
- Active audio: none
- Audio status: `not_created`

Doctor:

- `python scripts\doctor.py`: PASS, `critical_errors=0`
- Existing warning remains: speaker assignment drafts `15`, invalid `9`

## Remaining

1. Review the persistence and atomicity design.
2. Keep migration and PREPARE execution unauthorized until a separate implementation task.
3. Commit only the design checkpoint in a later closeout task.

## Next Exact Action

1. Review `docs/BATCH_PREPARE_IDEMPOTENCY_DESIGN.md`.
2. Review `story_audio/batch_prepare_persistence_contract.py`.
3. Verify request state and duplicate replay semantics.
4. Verify proposed schema matches repository conventions.
5. Reconcile the documentation checkpoint.
6. Commit design-only checkpoint.
7. Stop before migration or execution implementation.
