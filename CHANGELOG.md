# Changelog

Ghi thay Ä‘á»•i hÃ nh vi ngÆ°á»i dÃ¹ng, schema, artifact contract vÃ  váº­n hÃ nh. KhÃ´ng dÃ¹ng file nÃ y thay cho `PROJECT_STATUS.md`.

## Unreleased

### Added

- **Task 11B1 — Guarded production chapter runner**: Added a production-oriented local runner that defaults to preflight-only mode and only submits with explicit `--submit`.
  - **Runner core**: `story_audio/production_runner.py` validates an absolute isolated data root, rejects the canonical live root, proves API/data-root identity, resolves chapter by book + chapter number, verifies immutable approved Casting Plan bindings, detects duplicate jobs by pinned identity, and returns structured CLI errors including `internal_error` exit `8`.
  - **CLI entrypoint**: `scripts/run_production_chapter.py` exposes the guarded runner without shell-generated JSON.
  - **Read-only API support**: added `GET /api/runtime` for local runtime identity and `GET /api/casting/{casting_plan_id}` for exact-ID Casting Plan fetch needed by the runner.
  - **Unicode safety**: mutating JSON requests are serialized with `ensure_ascii=True` and UTF-8 bytes so operator payloads do not depend on terminal encoding.
  - **Verification**: focused runner/API 36/36 pass, related operational/live-guard 17/17 pass, full offline suite 759/759 pass.
  - **Disposable smoke**: isolated verification runtime confirmed identity/read-only contracts, Chapter 629 duplicate job detection returned `already_completed`, runtime mismatch failed closed with exit `3`, and no real production job was created.
  - **Migration**: none.

- **Task 10 complete — Long Chapter Production Pilot**: Closed the production pilot with evidence only, no application code changes.
  - **Chapter 804 workflow validation** completed on isolated runtime V2: pause/restart/resume, controlled regeneration, A/B review, and Reject workflow all passed; no candidate was accepted; final chapter artifact remained 503.800 s.
  - **Chapter 629 production pilot** completed end-to-end: Character Bible apply, Gemini speaker draft, full editorial review, one corrected attribution, approved immutable Casting Plan #2, three-voice render, and final artifacts verified.
  - **Render result**: Job #2 / JobChapter #2 completed with 119/119 verified segments, duration 824.420 s, and realized voices Ngọc Lan 90 / Đức Trí 26 / Mỹ Duyên 3.
  - **QA result**: objective audio QA package generated, then operator listened to the full chapter and marked `OPERATIONAL_PASS`; no pronunciation, pacing, speaker-switching, clipping, volume, or pause issue justified regeneration.
  - **Evidence runtime**: `D:\Youtube\StoryAudioTask10PilotV2\data` with captures in `D:\Youtube\StoryAudioTask10PilotV2\captures`.
  - **Repository baseline**: Task 10 closeout was verified against `main` at `6fa018076ad7c146b55d05a8c6bf619abd2176f2`; no repo code change was required for that closeout.

- **Manual Casting Draft Character Assignment Fix**: Hybrid API endpoint for preserving manual character assignments by text offsets. The POST `/api/chapters/{chapter_id}/casting/draft` endpoint now supports both offset-based (new authoritative manual mode) and utterance-ID-based (existing auto-draft mode) assignments.
  - **Root cause**: Previous implementation regenerated utterances via `split_utterances()` and matched assignments only by `utterance_id`. UI/manual span IDs did not reliably match regenerated IDs, causing manual assignments to be rejected, ignored, or silently defaulted to narrator.
  - **Offset-based assignments**: Use `start_offset` and `end_offset` to specify character spans within the approved TextRevision. When an authoritative span is split into multiple utterances by the chunker, every child utterance inherits the source `role`, `character_id`, resolved voice, and resolution metadata.
  - **Validation**: XOR constraint (exactly one of utterance_id or offsets required), integer offsets within text bounds, ordered non-overlapping spans, active character validation, role/character_id consistency checks. Invalid requests return clear 400 errors with specific messages.
  - **Coverage behavior**: Partial coverage allowed; uncovered text defaults to narrator. Manual offset mode does not call Gemini.
  - **Backward compatibility**: Existing utterance-ID workflow unchanged. Empty assignments (auto-draft) still supported. Approved Casting Plans remain immutable.
  - **Vietnamese smoke validation**: 750-character "Ngôi Nhà Bỏ Hoang" text, 5 offset-based character dialogue spans (3 An, 2 Bình), uncovered narrator spans. Result: 20 utterances with 10 narrator, 4 An (resolved via book_male → Đức Trí), 6 Bình (resolved via book_female → Mỹ Duyên). Distribution difference from expected 13/3/4 is correct: some submitted dialogue spans split into multiple child utterances, all inheriting character assignment.
  - Test coverage: 723 offline tests passing (13 new offset-based tests in `tests/test_offset_casting.py`).
  - Live DB remained unchanged during isolated smoke testing.

