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
- Custom Reference Voice Library UI (Complete): Global library interface, logical voice management, immutable revision upload, exact revision selection, Reference Audio playback, custom Preview Text, short preview support, compact Preset Voice Preview restored, smoke/test book filtering, full-width vertical form layouts, responsive design. **Merged into main via PR #2. Ready for personal production use.**

## Next — Deferred (Awaiting User Approval)

YouTube Auto Handoff V2 Output Package: Chapter-level output contract for YouTube Auto downstream processing.

Required outputs:
- Final chapter audio (M4A/MP3)
- timeline.json: segment-level timing with speaker labels, timestamps from assembled audio
- subtitles.srt: relative timestamps for portable bundle
- manifest.json: chapter metadata, artifact references, relative paths

Validation:
- Real chapter render validation
- Full handoff smoke test with timeline/subtitles
- Portable bundle structure verification

## Paused

No active implementation task. Custom Voice Library UI complete and merged. Chapter Output Package for YouTube Auto deferred until user explicitly approves starting it.


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
