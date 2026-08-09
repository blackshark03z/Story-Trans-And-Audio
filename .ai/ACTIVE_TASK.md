# Task Template — DEEP

Task Status: ACTIVE
Task Mode: DEEP
Task ID: STORY_AUDIO_PRODUCT_GOAL_R3-BOOK_SCOPED_CUSTOM_VOICE
Task Revision: 1
Created: 2026-08-09
Owner Authorization: APPROVED
Authorization Reference: OWNER AUTHORIZATION — RECOVER BUILD OS GOVERNANCE DEADLOCK AND COMPLETE BOOK-SCOPED VOICE, 2026-08-09

## Single Outcome

ADD CUSTOM VOICE TO SELECTED BOOK

## Product Link

- Milestone ID: M-001
- Success Criterion: A normal user can add a sample-backed custom voice to one Book, it persists on reload, resolves in that Book runtime context, and cannot be seen or resolved by another Book.
- Goal ID: STORY_AUDIO_PRODUCT_GOAL_R3
- Goal Node: BOOK_SCOPED_CUSTOM_VOICE
- Delivery Delta: USER_VISIBLE_BEHAVIOR
- Demonstrable Result: runtime/output evidence listed in task evidence index
- Unlocks: next ready Goal node
- Consecutive Non-Shipping Tasks Before This Task: 0

## Risk and Execution Profile

- Risk At Start: R3
- Risk Tier: R3
- Declared Risk Tier: R3
- Risk Floor: R3
- Risk Floor Reason: R2:persistent data version creation; R3:migration/deployment/production/payment surface
- Negative path required: yes
- Execution Profile: DEEP
- Human review required: yes
- Specialist reviewer trigger: security/data/operations
- Full suite required: yes
- Review policy: required
- Acceptance Contract SHA256: 51ceff3bb4cd32181c629ce84d4eb5d2eeeef5fb85dc3724962f2eda77493f3e
- Acceptance Contract JSON: {"commands":["D:\\Youtube\\VieNeu-TTS\\.venv\\Scripts\\python.exe -m unittest tests.test_book_scoped_custom_voices tests.test_custom_voice_api tests.test_custom_voice tests.test_voice_catalog tests.test_assignment_workflow_browser"],"expected_outputs":["OK"],"probe_files":[],"probe_hashes":{},"effective_risk_at_freeze":"R3","frozen_at":"2026-08-09T08:14:08+00:00","contract_sha256":"51ceff3bb4cd32181c629ce84d4eb5d2eeeef5fb85dc3724962f2eda77493f3e"}
- State Hazard Level: S2
- State Hazard Signals: explicit:S2, voice creation and book-scoped catalog reload
- State Contract SHA256: 488010ed0306ec024feb2f41e495e25227cfc6676a087e7e02a42d4df36c5ec1
- State Contract JSON: {"schema_version":1,"level":"S2","authority":"custom_voices.book_id and custom_voice_revisions","transitions":["Book A add voice -> save -> reload -> Book A visible, Book B absent"],"invariants":["A normal custom voice has exactly one owning book; legacy references remain resolvable."],"dependencies":["story_audio/custom_voice.py,story_audio/custom_voice_api.py,story_audio/api.py,story_audio/voice_ref.py,story_audio/pipeline.py,ui/index.html,ui/app.js,story_audio/migrations/*.sql"],"signals":["explicit:S2","voice creation and book-scoped catalog reload"],"contract_sha256":"488010ed0306ec024feb2f41e495e25227cfc6676a087e7e02a42d4df36c5ec1"}

## Continuity Fingerprint at Authorization

- Project ID: story-audio
- Branch: main
- HEAD: 46d74ce59ce87ad03438bb9ffcc720e06a632f15
- Worktree: CLEAN
- Starting Snapshot SHA256: 031315d182020b7127cd6f719c11097e956eabb2e8763845e7feedb3283cae73
- Verified Snapshot SHA256: NONE
- State Revision: 3
- Context Capsule Revision: 10

## Permission Matrix

### Allowed

- Read: task-relevant repository files
- Modify: story_audio/custom_voice.py,story_audio/custom_voice_api.py,story_audio/api.py,story_audio/voice_eligibility.py,story_audio/voice_ref.py,story_audio/pipeline.py,story_audio/migrations/__init__.py,ui/index.html,ui/app.js,tests/**,story_audio/backup.py,story_audio/integrity.py,story_audio/batch_prepare_clone_api.py,story_audio/batch_prepare_isolated_adapter.py
- Create: story_audio/migrations/0016_book_scoped_custom_voices.sql,tests/test_book_scoped_custom_voices.py,scripts/browser_book_custom_voice_acceptance.mjs
- Commands: focused checks and task-authorized commands
- Local services: NONE
- External calls: NONE
- Data operation: CREATE_NEW_VERSION
- Artifact operation: CREATE_NEW_VERSION
- Git: status/diff/log; commit only if explicitly authorized

### Prohibited

- Scope, production, destructive and architecture actions not listed above.

## Acceptance Criteria

- [ ] Browser Book A: add a named sample-backed voice, save, and see it after reload.
- [ ] Book B excludes the Book A voice in UI/API/runtime resolution while legacy NULL voices remain compatible.
- [ ] PipelineWorker cannot reuse Book A custom-voice context for Book B or reverse order.
- [ ] Browser acceptance fails closed before mutation for canonical runtime or missing isolation marker.
- [ ] No provider/render/QA action and canonical Jobs, JobChapters, Artifacts, casting, and Chapter 369 remain unchanged.

## Verification Plan

1. Cheapest focused check.
2. Critical negative path.
3. Affected runtime/integration check.
4. Rollback rehearsal/proof that leaves final state intact.
5. Full/critical suite as required.
6. Inspect final output and task delta; independent review for R3.

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
- Initial execution profile: DEEP
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

- Lease Status: CLAIMED
- Writer Role: WORKER
- Platform: ChatGPT
- Model Claimed: UNSPECIFIED
- Identity Verification: VERIFIED
- Session Label: product-task-1-book-custom-voice-r3
- Claimed At: 2026-08-09T08:27:54+00:00
- Last Heartbeat: 2026-08-09T08:27:54+00:00
- Released At: 2026-08-09T08:24:00+00:00
- Takeover From: NONE

## Lifecycle Timing

- Started At: 2026-08-09T08:14:09+00:00
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
- Lease release: PENDING

## Replacement Contract

- STORY_AUDIO_PRODUCT_GOAL-BOOK_SCOPED_CUSTOM_VOICE

## Revision Stop-Loss Acknowledgement

- Prior failed-first-pass revisions: 0
- Changed root-cause hypothesis: Preserved implementation is stashed; remediate Guardian P1 only, then independently review before canonical migration.

## Scope Amendments

- 2026-08-09T08:27:48+00:00: Close Guardian P1 only: schema-16 backup/integrity compatibility and book-scoped custom voice propagation through the two real PREPARE paths. | modify+=story_audio/backup.py,story_audio/integrity.py,story_audio/batch_prepare_clone_api.py,story_audio/batch_prepare_isolated_adapter.py | create+=NONE | risk R3->R3