- **Multi-voice Segment Regeneration**: Isolated segment re-synthesis for verified segments without re-running entire jobs. Users can generate candidate attempts using immutable segment snapshots (text, voice, settings), listen to original (active) and candidate side-by-side, then Accept (rebuilds chapter artifacts) or Reject (keeps original). Full attempt history preserved for audit and rollback.
  - `segment_attempts` table tracks active attempt, candidates, rejected attempts, and superseded attempts with timestamps.
  - On first regeneration, system transactionally seeds existing verified output as active Attempt 1, then creates candidate as Attempt 2.
  - POST `/api/segments/{segment_id}/regenerate` validates segment status, job idle state, loads immutable snapshot via `load_segment_synthesis_input()`, synthesizes candidate WAV, and records attempt with status='candidate'.
  - Accept workflow (`/api/segments/{segment_id}/accept-candidate`) rebuilds chapter artifacts with candidate, atomically promotes candidate to active, marks old active as superseded, updates segment pointers, and creates new render directory.
  - Reject workflow (`/api/segments/{segment_id}/reject-candidate`) marks candidate as rejected, retains WAV for audit, does not modify active segment or artifacts.
  - List workflow (`/api/segments/{segment_id}/attempts`) returns active, candidate, and history with legacy state repair for pre-seeding segments.
  - Voice preservation verified: Character An → Đức Trí assignment preserved across regeneration (immutable snapshot guarantees correct voice used).
  - Vietnamese multi-voice pilot passed: Book 19, Chapter 1996, Job 16 with 20/20 segments verified, Ngọc Lan (narrator) / Đức Trí (male An) / Mỹ Duyên (female Bình) voices.
  - Real regeneration smoke: Segment 350 generated candidate (1510ms) from original (1750ms), manual rejection workflow passed, active Attempt 1 preserved.
  - Test coverage: 708 offline tests passing (includes segment regeneration, voice preview, casting/speaker review, migration tests).

### Planned

- **Chapter Output Package for YouTube Auto**: Segment-level timeline.json with speaker labels, timestamps derived from final assembled audio, subtitles.srt with relative timestamps, manifest.json with chapter metadata and artifact references. Real handoff smoke test validation with full chapter render and portable bundle structure.

### Backlog

- Make smoke-title filter more conservative so legitimate book titles containing the word "smoke" are not accidentally hidden.

### Added

- **Custom Reference Voice Library UI (Complete)**: Global library interface for managing custom reference voices. Logical voice management (create, list, select, deactivate/reactivate), immutable revision upload (multipart audio + transcript), revision history display, exact revision selection (radio buttons + summary), Reference Audio playback (GET `/api/custom-voice-revisions/{id}/audio` with SHA-256 verification), custom Preview Text (optional, max 500 chars, empty uses default), short custom preview support (removed 10s minimum, accepts >0s to 20s), cache isolation by revision + text. Compact standalone Preset Voice Preview restored after UI consolidation. UI usability consolidation eliminates redundant custom preview panel; Custom Voice Library remains single custom-reference workflow. Smoke/test books hidden by default with "Show test data" checkbox. Custom Voice input fields use full-width vertical labels and responsive two-column upload layout. Test coverage: 613 tests passing (3 known pre-existing failures in brittle minified-JavaScript assertions unrelated to changes). Real manual smoke passed: preset preview functional, two revisions uploaded, exact selection works, Reference Audio plays, custom short text synthesis succeeds, cache hit/miss verified. Test isolation verified: live DB unchanged during automated runs. No migration required (schema v6 sufficient). **Work merged into main via PR #2.**

