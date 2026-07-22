# DAILY-PROD Checkpoint State

Updated: 2026-07-22 14:11:49 +07:00

## Current Phase

`DAILY-PROD-5A` is complete.

Current milestone:
`DAILY-PROD-5` - Batch Approval, Prepare, Render And QA Closeout.

Current task:
`DAILY-PROD-5B` - Batch Prepare Mutation Contract And Stale-Plan Guard.

## Checkpoints

Backend checkpoint:
`4784c16c69fbfc6d714c1a636068e35ab41e3bb1`

Subject:
`feat: add read-only batch planning API`

UI checkpoint:
`b364b51ed72a4c1e506de12e368a6b5a69a3356e`

Subject:
`feat: add read-only batch planning UI`

## DAILY-PROD-5A Acceptance

Implemented:
- Read-only `GET /api/production/batch-plan`.
- Deterministic selected range and target phase allowlist.
- Deterministic plan fingerprint.
- Included/excluded chapter lists.
- Clear exclusion reason codes.
- Summary counts.
- Authorization status `MUTATION_NOT_AUTHORIZED`.
- `execution_endpoint_available = false`.
- Honest safety limitations for idempotency, retry/resume, and partial failure.
- Read-only Batch Plan Review UI under the Production range surface.
- Authorization banner, safety contract display, truncated fingerprint, loading/error/retry/refresh, stale-response protection, and safe single-chapter navigation.

Verdict:
`DAILY-PROD-5A_COMPLETE`

## Mutation Authorization

`MUTATION_NOT_AUTHORIZED`

No batch mutation endpoint, execution control, approval, prepare, start, resume, render, QA mutation, provider call, or TTS action is authorized for passive plan review.

## Latest Validation

Syntax:
- `node --check ui\app.js`: PASS
- `node --check ui\production_state.js`: PASS

Focused and affected tests:
- `python -m unittest tests.test_batch_plan_ui tests.test_range_readiness_ui tests.test_daily_prod_shell_ui tests.test_runtime_identity_ui -v`: PASS, 49 tests

Full offline validation:
- `python -m unittest discover -s tests -v`: PASS, 1127 tests, 1 skipped

Canonical runtime smoke:
- Runtime: `http://127.0.0.1:8772`
- Schema: `12`
- `GET /api/production/batch-plan?book_id=1&from_chapter=364&to_chapter=369&target_phase=PREPARE`: PASS
- Authorization: `MUTATION_NOT_AUTHORIZED`
- Execution endpoint available: false
- Included: 0
- Excluded: 6
- Fingerprint: `3ecbe9c69353157f2e0f6e4af48ec21616891469ef2c7c704bfe0f69dcc211b1`

Browser smoke:
- Batch Plan panel reused Book `1`, chapters `364-369`.
- Target phase `PREPARE`.
- Authorization warning and unavailable execution endpoint were visible.
- Summary, excluded reasons, safety contract, truncated fingerprint, refresh/dedupe, phase invalidation, and route isolation were verified.
- Row action opened Chapter `369` in the existing single-chapter Production flow at `CASTING_REVIEW`.
- Direct browser network-method capture was unavailable; source review and focused tests prove GET-only behavior.

Sensitive table counts before and after browser smoke:
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
- Active audio: none
- No production mutation observed.

## Runtime Facts For Batch Plan

- Chapters `364-367`: excluded from PREPARE because runtime Human QA is not accepted.
- Chapter `368`: excluded from PREPARE because active output is complete.
- Chapter `369`: excluded from PREPARE because Casting Plan `24` revision `1` is draft/unapproved.

## Next Exact Action

1. Inspect existing single-job PREPARE lifecycle.
2. Define PREPARE-only batch mutation contract.
3. Define plan fingerprint and stale-plan rejection.
4. Define duplicate-request, partial-failure and retry semantics.
5. Add contract-focused tests.
6. Stop before implementation of any mutation endpoint.
