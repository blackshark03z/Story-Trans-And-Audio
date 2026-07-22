# Batch PREPARE Canonical Activation Runbook Design

This document is `DESIGN_ONLY`. Canonical activation remains unauthorized.

## Prerequisites

Approved change window, reviewed explicit migration hashes for 13/14/15, verified
backup capacity, tested restore artifact, disabled feature flags, production-ready
operator auth, and separate canonical activation authorization are mandatory.

## Personnel And Roles

One operator executes, one reviewer verifies evidence, and one rollback owner is
available. All actions share a deployment correlation ID; credentials are never
stored in evidence or command history.

## Maintenance Entry

Inventory API/worker/script processes and port ownership, stop mutation-capable
processes, detect stale instances, enter `ENTERING -> ACTIVE`, and prove no active
write transaction. Unknown state becomes `FAILED_LOCKED`.

## Preflight

Verify canonical identity, schema exactly 12, `quick_check=ok`, DB hash/size/mtime,
WAL/SHM strategy, disk space, explicit migration list and hashes, feature flags
off, zero active PREPARE requests, operator approval, and protected baseline.

## Backup

Use SQLite backup API with mutation processes stopped. Record source and backup
identity/schema/hash/size/quick-check, atomic snapshot proof, timestamp, operator/
correlation, sidecar policy, and retention reference. Bind that evidence to the
preflight and verify the backup opens read-only before proceeding.

## Clone Rehearsal Evidence

Before canonical work, a separately authorized rehearsal must prove canonical
source read-only, matching clone provenance, exact 12->15 activation, preserved
legacy facts, required schema objects, and full restore back to original clone
hash/schema. Phase 11 performs no rehearsal.

## Activation Sequence

A future dedicated activation tool uses a non-recursive explicit allowlist:
`0013_batch_prepare_requests.sql`, `0014_batch_prepare_job_links.sql`, then
`0015_batch_prepare_execution_attempts.sql`. Verify each stage and its reviewed
hash. Run each stage as a separately verified atomic transaction and do not begin
the next stage until the committed schema is confirmed. Failure at any target,
including a partial schema 13 or 14 state, remains
`FAILED_LOCKED` and requires verified full restore. Do not move files into normal
migration discovery or auto-run from application startup.

## Postflight

Require schema 15, exact migration records/checksums, required tables/indexes/FKs,
unchanged legacy counts and protected baseline, zero new Job/request rows,
`quick_check=ok`, feature flags off, and disabled-runtime read-only smoke.

## Failure Handling

Any exception, stage mismatch, integrity failure, missing schema object, count
change, protected-state change, startup failure, or flag anomaly enters
`FAILED_LOCKED`, activates the kill switch, and starts incident handling.

## Restore

Within the schema-activation window, keep runtime stopped, archive the failed DB,
atomically restore the verified full database backup, handle WAL/SHM consistently,
and verify original hash/schema/quick-check plus read-only startup. Record the
incident and require reviewer approval. Do not use SQL down-migrations. Keep
PREPARE disabled after restore. After activation has accepted new durable state,
do not apply the old full backup; kill-switch, preserve, and reconcile instead.

## Maintenance Exit

Only verified postflight or verified restore may enter `EXIT_READY`. A reviewer
checks the evidence package before `EXITED`. Failure cannot be overridden by a
normal operator action.

## Kill Switch

Unknown switch state is active. It blocks PREPARE mutation and retry but preserves
read-only planning/status and durable existing state. START_RENDER is independent
and remains unauthorized. The legacy Job start route is not accepted for future
batch-linked Jobs until a separate linkage and authorization guard exists.

## Evidence Package

Include process inventory, correlation/operator references, pre/post hashes and
counts, schema/checksum records, backup verification, maintenance transitions,
postflight results, protected baseline comparison, flag state, and incident links.
Exclude secrets, raw tokens, SQL, tracebacks, and sensitive absolute destinations.

## Incident Triggers

Duplicate Jobs, hash/schema anomalies, corrupt request/link/attempt state,
ambiguous recovery, unexpected worker pickup, Chapter 369 baseline change,
authentication incident, audit failure, or elevated PREPARE failure rate require
kill switch and rollback assessment.

## Authorization Boundary

This runbook does not authorize canonical migration, PREPARE route enablement,
production Job creation, UI controls, worker wake, provider/TTS, or START_RENDER.