- **Custom Voice Preview**: Immutable custom voice revision preview with exact revision ID, reference audio/transcript integrity verification, content-addressed preview cache, and backward-compatible preset request API.
  - `VoicePreviewService.create_custom()` validates revision metadata, checks SHA-256 integrity for reference audio/transcript, synthesizes preview WAV, and stores in content-addressed cache with atomic manifest.
  - `TtsService.synthesize()` extended with optional `reference_audio_path` and `reference_transcript` parameters for custom-reference synthesis preview (routing validation prevents mixing modes).
  - POST `/api/voice-previews` accepts XOR selector: `voice_id` (preset) or `custom_voice_revision_id` (custom), maps domain exceptions to HTTP 404/400/503 without leaking internal details.
  - Custom Voice Preview UI panel with logical custom voice selector, immutable revision selector, preview button, audio player, and status display. JavaScript converts revision ID to integer and sends exact `custom_voice_revision_id` (no `voice_type` or `preview_text`).
  - Test coverage: 27 UI contract tests, 16 API integration tests, 29 service tests, 23 TTS tests. Total: 450 tests passing (41.9s).
  - Real VieNeu custom preview smoke not performed; accepted residual risk with comprehensive offline test coverage.
  - Live DB remained unchanged; no migration required.

- **Phase 3B: Immutable voice synthesis snapshots** for preset and custom-reference voices with strict version-1 validation, fail-closed legacy policy, and deterministic retry behavior.
  - `SegmentSynthesisInput` dataclass with 14 immutable snapshot fields including voice provider/model, synthesis settings JSON, text SHA-256, and custom reference audio/transcript integrity.
  - `load_segment_synthesis_input()` validates snapshots before TTS, performs SHA-256 integrity checks, and loads managed-storage reference audio without database lookups.
  - `TtsService.synthesize()` dual API: snapshot-based path (Phase 3B) and temporary legacy path for non-pipeline callers.
  - Pipeline integration: `_process_chapter` loads snapshots once per segment outside retry loop; retry operations preserve all 14 snapshot fields while resetting only wav_path/audio_sha256/duration_ms/verified_at.
  - Test coverage: 92 new tests across snapshot validation (preset 23, custom 20), TTS integration (17), pipeline integration (12), plus updated casting/recovery mocks (20 tests modified). Total: 377 tests passing.
  - Real smoke validation: VieNeu v3turbo preset (1.04s) and custom-reference (4.31s) synthesis in offline mode with integrity failure detection.
  - E2 waiver: Full pipeline/retry smoke deferred due to temporary DB fixture complexity; accepted residual risk with existing mocked integration coverage.
  - Live DB remained at schema version 6; code supports schema version 7.

### Documentation

- Äá»“ng bá»™ README, AGENTS, ROADMAP, NEXT_TASK vÃ  ARCHITECTURE sau khi Long-Chapter Validation hoÃ n táº¥t; sá»­a Ä‘Ã¡nh sá»‘ quy trÃ¬nh README vÃ  gáº¯n nhÃ£n cÃ¡c ghi chÃº kiáº¿n trÃºc lá»‹ch sá»­ chÆ°a/khÃ´ng triá»ƒn khai.

### Added

