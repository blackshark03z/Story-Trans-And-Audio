# Roadmap

Roadmap mô tả thứ tự đầu tư, không phải cam kết thời gian. Ưu tiên theo: bảo vệ dữ liệu → khả năng phục hồi → chất lượng audio → tính năng mới.

## Completed

- Audio MVP: EPUB, immutable TextRevision, Gemini punctuation repair, VieNeu segment checkpoint và chapter audio.
- Manual/multi-voice casting với immutable CastingPlan và resolved job snapshot.
- Text Revision Diff và Shared Gemini repair cache.
- Schema/backup/recovery/diagnostic hardening.
- Story Audio → YouTube Auto Handoff V1.
- Three-Voice Profile Core và UI integration.
- Book-level Character Bible Import Core, UI và Handoff integration.
- Gemini Speaker Assignment Draft Core.
- Speaker Assignment Review and Approval UI: confidence/alternatives/manual choice, effective voice preview, partial immutable approval, stale protection và idempotency.
- Long-Chapter End-to-End Validation and Hardening: Phase 1 preflight/draft/review/approval, Phase 2 VieNeu render/retry/audio QA, Phase 3 Handoff export/import/downstream compatibility.

## Next — In Progress

Custom Reference Voice Library UI: Global library interface for managing custom reference voices (not model training). Create logical voices with display name/description, upload immutable audio/transcript revisions via multipart form, view revision history, deactivate/reactivate voices, preview exact revisions with VieNeu reference-audio synthesis. Repository code supports schema version 7; migration 0006_custom_voices provides the storage contract; no new migration required. UI maps HTTP statuses to safe user-facing messages without exposing backend internals.

Implementation phases:
- Phase 5B1: Logical Voice Library UI (list, create, select, deactivate/reactivate, safe errors, API integration)
- Phase 5B2: Immutable Revision Upload and History (file picker, transcript input, multipart upload, no edit/overwrite)
- Phase 5B3: Preview Integration and Offline Tests (exact revision ID, UI contract tests, API regressions)
- Phase 5B4: Real Smoke and Closure (real VieNeu preview, immutability verification, full suite, Doctor)

## Paused

Controlled Maintenance Sprint: completed Custom Voice Preview; paused for Custom Reference Voice Library UI priority.


## Ownership Boundary

- Story Audio sở hữu approved text, immutable casting, resolved voices, audio, speech timing, Character Bible seed và immutable Handoff V1 bundle.
- YouTube Auto sở hữu visual timeline, visual character bible, images, subtitle render, video, metadata, thumbnail và final composition.

## Deferred / Only When Needed

- Generic image provider framework hoặc video composer trong Story Audio.
- Metadata/thumbnail pipeline trong Story Audio.
- Usage ledger, daily batch cap, budget/quota dashboard.
- Multi-user/SaaS, remote worker, distributed locking và generic plugin system.
- Word alignment bắt buộc.
- Incremental backup.
- Microservices/Redis/Celery, nhiều TTS worker và cloud storage.
