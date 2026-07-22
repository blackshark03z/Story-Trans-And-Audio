# Batch PREPARE Phase 11 Runtime Rollout Design

## 1. Status And Authorization

Labels: `DESIGN_ONLY`, `NO_RUNTIME_IMPLEMENTATION`, `NO_API_ROUTE`,
`NO_UI_CONTROL`, `NO_CANONICAL_ACTIVATION`, `NO_PRODUCTION_PREPARE`,
`NO_JOB_CREATION`, `NO_WORKER_WAKE`, `START_RENDER_NOT_AUTHORIZED`.

Phase 11 defines pure contracts and rollout evidence only. The current maximum
rollout state is `DESIGN_READY`. Runtime implementation and every production
mutation remain unauthorized.

## 2. Existing Isolated Acceptance

Phase 10 proved replay-first validation, ownership/fencing, authoritative
revalidation, one prepared Job with exact JobChapters and linkage, durable
evidence, recovery, and no render on disposable schema-15 databases. That proof
does not activate schemas 13-15 or make the adapter safe to import at runtime.

## 3. Goals

- Define fail-closed runtime dependency wiring and feature flags.
- Define canonical schema activation, backup, restore, and maintenance evidence.
- Define PREPARE request, response, status, auth, audit, and operator contracts.
- Define rollout, kill-switch, rollback, and production acceptance gates.

## 4. Non-Goals

No route, UI, runtime import, active migration, canonical write, Job creation,
worker wake, provider call, TTS, audio, or START_RENDER is implemented.

## 4A. Current-To-Future Matrix

| Area | Current behavior | Required production design | Risk | Future implementation seam |
| --- | --- | --- | --- | --- |
| Runtime construction | Global API/lifespan dependencies | Explicit default-off construction | Startup side effects | Runtime config/factory |
| Feature flag | No batch PREPARE runtime flag | Fail-closed hierarchy and kill switch | Accidental enablement | FeatureFlagProvider |
| DB startup | Active schema 12 only | Exact schema 15 gate | Dormant auto-activation | CanonicalDatabaseProvider |
| Migration activation | Dormant 13/14/15 files | Explicit hashed allowlist | Partial schema | Dedicated activation tool |
| Backup/restore | General backup facilities | Bound atomic evidence and verified restore | Inconsistent snapshot | Activation runbook/tool |
| Maintenance mode | No PREPARE-specific lock | Reviewer-gated state machine | Concurrent writes | Deployment control plane |
| POST PREPARE API | Absent | Bounded authenticated request | Unauthorized mutation | PrepareApiService |
| Status/recovery API | Absent | Read-only lease-aware status | Hidden mutation/retry | PrepareStatusRecoveryApiService |
| Audit logging | Generic audit sink | Bounded recursive redaction | Secret/path leakage | Reviewed audit adapter |
| Kill switch | No batch switch | Override all mutation flags | Retry/render escape | FeatureFlagProvider |
| Canary rollout | None | Separate 1-3 chapter approval | Scope expansion | Rollout evaluator |
| Rollback | No schema-15 production path | Window-aware restore/reconcile | Durable data loss | Activation/recovery runbook |
| Chapter 369 protection | Draft plan, zero jobs | Generic baseline comparison | Premature Job | Pre/postflight checks |
| START_RENDER separation | Legacy prepared-job start route | Batch linkage and separate authorization | Worker wake | Future start guard |

## 5. Runtime Dependency Graph

Future construction order is:

```text
RuntimeConfig
-> FeatureFlagProvider
-> CanonicalDatabaseProvider
-> PrepareRequestStore
-> ExecutionAttemptStore
-> JobLinkStore
-> TransactionManager
-> TransactionRevalidator
-> PreparedJobWriter
-> ProductionAdapterFacade
-> PrepareApiService
-> PrepareStatusRecoveryApiService
```

Construction must be explicit and side-effect free. No route construction may
initialize or migrate a database. No in-memory fallback is allowed.

## 6. Feature-Flag Hierarchy

Future flags are `PREPARE_FEATURE_AVAILABLE`, `PREPARE_MUTATION_ENABLED`,
`PREPARE_CANONICAL_SCHEMA_READY`, `PREPARE_OPERATOR_WINDOW_OPEN`, and
`PREPARE_KILL_SWITCH_ACTIVE`. Missing or invalid enable flags are false. Missing
or invalid kill-switch state is active. Mutation requires every positive gate,
schema 15, explicit canonical identity, and production-ready authentication.
Read-only planning and status remain available. START_RENDER is independent.

## 7. Runtime Startup Behavior

Current runtime builds global dependencies in `story_audio/api.py`, initializes
the database and starts the worker in lifespan. Future PREPARE wiring must not be
added to global import-time construction. Disabled startup must not construct a
mutation service. Schema below or above 15 fails closed. Existing read-only plan
endpoints remain usable, and the worker continues to exclude `prepared` jobs.