- Speaker Assignment Review UI trong Character Voices vá»›i draft selector, confidence/needs-review filters, bulk actions, Gemini alternatives, manual character/narrator/unknown decisions vÃ  effective voice preview.
- Immutable partial approval táº¡o Casting Plan revision má»›i, giá»¯ nguyÃªn assignment ngoÃ i pháº¡m vi Ä‘Ã£ review, há»— trá»£ base-plan compare-and-swap vÃ  deterministic decision fingerprint.
- Approval idempotency theo draft/base/decision identity; exact repeat tráº£ láº¡i plan cÅ©, cÃ²n key trÃ¹ng vá»›i quyáº¿t Ä‘á»‹nh khÃ¡c bá»‹ tá»« chá»‘i.
- Stale protection cho TextRevision, Character Bible fingerprint vÃ  confirmed Casting Plan context; draft cÅ© váº«n Ä‘á»c Ä‘Æ°á»£c Ä‘á»ƒ audit.
- Doctor kiá»ƒm tra review metadata liÃªn káº¿t Ä‘Ãºng draft/chapter/base plan, fingerprint vÃ  idempotency identity.
- Gemini Speaker Assignment Draft Core vá»›i deterministic utterance selection, context trÆ°á»›c/sau, Character Bible candidates vÃ  confirmed casting context.
- Structured response `story-audio-speaker-assignment-draft/v1` gá»“m candidate, confidence, alternatives, concise reason, confidence level vÃ  `needs_review=true`.
- Migration `0005_speaker_assignment_drafts` lÆ°u immutable draft index; payload náº±m trong content-addressed JSON blob, khÃ´ng náº±m trong Casting Plan.
- Shared Gemini Cache há»— trá»£ task `speaker_assignment`, validate payload á»Ÿ cáº£ miss/hit vÃ  coi cache há»ng lÃ  safe miss.
- API POST/GET vÃ  CLI `scripts/speaker_assignment_draft.py`; Doctor kiá»ƒm tra ownership, schema, hash, fingerprint vÃ  character references.
- Prompt boundary tÃ¡ch system instruction khá»i untrusted chapter/alias/Character Bible data vÃ  cáº¥m táº¡o character má»›i hoáº·c suy luáº­n tá»« voice.

- Character Bible JSON importer for `story-audio-character-bible/v1` with CLI dry-run/apply and structured backend dry-run/apply API.
- Character Bible UI in the casting panel with JSON file selection, dry-run plan preview, apply action, conflict blocking and import summary.
- Custom Reference Voice API and Global Repository. Immutable custom voice revisions and atomic content-addressed audio/transcript storage.
- Character Manager metadata editor for canonical identity, aliases, gender, role, age group, description, speech style, visual notes, notes and import provenance display.
- Migration `0004_character_bible` adds queryable character identity fields, aliases, role/age metadata and import provenance without storing full JSON in SQLite.
- Deterministic matching by external key, canonical name and unique alias, with conflict detection and idempotent re-import.
- Doctor checks for duplicate external keys, orphan aliases, alias/book mismatch and invalid Character Bible enums.

- Book Voice Profile vá»›i narrator, male dialogue, female dialogue vÃ  configurable unknown fallback.
- Optional character voice override, manual gender metadata vÃ  deterministic voice resolver cÃ³ resolution source/needs-review.
- Minimal profile/override/resolve API Ä‘á»ƒ chuáº©n bá»‹ cho UI task tiáº¿p theo.
- Book Voice Profile UI vá»›i empty/invalid state, bá»‘n preview slot, fallback policy vÃ  profile version.
- Character Manager há»— trá»£ gender, Use book default/Use custom voice, effective voice vÃ  resolution source.
- Manual Casting hiá»ƒn thá»‹ resolved voice, gender vÃ  needs-review; preview resolution read-only khÃ´ng táº¡o plan/job.

### Changed

