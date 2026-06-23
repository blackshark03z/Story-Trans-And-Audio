# Trạng thái dự án

**Cập nhật:** 2026-06-23 (Asia/Saigon)
**Milestone:** Audio MVP + Gemini punctuation repair
**Trạng thái:** Hoạt động cục bộ tại `http://127.0.0.1:8766`

Đây là nguồn sự thật ngắn gọn về tiến độ. Sau mỗi thay đổi đáng kể, cập nhật file này thay vì buộc người tiếp theo đọc lịch sử chat hoặc toàn bộ kiến trúc.

## Baseline đã xác minh

- EPUB: `Quang_Am_Chi_Ngoai.epub`.
- Import: 1 sách, 1.980 chương, khoảng 12,6 triệu ký tự.
- Storage: text blobs theo SHA-256; SQLite chỉ giữ metadata/path.
- QA import: 600 issue được ghi để review.
- Gemini key: được nhận diện; không lưu trong DB/log.
- VieNeu: v3 Turbo CPU/ONNX, 10 preset voice.
- FFmpeg/FFprobe: hoạt động.
- Schema migration: version 2 (`0002_character_voice`), checksum-locked.
- Offline tests: 67 test đạt.
- End-to-end smoke: chương 858, giọng Ngọc Lan, Gemini `all_selected`.
- Kết quả smoke: 10/10 segment, M4A dài 118.710 ms, artifact active.
- Multi-voice real-TTS smoke: isolated book 3 / chapter 1982, casting plan 2, job 3.
- Kết quả multi-voice: Ngọc Lan + Gia Bảo + Thái Sơn; 8 utterance/8 segment; M4A sau retry 22.810 ms.
- Controlled retry: render lại đúng segment 20 trong 2,47 giây; 7 segment còn lại giữ nguyên hash/mtime.
- Audio signal check: không có silence trên 0,8 giây ở -45 dB; mean volume ba voice lệch tối đa 3,2 dB.
- Backup smoke: 3.989 file, 60.216.155 byte, manifest/hash/SQLite verify đạt.
- Restore smoke: sang data root mới, 13 đường dẫn được remap, deep integrity đạt.
- Shared Gemini cache benchmark local: chapter 858/784/363 (1.958/6.198/18.641 ký tự) hit + hash + lexical validation lần lượt khoảng 22/44/121 ms; không gọi mạng.
- Fake pipeline một block: miss + lưu revision khoảng 66 ms; job/chapter thứ hai shared-cache hit khoảng 54 ms; fake Gemini chỉ được gọi một lần.

## Shared Gemini cache contract

- Key pin source SHA-256, model, prompt version, punctuation-only contract, block splitter, lexical validator và generation settings.
- Thứ tự reuse: approved repaired TextRevision → job repair-block checkpoint → shared cache → Gemini API.
- Cache hit luôn verify manifest/key/blob/hash/count và lexical tokens; entry hỏng/mất là safe miss.
- Manifest nằm trong `data/cache/gemini_repairs/`; repaired payload dùng text blob bất biến. Cleanup TTL/quota chỉ xóa manifest và mặc định dry-run.

## Quyết định voice casting Personal Edition

Audio casting mặc định sẽ dùng ba nhóm voice cấp book: narrator, male dialogue và female dialogue; unknown fallback mặc định về narrator. Character identity tách khỏi voice identity và chỉ nhân vật quan trọng mới có optional voice override. Quyết định này đã được chốt trong ADR, nhưng Book Voice Profile và resolver chưa triển khai.

## Chức năng đã hoàn thành

- [x] Import EPUB và SHA deduplication.
- [x] Sửa số chương sai dựa trên spine/href.
- [x] Raw/reflowed/repaired TextRevision.
- [x] Lossless hard-wrap reflow và QA issue.
- [x] Gemini punctuation repair theo block.
- [x] Khôi phục exact token spelling/casing từ nguồn.
- [x] Lexical integrity validation.
- [x] Chọn một chương hoặc khoảng từ–đến.
- [x] Chọn preset voice, Gemini mode và M4A/MP3.
- [x] Cửa sổ undo 10 giây.
- [x] Checkpoint Gemini block và TTS segment.
- [x] Pause, resume, cancel và retry.
- [x] Master WAV, audio export và segment timeline.
- [x] Artifact/revision và dependency cơ bản.
- [x] Audio player trong chapter dialog.
- [x] Cleanup segment sau retention 24 giờ.
- [x] Schema version và migration runner tự động khi startup.
- [x] Fail-safe khi DB mới hơn code hoặc checksum migration bị đổi.
- [x] Backup/verify/restore có manifest và SQLite snapshot nhất quán.
- [x] Recovery tests offline cho restart, retry, cancel và artifact corruption.
- [x] Diagnostic UI ba cấp cho job, chapter và segment; retry riêng phần lỗi.
- [x] Voice preview preset 10–20 giây với file cache độc lập, không tạo job/artifact.
- [x] Character Voice MVP: character manager, manual casting revision và multi-voice render.
- [x] Real VieNeu multi-voice smoke và controlled retry/reuse verification.
- [x] Text Revision Diff raw/reflowed/repaired với Inline và Side-by-side UI.
- [x] Shared Gemini repair cache theo source/model/prompt/repair contract, có lexical revalidation và cleanup dry-run.
- [x] Story Audio → YouTube Auto Handoff V1 một chương, manifest SHA-256, speech timing và character seed.