## 8. Canonical Migration Preflight

Preflight requires process inventory, stopped mutation-capable processes,
maintenance `ACTIVE`, exact canonical identity, schema 12, `quick_check=ok`, no
write transaction, hash/size/mtime evidence, consistent SQLite backup evidence,
free-space proof, reviewed hashes for explicit migrations 13/14/15, rollback
artifact, disabled flags, operator approval, protected baseline verification,
zero active PREPARE requests, and a deployment correlation ID.

## 9. Backup Evidence

Evidence records source identity/schema/hash/size/mtime/quick-check, backup
identity/schema/hash/size/quick-check, atomic-snapshot verification, timestamp,
operator reference, correlation ID, WAL/SHM policy, and retention reference. The
preflight binds this exact evidence to its source and backup identities. Use SQLite
backup API while all mutation processes are stopped; never copy a changing database
and sidecars independently.

## 10. Migration Sequence

The only future sequence is schema `12 -> 13 -> 14 -> 15`, using one dedicated,
reviewed activation tool with an explicit migration allowlist and expected hashes.
Each stage runs as a separately verified atomic transaction so evidence identifies
the last committed schema before a failure; no later stage begins before checks pass.
Do not promote dormant files into normal startup discovery. Verify each stage and
its reviewed hash, then stop on failure. Failure at 13, 14, or 15 remains locked
and requires full verified restore; an intermediate schema is never runnable.
Feature flags stay off and no Job/request row is created.

## 11. Postflight

Require final schema 15, exact applied chain, required tables/indexes/FKs,
preserved legacy counts, zero new Job/request rows, disabled feature flags,
`quick_check=ok`, protected baseline unchanged, and disabled-runtime startup/read
smoke. Any missing evidence produces `ROLLBACK_REQUIRED`.

## 12. Restore And Rollback

During the schema-activation maintenance window, rollback is full-file restore
from a verified backup, not SQL down-migrations. Keep runtime stopped, archive the
failed DB, restore atomically with WAL/SHM handled, verify expected hash/schema/
quick-check and read-only startup, record the incident, require reviewer approval,
and keep PREPARE disabled. After activation has accepted new durable state, never
overwrite it with the pre-activation backup: activate the kill switch, preserve
the database, reconcile explicitly, and obtain separate recovery authorization.

## 13. Maintenance Mode

States are `ENTERING`, `ACTIVE`, `MIGRATING`, `VERIFYING`, `FAILED_LOCKED`,
`EXIT_READY`, and `EXITED`. Unknown or invalid transitions enter
`FAILED_LOCKED`. Exit is impossible without verified postflight. Maintenance
blocks canonical writes, worker mutation, PREPARE, and render start. `EXITED`
requires a reviewer-approved evidence package after verified postflight or restore.

## 14. PREPARE API Request

Future candidate: `POST /api/production/prepare`. Required fields are bounded
`client_request_id`, positive `book_id`, ordered chapter range, exact
`target_phase=PREPARE`, SHA-256 plan fingerprint, and literal boolean
`confirmation=true`; a bounded correlation ID is optional. Reject eligibility
lists, Job fields, owner/fence fields, prepared results, render/start fields,
unknown fields, malformed JSON, and bodies over 16 KiB. The server recomputes the
plan and never trusts a UI-provided eligibility list.

## 15. PREPARE API Response

Safe states map explicitly: APPLIED 200; PLANNED/APPLYING 202; conflict/stale or
operator review 409; rejected 422; closed operator window 423; disabled, killed,
schema-not-ready, or recovery-required 503; internal failed 500. Responses use an
allowlist of IDs, scope, fingerprint, replay, action, error code, and correlation.
They always report mutation/execution/render authorization false until separately
authorized. Tokens, hashes of tokens, paths, SQL, traceback, text, plan blobs,
provider details, and credentials are forbidden.

## 16. Status And Recovery API

Future candidate: `GET /api/production/prepare-status` by bounded
`client_request_id`. It replays terminal history and classifies active owner,
expired owner, committed evidence, ambiguity, corruption, and unknown request.
It never acquires ownership, runs a transaction, creates a Job, resets state,
auto-retries, or starts render. Active ownership requires durable lease evidence;
responses expose only bounded retry guidance and callers stop after a bounded
polling interval before a fresh status read. Any recovery mutation requires a
later explicit operator contract and authorization.

## 17. Authentication And Authorization

Current classification is `AUTH_MISSING_BLOCKS_PRODUCTION`: the local FastAPI
runtime has no reusable operator authentication, role, CSRF, or origin-bound
production authorization boundary. Local-only binding is not sufficient.
Production needs explicit operator identity/role, credentials outside URLs,
origin and CSRF controls for browser use, audit identity, and no credential logs.
This blocks enabled production PREPARE, not clone rehearsal or unreachable
default-off skeleton design.

## 18. Operator Confirmation

