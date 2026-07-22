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

- start with a read-only batch scope plan and mutation safety contract;
- reuse `DAILY-PROD-4` range readiness as the eligibility source;
- require explicit operator confirmation before any batch mutation;
- preserve existing single-chapter approval, prepare, start, render, repair, and QA boundaries;
- define idempotent behavior for repeated actions, partial failures, retries, and already-complete chapters;
- stop before provider/TTS work unless a later task explicitly authorizes execution.

## Ordered Daily Production UX Roadmap

1. `DAILY-PROD-1` - Modular Navigation And Sequential Production Shell.
2. `DAILY-PROD-2` - Custom Voice Assignment UI Closure.
3. `DAILY-PROD-3` - Audio Library And Output Retrieval.
4. `DAILY-PROD-4` - Range Readiness And Exception Queue.
5. `DAILY-PROD-5` - Batch Approval, Prepare, Render And QA Closeout.
6. `DAILY-PROD-6` - Multi-Chapter Production Acceptance.

## Next

See `NEXT_TASK.md` for:

`DAILY-PROD-5A - Batch Scope Plan And Mutation Safety Contract`

## Paused

No paused tasks.

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
