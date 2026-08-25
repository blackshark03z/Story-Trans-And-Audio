# Task Template — STANDARD

Task Status: ABORTED
Task Mode: STANDARD
Task ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125-B_CI_RECONCILIATION
Task Revision: 1
Created: 2026-08-25
Owner Authorization: APPROVED
Authorization Reference: STORY_AUDIO_BASELINE_RECONCILIATION_AND_BUILDOS_V125_ADOPTION owner brief, 2026-08-25

## Single Outcome

Repair the machine-readable Project Contract command encoding and prove CI command resolution and relevant checks.

## Product Link

- Milestone ID: M-001
- Success Criterion: CI install and product-check commands resolve without Markdown delimiter tokens and relevant checks pass.
- Goal ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125
- Goal Node: B_CI_RECONCILIATION
- Delivery Delta: RISK_RETIREMENT
- Demonstrable Result: runtime/output evidence listed in task evidence index
- Unlocks: next ready Goal node
- Consecutive Non-Shipping Tasks Before This Task: 0

## Risk and Execution Profile

- Risk At Start: R2
- Risk Tier: R2
- Declared Risk Tier: R2
- Risk Floor: R0
- Risk Floor Reason: none
- Negative path required: yes
- Execution Profile: STANDARD
- Human review required: trigger-based
- Specialist reviewer trigger: UNSET
- Full suite required: only-if-gate-requires
- Review policy: required
- Acceptance Contract SHA256: 162d59ec8d163c954f2e691d0d4e5a25e8effc4f41d5b93fca892472bfdbf613
- Acceptance Contract JSON: {"commands":["D:\\Youtube\\VieNeu-TTS\\.venv\\Scripts\\python.exe -m unittest tests.test_project_ci_contract -v"],"expected_outputs":["OK"],"probe_files":[],"probe_hashes":{},"effective_risk_at_freeze":"R2","frozen_at":"2026-08-25T07:48:38+00:00","contract_sha256":"162d59ec8d163c954f2e691d0d4e5a25e8effc4f41d5b93fca892472bfdbf613"}
- State Hazard Level: S1
- State Hazard Signals: CI command contract parsing, explicit:S1
- State Contract SHA256: fa90274bf2b4176ed519e4a23ac6e60c5cbb9e55f594a67682464a58cb1d8d85
- State Contract JSON: {"schema_version":1,"level":"S1","authority":"","transitions":[],"invariants":[],"dependencies":[".ai/PROJECT.md","scripts/project_ci.py","tests/test_project_ci_contract.py"],"signals":["CI command contract parsing","explicit:S1"],"contract_sha256":"fa90274bf2b4176ed519e4a23ac6e60c5cbb9e55f594a67682464a58cb1d8d85"}

## Continuity Fingerprint at Authorization

- Project ID: story-audio
- Branch: goal/story-audio-baseline-v125
- HEAD: c9504ddf50c48d1066f3aea4038b63086ffcbf79
- Worktree: CLEAN
- Starting Snapshot SHA256: 861e85b1a25bf9460c39fe53e2e609487a15b9abe8a7fd6d09f98db0efc9f62c
- Verified Snapshot SHA256: NONE
- State Revision: 5
- Context Capsule Revision: 15

## Permission Matrix

### Allowed

- Read: task-relevant repository files
- Modify: .ai/PROJECT.md,scripts/project_ci.py,tests/test_voice_preview_api.py
- Create: tests/test_project_ci_contract.py
- Commands: focused checks and task-authorized commands
- Local services: NONE
- External calls: NONE
- Data operation: READ_ONLY
- Artifact operation: READ_ONLY
- Git: status/diff/log; commit only if explicitly authorized

### Prohibited

- Scope, production, destructive and architecture actions not listed above.

## Acceptance Criteria

- [ ] Project Contract parsing returns raw executable argv for install and test commands.
- [ ] Equivalent install and canonical product-check resolution passes locally.

## Verification Plan

1. Cheapest focused check.
2. Affected runtime/integration check.
3. Inspect final output and Git diff.

## Before-Execution Preflight

- Inputs: task-relevant source and fixtures
- Outputs: accepted outcome and evidence
- Files created: NONE
- Files overwritten: NONE
- Data mutated: NONE
- External/provider calls: NONE
- Expected provider cost: 0.0
- Disk requirement: MINIMAL
- RAM/GPU requirement: MINIMAL
- Process/port: NONE
- Cache/artifact lineage: source inputs and evidence manifest
- Rollback: revert task-scoped diff and remove new artifacts

## Cost Efficiency Plan

- Outcome value: UNSET
- Expected cost range: small; investigate repeated attempts without evidence
- Primary cost drivers: implementation, verification and output inspection
- Cheapest evidence-first sequence: focused → affected regression/runtime → acceptance contract → diff review
- Initial execution profile: STANDARD
- Escalation conditions: risk exceeds profile or same approach fails twice
- Marginal value checkpoint: before repeated expensive operation
- Continue spending when: next spend buys evidence, lower uncertainty, acceptance or safety proof
- Split/change strategy when: same approach fails twice or no new evidence
- Quality gates that may not be reduced: acceptance, safety, authorization, output, regression, rollback, cleanup

## Economic Stop-Loss Conditions

- Same approach failed twice.
- Repeated test/provider/context/review without relevant change.
- Scope expansion or two work cycles without new evidence.

## Relevant Decisions

- NONE_LISTED

## Execution Lease

- Lease Status: RELEASED
- Writer Role: WORKER
- Platform: Codex
- Model Claimed: UNSPECIFIED
- Identity Verification: PENDING
- Session Label: story-audio-baseline-ci
- Claimed At: 2026-08-25T07:48:38+00:00
- Last Heartbeat: 2026-08-25T08:14:17+00:00
- Released At: 2026-08-25T08:45:50+00:00
- Takeover From: NONE

## Lifecycle Timing

- Started At: 2026-08-25T07:48:38+00:00
- First Runnable At: NONE
- First Runnable Evidence: NONE
- Completed At: 2026-08-25T08:45:50+00:00

## Completion

- Outcome: NONE
- Evidence index: NONE
- Evidence Bundle: NONE
- Worker report: NONE
- Review report: NONE
- Ending HEAD: UNSET
- Lease release: PENDING

## Shipping Breaker Override

- Breaker at start: INACTIVE
- Reason: Goal dependency path to accepted shipping node

## Scope Amendments

- 2026-08-25T08:10:07+00:00: Full Product CI exposed an offline-isolation defect: logical-reference preview tests inject the real global TTS service and can download VieNeu model assets. Add only this test file to replace the provider-capable dependency with a deterministic local test double. | modify+=tests/test_voice_preview_api.py | create+=NONE | risk R2->R2
