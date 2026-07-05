# Roadmap

Roadmap mô tả thứ tự đầu tư, không phải cam kết thời gian. Ưu tiên theo: bảo vệ dữ liệu -> khả năng phục hồi -> chất lượng audio -> tính năng mới.

## Completed

- Audio MVP: EPUB, immutable TextRevision, Gemini punctuation repair, VieNeu segment checkpoint và chapter audio.
- Manual/multi-voice casting với immutable CastingPlan và resolved job snapshot.
- Text Revision Diff và Shared Gemini repair cache.
- Schema/backup/recovery/diagnostic hardening.
- Story Audio -> YouTube Auto Handoff V1.
- Three-Voice Profile Core và UI integration.
- Book-level Character Bible Import Core, UI và Handoff integration.
- Gemini Speaker Assignment Draft Core.
- Speaker Assignment Review and Approval UI: confidence/alternatives/manual choice, effective voice preview, partial immutable approval, stale protection và idempotency.
- Long-Chapter End-to-End Validation and Hardening: Phase 1 preflight/draft/review/approval, Phase 2 VieNeu render/retry/audio QA, Phase 3 Handoff export/import/downstream compatibility.
- Custom Reference Voice Library UI: Global library interface, logical voice management, immutable revision upload, exact revision selection, Reference Audio playback, custom Preview Text, short preview support, compact Preset Voice Preview restored, smoke/test book filtering, full-width vertical form layouts, responsive design. **Merged into main via PR #2.**
- Custom Voice Backend Resolution & Snapshot Support: voice_ref.py `custom:<id>` parser, CustomVoiceContext catalog, resolver integration in casting/profile/pipeline, 14-field immutable snapshot, snapshot-based TTS synthesis, fail-closed legacy policy, 377 offline tests (92 new snapshot tests), real VieNeu smoke (preset + custom). **Migration 0007, Phase 3A/3B complete.**
- Task 10 Long Chapter Production Pilot: Chapter 804 workflow validation plus Chapter 629 end-to-end production pilot completed on isolated runtime with operator listening pass.
- Task 11B1 Guarded Production Runner: isolated-root production runner, read-only runtime identity endpoint, exact Casting Plan endpoint, Unicode-safe submit path, duplicate protection, immutable binding verification, structured CLI errors, and 759/759 offline tests passing.

## Next

Task 11B2 — Production Runner Progress, Resume and Final Manifest

**Planned scope**:
1. Identify and report the existing active job under the guarded isolated runtime.
2. Perform a controlled resume of that same job and capture progress checkpoints.
3. Verify terminal job state and final artifact manifest data (paths, sizes, SHA-256).
4. Stop before objective listening QA and before any automatic regeneration or candidate-accept workflows.

**Prerequisites**:
- Task 11B1 implementation commit `556023a94670730cafa995aa30d70a389f4a995a`.
- Authoritative interpreter `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Explicit isolated runtime/data root.
- Protected paths `experiment_b_transcript/` and `runs/` remain untouched.

## Paused

No paused tasks.

## Deferred (Awaiting User Approval After Current Task)

YouTube Auto Handoff V2 Output Package: Chapter-level output contract with `timeline.json`, `subtitles.srt`, `manifest.json` for YouTube Auto downstream processing.

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
