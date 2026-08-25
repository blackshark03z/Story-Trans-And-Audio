# Worker Packet

Generated: 2026-08-25T09:27:58+00:00
Capsule Revision: 23

## Task

- ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-B_FIXTURE_ISOLATION/r001
- Status: COMPLETED
- Goal: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR / node B_FIXTURE_ISOLATION
- Milestone / criterion: M-001 / All assignment, batch-plan, Human Approval, Production Runner, phase13 and phase14 focused tests pass using isolated schema-16/temp dependencies with no provider or canonical mutation.
- Risk / profile: R2 / STANDARD
- Negative path required: yes
- Shipping breaker: INACTIVE (1/3 non-shipping)

## Outcome

Repair all inventory-proven offline fixture/dependency-binding failures without weakening production voice-catalog or live-data guards.

## Goal Context

Repair blockers discovered by the parent baseline Goal, restore a truthful green development baseline, reconcile current Story Audio authority, safely adopt the approved Build OS v1.25 RC4 lineage, and prove the new Work Loop without produc

## Scout Handoff

Scout A_FAILURE_INVENTORY (HIGH): Complete read-only inventory: full offline suite ran 1970 tests in 737s with 6 failures, 16 errors, 1 skip. Errors are four fixture families: worktree-local empty data/app.db assumption; batch-plan voice-catalog lambda signature drift; Human Approval and Production Runner custom_voice_repo binding drift. Failures are shared phase13/14 catalog stub readiness, Golden Journey stale schema/canonical/apply-button expectations, and two real 1366x768 layout regressions. Parent CI and voice-preview repairs remain green. JS syntax passes. v1.25 package/receipt identity is valid at source 595c0f7/frozen b34eb36, but official adoption rejects callable legacy scripts/state and conflicting AGENTS until archived.
- Affected: tests/test_assignment_workflow_browser.py, tests/test_batch_plan_api.py, tests/test_human_approval_api.py, tests/test_production_runner_api.py, tests/batch_prepare_phase13_runtime_worker.py, tests/test_batch_prepare_phase13_clone_runtime.py, tests/test_batch_prepare_phase14_restart.py, tests/test_golden_journey_certification.py
- Invariants: Port 8772 remained closed; canonical DB, providers, protected artifacts, secrets, push, merge, and production commands remained untouched.
- Risk: R2 bounded test/UI repair; R3 lifecycle authority transition due legacy-state archival and v1.25 bootstrap.
- Entry: D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest discover -s tests

## Scope

- Modify: tests/test_assignment_workflow_browser.py,tests/test_batch_plan_api.py,tests/test_human_approval_api.py,tests/test_production_runner_api.py,tests/batch_prepare_phase13_runtime_worker.py
- Create: NONE
- External calls: NONE
- Pre-existing dirty files: 0 (not part of task unless changed again)
- Current task delta: NONE

## Acceptance

- [ ] Observable outcome exists.
- [ ] Critical negative path checked.
- [ ] Output and side effects match preflight.

## Verify

1. Cheapest focused check.
2. Affected runtime/integration check.
3. Inspect final output and Git diff.
- Acceptance contract: d8ec9d925ceeaef55b579b7ee503afc618a6f6e7f147908b0e989902124e60c8 (predeclared commands=1, locked probes=0)
- Review policy: required

## Stop

- Stop/change strategy after two failed attempts without new evidence.
- Amend scope instead of widening it silently.
- Final output and task delta must be inspected before acceptance.
- If shipping breaker is ACTIVE, do not start/continue non-shipping work without an explicit override.

## Shared/Operational Context

- Product goal: The operator completes the frozen North Star journey from EPUB import through accepted downloadable chapter audio, with explicit control over AI proposals.
- Data operation: READ_ONLY
- Artifact operation: CREATE_NEW_VERSION
- Rollback: revert task-scoped diff and remove new artifacts

## Relevant Decisions

- NONE_LISTED
