# Worker Packet

Generated: 2026-08-25T09:49:08+00:00
Capsule Revision: 26

## Task

- ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-D_GOLDEN_CERTIFICATION/r001
- Status: COMPLETED
- Goal: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR / node D_GOLDEN_CERTIFICATION
- Milestone / criterion: M-001 / Golden Journey passes entirely in an isolated non-8772 runtime with fake TTS/prepare boundaries, current schema semantics, no canonical artifact assumptions, and before/after non-mutation evidence.
- Risk / profile: R3 / DEEP
- Negative path required: yes
- Shipping breaker: INACTIVE (2/3 non-shipping)

## Outcome

Reconcile Golden Journey with isolated schema-16 representative state and current explicit repair-plan behavior while preserving a read-only canonical non-mutation proof.

## Goal Context

Repair blockers discovered by the parent baseline Goal, restore a truthful green development baseline, reconcile current Story Audio authority, safely adopt the approved Build OS v1.25 RC4 lineage, and prove the new Work Loop without produc

## Scout Handoff

NONE

## Scope

- Modify: tests/test_golden_journey_certification.py,scripts/run_golden_journey_certification.py,scripts/browser_golden_journey_certification.mjs
- Create: NONE
- External calls: Loopback isolated runtime and headless Chromium only.
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
- Acceptance contract: 387fe03930e69562ddf77b941a9e88544978e7b08c0c98e008b7aa1216e3409a (predeclared commands=1, locked probes=0)
- Review policy: required

## Stop

- Stop/change strategy after two failed attempts without new evidence.
- Amend scope instead of widening it silently.
- Final output and task delta must be inspected before acceptance.
- If shipping breaker is ACTIVE, do not start/continue non-shipping work without an explicit override.

## Shared/Operational Context

- Product goal: The operator completes the frozen North Star journey from EPUB import through accepted downloadable chapter audio, with explicit control over AI proposals.
- Data operation: CREATE_NEW_VERSION
- Artifact operation: CREATE_NEW_VERSION
- Rollback: revert task-scoped diff and remove new artifacts

## Relevant Decisions

- NONE_LISTED

## Critical Gates

- Owner authorization: APPROVED / C:\Users\ADMIN\.codex\attachments\b3a8ed2c-bea9-4158-a81e-3054c5b46954\pasted-text-1.txt STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR R3 ceiling and isolated Golden Journey authorization
- Human review required: yes
- Full suite required: yes
- Specialist trigger: UNSET
