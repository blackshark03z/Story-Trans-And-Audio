# Task Template — LEAN Fast Lane

Task Status: COMPLETED
Task Mode: LEAN
Task ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-H_CHARACTER_VIEWPORT_STABILITY
Task Revision: 1
Created: 2026-08-25
Owner Authorization: NOT_REQUIRED
Authorization Reference: NONE

## Single Outcome

Make 1920x1080 character-assignment viewport evidence wait for post-emulation layout settlement while preserving exact primary-action visibility and horizontal-overflow acceptance.

## Product Link

- Milestone ID: M-001
- Success Criterion: SC-001
- Goal ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR
- Goal Node: H_CHARACTER_VIEWPORT_STABILITY
- Delivery Delta: RISK_RETIREMENT

## Risk and Execution Profile

- Risk At Start: R1
- Risk Tier: R1
- Declared Risk Tier: R1
- Risk Floor: R0
- Risk Floor Reason: none
- Negative path required: no
- Execution Profile: LEAN
- Human review required: no
- Full suite required: no
- Review policy: auto
- Acceptance Contract SHA256: NONE
- Acceptance Contract JSON: {}
- State Hazard Level: S1
- State Hazard Signals: explicit:S1, viewport
- State Contract SHA256: 737ddc8598ef6f7e044acd5b5a8880bcf51215da8f3b75ec47a499e315836aeb
- State Contract JSON: {"schema_version":1,"level":"S1","authority":"","transitions":[],"invariants":[],"dependencies":["scripts/browser_character_assignment_smoke.mjs"],"signals":["explicit:S1","viewport"],"contract_sha256":"737ddc8598ef6f7e044acd5b5a8880bcf51215da8f3b75ec47a499e315836aeb"}

## Continuity Fingerprint at Authorization

- Project ID: story-audio
- Branch: goal/story-audio-baseline-v125
- HEAD: 40edfa20569fa8c37ffda4e5e4d3e21fbd40338e
- Worktree: CLEAN
- Starting Snapshot SHA256: fc301b16f274981393d855e3dfa7378011c0ff21083a17e3e3bc92e63a33ddbd
- Verified Snapshot SHA256: 19572d6373df16ba8a80977e373bd3d37bb3c8cad76b607a7b132777bf4ceff0
- State Revision: 15
- Context Capsule Revision: 30

## Permission Matrix

### Allowed

- Read: browser character assignment harness and UI layout
- Modify: scripts/browser_character_assignment_smoke.mjs
- Create: NONE
- Commands: focused browser test and syntax check
- External calls: NONE
- Data operation: READ_ONLY
- Artifact operation: READ_ONLY

### Prohibited

- Production, destructive, architecture and out-of-scope actions not explicitly listed.

## Acceptance Criteria

- [ ] Five consecutive real-browser character-assignment journeys pass with the primary action fully visible and no horizontal overflow at 1920x1080.

## Verification Plan

1. Focused check.
2. Negative-path check only when the task has a real failure behavior.
3. Runtime/output and diff inspection.

## Before-Execution Preflight

- External/provider calls: NONE
- Files overwritten: NONE
- Data mutated: NONE
- Expected provider cost: 0.0
- Process/port: EPHEMERAL
- Rollback: revert task-scoped harness diff

## Execution Lease

- Lease Status: RELEASED
- Writer Role: WORKER
- Platform: CODEX
- Model Claimed: UNSPECIFIED
- Identity Verification: VERIFIED
- Session Label: character-viewport-stability
- Claimed At: 2026-08-25T10:33:34+00:00
- Last Heartbeat: 2026-08-25T10:36:38+00:00
- Released At: 2026-08-25T10:36:38+00:00

## Lifecycle Timing

- Started At: 2026-08-25T10:33:34+00:00
- First Runnable At: NONE
- First Runnable Evidence: NONE
- Completed At: 2026-08-25T10:36:38+00:00

## Completion

- Outcome: Character-assignment browser evidence now waits for local suggestion completion within the integration budget, records actionable timeout diagnostics, and waits two animation frames after 1920x1080 emulation before enforcing full primary-action visibility and zero horizontal overflow.
- Evidence index: .ai/evidence/STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-H_CHARACTER_VIEWPORT_STABILITY/r001/EVIDENCE_INDEX.md
- Evidence Bundle: .ai/evidence/STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-H_CHARACTER_VIEWPORT_STABILITY/r001
- Worker report: .ai/evidence/STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-H_CHARACTER_VIEWPORT_STABILITY/r001/WORKER_REPORT.md
- Review report: NONE
- Ending HEAD: 40edfa20569fa8c37ffda4e5e4d3e21fbd40338e
- Lease release: RELEASED

## Shipping Breaker Override

- Breaker at start: ACTIVE
- Reason: Mandatory full-suite acceptance is blocked by this single non-shipping harness race; completing it directly unlocks the Goal's frozen baseline criterion.
