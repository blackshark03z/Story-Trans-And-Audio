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

## Next

Task 11C2 - Deterministic Listening Checklist HTML

**Planned scope**:
1. Consume the Task 11B2 production manifest plus Task 11C1 QA JSON as authoritative inputs.
2. Generate a deterministic local HTML listening checklist package for human review.
3. Show chapter overview, prioritized risk samples, and representative narrator/male/female/unknown samples where present.
4. Provide local audio controls and operator review fields without mutating chapter audio.
5. Keep human listening as the final quality authority.
6. Stop before any automatic regenerate/accept/reject workflow.

**Prerequisites**:
- Task 11C1 implementation commit `9cc41720b7da755dd11302e053573dbb9272cd1a`.
- Authoritative interpreter `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Explicit isolated runtime/data root.
- Task 11C1 deterministic QA output available for the target manifest.
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
