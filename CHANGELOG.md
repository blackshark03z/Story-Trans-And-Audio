# Changelog

Ghi thay đổi hành vi người dùng, schema, artifact contract và vận hành. Không dùng file này thay cho `PROJECT_STATUS.md`.

## Unreleased

### Added

- Speaker Assignment Review UI trong Character Voices với draft selector, confidence/needs-review filters, bulk actions, Gemini alternatives, manual character/narrator/unknown decisions và effective voice preview.
- Immutable partial approval tạo Casting Plan revision mới, giữ nguyên assignment ngoài phạm vi đã review, hỗ trợ base-plan compare-and-swap và deterministic decision fingerprint.
- Approval idempotency theo draft/base/decision identity; exact repeat trả lại plan cũ, còn key trùng với quyết định khác bị từ chối.
- Stale protection cho TextRevision, Character Bible fingerprint và confirmed Casting Plan context; draft cũ vẫn đọc được để audit.
- Doctor kiểm tra review metadata liên kết đúng draft/chapter/base plan, fingerprint và idempotency identity.
- Gemini Speaker Assignment Draft Core với deterministic utterance selection, context trước/sau, Character Bible candidates và confirmed casting context.
- Structured response `story-audio-speaker-assignment-draft/v1` gồm candidate, confidence, alternatives, concise reason, confidence level và `needs_review=true`.
- Migration `0005_speaker_assignment_drafts` lưu immutable draft index; payload nằm trong content-addressed JSON blob, không nằm trong Casting Plan.
- Shared Gemini Cache hỗ trợ task `speaker_assignment`, validate payload ở cả miss/hit và coi cache hỏng là safe miss.
- API POST/GET và CLI `scripts/speaker_assignment_draft.py`; Doctor kiểm tra ownership, schema, hash, fingerprint và character references.
- Prompt boundary tách system instruction khỏi untrusted chapter/alias/Character Bible data và cấm tạo character mới hoặc suy luận từ voice.

- Character Bible JSON importer for `story-audio-character-bible/v1` with CLI dry-run/apply and structured backend dry-run/apply API.
- Character Bible UI in the casting panel with JSON file selection, dry-run plan preview, apply action, conflict blocking and import summary.
- Character Manager metadata editor for canonical identity, aliases, gender, role, age group, description, speech style, visual notes, notes and import provenance display.
- Migration `0004_character_bible` adds queryable character identity fields, aliases, role/age metadata and import provenance without storing full JSON in SQLite.
- Deterministic matching by external key, canonical name and unique alias, with conflict detection and idempotent re-import.
- Doctor checks for duplicate external keys, orphan aliases, alias/book mismatch and invalid Character Bible enums.

- Book Voice Profile với narrator, male dialogue, female dialogue và configurable unknown fallback.
- Optional character voice override, manual gender metadata và deterministic voice resolver có resolution source/needs-review.
- Minimal profile/override/resolve API để chuẩn bị cho UI task tiếp theo.
- Book Voice Profile UI với empty/invalid state, bốn preview slot, fallback policy và profile version.
- Character Manager hỗ trợ gender, Use book default/Use custom voice, effective voice và resolution source.
- Manual Casting hiển thị resolved voice, gender và needs-review; preview resolution read-only không tạo plan/job.

### Changed

- Speaker assignment prompt tăng lên `speaker-assignment-v2` và yêu cầu alternatives khi còn candidate hợp lệ; cache identity thay đổi theo prompt version.
- Manual Casting hỗ trợ explicit `Unknown`; approval không tự tạo job, audio hoặc sửa Book Voice Profile/Character Bible.
- Casting plan/job mới snapshot resolved preset, resolution source và Book Voice Profile ID/version; retry tiếp tục dùng snapshot cũ.
- Migration `0003_three_voice_profile` bảo toàn `characters.default_voice_id` và sao chép giá trị cũ thành legacy override.
- Segment timeline mới mang resolution source, resolved gender, needs-review và profile ID/version từ immutable job snapshot.
- YouTube Auto `character_seed.json` now exports Character Bible canonical metadata, aliases, notes and resolved preset hints; metadata changes produce a new immutable bundle without mutating old exports.

### Verified