An authenticated operator reads the current plan, inspects included/excluded rows,
confirms exact scope and fingerprint, and submits literal confirmation with a
server-bound identity, correlation ID, and CSRF/origin proof. The server recomputes
and rejects stale input. General design maximum is 256 chapters; initial canary
maximum is one book and one to three chapters. PREPARE never offers START_RENDER.

## 19. Chapter 369 Protection

The runbook records Chapter 369 baseline: Text Revision 738, Casting Plan 24 rev 1
draft/unapproved, zero Jobs, zero Artifacts, audio `not_created`. Domain logic must
use generic readiness/unapproved-plan safeguards, never a hard-coded chapter
branch. Clone/canonical preflight and postflight compare this baseline; any change
is an incident and rollback trigger.

## 20. Audit Events

The pure contract defines a bounded PREPARE request/replay/conflict/stale/owner/
commit/APPLIED/recovery/failure/disabled/kill-switch/migration/rollback taxonomy.
Safe fields are versioned timestamps, correlation/request identities, book/range,
fingerprint, state/result, replay, operator reference, flag state, and schema.
Validation and redaction recurse through nested containers and reject unbounded
values, credential variants, absolute/UNC paths, SQL, and tracebacks.
The existing generic `audit_events` table is not yet accepted as the production
audit sink; persistence/retention and transaction semantics need Phase 12+ review.

## 21. Logging And Redaction

Use structured, error-code-first, bounded logs. Separate public errors from
internal diagnostics. Never dump request bodies or result payloads. Reject or
redact token material, credentials, absolute paths, SQL, tracebacks, text, and
plan blobs. Preserve safe correlation fields for incident lookup.

## 22. Kill Switch

Unknown state means active. It immediately blocks new PREPARE mutations and
automatic retries while preserving read-only planning/status, existing requests,
and prepared Jobs. It never starts render. Duplicate Jobs, hash/schema anomalies,
corrupt evidence, recovery ambiguity, worker pickup, protected baseline change,
failure threshold, auth incident, or mandatory-audit failure recommends activation.

## 23. Rollout Stages

1. `DISABLED`: schema 12, read-only planning.
2. `DESIGN_READY`: current Phase 11 maximum.
3. `MIGRATION_REHEARSAL_READY`: verified clone migration and restore rehearsal.
4. `CANONICAL_SCHEMA_READY_BUT_DISABLED`: later maintenance activation only.
5. `CANARY_ENABLED`: separate authorization, one to three chapters, no render.
6. `LIMITED_ENABLED`: requires a separate limited-rollout authorization.
7. `GENERAL_ENABLED`: requires a separate general-rollout authorization.

`KILL_SWITCHED` and `ROLLBACK_REQUIRED` are fail-closed terminal interventions.
Stages cannot be skipped.

## 24. Canary Policy

Canary requires separate approval, production-ready authentication, schema 15,
verified backup/postflight, operator window, disabled START_RENDER, inactive kill
switch, no overlap, approved casting, and generic readiness. Chapter 369 remains
excluded by current readiness and protected-baseline policy. Phase 11 authorizes
no canary execution, and later stages cannot inherit canary authorization.

## 25. START_RENDER Boundary

The existing legacy `POST /api/jobs/{job_id}/start` route can start a prepared Job
without proving future batch-request linkage. It is therefore unsafe for batch
PREPARE rollout. Future runtime wiring must distinguish batch-linked Jobs and
require separate authenticated start authorization before any transition or
worker wake. Phase 11 changes neither the route nor worker behavior.

## 26. Production Acceptance Matrix

Gates include runtime/auth review, default-off and kill-switch tests, clone
migration/restore rehearsal, verified backup/maintenance, canonical dry-run
evidence, API idempotency/status/recovery/audit/redaction, no-worker/no-render,
concurrency/restart/recovery, Chapter 369 unchanged, full tests, Doctor, operator
signoff, and separate canonical plus production mutation authorizations.

## 27. Phase 12 Implementation Prerequisites

Phase 12 may rehearse migration/rollback on a verified external clone and create
an unreachable default-off wiring skeleton only. It must prove source DB read-only,
clone provenance, exact 12->15 migration, preserved data, hash-restoring rollback,
disabled service construction, no route, no Job, and canonical schema still 12.

## 28. Open Risks

- Production operator authentication/CSRF/origin policy is absent.
- Production audit sink, retention, and atomicity are not approved.
- Maintenance/process exclusion has not been implemented or rehearsed.
- Dormant migration hashes and explicit activation tool do not yet exist.
- Clone handling and rollback have not been proven against canonical-shaped data.
- The legacy start route lacks a batch-linkage authorization guard.

## 29. Authorization Gates

Phase 11 completion may authorize only clone migration rehearsal and a disabled,
unreachable runtime wiring skeleton. Canonical activation, enabled PREPARE API,
production PREPARE, UI mutation, worker wake, provider/TTS, and START_RENDER remain
unauthorized.