- Speaker assignment prompt tÄƒng lÃªn `speaker-assignment-v2` vÃ  yÃªu cáº§u alternatives khi cÃ²n candidate há»£p lá»‡; cache identity thay Ä‘á»•i theo prompt version.
- Manual Casting há»— trá»£ explicit `Unknown`; approval khÃ´ng tá»± táº¡o job, audio hoáº·c sá»­a Book Voice Profile/Character Bible.
- Casting plan/job má»›i snapshot resolved preset, resolution source vÃ  Book Voice Profile ID/version; retry tiáº¿p tá»¥c dÃ¹ng snapshot cÅ©.
- Custom voices are now managed at the Global Library level rather than book-level to maximize reusability across projects.
- Migration `0003_three_voice_profile` báº£o toÃ n `characters.default_voice_id` vÃ  sao chÃ©p giÃ¡ trá»‹ cÅ© thÃ nh legacy override.
- Segment timeline má»›i mang resolution source, resolved gender, needs-review vÃ  profile ID/version tá»« immutable job snapshot.
- YouTube Auto `character_seed.json` now exports Character Bible canonical metadata, aliases, notes and resolved preset hints; metadata changes produce a new immutable bundle without mutating old exports.

### Verified

- Long-Chapter Validation Phase 2 trÃªn job #6/chapter 56: Casting Plan #8 táº¡o job thá»§ cÃ´ng, VieNeu tháº­t render 210/210 segment verified, final M4A render_0002 dÃ i 752.310 s.
- Long-Chapter Validation Phase 3 trÃªn job #6/chapter 56/artifact #30: export handoff bundle identity `050ac2f2a73bda7b84beb7c1e9bd5b06d9fd3a00773214fa91616c451e8f9280` láº§n Ä‘áº§u táº¡o manifest 752310 ms / 210 utterances / 2 characters; export #2 reused cÃ¹ng identity; legacy bundles `93ff2e0a367a` vÃ  `3255141aa34f` verify/import/reuse Ä‘áº¡t; Story Audio 119 offline tests / Doctor deep `critical_errors=0`; YouTube Auto 96 tests / import 7/7 Ä‘áº¡t.
- 28 isolated API offline tests verify strict boundaries for Custom Voice routes. 244 full suite offline tests and Doctor run clean with Schema v6.
- Phase 2 voice/timing QA: Ngá»c Lan 110, Äá»©c TrÃ­ 56, Má»¹ DuyÃªn 44; 210 utterance sequence liÃªn tá»¥c, final AAC mono 48 kHz, audio sample RMS/peak dÆ°Æ¡ng.
- Phase 2 retry/reuse: `retry_segment` cho segment #247 táº¡o render_0002, 4 segment Ä‘á»‘i chá»©ng giá»¯ nguyÃªn hash/mtime, render_0001 váº«n tá»“n táº¡i vÃ  final cÅ© chuyá»ƒn `stale`.
- Phase 2 immutability: TextRevision #112 hash match, Casting Plan #8 hash match, speaker draft/casting plan khÃ´ng tÄƒng, YouTube Auto khÃ´ng bá»‹ ghi trong Phase 2.
- Long-Chapter Validation Phase 1 trÃªn `Quang Ã‚m Chi Ngoáº¡i` chapter 56: Draft #4 generated 101/101 valid báº±ng Gemini tháº­t, 6 batch, prompt `speaker-assignment-v2`.
- Review UI tháº­t táº¡o plan #7 partial 15 decision vÃ  plan #8 final 86 decision; exact repeat reused plan #8 vá»›i cÃ¹ng decision fingerprint, khÃ´ng táº¡o job/audio.
- Accuracy smoke Phase 1 Ä‘áº¡t 40/40 máº«u thá»§ cÃ´ng; TextRevision #112, Character Bible fingerprint, draft payload hash giá»¯ nguyÃªn; jobs/segments/artifacts váº«n 5/42/24.
- Real Gemini/UI smoke trÃªn book 7/chapter 1985: Draft #3 valid 15/15, 7 high + 8 medium; suggestion, alternative, manual correction, unknown vÃ  skipped rows Ä‘Æ°á»£c review qua hai approval revision.
- Plan #5 partial vÃ  plan #6 final; exact repeat reuse plan #6 vá»›i cÃ¹ng decision fingerprint. Job count giá»¯ nguyÃªn 5 vÃ  khÃ´ng cÃ³ audio má»›i.
- Handoff má»›i export hai láº§n cÃ¹ng identity/reuse; bundle cÅ© vÃ  bundle giÃ u metadata Ä‘á»u verify/import tháº­t láº¡i vÃ o `D:\Youtube\Youtube Auto`.
- 119 offline tests, JavaScript syntax check, schema v5, SQLite quick check vÃ  Doctor deep `critical_errors=0`.
- Real Gemini smoke chapter 1982/utterance `u0001-a99461c9571c`: draft #1 generated, valid 1/1, model `gemini-2.5-flash`; láº§n hai cache hit vÃ  reuse cÃ¹ng fingerprint/content.
- Backup tháº­t trÆ°á»›c migration v5: 4.060 file / 76.112.399 byte, schema v4. Character, casting, job, segment, artifact vÃ  TextRevision tables khÃ´ng Ä‘á»•i sau smoke.