- Long-Chapter Validation Phase 2 trên job #6/chapter 56: Casting Plan #8 tạo job thủ công, VieNeu thật render 210/210 segment verified, final M4A render_0002 dài 752.310 s.
- Long-Chapter Validation Phase 3 trên job #6/chapter 56/artifact #30: export handoff bundle identity `050ac2f2a73bda7b84beb7c1e9bd5b06d9fd3a00773214fa91616c451e8f9280` lần đầu tạo manifest 752310 ms / 210 utterances / 2 characters; export #2 reused cùng identity; legacy bundles `93ff2e0a367a` và `3255141aa34f` verify/import/reuse đạt; Story Audio 119 offline tests / Doctor deep `critical_errors=0`; YouTube Auto 96 tests / import 7/7 đạt.
- Phase 2 voice/timing QA: Ngọc Lan 110, Đức Trí 56, Mỹ Duyên 44; 210 utterance sequence liên tục, final AAC mono 48 kHz, audio sample RMS/peak dương.
- Phase 2 retry/reuse: `retry_segment` cho segment #247 tạo render_0002, 4 segment đối chứng giữ nguyên hash/mtime, render_0001 vẫn tồn tại và final cũ chuyển `stale`.
- Phase 2 immutability: TextRevision #112 hash match, Casting Plan #8 hash match, speaker draft/casting plan không tăng, YouTube Auto không bị ghi trong Phase 2.
- Long-Chapter Validation Phase 1 trên `Quang Âm Chi Ngoại` chapter 56: Draft #4 generated 101/101 valid bằng Gemini thật, 6 batch, prompt `speaker-assignment-v2`.
- Review UI thật tạo plan #7 partial 15 decision và plan #8 final 86 decision; exact repeat reused plan #8 với cùng decision fingerprint, không tạo job/audio.
- Accuracy smoke Phase 1 đạt 40/40 mẫu thủ công; TextRevision #112, Character Bible fingerprint, draft payload hash giữ nguyên; jobs/segments/artifacts vẫn 5/42/24.
- Real Gemini/UI smoke trên book 7/chapter 1985: Draft #3 valid 15/15, 7 high + 8 medium; suggestion, alternative, manual correction, unknown và skipped rows được review qua hai approval revision.
- Plan #5 partial và plan #6 final; exact repeat reuse plan #6 với cùng decision fingerprint. Job count giữ nguyên 5 và không có audio mới.
- Handoff mới export hai lần cùng identity/reuse; bundle cũ và bundle giàu metadata đều verify/import thật lại vào `D:\Youtube\Youtube Auto`.
- 119 offline tests, JavaScript syntax check, schema v5, SQLite quick check và Doctor deep `critical_errors=0`.
- Real Gemini smoke chapter 1982/utterance `u0001-a99461c9571c`: draft #1 generated, valid 1/1, model `gemini-2.5-flash`; lần hai cache hit và reuse cùng fingerprint/content.
- Backup thật trước migration v5: 4.060 file / 76.112.399 byte, schema v4. Character, casting, job, segment, artifact và TextRevision tables không đổi sau smoke.

- 94 offline tests pass; schema v4; JavaScript syntax check passes; SQLite quick check and Doctor deep `critical_errors=0`.
- Character Bible smoke on isolated book 5: dry-run creates 3, first apply creates 3/2 aliases, second apply matches 3 with no writes; API character read and voice resolution verified.
- UI contract covers safe metadata rendering for Character Bible import and character cards; handoff regression verifies old bundles stay immutable when metadata changes.
- Jobs #3/#4/#5 casting snapshot hashes stayed unchanged after Character Bible import.

- 78 offline tests, JavaScript syntax check, schema v3, SQLite quick check và Doctor deep `critical_errors=0`.
- Real VieNeu smoke jobs 4–5: profile v1/v2, five resolution paths, controlled retry reuse 7/8 segment và verified M4A/timeline.

- Thêm bộ tài liệu điều hành, testing, data model và runbook.
- Thêm công cụ chẩn đoán read-only `scripts/doctor.py`.

### Added

