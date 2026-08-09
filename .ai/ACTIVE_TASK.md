# Active Task

Task Status: NOT_CREATED
Task Mode: LEAN
Task ID: NONE
Task Revision: 0
Created: YYYY-MM-DD
Owner Authorization: NOT_REQUIRED_FOR_TEMPLATE
Authorization Reference: NONE

## Single Outcome

UNSET

## Product Link

- Milestone ID: UNSET
- Success Criterion: SC-001
- Goal ID: NONE
- Goal Node: NONE
- Delivery Delta: NO_DELTA
- Demonstrable Result: UNSET
- Unlocks: UNSET
- Consecutive Non-Shipping Tasks Before This Task: 0

## Risk and Execution Profile

- Risk At Start: R0
- Risk Tier: R0
- Declared Risk Tier: auto
- Risk Floor: R0
- Risk Floor Reason: none
- Negative path required: no
- Execution Profile: LEAN
- Human review required: no
- Specialist reviewer trigger: NONE
- Full suite required: no
- Review policy: auto
- Acceptance Contract SHA256: NONE
- Acceptance Contract JSON: {}

## Continuity Fingerprint at Authorization

- Project ID: UNSET
- Branch: UNSET
- HEAD: UNSET
- Worktree: CLEAN_OR_UNKNOWN
- Starting Snapshot SHA256: UNSET
- Verified Snapshot SHA256: NONE
- State Revision: 0
- Context Capsule Revision: 0

## Permission Matrix

### Allowed

- Read: repository metadata and task-relevant files
- Modify: NONE
- Create: NONE
- Commands: read-only inspection
- Local services: NONE
- External calls: NONE
- Data operation: READ_ONLY
- Artifact operation: READ_ONLY
- Git: status/diff/log only

### Prohibited

- Application writes before task creation.
- Production mutation, delete, overwrite, deploy, push or merge.

## Acceptance Criteria

- [ ] Task contract has been initialized.
- [ ] Fingerprint has been verified.
- [ ] Lease has been claimed before writes.

## Verification Plan

1. Verify repository fingerprint.
2. Verify permission matrix.
3. Run risk-adjusted checks after execution.

## Before-Execution Preflight

- Inputs: UNSET
- Outputs: UNSET
- Files created: NONE
- Files overwritten: NONE
- Data mutated: NONE
- External/provider calls: NONE
- Expected provider cost: 0
- Disk requirement: MINIMAL
- RAM/GPU requirement: MINIMAL
- Process/port: NONE
- Cache/artifact lineage: NONE
- Rollback: NOT_APPLICABLE

## Cost Efficiency Plan

- Outcome value: UNSET
- Expected cost range: UNSET
- Primary cost drivers: UNSET
- Cheapest evidence-first sequence: fingerprint → focused action → focused evidence → runtime/output check
- Initial execution profile: LEAN
- Escalation conditions: risk or uncertainty exceeds current profile
- Marginal value checkpoint: before repeating any expensive operation
- Continue spending when: next increment buys evidence, lower uncertainty, accepted functionality or required safety verification
- Split/change strategy when: repeated failure/context/operation produces no new evidence
- Quality gates that may not be reduced: acceptance, output inspection, regression, security, authorization, data safety, artifact integrity, rollback, cleanup

## Economic Stop-Loss Conditions

- Same approach failed twice.
- Same test repeated without relevant code/config/input change.
- Full suite repeated without relevant change.
- Provider call repeated without changed input/config.
- Context is being reread without new decisions.
- Reviewer duplicates an existing review.
- Scope expands beyond authorization.
- Two work cycles produce no new evidence.

## Relevant Decisions

- NONE_LISTED

## Execution Lease

- Lease Status: UNCLAIMED
- Writer Role: NONE
- Platform: UNSET
- Model Claimed: UNSPECIFIED
- Identity Verification: NOT_VERIFIED
- Session Label: NONE
- Claimed At: NONE
- Last Heartbeat: NONE
- Released At: NONE
- Takeover From: NONE

## Lifecycle Timing

- Started At: NONE
- First Runnable At: NONE
- First Runnable Evidence: NONE
- Completed At: NONE

## Completion

- Outcome: NONE
- Evidence index: NONE
- Evidence Bundle: NONE
- Worker report: NONE
- Review report: NONE
- Ending HEAD: UNSET
- Lease release: NOT_APPLICABLE
