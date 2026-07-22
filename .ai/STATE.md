# DAILY-PROD Checkpoint State

Updated: 2026-07-22 12:58:00 +07:00

## Current Phase

`DAILY-PROD-5A Phase 1` - read-only batch scope plan and mutation safety contract.

## Starting Commit

`5d5d495acb3d1d5bfe15307ca609069b1cafe1d5`

Subject:
`docs: close DAILY-PROD-4 and define batch planning boundary`

## Status

closeout-complete

## Mutation Authorization

`MUTATION_NOT_AUTHORIZED`

No batch mutation endpoint is authorized or implemented.

## Implementation

Files changed:
- `story_audio/batch_plan.py`
- `story_audio/api.py`
- `tests/test_batch_plan_api.py`
- `.ai/STATE.md`

Endpoint:
- `GET /api/production/batch-plan`

Query:
- `book_id`
- `from_chapter`
- `to_chapter`
- `target_phase`

Supported target phases:
- `APPROVAL`
- `PREPARE`
- `START_RENDER`
- `RESUME_OR_MONITOR`
- `QA_CLOSEOUT`
- `NO_ACTION`

Invalid target phases fail with HTTP `400`.

Response behavior:
- Reuses `get_range_readiness`; no second readiness resolver.
- Returns deterministic `plan_fingerprint`.
- Returns one included or excluded row per chapter.
- Returns reason codes and operator messages.
- Does not expose absolute paths, content blob paths, voice snapshots, casting snapshots, or utterance payloads.
- Always returns authorization status `MUTATION_NOT_AUTHORIZED`.
- Always returns `requires_explicit_confirmation = true`.
- Always returns `execution_endpoint_available = false`.

Prepare eligibility:
- `READY_TO_PREPARE` -> `ELIGIBLE`
- `COMPLETE` -> `EXCLUDED_COMPLETE`
- `RENDERED_NOT_QA` -> `EXCLUDED_RENDERED_NOT_QA`
- `PREPARED` -> `EXCLUDED_ALREADY_PREPARED`
- `RENDERING_OR_PAUSED` -> `EXCLUDED_RUNNING_OR_PAUSED`
- `TEXT_BLOCKED`, `SPEAKER_EXCEPTIONS`, `VOICE_BLOCKED`, `CASTING_REVIEW` -> `EXCLUDED_BLOCKED`
- `STATE_UNRESOLVED` and unknown states -> `EXCLUDED_UNSUPPORTED`

Safety semantics:
- Idempotency status: `PARTIALLY_SUPPORTED`
- Retry status: `PARTIALLY_SUPPORTED`
- Partial-failure status: `PARTIALLY_SUPPORTED`
- Policy: `PLAN_ONLY_NOT_EXECUTED`
- Reason: single-chapter prepare/start/retry boundaries exist, but no persisted batch execution or batch idempotency record exists in Phase 1.

## Lifecycle Investigation

Prepare lifecycle:
- `prepare_job` calls `create_job(..., start_immediately=False)`.
- It creates one Job and pinned JobChapter rows in status `prepared`/`pending`.
- It validates approved Casting Plan and active Text Revision when a casting plan is supplied.
- It rejects duplicate prepared/live jobs through existing conflict checks.

Start lifecycle:
- `start_prepared_job` atomically transitions the same job from `prepared` to `scheduled`.
- Worker wake happens in the API route after the transition.
- Repeated/non-prepared starts raise conflict.

Worker selection:
- Worker pickup statuses are `scheduled`, `queued`, and `interrupted`.
- `prepared` is intentionally excluded.

Resume/retry:
- Existing resume route sets job status to `queued`.
- Existing retry routes operate on failed job chapters or failed/interrupted segments.
- Verified segments are immutable and not retried.

Partial failure:
- Worker records per-JobChapter completion/failure.
- A job can complete with `completed_with_errors`.
- No batch rollback/execution policy exists yet.

## Validation

Baseline:
- Branch `main`
- Starting HEAD matched `5d5d495acb3d1d5bfe15307ca609069b1cafe1d5`
- Protected untracked paths were only `experiment_b_transcript/` and `runs/`

Canonical runtime:
- Reloaded `http://127.0.0.1:8772` successfully.
- Runtime root: `D:\Youtube\Story Trans And Audio`
- Data root: `D:\Youtube\Story Trans And Audio\data`
- DB path: `D:\Youtube\Story Trans And Audio\data\app.db`
- Schema: `12`
- Canonical live data root: true
- Canonical live DB: true

Doctor:
- `scripts\doctor.py`: PASS with `critical_errors=0`

Focused validation:
- `py_compile story_audio\batch_plan.py story_audio\api.py`: PASS
- `python -m unittest tests.test_batch_plan_api tests.test_range_readiness_api tests.test_active_output tests.test_prepared_jobs -v`: PASS, 49 tests

Full offline validation:
- `python -m unittest discover -s tests -v`: PASS, 1112 tests, 1 skipped

Canonical runtime GET smoke:
- Scope: Book `1`, chapters `364-369`
- Target phase: `PREPARE`
- Repeated response deterministic: true
- Plan fingerprint: `3ecbe9c69353157f2e0f6e4af48ec21616891469ef2c7c704bfe0f69dcc211b1`
- Included: `0`
- Excluded: `6`
- `364-367`: `EXCLUDED_RENDERED_NOT_QA`, reason `HUMAN_QA_NOT_ACCEPTED`
- `368`: `EXCLUDED_COMPLETE`, reason `ACTIVE_OUTPUT_COMPLETE`
- `369`: `EXCLUDED_BLOCKED`, reason `CASTING_PLAN_NOT_APPROVED`
- Authorization: `MUTATION_NOT_AUTHORIZED`
- Execution endpoint available: false
- No path or internal snapshot leakage detected

Target-phase smoke:
- `APPROVAL`: PASS, included `1`, excluded `5`
- `PREPARE`: PASS, included `0`, excluded `6`
- `START_RENDER`: PASS, included `0`, excluded `6`
- `RESUME_OR_MONITOR`: PASS, included `0`, excluded `6`
- `QA_CLOSEOUT`: PASS, included `4`, excluded `2`
- `NO_ACTION`: PASS, included `1`, excluded `5`
- Invalid phase: HTTP `400`

Sensitive table counts before and after live smoke:
- `speaker_assignment_drafts`: 15 -> 15
- `casting_plans`: 23 -> 23
- `jobs`: 21 -> 21
- `job_chapters`: 21 -> 21
- `segments`: 688 -> 688
- `artifacts`: 84 -> 84

Chapter 369 after smoke:
- Casting Plan 24 revision 1 remains `draft`, `approved_at = null`
- Jobs: 0
- Artifacts: 0
- Active audio: none
- No production mutation observed

## Remaining

UI work has not started.

Batch mutation remains unauthorized and unimplemented.

## Next Exact Action

1. Review the committed read-only batch-plan checkpoint.
2. Decide whether DAILY-PROD-5A requires a read-only Batch Plan UI.
3. Keep execution endpoints and batch mutation unauthorized.
4. Require a separate owner/Tech Lead decision before mutation design.
