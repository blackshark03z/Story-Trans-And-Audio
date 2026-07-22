# Roadmap

Roadmap mo ta thu tu uu tien, khong phai cam ket thoi gian. Uu tien theo: bao ve du lieu -> kha nang phuc hoi -> chat luong audio -> tinh nang moi.

## Completed

- Audio MVP: EPUB, immutable TextRevision, Gemini punctuation repair, VieNeu segment checkpoint va chapter audio.
- Manual/multi-voice casting voi immutable CastingPlan va resolved job snapshot.
- Text Revision Diff va Shared Gemini repair cache.
- Schema/backup/recovery/diagnostic hardening.
- Story Audio -> YouTube Auto Handoff V1.
- Three-Voice Profile Core va UI integration.
- Book-level Character Bible Import Core, UI va Handoff integration.
- Gemini Speaker Assignment Draft Core.
- Speaker Assignment Review and Approval UI.
- Long-Chapter End-to-End Validation and Hardening.
- Custom Reference Voice Library UI.
- Custom Voice Backend Resolution & Snapshot Support.
- Task 10 Long Chapter Production Pilot.
- Task 11B1 Guarded Production Runner: isolated-root production runner, read-only runtime identity endpoint, exact Casting Plan endpoint, Unicode-safe submit path, duplicate protection, immutable binding verification, structured CLI errors, and 759/759 offline tests passing.
- Task 11B2 Production Runner Monitoring + Manifest: exact existing/new job selection, structured watch progress, controlled same-job resume, completed-job terminal validation, final manifest schema `story-audio-production-manifest/v1`, disposable completed-job smoke, and 774/774 offline tests passing.
- Task 11C1 Objective Audio QA Reporting: offline manifest-driven QA JSON, FFmpeg/PCM clipping/loudness/silence/duration metrics, deterministic risk shortlist, byte-identical reuse smoke on Chapter 629, and 814/814 offline tests passing.
- Task 11C2 Deterministic Listening Checklist HTML: offline listening checklist package, localStorage-scoped review state, browser-only review JSON export, deterministic queue coverage, Chapter 629 disposable smoke, and 835/835 offline tests passing.
- Task 11D1 Unified Production Workflow: guarded operator entry point composing preflight, explicit submit/resume, completed-job downstream reuse, production manifest, objective QA, deterministic listening checklist, disposable Chapter 629 smoke, and 855/855 offline tests passing.
- Task 11D2 First Production Acceptance Run: Chapter 357 isolated acceptance passed with approved Casting Plan #6, Job #2 completed, production manifest, objective QA, deterministic listening checklist, and human full-chapter listening PASS.
- Task 11D3C Production-Go Decision: final readiness re-audit recorded `PRODUCTION_GO`; a second acceptance chapter is not required for rollout.
- Production validation evidence: Chapters 364-368 completed routine production with Human QA PASS and active artifacts 69, 72, 78, 75, and 84.
- Reusable hardening after production blockers: runtime identity/active-output clarity, separated speaker-review workflow, prepared-job lifecycle, targeted text correction workflow, repair-block workflow, and custom voice preview provenance fail-closed guard.
- DAILY-PROD-1 - Modular Navigation And Sequential Production Shell: complete.
- DAILY-PROD-2 - Custom Voice Assignment UI Closure: complete.
- DAILY-PROD-3 - Audio Library And Output Retrieval: complete. `DAILY-PROD-3A` added read-only `GET /api/audio-library`, active-artifact semantics, runtime QA labels, safe playback/download, loading/error/empty/refresh states, and browser/runtime validation.
- DAILY-PROD-4 - Range Readiness And Exception Queue: complete. `DAILY-PROD-4A` added read-only `GET /api/production/range-readiness`, active-output and QA semantics, deterministic workflow precedence, summary counts, ordered chapter list, exception queue, safe single-chapter navigation, and runtime/browser validation with no production mutation.
- DAILY-PROD-5A - Batch Scope Plan And Mutation Safety Contract: complete. Added read-only `GET /api/production/batch-plan`, deterministic target-phase planning and fingerprints, included/excluded rows, reason codes, safety contract, authorization `MUTATION_NOT_AUTHORIZED`, unavailable execution endpoint, read-only UI review, stale-response protection, and runtime/browser validation with no production mutation.
- DAILY-PROD-5B Phase 1 - Pure PREPARE Mutation Safety Contract: complete. Added a pure PREPARE-only contract with required plan fingerprint, stale-plan rejection, exact boolean confirmation, current-plan authority, deterministic planned intent, no-eligible safe result, honest safety statuses, and no execution endpoint or production mutation.
- DAILY-PROD-5B Phase 2 - PREPARE Idempotency Persistence Design: complete. Defined durable `client_request_id`, canonical request identity, payload binding, explicit request state machine, duplicate/timeout replay, Option A atomicity, stale APPLYING reconciliation, fingerprint race guard, one request/one Job, bounded historical result replay, retention, and proposed schema 13 `batch_prepare_requests`; no migration or execution endpoint was implemented.
- DAILY-PROD-5B Phase 3 - Dormant PREPARE Request Persistence: complete. Added dormant schema-13 migration artifact `story_audio/migrations/dormant/0013_batch_prepare_requests.sql` and durable request store `story_audio/batch_prepare_store.py` with create-or-replay, payload conflict detection, SQLite uniqueness, guarded transitions, historical result replay, stale APPLYING lookup, bounded result payloads, no auto-migration, no execution integration, canonical/default schema `12 / 12`, and full offline validation.
- DAILY-PROD-5B Phase 4 - Isolated Schema 13 Persistence Acceptance: complete. Temporary schema-12 production-like fixtures explicitly activate dormant schema 13 and validate legacy-data preservation, connection/process restart persistence, same-request replay, payload conflicts, APPLIED/REJECTED/FAILED historical replay, concurrent uniqueness, transition races, terminal overwrite protection, stale APPLYING read-only detection, rollback behavior, canonical path guards, and full offline validation while canonical schema/latest remains `12 / 12`.
- DAILY-PROD-5B Phase 5 - Isolated PREPARE Orchestration Contract: complete. Added the isolated service-level orchestration contract with request validation, current-plan authority, durable create-or-replay, atomic `PLANNED -> APPLYING` ownership, ownership-loser replay, second fingerprint validation, injected fake FuturePrepareTransaction, durable APPLIED/REJECTED/FAILED ordering, timeout replay, deterministic operator actions, and classify-only stale APPLYING reconciliation while canonical schema/latest remains `12 / 12`.
- DAILY-PROD-5B Phase 6 - PREPARE Job Transaction Adapter Design Contract: complete. Accepted the adapter design contract for one-request/one-Job behavior, one Job plus N JobChapter transaction semantics, prepared-job worker isolation, explicit start separation, deterministic chapter snapshots, conflict/failure taxonomy, interruption recovery, historical replay, reconciliation classification, and dedicated request-to-Job linkage persistence while canonical schema/latest remains `12 / 12`.
- DAILY-PROD-5B Phase 7 - Dormant Request-to-Job Linkage Persistence: complete. Added dormant schema-14 linkage artifact, pure isolated linkage repository, request/Job uniqueness, transaction evidence validation, deterministic replay/conflict behavior, concurrency/rollback tests, and no canonical activation or pipeline integration.
- DAILY-PROD-5B Phase 8 - Same-Transaction PREPARE Adapter Integration Design: complete. Defined the caller-owned transaction boundary, authoritative input revalidation, ownership fencing prerequisites, overlap-race mitigation, immutable JobChapter evidence, commit/recovery semantics, evidence-gated APPLIED handoff, and isolated model validation; implementation remains blocked until Phase 9.
- DAILY-PROD-5B Phase 9 - Isolated Same-Transaction PREPARE Prerequisites: complete. Added dormant schema 15 ownership/fencing/lease evidence, caller-owned `BEGIN IMMEDIATE`, transaction-scoped revalidation and Job/JobChapter/linkage writers, overlap serialization, rollback/ambiguous-outcome recovery, and process-restart acceptance without runtime wiring or canonical activation.
- DAILY-PROD-5B Phase 10 - Isolated End-to-End PREPARE Adapter Assembly: complete. Assembled request replay, ownership/fencing, second-plan validation, authoritative transaction revalidation, one Job/N JobChapter/linkage/COMMITTED attempt, durable evidence-gated APPLIED persistence, replay, concurrency, bounded busy, response-loss, process-restart, rollback, ambiguous-commit, redaction, render-compatible pin, and temporary-root acceptance. Implementation commit `c47d829cddd3e16914d5bf60b4beb20063299820`; runtime wiring and canonical activation remain unauthorized.

