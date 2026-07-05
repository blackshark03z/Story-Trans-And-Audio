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

## Next

Task 11D - Production Workflow Consolidation and Operator Entry Point

**Planned scope**:
1. Compose Task 11B1 + 11B2 + 11C1 + 11C2 into one guarded operator workflow.
2. Keep production submit/watch/resume, manifest generation, objective QA, and listening checklist as explicit sequential checkpoints.
3. Do not add new synthesis logic or automatic QA pass/fail decisions.
4. Preserve human listening as the final quality authority.
5. Stop before YouTube Auto handoff changes in this slice.

**Prerequisites**:
- Task 11C2 implementation commit `26b8f50acabed3f5f4a7a8c89e62128469221a1d`.
- Authoritative interpreter `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Explicit isolated runtime/data root.
- Deterministic production manifest plus deterministic QA output available for the target chapter.
- Protected paths `experiment_b_transcript/` and `runs/` remain untouched.

## Paused

No paused tasks.

## Deferred (Awaiting User Approval After Current Task)

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
