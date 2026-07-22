# Continuity Decisions

Updated: 2026-07-22 17:06:00 +07:00

## CONT-001 - Real state outranks checkpoint

Git, runtime, database, artifacts, and test output have higher authority than continuity documentation.

Checkpoint files guide takeover, but they do not replace verifying the real state.

## CONT-002 - Compact checkpoint inside repository

`.ai/PROJECT.md`, `.ai/STATE.md`, and `.ai/DECISIONS.md` are the first-read continuity layer for a new Tech Lead.

Detailed documentation and history remain in the existing canonical documentation.

## CONT-003 - Detailed mutable state lives in external capsule

Session/worker details, command logs, worker identity, and interruption recovery live at:

`D:\Youtube_AI_HANDOFFS\Story Audio`

The external capsule does not control strategic direction and does not outrank Git/runtime.

## CONT-004 - Audio Library uses active artifact binding

Audio Library must get chapter output from:

`chapters.active_audio_artifact_id`

It must not select output by newest Job, highest Job ID, or latest completion time.

## CONT-005 - Runtime QA state is displayed as-is

QA state displayed in Audio Library must come from runtime/API/database.

Historical documentation that records Human QA PASS must not be used to auto-upgrade or repair runtime QA state.

Mismatches must be recorded, not fixed in production data during DAILY-PROD-3A.

## CONT-006 - Audio Library is read-only retrieval

Loading, listing, filtering, playback, and download/open-file must not:

- create jobs;
- create previews;
- call provider/TTS;
- modify QA;
- create or replace active artifacts;
- regenerate audio.

## CONT-007 - Chapter 369 remains outside current task

Chapter 369 is a paused production operation.

DAILY-PROD-3A must not approve a plan, prepare a job, render, or create artifacts for Chapter 369.

## CONT-008 - No schema migration without proof and approval

Do not create a migration for Audio Library if the existing schema/API/helpers are sufficient.

If a migration is genuinely required, stop and ask for a decision first.

## CONT-009 - Batch mutation requires a reviewed read-only plan

`DAILY-PROD-4` is complete with read-only range readiness and exception queue.

`DAILY-PROD-5` may not begin with mutation. It must first define a deterministic batch scope plan, eligibility and exclusion rules, explicit operator confirmation, idempotency, retry, partial-failure, and recovery semantics.

Until that contract exists, do not implement or use batch approval, batch prepare, batch render, batch QA, provider/TTS execution, or any batch mutation endpoint.

## CONT-010 - Batch PREPARE must be isolated from render start

The first batch mutation contract may cover PREPARE only.

It must require:

- deterministic plan fingerprint;
- stale-plan rejection;
- explicit operator confirmation;
- idempotency;
- duplicate-request handling;
- per-chapter results;
- partial-failure semantics;
- retry semantics.

PREPARE must create durable prepared work only.

It must not automatically start synthesis.

START_RENDER, RESUME, and QA mutation require separate bounded tasks and separate review.

## CONT-011 - PREPARE execution requires durable request idempotency

The pure PREPARE contract is complete, but execution remains unauthorized.

Before PREPARE mutation can be implemented, the system must define:

- durable request identity;
- client request ID binding;
- plan fingerprint binding;
- request state transitions;
- duplicate in-progress behavior;
- duplicate completed-result replay;
- retry after ambiguous client timeout;
- atomicity policy;
- per-chapter durable audit/result evidence.

A database transaction alone is not sufficient as the external idempotency contract.

START_RENDER remains separate.

## CONT-012 - Persistence may be implemented before PREPARE execution

The PREPARE idempotency design is complete.

Schema migration and durable request-store implementation may proceed in isolated development and temporary databases.

The implementation must provide:

- unique client request binding;
- canonical request identity;
- state constraints;
- atomic transitions;
- historical result replay;
- stale APPLYING reconciliation evidence;
- bounded versioned result payloads.

This authorization does not permit:

- canonical production migration;
- PREPARE execution endpoint;
- prepare_job invocation;
- Job or JobChapter creation;
- START_RENDER.

## CONT-013 - Schema 13 must pass isolated restart and concurrency acceptance

The dormant schema-13 migration and PREPARE request store are implemented.

Before canonical activation or PREPARE execution can be considered, an isolated production-like database must verify:

- explicit schema-12 to schema-13 migration;
- legacy-data preservation;
- restart persistence;
- historical result replay;
- request uniqueness across concurrent connections;
- atomic transition races;
- stale APPLYING detection;
- migration and store failure recovery.

This authorization applies only to temporary or isolated databases.

Canonical schema activation, PREPARE execution, and START_RENDER remain unauthorized.

## References

- `docs/AI_TECH_LEAD_PROTOCOL.md`
- `docs/DECISIONS.md`
- `docs/DATA_MODEL.md`
- `docs/DAILY_PRODUCTION_WORKFLOW.md`
- `ROADMAP.md`
- `PROJECT_STATUS.md`
- `NEXT_TASK.md`