## Hạn chế hiện tại

- Gemini và TTS chạy tuần tự trong một orchestration worker; chưa prefetch 2–5 chương.
- Shared Gemini cache vẫn chạy tuần tự; hai process có thể cùng gọi Gemini trước khi atomic write cùng một key (kết quả cuối vẫn hợp lệ).
- Cleanup cache hiện có CLI dry-run/apply nhưng chưa có quota/dashboard UI; text blob không bị xóa theo cache manifest.
- Text diff giới hạn 500.000 ký tự kết hợp; payload trên 50.000 ký tự có warning và collapse mặc định.
- Cleanup chưa có dry-run/quota dashboard trên UI.
- Manual casting chưa có AI speaker detection, emotion control hoặc voice cloning theo đúng phạm vi MVP.
- Book-level Three-Voice Profile chưa triển khai; `characters.default_voice_id` hiện tại vẫn là voice bắt buộc và sau này phải được bảo toàn như legacy override.
- Automatic speaker/gender assignment và unknown `needs_review` chưa triển khai.
- Loudness giữa preset có chênh nhẹ (smoke đo tối đa 3,2 dB mean); chưa normalization theo đúng phạm vi.
- Backup là full snapshot, chưa incremental/compress và có thể lớn khi thư viện tăng.
- Restore remap artifact/work paths trong data root nhưng không đóng gói EPUB nguồn nằm ngoài `data/`.
- Recovery test dùng fake TTS và startup state transition; chưa có OS-level kill-process harness.
- Story Audio không tự xây image/video/metadata/thumbnail; các bước này thuộc YouTube Auto qua handoff bundle.
- Handoff V1 chỉ hỗ trợ một chapter và segment-level timing; chưa có forced word alignment.
- Worker là một thread trong API process; chưa tách service/process riêng.

## Ưu tiên tiếp theo

### P0 — Trước khi thêm tính năng lớn

- [x] Thêm database schema version và migration runner.
- [x] Thêm backup/restore có manifest và integrity verification.
- [x] Thêm integration tests cho restart, retry, cancel và artifact corruption.
- [x] Thêm job/chapter/segment diagnostic UI để người dùng thấy lỗi cụ thể và retry an toàn.

### P1 — Hoàn thiện Audio MVP

- [x] Voice preview 10–20 giây.
- [x] Text diff raw → reflowed → repaired.
- [x] Gemini cache dùng chung theo source hash + model + prompt version.
- [ ] Disk estimate chính xác và cleanup dry-run.
- [ ] Usage ledger, daily batch cap và Gemini soft budget cảnh báo.
- [ ] Export SRT/VTT từ segment timeline.

### P2 — Personal Edition voice

- [x] YouTube Auto Handoff V1.
- [ ] Three-Voice Profile Core.
- [ ] Three-Voice Profile UI and Casting Integration.
- [ ] Book-level Character Bible Import.
- [ ] Gemini speaker assignment draft khi thực sự cần.
- [ ] Real end-to-end chapter video review.

## Quy tắc cập nhật tiến độ

- Chỉ đánh dấu `[x]` sau khi có test hoặc artifact xác minh.
- Việc chưa rõ phạm vi đưa vào `ROADMAP.md`, không nhét vào P0.
- Bug đang ảnh hưởng dữ liệu hoặc resume phải nằm trong Hạn chế hiện tại.
- Quyết định thay đổi invariant phải ghi thêm vào `docs/DECISIONS.md`.
- Thay đổi phát hành hoặc hành vi người dùng phải thêm vào `CHANGELOG.md`.

## Nhật ký milestone

| Ngày | Milestone | Bằng chứng |
|---|---|---|
| 2026-06-23 | Audio MVP đầu tiên | Import 1.980 chương; job #1 completed |
| 2026-06-23 | Gemini contract smoke | Sửa punctuation, token nguồn được bảo toàn |
| 2026-06-23 | Resume theo segment | Reuse 9/10 segment và chỉ tạo lại segment lỗi |
| 2026-06-23 | P0 hardening | Schema v1; backup/restore thật và 18 test offline đạt |
| 2026-06-23 | M2 Diagnostic UI | Job/chapter/segment diagnostics; retry giữ nguyên verified segment; 23 test offline đạt |
| 2026-06-23 | M2 Voice Preview | Preset preview cache theo voice/text/settings/engine; fake TTS; 28 test offline đạt |
| 2026-06-23 | M2 Character Voice MVP | Schema v2; manual casting; multi-voice snapshot/segments/timeline; 38 test offline đạt |
| 2026-06-23 | Multi-voice real-TTS smoke | Job 3; 3 voices; 8/8 segment; retry 1 segment và reuse 7; M4A 22.810 ms |
| 2026-06-23 | Text Revision Diff | Structured read-only API; Inline/Side-by-side; 50 tests; chapter 18.649 chars ≈330 ms live API |
| 2026-06-23 | Shared Gemini repair cache | Filesystem manifest + text blob; lexical revalidation; corrupt-as-miss; cleanup/doctor; 60 tests |
| 2026-06-23 | YouTube Auto Handoff V1 | Job 3/chapter 1982; 22.810s M4A; 8 timing items; 2 character seeds; imported/composed final 22.826s |