- 94 offline tests pass; schema v4; JavaScript syntax check passes; SQLite quick check and Doctor deep `critical_errors=0`.
- Character Bible smoke on isolated book 5: dry-run creates 3, first apply creates 3/2 aliases, second apply matches 3 with no writes; API character read and voice resolution verified.
- UI contract covers safe metadata rendering for Character Bible import and character cards; handoff regression verifies old bundles stay immutable when metadata changes.
- Jobs #3/#4/#5 casting snapshot hashes stayed unchanged after Character Bible import.

- 78 offline tests, JavaScript syntax check, schema v3, SQLite quick check vÃ  Doctor deep `critical_errors=0`.
- Real VieNeu smoke jobs 4â€“5: profile v1/v2, five resolution paths, controlled retry reuse 7/8 segment vÃ  verified M4A/timeline.

- ThÃªm bá»™ tÃ i liá»‡u Ä‘iá»u hÃ nh, testing, data model vÃ  runbook.
- ThÃªm cÃ´ng cá»¥ cháº©n Ä‘oÃ¡n read-only `scripts/doctor.py`.

### Added

- Story Audio â†’ YouTube Auto Handoff V1 exporter/verifier cho má»™t completed chapter.
- Bundle báº¥t biáº¿n gá»“m pinned `content.md`, copied narration audio, integer-ms speech timeline, character identity seed vÃ  SHA-256 manifest.
- Doctor kiá»ƒm tra export bundle; backup bao gá»“m `data/exports/youtube_auto`; 7 offline exporter tests.
- Shared Gemini punctuation-repair cache táº¡i `data/cache/gemini_repairs/`, khÃ³a canonical theo source hash, model, prompt, repair contract, block strategy, lexical validator vÃ  output settings.
- Cache manifest atomic trá» tá»›i content-addressed text blobs; cache hit xÃ¡c minh schema/key/hash/character count vÃ  cháº¡y láº¡i lexical validation.
- Cleanup cache máº·c Ä‘á»‹nh dry-run (`scripts/cleanup_gemini_cache.py`), TTL 180 ngÃ y, giá»›i háº¡n 10.000 manifest/256 MiB vÃ  khÃ´ng xÃ³a text blob.
- Doctor shallow/deep bÃ¡o cache manifest há»ng hoáº·c file táº¡m á»Ÿ má»©c warning; 10 fake-Gemini/cache regression tests offline.
- Text Revision Diff tab trong chapter dialog vá»›i preset raw/reflowed/repaired, Inline vÃ  Side-by-side.
- Read-only revision metadata/diff API vá»›i block matching, token/punctuation operations vÃ  lexical integrity summary.
- Whitespace toggle, unchanged collapse/expand, large-payload warning vÃ  explicit 500.000-character limit.
- 12 offline regression tests cho punctuation, whitespace, paragraph, Unicode, blob integrity, XSS vÃ  large text.
- Character manager theo book vÃ  Manual Casting panel trong chapter dialog.
- Immutable content-addressed Casting Plan Revision pin approved TextRevision báº±ng utterance offsets.
- Multi-voice job snapshot, speaker-bounded segments vÃ  timeline speaker metadata.
- Migration `0002_character_voice` cÃ¹ng offline upgrade/backward-compatibility tests.
- Voice Preview cho preset voice vá»›i máº«u Ä‘á»c 10â€“20 giÃ¢y vÃ  audio player ngay táº¡i mÃ n hÃ¬nh táº¡o job.
- Preview cache Ä‘á»™c láº­p táº¡i `data/cache/previews/`, khÃ³a theo voice, text, settings vÃ  engine version.
- Cache integrity verification, tá»± render láº¡i file há»ng vÃ  cleanup policy 30 ngÃ y/tá»‘i Ä‘a 100 entry.
- 5 fake-TTS tests offline; preview khÃ´ng táº¡o database, job hay chapter artifact.
- Diagnostic UI ba cáº¥p cho job, chapter vÃ  segment, gá»“m tráº¡ng thÃ¡i file/hash, lá»—i vÃ  metadata checkpoint.
- Retry action theo chapter hoáº·c segment lá»—i; verified segment Ä‘Æ°á»£c giá»¯ nguyÃªn vÃ  khÃ´ng cho retry trá»±c tiáº¿p.
- 5 offline tests cho aggregation, file corruption diagnostics vÃ  retry invariants.
- Schema migration runner vá»›i báº£ng `schema_migrations`, checksum vÃ  future-version guard.
- Baseline migration `0001_initial` cho cáº£ DB má»›i vÃ  DB 0.1.0 chÆ°a version.
- `scripts/backup.py`: SQLite Online Backup, blobs/output/work vÃ  manifest SHA-256.
- `scripts/restore.py`: verify-only, staging restore, path remap vÃ  overwrite cÃ³ pre-restore copy.
- Shared integrity checker cho doctor vÃ  integration tests.
- Offline integration tests cho legacy migration, restart recovery, retry reuse, cancel, backup/restore vÃ  artifact corruption.

