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

## Next

Task 11C - Objective Audio QA and Listening Package

**Planned scope**:
1. Consume the Task 11B2 production manifest as the authoritative chapter/job input.
2. Run deterministic FFmpeg/local metrics for whole-chapter and per-segment audio.
3. Rank clipping, loudness, silence, and duration risks without mutating chapter audio.
4. Generate a deterministic listening checklist package for human review.
5. Include representative narrator/male/female/unknown segments in the review set.
6. Keep human listening as the final quality authority.
7. Stop before any automatic regenerate/accept/reject workflow.

**Prerequisites**:
- Task 11B2 implementation commit `50a2a397b1626ca8abaa1d1ffab5755fdebf5eac`.
- Authoritative interpreter `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Explicit isolated runtime/data root.
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