## Current Strategic Phase

**PRODUCTION OPERATIONS AND ON-DEMAND HARDENING**

Story Audio is production-ready for operator-directed chapter work. The operator selected `CHOOSE_C_DEFER_CH369_AND_ACTIVATE_DAILY_PRODUCTION_UX_ROADMAP`, so Chapter 369 remains paused as production/editorial work while the Daily Production UX roadmap becomes the active system direction.

Canonical target workflow: [`docs/DAILY_PRODUCTION_WORKFLOW.md`](docs/DAILY_PRODUCTION_WORKFLOW.md).

System development is now authorized only for the ordered `DAILY-PROD` milestones below, unless a later operator decision or production blocker explicitly changes scope.

Chapter production tasks, including Chapter 369 voice selection or Casting Plan review, remain production operations. They do not redefine this strategic roadmap and are not active until the operator resumes them.

## Active System Milestone

**DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout**

Build batch production behavior only after a deterministic read-only plan, clear eligibility rules, explicit operator confirmation, idempotency, partial-failure handling, retry behavior, and recovery boundaries are defined.

The milestone must:

- continue from the completed read-only batch scope plan and mutation safety contract;
- reuse `DAILY-PROD-4` range readiness as the eligibility source;
- require explicit operator confirmation before any batch mutation;
- preserve existing single-chapter approval, prepare, start, render, repair, and QA boundaries;
- define idempotent behavior for repeated actions, partial failures, retries, and already-complete chapters;
- stop before provider/TTS work unless a later task explicitly authorizes execution.

