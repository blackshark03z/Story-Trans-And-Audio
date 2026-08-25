# Worker Packet

Generated: 2026-08-25T10:15:01+00:00
Capsule Revision: 30

## Task

- ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-G_BROWSER_POLL_STABILITY_V3/r001
- Status: COMPLETED
- Goal: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR / node G_BROWSER_POLL_STABILITY_V3
- Milestone / criterion: M-001 / Five consecutive isolated real-browser assignment journeys pass and preserve the exact polling stability assertions; then the independent full offline review may rerun.
- Risk / profile: R1 / LEAN
- Negative path required: no
- Shipping breaker: ACTIVE (3/3 non-shipping)

## Outcome

Certify and preserve the validated bounded assignment browser polling-race repair without weakening DOM identity, focus, draft, or scroll assertions.

## Goal Context

Repair blockers discovered by the parent baseline Goal, restore a truthful green development baseline, reconcile current Story Audio authority, safely adopt the approved Build OS v1.25 RC4 lineage, and prove the new Work Loop without produc

## Scout Handoff

NONE

## Scope

- Modify: scripts/browser_assignment_flow_smoke.mjs
- Create: NONE
- External calls: NONE
- Pre-existing dirty files: 0 (not part of task unless changed again)
- Current task delta: NONE

## Acceptance

- [ ] Observable outcome exists.
- [ ] Critical negative path is checked when `Negative path required: yes`.
- [ ] Final output and task-scoped diff are inspected.

## Verify

1. Focused check.
2. Negative-path check only when the task has a real failure behavior.
3. Runtime/output and diff inspection.
- Acceptance contract: 8b290c2fb46727240666b59f9d16ccb7f0cd2d2e43eb44b45f568064be453cba (predeclared commands=1, locked probes=0)
- Review policy: none

## Stop

- Stop/change strategy after two failed attempts without new evidence.
- Amend scope instead of widening it silently.
- Final output and task delta must be inspected before acceptance.
- If shipping breaker is ACTIVE, do not start/continue non-shipping work without an explicit override.
