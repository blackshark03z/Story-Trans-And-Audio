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

## Current Strategic Phase

**PRODUCTION OPERATIONS AND ON-DEMAND HARDENING**

Story Audio is production-ready for operator-directed chapter work. No system-development milestone is automatically active.

System development begins only when:

1. The operator explicitly requests a feature or hardening task.
2. A real production run proves a reusable blocker that should be fixed in the system rather than handled as one-off editorial work.

Chapter production tasks, including Chapter 369 voice selection, are production operations. They do not redefine this strategic roadmap.

## Next

No automatic roadmap milestone is active. See `NEXT_TASK.md` for the currently authorized operation or decision checkpoint; it must conform to this roadmap and cannot silently redefine strategic direction.

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
