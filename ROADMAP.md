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

## Next — Ready for Planning

Long-Chapter Validation hoàn tất. Chọn task tiếp theo từ danh sách dưới hoặc từ user request.


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
