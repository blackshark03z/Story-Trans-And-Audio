# DAILY-PROD Checkpoint State

Updated: 2026-07-22 14:57:45 +07:00

## Current Phase

`DAILY-PROD-5B Phase 1` complete.

Current next task:
`DAILY-PROD-5B Phase 2` - PREPARE Idempotency Persistence And Atomic Execution Design.

Starting commit:
`a3d6f956a103ed563f5bd9ea6496ea0da307440c`

## Mutation Authorization

`MUTATION_NOT_AUTHORIZED`

No batch execution endpoint, execution control, approval, prepare, start, resume, render, QA mutation, provider call, Gemini call, or TTS action is authorized in Phase 1.

## Implementation

Added a pure contract module:
- `story_audio/batch_prepare_contract.py`

Added focused contract tests:
- `tests/test_batch_prepare_contract.py`

Implemented:
- PREPARE-only request validation.
- Required `book_id`, `from_chapter`, `to_chapter`, `target_phase`, `plan_fingerprint`, and `explicit_confirmation`.
- Required `target_phase = PREPARE`.
- Required 64-character lowercase hex plan fingerprint.
- Deterministic stale-plan guard by recomputing the current PREPARE batch plan through an injected provider.
- Confirmation guard: `explicit_confirmation` must be true.
- Scope and target phase guard against the recomputed current plan.
- Authorization guard: current plan must still be `MUTATION_NOT_AUTHORIZED` with `execution_endpoint_available = false`.
- Execution intent schema built only from current plan `included` rows.
- No eligible chapters returns `REJECTED_NO_ELIGIBLE_CHAPTERS`, not execution-ready status.
- All accepted and rejected results report `mutation_authorized = false`, `execution_endpoint_available = false`, and `prepare_starts_render = false`.

No API route was registered.
No UI file was changed.
No database write helper is called by the contract module.

Closeout correction:
- Request objects that are not mappings now fail closed with `REJECTED_INVALID_REQUEST`.
- Empty fingerprints are rejected without provider recompute.
- Missing, false, or string truthy confirmation is rejected before provider recompute.
- Focused tests now verify the contract module has no database, lifecycle, provider, or TTS imports.

## PREPARE Lifecycle Evidence

- Single-chapter prepare uses `prepare_job(...)`, which delegates to `create_job(..., start_immediately=False)`.
- PREPARE creates one `jobs` row for the selected scope and one `job_chapters` row per selected chapter inside one `db.transaction()` block.
- Manual casting prepare pins `job_chapters.text_revision_id`, `job_chapters.casting_plan_id`, `job_chapters.casting_plan_sha256`, and `job_chapters.voice_snapshot_json`.
- Prepared jobs use `jobs.status = prepared`; worker pickup statuses are only `scheduled`, `queued`, and `interrupted`, so the worker ignores prepared jobs.
- `POST /api/jobs/prepare` does not call `worker.wake()`.
- `POST /api/jobs/{job_id}/start` uses `start_prepared_job(...)`, atomically transitions `prepared` to `scheduled`, then the API route calls `worker.wake()`.
- Duplicate single-chapter prepare with the same approved plan/text snapshot raises `JobPreparationConflict` and does not create a second job.
- Existing prepared or active jobs are detected before insert by `_find_conflicting_job(...)`.
- Stale approved Casting Plan versus active Text Revision is rejected before job creation.
- Worker execution records per-JobChapter success/failure after start; a job may end `completed_with_errors`.
- Retry is existing job-chapter or segment scoped, not batch scoped.

## Safety Semantics

Idempotency:
`PARTIALLY_SUPPORTED`

Basis:
- deterministic plan fingerprint;
- deterministic request validation;
- existing single-chapter conflict guard for prepared/active jobs.

Actual batch mutation idempotency is not persisted in Phase 1.

Duplicate request:
`PARTIALLY_SUPPORTED`

Same request and same facts return the same contract result. After prepared work exists, the current plan excludes the chapter as already prepared. After state change, old fingerprints are stale. No client request ID convention is implemented in Phase 1.

Partial failure:
`NOT_YET_DEFINED`

Existing worker failure accounting is per JobChapter after start. This Phase 1 contract performs no mutation and does not define batch rollback or partial durable commit policy.

Retry:
`PARTIALLY_SUPPORTED`

Retry before mutation is safe by re-evaluating the contract. Retry after state changes requires recomputing the plan; stale fingerprints are rejected. Existing retry helpers are job-chapter or segment scoped, not batch scoped.

## Validation

Syntax:
- `python -m py_compile story_audio\batch_prepare_contract.py`: PASS

Focused tests:
- `python -m unittest tests.test_batch_prepare_contract tests.test_batch_plan_api tests.test_prepared_jobs -v`: PASS, 57 tests

Full offline validation:
- `python -m unittest discover -s tests -v`: PASS, 1158 tests, 1 skipped

Canonical read-only contract smoke:
- Runtime: `http://127.0.0.1:8772`
- Schema: `12`
- Scope: Book `1`, chapters `364-369`, target `PREPARE`
- Current fingerprint: `3ecbe9c69353157f2e0f6e4af48ec21616891469ef2c7c704bfe0f69dcc211b1`
- Included: `0`
- Excluded: `6`
- Valid confirmed request result: `REJECTED_NO_ELIGIBLE_CHAPTERS`
- Stale fingerprint result: `REJECTED_STALE_PLAN`
- Missing confirmation result: `REJECTED_CONFIRMATION_REQUIRED`
- Repeated result deterministic: yes
- `mutation_authorized = false`
- `execution_endpoint_available = false`
- `prepare_starts_render = false`

Sensitive table counts before and after smoke:
- `speaker_assignment_drafts`: 15 -> 15
- `casting_plans`: 23 -> 23
- `jobs`: 21 -> 21
- `job_chapters`: 21 -> 21
- `segments`: 688 -> 688
- `artifacts`: 84 -> 84

Chapter 369 after smoke:
- Casting Plan `24` revision `1` remains draft/unapproved.
- Jobs: 0
- Artifacts: 0
- Active audio: none.
- Audio status: `not_created`.

Doctor:
- `python scripts\doctor.py`: PASS, `critical_errors=0`
- Existing speaker-assignment draft warning remains: drafts `15`, invalid `9`.

## Remaining

Phase 1 implementation, full validation, and read-only canonical smoke are complete.

Remaining:
1. Design durable PREPARE request identity.
2. Define request state machine, replay and retry semantics.
3. Define atomicity and per-chapter audit/result schema.
4. Stop before migration implementation or execution endpoint.

## Next Exact Action

1. Inspect schema and migration conventions.
2. Design durable PREPARE request identity.
3. Define request state machine and fingerprint binding.
4. Define duplicate replay and retry-after-timeout.
5. Define atomicity and per-chapter audit/result schema.
6. Stop before migration implementation or execution endpoint.
