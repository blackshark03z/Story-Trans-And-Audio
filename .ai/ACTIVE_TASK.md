# Task Template — LEAN Fast Lane

Task Status: COMPLETED
Task Mode: LEAN
Task ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-G_BROWSER_POLL_STABILITY_V3
Task Revision: 1
Created: 2026-08-25
Owner Authorization: NOT_REQUIRED
Authorization Reference: NONE

## Single Outcome

Certify and preserve the validated bounded assignment browser polling-race repair without weakening DOM identity, focus, draft, or scroll assertions.

## Product Link

- Milestone ID: M-001
- Success Criterion: Five consecutive isolated real-browser assignment journeys pass and preserve the exact polling stability assertions; then the independent full offline review may rerun.
- Goal ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR
- Goal Node: G_BROWSER_POLL_STABILITY_V3
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
- Review policy: none
- Acceptance Contract SHA256: 8b290c2fb46727240666b59f9d16ccb7f0cd2d2e43eb44b45f568064be453cba
- Acceptance Contract JSON: {"commands":["D:\\Youtube\\VieNeu-TTS\\.venv\\Scripts\\python.exe -m unittest tests.test_assignment_workflow_browser"],"expected_outputs":["OK"],"probe_files":[],"probe_hashes":{},"effective_risk_at_freeze":"R1","frozen_at":"2026-08-25T10:14:19+00:00","contract_sha256":"8b290c2fb46727240666b59f9d16ccb7f0cd2d2e43eb44b45f568064be453cba"}
- State Hazard Level: S3
- State Hazard Signals: draft, explicit:S3, polling
- State Contract SHA256: 697629749538ce4872b6feb0c293fd2eb1f88968d9484109087288729b03b9ca
- State Contract JSON: {"schema_version":1,"level":"S3","authority":"live assignment DOM plus window.storyAudioAppState","transitions":["settled assignment -> local DIRTY draft -> repeated job polling -> same DOM and DIRTY draft"],"invariants":["deferred background reconciliation never replaces or scrolls an actively edited assignment row"],"dependencies":["ui/app.js","scripts/browser_assignment_flow_smoke.mjs"],"signals":["draft","explicit:S3","polling"],"contract_sha256":"697629749538ce4872b6feb0c293fd2eb1f88968d9484109087288729b03b9ca"}

## Continuity Fingerprint at Authorization

- Project ID: story-audio
- Branch: goal/story-audio-baseline-v125
- HEAD: 801ac72664eb4a8274914b87ab562bd8e9d03968
- Worktree: CLEAN
- Starting Snapshot SHA256: ed1a01441b68fb7bd770a28fd9df2e81ed7d1429e24ba904166239aae19d3fd1
- Verified Snapshot SHA256: 5af5167acf43426b96e245fd1c9a5fdddbe220ec5d0f2ef229132f0322ad479e
- State Revision: 13
- Context Capsule Revision: 28

## Permission Matrix

### Allowed

- Read: task-relevant repository files
- Modify: scripts/browser_assignment_flow_smoke.mjs
- Create: NONE
- Commands: focused checks and task-authorized commands
- External calls: NONE
- Data operation: READ_ONLY
- Artifact operation: READ_ONLY

### Prohibited

- Production, destructive, architecture and out-of-scope actions not explicitly listed.

## Acceptance Criteria

- [ ] Observable outcome exists.
- [ ] Critical negative path is checked when `Negative path required: yes`.
- [ ] Final output and task-scoped diff are inspected.

## Verification Plan

1. Focused check.
2. Negative-path check only when the task has a real failure behavior.
3. Runtime/output and diff inspection.

## Before-Execution Preflight

- External/provider calls: NONE
- Files overwritten: NONE
- Data mutated: NONE
- Expected provider cost: 0.0
- Process/port: NONE
- Rollback: revert task-scoped diff and remove new artifacts

## Execution Lease

- Lease Status: RELEASED
- Writer Role: WORKER
- Platform: CODEX
- Model Claimed: UNSPECIFIED
- Identity Verification: VERIFIED
- Session Label: browser-poll-stability-v3
- Claimed At: 2026-08-25T10:14:19+00:00
- Last Heartbeat: 2026-08-25T10:15:01+00:00
- Released At: 2026-08-25T10:15:01+00:00

## Lifecycle Timing

- Started At: 2026-08-25T10:14:19+00:00
- First Runnable At: NONE
- First Runnable Evidence: NONE
- Completed At: 2026-08-25T10:15:01+00:00

## Completion

- Outcome: Assignment browser polling evidence now waits for the real UI to quiesce, preserves active DOM identity/focus/draft/scroll invariants through repeated loadJobs polling, and atomically exercises injected repair controls without route-refresh races.
- Evidence index: .ai/evidence/STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-G_BROWSER_POLL_STABILITY_V3/r001/EVIDENCE_INDEX.md
- Evidence Bundle: .ai/evidence/STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-G_BROWSER_POLL_STABILITY_V3/r001
- Worker report: .ai/evidence/STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-G_BROWSER_POLL_STABILITY_V3/r001/WORKER_REPORT.md
- Review report: NONE
- Ending HEAD: 801ac72664eb4a8274914b87ab562bd8e9d03968
- Lease release: RELEASED
