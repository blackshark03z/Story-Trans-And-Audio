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
- Offline tests: 8 test đạt.
- End-to-end smoke: chương 858, giọng Ngọc Lan, Gemini `all_selected`.
- Kết quả smoke: 10/10 segment, M4A dài 118.710 ms, artifact active.

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

## Hạn chế hiện tại

- Gemini và TTS chạy tuần tự trong một orchestration worker; chưa prefetch 2–5 chương.
- Gemini cache hiện gắn với `job_chapter`; chưa reuse theo content hash giữa hai job khác nhau.
- Chưa có schema migration framework/version table. Đây là rủi ro lớn nhất trước khi đổi DB.
- Chưa có backup/restore command được kiểm thử.
- UI chưa có voice preview audio, diff trực quan hoặc màn hình chi tiết lỗi theo block/segment.
- Cleanup chưa có dry-run/quota dashboard trên UI.
- Chưa có integration test tự động cho kill/restart/pause/cancel.
- Chưa có SRT/VTT, forced alignment, image hoặc video trong MVP.
- Worker là một thread trong API process; chưa tách service/process riêng.

## Ưu tiên tiếp theo

### P0 — Trước khi thêm tính năng lớn

- [ ] Thêm database schema version và migration runner.
- [ ] Thêm backup/restore có manifest và integrity verification.
- [ ] Thêm integration tests cho restart, retry, cancel và artifact corruption.
- [ ] Thêm job/chapter diagnostic UI để người dùng thấy lỗi cụ thể.

### P1 — Hoàn thiện Audio MVP

- [ ] Voice preview 10–20 giây.
- [ ] Text diff raw → reflowed → repaired.
- [ ] Gemini cache dùng chung theo source hash + model + prompt version.
- [ ] Disk estimate chính xác và cleanup dry-run.
- [ ] Usage ledger, daily batch cap và Gemini soft budget cảnh báo.
- [ ] Export SRT/VTT từ segment timeline.

### P2 — Sau khi Audio MVP ổn định

- [ ] Word alignment tùy chọn.
- [ ] Scene planning và visual bible.
- [ ] Image provider adapter.
- [ ] Video composition từ các phần tái sử dụng của `Youtube Auto`.

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
