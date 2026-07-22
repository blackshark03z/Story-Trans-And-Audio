# Next Task

Task classification:
`SYSTEM_ROADMAP / RUNTIME_PREPARE_WIRING_DESIGN_AUTHORIZED / RUNTIME_IMPLEMENTATION_NOT_AUTHORIZED / CANONICAL_ACTIVATION_NOT_AUTHORIZED / PRODUCTION_PREPARE_EXECUTION_NOT_AUTHORIZED / START_RENDER_NOT_AUTHORIZED`

Active milestone:
`DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout`

Exact next task:
`DAILY-PROD-5B Phase 11 — Runtime PREPARE Wiring, Canonical Activation, And Operator Rollout Design Contract`

Operator pain:

The isolated PREPARE adapter has passed end-to-end transaction, replay, fencing, concurrency and recovery acceptance, but production runtime wiring, canonical migration rollout, operator controls, audit visibility and rollback procedures have not been reviewed as one deployment boundary.

Allowed Phase 11 scope:

- Inspect runtime API/startup/service conventions.
- Design runtime adapter dependency wiring.
- Design canonical schema 12 -> 15 activation sequence.
- Design backup, hash verification, and rollback procedure.
- Design preflight and maintenance-mode requirements.
- Design API request/status contract and idempotency fields.
- Design operator confirmation boundary and audit/redaction.
- Design rollout feature flag, recovery flow, and kill switch.
- Design Chapter 369 protection and production acceptance plan.
- Pure contracts, model tests, and documentation only.

Excluded:

- Active migration or canonical DB mutation.
- Production API route or UI mutation control.
- Actual PREPARE execution or Job/JobChapter creation.
- Worker wake, START_RENDER, provider, Gemini, or TTS.
- Chapter 369 production action.

Acceptance criteria:

1. Runtime dependency graph is explicit.
2. No import-time migration or mutation.
3. Canonical migration sequence is explicit.
4. Backup, hash, and rollback procedure is explicit.
5. Maintenance-mode requirement is explicit.
6. API idempotency and confirmation fields are explicit.
7. Status and recovery endpoint behavior is explicit.
8. Authorization and feature flag default off.
9. Logs redact owner tokens and sensitive paths.
10. Operator can kill or disable PREPARE without affecting read-only planning.
11. START_RENDER remains separate.
12. No runtime implementation occurs.
