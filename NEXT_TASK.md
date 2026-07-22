# Next Task

Task classification:
`SYSTEM_ROADMAP / PHASE_9_PREREQUISITES_AUTHORIZED_ISOLATED_ONLY / RUNTIME_ADAPTER_NOT_AUTHORIZED / CANONICAL_ACTIVATION_NOT_AUTHORIZED / PREPARE_EXECUTION_NOT_AUTHORIZED`

Active milestone:
`DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout`

Exact next task:
`DAILY-PROD-5B Phase 9 - Isolated Same-Transaction PREPARE Prerequisite Resolution`

Checkpoint authority:

- Phase 8 design/model commit: `24087732b8a05d94eaf5a3af2c743602123923e8`.
- Phase 8 verdict: `DAILY_PROD_5B_PHASE_8_COMPLETE`.
- Canonical runtime schema/latest schema: `12 / 12`.
- Canonical database was not mutated; Chapter 369 remains at zero jobs and artifacts.
- Protected untracked paths remain `experiment_b_transcript/` and `runs/`.

Phase 9 purpose:

Resolve and prove the prerequisites that Phase 8 found blocking before any runtime batch PREPARE integration:

1. Add a caller-owned SQLite write transaction and transaction-scoped request, authoritative-input, Job, JobChapter, and linkage seams.
2. Revalidate chapter eligibility, active Text Revision, approved Casting Plan, ownership token, fencing generation, lease, and immutable pins inside that transaction.
3. Resolve overlap conflict races under SQLite writer serialization and prove exactly-one-winner behavior across independent connections/processes.
4. Add or validate durable owner token, monotonic fencing generation, and lease/execution-attempt evidence in dormant/isolated schema work only.
5. Add failure injection, rollback/absence proof, ambiguous-commit recovery, post-commit evidence reload, audit-failure semantics, and evidence-gated APPLIED handoff tests.
6. Preserve legacy single-chapter job behavior and prove no worker wake, provider/TTS, or START_RENDER from prerequisite code.

Allowed scope:

- Temporary or isolated databases only.
- Behavior-preserving transaction seam extraction and pure/isolated tests.
- Dormant migration artifacts after the existing dormant linkage artifact, only when required for isolated proof.
- Read-only canonical safety checks.

Explicitly excluded:

- Active migration registration or canonical schema activation.
- Runtime batch PREPARE adapter/orchestrator wiring.
- PREPARE API/UI execution controls.
- Real production Job/JobChapter creation.
- Worker wake, provider/Gemini/TTS, audio, artifacts, or START_RENDER.
- Chapter 369 production or any mutation of Text Revisions, Casting Plans, voices, `experiment_b_transcript/`, or `runs/`.

Required stop conditions:

- Stop if a proposed change needs canonical DB access, production mutation, provider/TTS work, or runtime execution wiring.
- Stop if a transaction seam changes legacy single-job behavior without a separate approved task.
- Do not claim real adapter readiness until all Phase 8 blockers have isolated evidence and the operator authorizes a separate integration task.

Phase 8 validation reference:

- Focused model tests: `90` PASS.
- Affected suite: `198` PASS.
- Full offline suite: `1447` PASS, `1` skipped.
- Doctor: `critical_errors=0`; canonical DB SHA-256 `dba41f6eb3eaba5de4a4d9964f41ee93bb730ac8c2d6fd47df202479ad203b23`, size `4009984`, mtime unchanged.
