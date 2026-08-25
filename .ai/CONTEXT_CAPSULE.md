# Worker Packet

Generated: 2026-08-25T10:36:38+00:00
Capsule Revision: 32

## Task

- ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-H_CHARACTER_VIEWPORT_STABILITY/r001
- Status: COMPLETED
- Goal: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR / node H_CHARACTER_VIEWPORT_STABILITY
- Milestone / criterion: M-001 / SC-001
- Risk / profile: R1 / LEAN
- Negative path required: no
- Shipping breaker: ACTIVE (4/3 non-shipping)

## Outcome

Make 1920x1080 character-assignment viewport evidence wait for post-emulation layout settlement while preserving exact primary-action visibility and horizontal-overflow acceptance.

## Goal Context

Repair blockers discovered by the parent baseline Goal, restore a truthful green development baseline, reconcile current Story Audio authority, safely adopt the approved Build OS v1.25 RC4 lineage, and prove the new Work Loop without produc

## Scout Handoff

NONE

## Scope

- Modify: scripts/browser_character_assignment_smoke.mjs
- Create: NONE
- External calls: NONE
- Pre-existing dirty files: 0 (not part of task unless changed again)
- Current task delta: NONE

## Acceptance

- [ ] Five consecutive real-browser character-assignment journeys pass with the primary action fully visible and no horizontal overflow at 1920x1080.

## Verify

1. Focused check.
2. Negative-path check only when the task has a real failure behavior.
3. Runtime/output and diff inspection.
- Acceptance contract: NONE (predeclared commands=0, locked probes=0)
- Review policy: auto

## Stop

- Stop/change strategy after two failed attempts without new evidence.
- Amend scope instead of widening it silently.
- Final output and task delta must be inspected before acceptance.
- If shipping breaker is ACTIVE, do not start/continue non-shipping work without an explicit override.