### Changed

- Documented ADR-013 and synchronized README, architecture, runbook, testing and cost-control guidance for the planned Personal Edition three-voice profile; this is an architecture decision only, not an implemented feature.
- Gemini API chá»‰ Ä‘Æ°á»£c gá»i sau khi job checkpoint, approved repaired TextRevision vÃ  shared cache Ä‘á»u khÃ´ng reuse Ä‘Æ°á»£c; cache há»ng trá»Ÿ thÃ nh safe miss.
- Audit phÃ¢n biá»‡t `gemini_cache_hit`, `gemini_cache_miss`, `gemini_cache_invalid`, `gemini_api_call` vÃ  `gemini_checkpoint_reuse` mÃ  khÃ´ng lÆ°u source text/API key.
- Audio assembly dÃ¹ng thÆ° má»¥c `render_<generation>` Ä‘á»ƒ retry khÃ´ng ghi Ä‘Ã¨ artifact verified cÅ©.
- Doctor kiá»ƒm tra schema version, verified segments vÃ  hash blob khi dÃ¹ng `--deep`.
- App tá»« chá»‘i khá»Ÿi Ä‘á»™ng náº¿u DB má»›i hÆ¡n code hoáº·c migration Ä‘Ã£ apply bá»‹ sá»­a checksum.

### Verified

- 67 offline tests Ä‘áº¡t; JavaScript syntax Ä‘áº¡t.
- Live diff API trÃªn chapter 18.649 kÃ½ tá»± hoÃ n thÃ nh khoáº£ng 330 ms vÃ  khÃ´ng tráº£ internal path.
- VieNeu v3 Turbo multi-voice smoke: job 3, 3 preset voices, 8 utterance/segment, M4A 22.810 ms.
- Controlled retry render láº¡i má»™t segment trong 2,47 giÃ¢y vÃ  reuse nguyÃªn hash/mtime cá»§a 7 segment cÃ²n láº¡i.
- Timeline speaker metadata, job voice snapshot, artifact hashes vÃ  duration tolerance 1.000 ms Ä‘á»u Ä‘áº¡t.
- Backup tháº­t 3.989 file / 60.216.155 byte verify Ä‘áº¡t.
- Restore sang data root má»›i remap 13 path vÃ  deep integrity Ä‘áº¡t.