- Story Audio → YouTube Auto Handoff V1 exporter/verifier cho một completed chapter.
- Bundle bất biến gồm pinned `content.md`, copied narration audio, integer-ms speech timeline, character identity seed và SHA-256 manifest.
- Doctor kiểm tra export bundle; backup bao gồm `data/exports/youtube_auto`; 7 offline exporter tests.
- Shared Gemini punctuation-repair cache tại `data/cache/gemini_repairs/`, khóa canonical theo source hash, model, prompt, repair contract, block strategy, lexical validator và output settings.
- Cache manifest atomic trỏ tới content-addressed text blobs; cache hit xác minh schema/key/hash/character count và chạy lại lexical validation.
- Cleanup cache mặc định dry-run (`scripts/cleanup_gemini_cache.py`), TTL 180 ngày, giới hạn 10.000 manifest/256 MiB và không xóa text blob.
- Doctor shallow/deep báo cache manifest hỏng hoặc file tạm ở mức warning; 10 fake-Gemini/cache regression tests offline.
- Text Revision Diff tab trong chapter dialog với preset raw/reflowed/repaired, Inline và Side-by-side.
- Read-only revision metadata/diff API với block matching, token/punctuation operations và lexical integrity summary.
- Whitespace toggle, unchanged collapse/expand, large-payload warning và explicit 500.000-character limit.
- 12 offline regression tests cho punctuation, whitespace, paragraph, Unicode, blob integrity, XSS và large text.
- Character manager theo book và Manual Casting panel trong chapter dialog.
- Immutable content-addressed Casting Plan Revision pin approved TextRevision bằng utterance offsets.
- Multi-voice job snapshot, speaker-bounded segments và timeline speaker metadata.
- Migration `0002_character_voice` cùng offline upgrade/backward-compatibility tests.
- Voice Preview cho preset voice với mẫu đọc 10–20 giây và audio player ngay tại màn hình tạo job.
- Preview cache độc lập tại `data/cache/previews/`, khóa theo voice, text, settings và engine version.
- Cache integrity verification, tự render lại file hỏng và cleanup policy 30 ngày/tối đa 100 entry.
- 5 fake-TTS tests offline; preview không tạo database, job hay chapter artifact.
- Diagnostic UI ba cấp cho job, chapter và segment, gồm trạng thái file/hash, lỗi và metadata checkpoint.
- Retry action theo chapter hoặc segment lỗi; verified segment được giữ nguyên và không cho retry trực tiếp.
- 5 offline tests cho aggregation, file corruption diagnostics và retry invariants.
- Schema migration runner với bảng `schema_migrations`, checksum và future-version guard.
- Baseline migration `0001_initial` cho cả DB mới và DB 0.1.0 chưa version.
- `scripts/backup.py`: SQLite Online Backup, blobs/output/work và manifest SHA-256.
- `scripts/restore.py`: verify-only, staging restore, path remap và overwrite có pre-restore copy.
- Shared integrity checker cho doctor và integration tests.
- Offline integration tests cho legacy migration, restart recovery, retry reuse, cancel, backup/restore và artifact corruption.

### Changed

- Documented ADR-013 and synchronized README, architecture, runbook, testing and cost-control guidance for the planned Personal Edition three-voice profile; this is an architecture decision only, not an implemented feature.
- Gemini API chỉ được gọi sau khi job checkpoint, approved repaired TextRevision và shared cache đều không reuse được; cache hỏng trở thành safe miss.
- Audit phân biệt `gemini_cache_hit`, `gemini_cache_miss`, `gemini_cache_invalid`, `gemini_api_call` và `gemini_checkpoint_reuse` mà không lưu source text/API key.
- Audio assembly dùng thư mục `render_<generation>` để retry không ghi đè artifact verified cũ.
- Doctor kiểm tra schema version, verified segments và hash blob khi dùng `--deep`.
- App từ chối khởi động nếu DB mới hơn code hoặc migration đã apply bị sửa checksum.

### Verified

- 67 offline tests đạt; JavaScript syntax đạt.
- Live diff API trên chapter 18.649 ký tự hoàn thành khoảng 330 ms và không trả internal path.
- VieNeu v3 Turbo multi-voice smoke: job 3, 3 preset voices, 8 utterance/segment, M4A 22.810 ms.
- Controlled retry render lại một segment trong 2,47 giây và reuse nguyên hash/mtime của 7 segment còn lại.
- Timeline speaker metadata, job voice snapshot, artifact hashes và duration tolerance 1.000 ms đều đạt.
- Backup thật 3.989 file / 60.216.155 byte verify đạt.
- Restore sang data root mới remap 13 path và deep integrity đạt.

## 0.1.0 — 2026-06-23

### Added

- FastAPI UI/API tại cổng 8766.
- EPUB import cho 1.980 chương.
- Content-addressed text storage và TextRevision.
- Gemini punctuation repair theo block với lexical integrity validation.
- VieNeu v3 Turbo segment worker.
- SQLite checkpoint, pause/resume/cancel/retry.
- Artifact cho master WAV, M4A/MP3 và timeline.
- Audio player và cleanup retention.

### Verified

- 8 offline unit tests.
- End-to-end chương 858, 10 segment, M4A 118.710 ms.
- Resume test giữ 9 segment hợp lệ và tạo lại một segment lỗi.
