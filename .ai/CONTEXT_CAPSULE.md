# Worker Packet

Generated: 2026-08-25T08:14:17+00:00
Capsule Revision: 18

## Task

- ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125-B_CI_RECONCILIATION/r001
- Status: PAUSED
- Goal: STORY_AUDIO_BASELINE_RECONCILIATION_V125 / node B_CI_RECONCILIATION
- Milestone / criterion: M-001 / CI install and product-check commands resolve without Markdown delimiter tokens and relevant checks pass.
- Risk / profile: R2 / STANDARD
- Negative path required: yes
- Shipping breaker: INACTIVE (0/3 non-shipping)

## Outcome

Repair the machine-readable Project Contract command encoding and prove CI command resolution and relevant checks.

## Goal Context

Restore one trustworthy Story Audio execution baseline and safely adopt Build OS v1.25 Work Loop authority without laundering v1.16 history.

## Scout Handoff

Scout A_GROUND_TRUTH_PREFLIGHT (HIGH): Git: isolated goal worktree on goal/story-audio-baseline-v125 at c9504dd, 0/0 with origin/main; dirty sibling main preserved. Lifecycle: v1.16 reconciliation Goal active, no writer; legacy lease released; ignored .buildos v1.22 generation 4 CLOSED/released at c9504dd. Runtime: stopped, port 8772 no listener, identity endpoint unobserved; do not start. Data: canonical data/app.db schema 16, quick_check ok, FK 0; Ch372 Artifact93 stale needs_fixes, Artifact99 active accepted; Ch373 Artifact96 active QA pending. CI: remote run 31463977833 and local reproduction fail on literal backtick-python from .ai/PROJECT.md. Preserve DB/artifacts/history; no provider/runtime/push/merge; never relabel v1.16 history as v1.25.
- Affected: .ai/PROJECT.md, scripts/project_ci.py, DOCUMENTATION_SOURCES.md, PROJECT_STATUS.md, ROADMAP.md, NEXT_TASK.md, AGENTS.md
- Invariants: Canonical DB, Artifacts 93/96/99 and all historical lifecycle evidence remain read-only.; No v1.16 history may be represented as v1.25-supervised.
- Risk: dirty sibling canonical worktree; runtime stopped and identity endpoint unobserved; low disk 0.9 GB; legacy v1.16 and closed v1.22 authorities coexist
- Entry: scripts/project_ci.py and external v1.25 adoption/initialize.ps1

## Scope

- Modify: .ai/PROJECT.md,scripts/project_ci.py,tests/test_voice_preview_api.py
- Create: tests/test_project_ci_contract.py
- External calls: NONE
- Pre-existing dirty files: 0 (not part of task unless changed again)
- Current task delta: scripts/project_ci.py, tests/test_project_ci_contract.py, tests/test_voice_preview_api.py

## Acceptance

- [ ] Project Contract parsing returns raw executable argv for install and test commands.
- [ ] Equivalent install and canonical product-check resolution passes locally.

## Verify

1. Cheapest focused check.
2. Affected runtime/integration check.
3. Inspect final output and Git diff.
- Acceptance contract: 162d59ec8d163c954f2e691d0d4e5a25e8effc4f41d5b93fca892472bfdbf613 (predeclared commands=1, locked probes=0)
- Review policy: required

## Stop

- Stop/change strategy after two failed attempts without new evidence.
- Amend scope instead of widening it silently.
- Final output and task delta must be inspected before acceptance.
- If shipping breaker is ACTIVE, do not start/continue non-shipping work without an explicit override.

## Shared/Operational Context

- Product goal: The operator completes the frozen North Star journey from EPUB import through accepted downloadable chapter audio, with explicit control over AI proposals.
- Data operation: READ_ONLY
- Artifact operation: READ_ONLY
- Rollback: revert task-scoped diff and remove new artifacts

## Relevant Decisions

- NONE_LISTED
