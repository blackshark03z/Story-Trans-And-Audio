# Roadmap

Roadmap mô tả thứ tự đầu tư, không phải cam kết thời gian. Ưu tiên được chọn theo: bảo vệ dữ liệu → khả năng phục hồi → chất lượng audio → tính năng mới.

## Completed

- Audio MVP: EPUB, revision, Gemini punctuation repair, VieNeu segment checkpoint và chapter audio.
- Manual/multi-voice casting với immutable CastingPlan và resolved job snapshot.
- Text Revision Diff.
- Shared Gemini repair cache.
- Schema/backup/recovery/diagnostic hardening.
- Story Audio → YouTube Auto Handoff V1.

## Next — Personal Edition voice simplification

1. Three-Voice Profile Core.
2. Three-Voice Profile UI and Casting Integration.
3. Book-level Character Bible Import.
4. Gemini Speaker Assignment Draft.
5. Real chapter workflow review.

Story Audio kết thúc tại approved text, resolved casting, audio, speech timing, character seed và immutable handoff manifest. Visual timeline, image, subtitle render, video, metadata và thumbnail tiếp tục thuộc YouTube Auto.

## Deferred / Only when needed

- Generic image provider framework hoặc video composer trong Story Audio.
- Metadata/thumbnail pipeline trong Story Audio.
- Usage ledger, daily batch cap, budget/quota dashboard.
- Multi-user/SaaS, remote worker, distributed locking và generic plugin system.
- Word alignment bắt buộc.
- Incremental backup.
- Microservices/Redis/Celery, nhiều TTS worker và cloud storage.
