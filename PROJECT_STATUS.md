# Trạng thái dự án

**Cập nhật:** 2026-06-24 (Asia/Saigon)
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
- Schema migration: version 4 (`0004_character_bible`), checksum-locked.
- Offline tests: 92 test đạt.
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
- Three-Voice UI smoke: isolated book 4/chapter 1983, jobs 4–5, 8 utterance; profile v1→v2 và controlled retry giữ snapshot cũ.
- Preview thật: Ngọc Lan 14,16s, Gia Bảo 14,48s, Mỹ Duyên 15,12s; fallback reuse Ngọc Lan cache.
- Three-Voice real-TTS: job 4 dài 24.650 ms, job 5 dài 26.090 ms; narrator/male/female/unknown/override và timeline resolution metadata đều đạt.
- Character Bible Import Core: JSON V1 dry-run/apply CLI + backend API, schema v4, alias/external-key/role/metadata/provenance storage, idempotent re-import.
- Character Bible smoke: isolated book 5, dry-run create 3, first apply create 3 + 2 aliases, second apply match 3/no writes; API read and voice resolution verified.
- Doctor deep after schema v4: SQLite quick check OK, `critical_errors=0`; jobs #3/#4/#5 casting snapshot hashes unchanged.

## Shared Gemini cache contract

- Key pin source SHA-256, model, prompt version, punctuation-only contract, block splitter, lexical validator và generation settings.
- Thứ tự reuse: approved repaired TextRevision → job repair-block checkpoint → shared cache → Gemini API.
- Cache hit luôn verify manifest/key/blob/hash/count và lexical tokens; entry hỏng/mất là safe miss.
- Manifest nằm trong `data/cache/gemini_repairs/`; repaired payload dùng text blob bất biến. Cleanup TTL/quota chỉ xóa manifest và mặc định dry-run.

## Quyết định voice casting Personal Edition

Audio casting mặc định dùng ba nhóm voice cấp book: narrator, male dialogue và female dialogue; unknown fallback mặc định về narrator. Character identity tách khỏi voice identity và chỉ nhân vật quan trọng mới có optional voice override. Resolver deterministic và snapshot profile/version/source vào casting/job mới; plan/job cũ không bị resolve lại.

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
- [x] Three-Voice Profile Core: book profile, optional character override, gender-aware resolver và immutable job snapshot.
- [x] Three-Voice Profile UI and Casting Integration: profile/preview, default/custom character voice và effective resolution trong Manual Casting.
- [x] Book-level Character Bible Import Core: JSON schema V1, dry-run/apply, deterministic matching/conflict detection, idempotency, CLI/API and Doctor checks.

## Hạn chế hiện tại

- Gemini và TTS chạy tuần tự trong một orchestration worker; chưa prefetch 2–5 chương.
- Shared Gemini cache vẫn chạy tuần tự; hai process có thể cùng gọi Gemini trước khi atomic write cùng một key (kết quả cuối vẫn hợp lệ).
- Cleanup cache hiện có CLI dry-run/apply nhưng chưa có quota/dashboard UI; text blob không bị xóa theo cache manifest.
- Text diff giới hạn 500.000 ký tự kết hợp; payload trên 50.000 ký tự có warning và collapse mặc định.
- Cleanup chưa có dry-run/quota dashboard trên UI.
- Manual casting chưa có AI speaker detection, emotion control hoặc voice cloning theo đúng phạm vi MVP.
- Automatic speaker/gender assignment chưa triển khai; gender hiện là dữ liệu manual, unknown được đánh dấu `needs_review` trong resolution metadata.
- Character Bible Import Core chưa có UI upload/import và chưa có Gemini speaker assignment; task này chỉ import JSON core.
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

Các hạng mục vận hành/quota và alignment không cấp thiết được tập trung trong `ROADMAP.md` thay vì lặp backlog tại đây.

### P2 — Personal Edition voice

- [x] YouTube Auto Handoff V1.
- [x] Three-Voice Profile Core.
- [x] Three-Voice Profile UI and Casting Integration.
- [x] Book-level Character Bible Import.
- [ ] Character Bible UI and Handoff Integration.
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
| 2026-06-23 | Three-Voice Profile Core | Schema v3; profile/override/resolver/snapshot; 73 test offline và Doctor deep đạt |
| 2026-06-23 | Three-Voice UI + Casting | Profile/preview/default-custom/effective voice; jobs 4–5 real TTS; 78 test offline đạt |
| 2026-06-23 | Multi-voice real-TTS smoke | Job 3; 3 voices; 8/8 segment; retry 1 segment và reuse 7; M4A 22.810 ms |
| 2026-06-23 | Text Revision Diff | Structured read-only API; Inline/Side-by-side; 50 tests; chapter 18.649 chars ≈330 ms live API |
| 2026-06-23 | Shared Gemini repair cache | Filesystem manifest + text blob; lexical revalidation; corrupt-as-miss; cleanup/doctor; 60 tests |
| 2026-06-23 | YouTube Auto Handoff V1 | Job 3/chapter 1982; 22.810s M4A; 8 timing items; 2 character seeds; imported/composed final 22.826s |
| 2026-06-24 | Character Bible Import Core | Schema v4; 92 offline tests; smoke book 5 dry-run/apply/apply-lại; Doctor deep critical_errors=0 |
