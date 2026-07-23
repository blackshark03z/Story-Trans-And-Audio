# Next Task

Task classification:
`SYSTEM_ROADMAP / CLONE_ONLY_AUTHENTICATED_PREPARE_API_AUTHORIZED / CLONE_ONLY_PREPARE_MUTATION_TESTING_AUTHORIZED / CANONICAL_ACTIVATION_NOT_AUTHORIZED / PRODUCTION_PREPARE_NOT_AUTHORIZED / UI_PREPARE_NOT_AUTHORIZED / START_RENDER_NOT_AUTHORIZED`

Active milestone:
`DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout`

Exact next task:
`DAILY-PROD-5B Phase 14 - Clone-Only Authenticated PREPARE API And Kill-Switch Acceptance`

## Phase 13 Closeout

Implementation commit `a60b94c` added clone-only disabled runtime integration,
an immutable read-only schema-15 DB facade, GET-only readiness, and a redacted
single-operator Bearer/SHA-256 authentication boundary. Startup and restart
preserved exact clone bytes and read-only planning; the full offline suite passed
`1608` tests with `1` skip and Doctor reported `critical_errors=0`. Canonical
schema remained 12 and Chapter 369 remained unchanged.

## Authorized Scope

- Use only an external schema-15 clone and a separate authenticated test process.
- Add a batch PREPARE mutation API behind all flags, kill switch, operator window,
  schema readiness, synthetic authentication, literal confirmation, idempotency
  key, and plan fingerprint.
- Reuse the isolated adapter against the clone only.
- Test request/status/recovery, response loss, restart, concurrency, and redaction.
- Keep the route disabled by default and create no worker wake or render start.

## Excluded

- Canonical migration or production runtime activation.
- Real production credentials, PREPARE, Job/JobChapter creation, or Chapter 369 mutation.
- UI PREPARE controls, worker wake, START_RENDER, provider, Gemini, or TTS.
- Push and `DAILY-PROD-6` advancement.

Do not begin Phase 14 in the same task as this documentation closeout.
