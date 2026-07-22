# Next Task

Task classification:
`SYSTEM_ROADMAP / ISOLATED_END_TO_END_ADAPTER_ASSEMBLY_AUTHORIZED / RUNTIME_WIRING_NOT_AUTHORIZED / CANONICAL_ACTIVATION_NOT_AUTHORIZED / PRODUCTION_PREPARE_EXECUTION_NOT_AUTHORIZED / API_INTEGRATION_NOT_AUTHORIZED`

Active milestone:
`DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout`

Exact next task:
`DAILY-PROD-5B Phase 10 - Isolated End-to-End PREPARE Adapter Assembly And Recovery Acceptance`

Checkpoint authority:

- Phase 9 implementation commit: `9d0adf9a72e2d64e3bf3c4e8c6a42e3df813b544`.
- Phase 9 verdict: `DAILY_PROD_5B_PHASE_9_COMPLETE_ISOLATED_ONLY`.
- Dormant schema chain: explicit temporary `12 -> 13 -> 14 -> 15`; canonical/default schema remains `12 / 12`.
- Focused/affected validation: `233` tests PASS; full offline validation: `1481` tests PASS, `1` skipped.
- Canonical DB and Chapter 369 were not mutated.

Operator pain:

The isolated transaction prerequisites now exist, but the orchestrator, owner-fenced transaction service, Job/JobChapter writer, durable linkage, and terminal request-result store have not yet been assembled into one end-to-end temporary-database PREPARE adapter with historical replay and recovery acceptance.

Allowed Phase 10 scope:

1. Assemble the existing isolated modules behind an injected adapter.
2. Use disposable databases with the explicit dormant schema `12 -> 15` chain and synthetic facts only.
3. Call the existing orchestrator with the injected isolated adapter.
4. Create synthetic prepared Jobs and JobChapters only in temporary databases.
5. Persist durable `APPLIED`, `REJECTED`, and `FAILED` request results after evidence-gated transaction outcomes.
6. Prove concurrent duplicate requests, stale plans, owner fencing, response-loss recovery, failure injection, historical replay, and end-to-end process restart.
7. Preserve legacy single-chapter behavior and the explicit START_RENDER separation.

Explicitly excluded:

- Runtime import or pipeline/orchestrator wiring.
- Active migration registration or canonical schema activation.
- Production DB access or real production Job/JobChapter creation.
- API route or UI mutation controls.
- Worker wake, START_RENDER, provider, Gemini, TTS, audio, segments, attempts, or artifacts.
- Chapter 369 production or any protected-path mutation.

Required stop conditions:

- Stop if assembly requires a runtime import, canonical DB access, active migration, API/UI change, production mutation, worker wake, or provider/TTS call.
- Stop if a duplicate/recovery path can create a second Job or if `APPLIED` can be recorded without exact post-commit evidence.
- Stop if ownership fencing, stale-plan rejection, rollback absence proof, or ambiguous-outcome handling fails closed.
