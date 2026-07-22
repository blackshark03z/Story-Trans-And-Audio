# DAILY-PROD Checkpoint State

Updated: 2026-07-22 15:49:10 +07:00

## Current Phase

`DAILY-PROD-5B Phase 3` - Schema 13 Migration And Durable PREPARE Request Store.

## Completed Checkpoint

`DAILY-PROD-5B Phase 2` is complete.

Design commit:

- `68f4f3d059f08004d6fcb4d4d06505ad802f3c11`
- `feat: define PREPARE idempotency persistence contract`

Phase 2 artifacts:

- `docs/BATCH_PREPARE_IDEMPOTENCY_DESIGN.md`
- `story_audio/batch_prepare_persistence_contract.py`
- `tests/test_batch_prepare_persistence_contract.py`

## Phase 2 Acceptance

Accepted capabilities:

- Durable `client_request_id` rules.
- Deterministic canonical request identity.
- Payload binding to target phase, book/range scope, and plan fingerprint.
- PREPARE-only phase.
- Explicit request states: `PLANNED`, `APPLYING`, `APPLIED`, `REJECTED`, `FAILED`.
- Duplicate same-payload replay.
- Different-payload `REQUEST_ID_CONFLICT`.
- Duplicate `APPLYING` in-progress replay.
- `APPLIED`, `REJECTED`, and `FAILED` historical replay.
- `FAILED` requires operator review and a fresh request ID for a new attempt.
- Retry-after-timeout semantics.
- Stale `APPLYING` reconciliation contract.
- Option A atomicity: commit request `APPLYING` before the all-or-nothing Job/JobChapter transaction.
- Concurrency/uniqueness guard.
- Fingerprint race revalidation.
- One request -> one Job -> N JobChapter rows.
- Bounded versioned `result_payload_json`.
- Public failure taxonomy and retention policy.
- Proposed schema `12 -> 13` and proposed `batch_prepare_requests` table.
- No migration implementation.
- No execution endpoint.

Verdict:

- `DAILY-PROD-5B_PHASE_2_COMPLETE`

## Latest Validation

Phase 2 closeout validation:

- Pure persistence tests: `50` PASS.
- Focused/affected suite: `102` PASS.
- Full offline suite: `1208` PASS, `1` skipped.
- Doctor: PASS, `critical_errors=0`.

Canonical read-only verification:

- Runtime: `http://127.0.0.1:8772`
- Canonical live root/db: true
- Current runtime schema: `12`
- Proposed future schema: `13`
- Batch plan Book `1`, chapters `364-369`, target `PREPARE`: included `0`, excluded `6`
- Authorization: `MUTATION_NOT_AUTHORIZED`
- `execution_endpoint_available=false`

Sensitive counts unchanged:

- `speaker_assignment_drafts`: `15`
- `casting_plans`: `23`
- `jobs`: `21`
- `job_chapters`: `21`
- `segments`: `688`
- `artifacts`: `84`

Chapter 369 unchanged:

- Active Text Revision `738`
- Casting Plan `24` revision `1` remains draft/unapproved
- Jobs `0`
- Artifacts `0`
- Active audio none
- Audio status `not_created`

## Authorization Boundary

Migration implementation authorization:

- `AUTHORIZED_FOR_ISOLATED_DEVELOPMENT`

Canonical migration authorization:

- `NOT_AUTHORIZED`

PREPARE execution authorization:

- `NOT_AUTHORIZED`

START_RENDER authorization:

- `NOT_AUTHORIZED`

Phase 3 may implement repository migration code, a durable request store, and repository-level tests using temporary/isolated databases only.

Phase 3 must not implement API execution routes, call `prepare_job`, create Jobs or JobChapters, migrate canonical `data/app.db`, modify UI, start render, or call providers/Gemini/TTS.

## Next Exact Action

1. Implement schema 13 migration in repository.
2. Add durable `batch_prepare_requests` store.
3. Add repository-level idempotency and replay tests.
4. Test only against temporary/isolated databases.
5. Verify canonical DB remains schema 12.
6. Stop before API or `prepare_job` integration.