## [2026-06-27] Phase 3A: Job/Casting Snapshot Pinning (Migration 0007)

**Commit**: `7705bc3737644037c701ea87533811d7204b1b44`
**Branch**: `fix/epub-inline-unicode-extraction`

### Added
- `story_audio/pipeline.py` — `_prepare_segments` now pins 14 snapshot columns (from migration 0007) during segment creation.
- `tests/test_voice_snapshot.py` — New offline test suite for snapshot logic with 11 focused isolated tests.

### Changed
- `story_audio/pipeline.py` — Modified `_prepare_segments` to build the full 25-column segments row. Lazily resolves and pins exact custom reference `custom_voice_revision_id`, `reference_audio_sha256`, `reference_audio_storage_key`, `reference_transcript`, and `reference_transcript_sha256`. Also deterministically serializes `synthesis_settings_json`.

### Verified
- 305/305 offline tests pass, including historical legacy migration tests (v2 test fixture regression fixed).
- Doctor confirms code supports schema 7.
- Live database remains schema version 6 and was not migrated (no live DB mutation occurred).

### Notes
- Snapshot persistence is complete (Phase 3A closed).
- Retry does NOT yet consume snapshots (planned for Phase 3B).
- Reference audio is NOT yet passed to VieNeu (planned for Phase 3B).
- Next task is Phase 3B: TTS + Retry Integration.

## [2026-06-27] Resolve custom reference voice assignments

**Commit**: `64c7ea4949b4c5c37b01cc05bb2eddd686691066`
**Branch**: `fix/epub-inline-unicode-extraction`

### Added
- `story_audio/voice_ref.py` — New module. Custom voice logical reference parser (`custom:<id>`), `CustomVoiceContext` catalog, availability check, deterministic latest revision selection, and `resolve_custom_ref` with structured output (kind=`custom_reference`).
- `tests/test_voice_ref.py` — 31 offline tests: `custom:<id>` parsing, context build, resolution, voice profile integration, casting draft integration (preset backward compat + custom narrator + mixed plan), and live DB guard.

### Changed
- `story_audio/casting.py` — `create_casting_draft`, `casting_context`, and validation now accept optional `custom_voice_context: CustomVoiceContext | None`. `_is_allowed_voice` helper added. All preset-only voice checks extended to allow custom references.
- `story_audio/voice_profile.py` — `set_book_voice_profile`, `profile_validation`, `set_character_voice_override`, and `resolve_voice` extended with `custom_voice_context` parameter. `resolve_voice` now returns `custom_reference` kind dict for custom refs.
- `pyproject.toml` — Added `python-multipart>=0.0.18` to declared dependencies.

### Notes
- All preset voice resolution paths are fully backward compatible.
- No migration, no schema change, no live DB access during development.
- Full offline suite: 290/290 pass.

## 0.1.0 â€” 2026-06-23

### Added

- FastAPI UI/API táº¡i cá»•ng 8766.
- EPUB import cho 1.980 chÆ°Æ¡ng.
- Content-addressed text storage vÃ  TextRevision.
- Gemini punctuation repair theo block vá»›i lexical integrity validation.
- VieNeu v3 Turbo segment worker.
- SQLite checkpoint, pause/resume/cancel/retry.
- Artifact cho master WAV, M4A/MP3 vÃ  timeline.
- Audio player vÃ  cleanup retention.

### Verified

- 8 offline unit tests.
- End-to-end chÆ°Æ¡ng 858, 10 segment, M4A 118.710 ms.
- Resume test giá»¯ 9 segment há»£p lá»‡ vÃ  táº¡o láº¡i má»™t segment lá»—i.
