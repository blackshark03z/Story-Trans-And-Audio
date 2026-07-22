# DAILY-PROD Checkpoint State

Updated: 2026-07-22 13:49:35 +07:00

## Current Phase

`DAILY-PROD-5A Phase 2` - read-only Batch Plan Review UI.

## Backend Checkpoint

`4784c16c69fbfc6d714c1a636068e35ab41e3bb1`

Subject:
`feat: add read-only batch planning API`

## Status

closeout-complete

## Mutation Authorization

`MUTATION_NOT_AUTHORIZED`

No batch mutation endpoint, execution control, approval, prepare, start, resume, render, QA mutation, provider call, or TTS action is authorized or implemented in this phase.

## UI Implementation

Files changed:
- `ui/index.html`
- `ui/app.js`
- `ui/styles.css`
- `tests/test_batch_plan_ui.py`
- `.ai/STATE.md`

Production range surface:
- Reuses the existing book/from/to range scope.
- Keeps Batch Plan below range readiness.
- Requires readiness for the current scope before enabling the plan action.
- Does not create a second book or chapter selector.

Target phase selector:
- Supports exactly `APPROVAL`, `PREPARE`, `START_RENDER`, `RESUME_OR_MONITOR`, `QA_CLOSEOUT`, and `NO_ACTION`.
- Defaults to `PREPARE`.
- Changing target phase clears the old plan and does not auto-fetch.

Read-only plan action:
- Button: `Lập kế hoạch batch`.
- Calls only `GET /api/production/batch-plan`.
- Sends `book_id`, `from_chapter`, `to_chapter`, and `target_phase`.
- Uses request-id plus scope/phase key stale-response protection.

Rendered plan:
- Prominent authorization banner: `Chỉ xem trước — chưa được phép thực thi batch`.
- Shows `MUTATION_NOT_AUTHORIZED`, no execution endpoint, and no production mutation.
- Shows backend summary fields.
- Shows included rows only from backend `included`.
- Shows excluded rows only from backend `excluded`.
- Maps reason codes to operator-friendly labels.
- Unknown reason falls back to `Chưa xác định lý do`.
- Shows safety contract from backend `execution_contract`.
- Shows fingerprint as truncated secondary metadata.
- Row action only opens the existing single-chapter Production flow.

Safety boundary:
- No batch execution button or fake disabled execution workflow was added.
- No UI mutation endpoint was added.
- Batch result rendering uses `createElement`, `textContent`, and attributes instead of API-data `innerHTML`.
- Leaving Production hides the Production view and the Batch Plan panel.

## Validation

Baseline:
- Branch `main`
- Starting HEAD matched `4784c16c69fbfc6d714c1a636068e35ab41e3bb1`
- Initial tracked worktree was clean
- Protected untracked paths were only `experiment_b_transcript/` and `runs/`

Canonical runtime:
- `http://127.0.0.1:8772/api/runtime` reachable
- Runtime root: `D:\Youtube\Story Trans And Audio`
- Data root: `D:\Youtube\Story Trans And Audio\data`
- DB path: `D:\Youtube\Story Trans And Audio\data\app.db`
- Schema: `12`
- Canonical live data root: true
- Canonical live DB: true

Backend contract smoke:
- `GET /api/production/batch-plan?book_id=1&from_chapter=364&to_chapter=369&target_phase=PREPARE`: PASS
- Authorization: `MUTATION_NOT_AUTHORIZED`
- Execution endpoint available: false

Syntax:
- `node --check ui\app.js`: PASS
- `node --check ui\production_state.js`: PASS

Focused and affected tests:
- `python -m unittest tests.test_batch_plan_ui tests.test_range_readiness_ui tests.test_daily_prod_shell_ui tests.test_runtime_identity_ui -v`: PASS, 49 tests

Full offline validation:
- `python -m unittest discover -s tests -v`: PASS, 1127 tests, 1 skipped

Browser smoke:
- Browser: Codex in-app browser
- Scope: Book `1`, chapters `364-369`
- Range readiness: PASS
- Target phase: `PREPARE`
- Batch plan: PASS
- Included: `0`
- Excluded: `6`
- Reasons: `364-367` Human QA pending, `368` active output complete, `369` Casting Plan not approved
- Authorization warning: visible
- Execution endpoint unavailable: visible
- Fingerprint: visible as truncated metadata
- Safety statuses: `PARTIALLY_SUPPORTED` shown as `Hỗ trợ một phần`
- Open Chapter `369`: navigated to existing Production flow and settled on `CASTING_REVIEW`
- Open Chapter evidence: route `#/production?book=1&chapter=369`, Casting Plan `#24 / v1`
- Refresh/dedupe: rebuilding the plan remained `6` rows total, no duplicate rows
- Phase invalidation: changing to `QA_CLOSEOUT` cleared old plan
- Route isolation: leaving Production hid the Production view and Batch Plan panel
- Network-method capture: direct browser network capture was not available; source review and focused tests prove the Batch Plan action uses GET-only and no mutation request path

Sensitive table counts before and after browser smoke:
- `speaker_assignment_drafts`: 15 -> 15
- `casting_plans`: 23 -> 23
- `jobs`: 21 -> 21
- `job_chapters`: 21 -> 21
- `segments`: 688 -> 688
- `artifacts`: 84 -> 84

Chapter 369 after browser smoke:
- Casting Plan 24 revision 1 remains `draft`, `approved_at = null`
- Jobs: 0
- Artifacts: 0
- Active audio: none
- No production mutation observed

## Remaining

Phase 2 closeout validation is complete and ready for checkpoint commit.

Remaining:
1. Create the Phase 2 checkpoint commit.
2. Keep batch execution unauthorized.
3. Do not start documentation closeout or batch execution in this task.

## Next Exact Action

1. Review the committed DAILY-PROD-5A backend and UI checkpoints.
2. Reconcile PROJECT_STATUS.md, ROADMAP.md, NEXT_TASK.md, and CHANGELOG.md.
3. Decide whether DAILY-PROD-5A is complete.
4. Decide the smallest safe next DAILY-PROD-5 task.
5. Keep mutation unauthorized pending explicit review.
