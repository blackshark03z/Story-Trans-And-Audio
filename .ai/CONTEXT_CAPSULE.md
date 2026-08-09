# Worker Packet

Generated: 2026-08-09T05:08:09+00:00
Capsule Revision: 7

## Task

- ID: NONE/r000
- Status: NOT_CREATED
- Goal: NONE / node NONE
- Milestone / criterion: UNSET / SC-001
- Risk / profile: R0 / LEAN
- Negative path required: no
- Shipping breaker: INACTIVE (0/3 non-shipping)

## Outcome

UNSET

## Goal Context

NONE

## Scout Handoff

NONE

## Scope

- Modify: NONE
- Create: NONE
- External calls: NONE
- Pre-existing dirty files: 0 (not part of task unless changed again)
- Current task delta: NONE

## Acceptance

- [ ] Task contract has been initialized.
- [ ] Fingerprint has been verified.
- [ ] Lease has been claimed before writes.

## Verify

1. Verify repository fingerprint.
2. Verify permission matrix.
3. Run risk-adjusted checks after execution.
- Acceptance contract: NONE (predeclared commands=0, locked probes=0)
- Review policy: auto

## Stop

- Stop/change strategy after two failed attempts without new evidence.
- Amend scope instead of widening it silently.
- Final output and task delta must be inspected before acceptance.
- If shipping breaker is ACTIVE, do not start/continue non-shipping work without an explicit override.