Current boundary:

1. Treat DAILY-PROD-5B Phases 1-10 as complete and keep dormant schema artifacts dormant with canonical/default schema at version 12.
2. Review only the Phase 11 runtime PREPARE wiring, canonical activation, operator rollout, backup/rollback, audit, maintenance, feature-flag, and kill-switch design boundary.
3. Keep runtime adapter/orchestrator wiring, PREPARE API/UI, production Job creation, provider/Gemini/TTS, worker wake, and START_RENDER unauthorized.
4. Keep START_RENDER as a separate explicit lifecycle action and do not advance to DAILY-PROD-6.

## Ordered Daily Production UX Roadmap

1. `DAILY-PROD-1` - Modular Navigation And Sequential Production Shell.
2. `DAILY-PROD-2` - Custom Voice Assignment UI Closure.
3. `DAILY-PROD-3` - Audio Library And Output Retrieval.
4. `DAILY-PROD-4` - Range Readiness And Exception Queue.
5. `DAILY-PROD-5` - Batch Approval, Prepare, Render And QA Closeout.
6. `DAILY-PROD-6` - Multi-Chapter Production Acceptance.

## Next

See `NEXT_TASK.md` for:

`DAILY-PROD-5B Phase 11 — Runtime PREPARE Wiring, Canonical Activation, And Operator Rollout Design Contract`

## Paused

Chapter 369 remains paused as production/editorial work; this does not authorize production PREPARE.

## Deferred (Awaiting User Approval)

YouTube Auto Handoff V2 Output Package: chapter-level output contract with `timeline.json`, `subtitles.srt`, and `manifest.json` for downstream processing.

## Ownership Boundary

- Story Audio so huu approved text, immutable casting, resolved voices, audio, speech timing, Character Bible seed, va immutable Handoff V1 bundle.
- YouTube Auto so huu visual timeline, visual character bible, images, subtitle render, video, metadata, thumbnail, va final composition.

## Deferred / Only When Needed

- Generic image provider framework hoac video composer trong Story Audio.
- Metadata/thumbnail pipeline trong Story Audio.
- Usage ledger, daily batch cap, budget/quota dashboard.
- Multi-user/SaaS, remote worker, distributed locking, va generic plugin system.
- Word alignment bat buoc.
- Incremental backup.
- Microservices/Redis/Celery, nhieu TTS worker, va cloud storage.
