# Changelog

Ghi thay đổi hành vi người dùng, schema, artifact contract và vận hành. Không dùng file này thay cho `PROJECT_STATUS.md`.

## Unreleased

### Added

- Book Voice Profile với narrator, male dialogue, female dialogue và configurable unknown fallback.
- Optional character voice override, manual gender metadata và deterministic voice resolver có resolution source/needs-review.
- Minimal profile/override/resolve API để chuẩn bị cho UI task tiếp theo.
- Book Voice Profile UI với empty/invalid state, bốn preview slot, fallback policy và profile version.
- Character Manager hỗ trợ gender, Use book default/Use custom voice, effective voice và resolution source.
- Manual Casting hiển thị resolved voice, gender và needs-review; preview resolution read-only không tạo plan/job.

### Changed

- Casting plan/job mới snapshot resolved preset, resolution source và Book Voice Profile ID/version; retry tiếp tục dùng snapshot cũ.
- Migration `0003_three_voice_profile` bảo toàn `characters.default_voice_id` và sao chép giá trị cũ thành legacy override.
- Segment timeline mới mang resolution source, resolved gender, needs-review và profile ID/version từ immutable job snapshot.

### Verified

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
