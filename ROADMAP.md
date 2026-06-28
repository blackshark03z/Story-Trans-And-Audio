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
- Custom Reference Voice Library UI: Global library interface, logical voice management, immutable revision upload, exact revision selection, Reference Audio playback, custom Preview Text, short preview support, compact Preset Voice Preview restored, smoke/test book filtering, full-width vertical form layouts, responsive design. **Merged into main via PR #2.**
- Custom Voice Backend Resolution & Snapshot Support: voice_ref.py `custom:<id>` parser, CustomVoiceContext catalog, resolver integration in casting/profile/pipeline, 14-field immutable snapshot, snapshot-based TTS synthesis, fail-closed legacy policy, 377 offline tests (92 new snapshot tests), real VieNeu smoke (preset + custom). **Migration 0007, Phase 3A/3B complete.**

## Next — In Progress

Multi Custom Voice Ready for Personal Use: Complete end-to-end workflow validation for custom reference voices in production use.

**Current Phase**: UI Integration

**Remaining Work**:
1. **UI Integration**: Load custom voices from `/api/custom-voices` into Book Voice Profile, Character Override, and Manual Casting voice selects. Merge with presets in `castingVoiceOptions()`, display format `"<name> (Custom)"`, preserve preset-only backward compatibility.

2. **Short Smoke Test**: 3-utterance isolated chapter with mixed custom/preset voices, verify job/TTS/timeline/retry.

3. **Real Chapter Render**: Full chapter (20–50 utterances) with custom narrator + preset dialogue, verify distribution/quality/handoff.

4. **Retry Validation**: Force segment failure, verify custom voice snapshot preservation during retry.

5. **Documentation Closeout**: Update PROJECT_STATUS, ROADMAP, CHANGELOG to reflect "Ready for Personal Use" status.

**Status**: Backend complete (resolution, snapshot, TTS integration, 377 tests). UI library panel complete and merged (PR #2, 613 tests). Voice selects do not yet expose custom voices to user.

## Paused

No paused tasks. Active implementation: Multi Custom Voice Ready for Personal Use (UI Integration phase).

## Deferred (Awaiting User Approval After Current Task)

YouTube Auto Handoff V2 Output Package: Chapter-level output contract with timeline.json, subtitles.srt, manifest.json for YouTube Auto downstream processing.


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
