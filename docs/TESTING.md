# Testing Strategy

Mục tiêu là bắt lỗi phục hồi và dữ liệu với chi phí thấp nhất. Test mặc định phải offline, nhanh và không nạp model.

## Tầng 1 — Offline unit tests (mỗi thay đổi)

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' -m unittest discover -s tests -v
node --check ui\app.js
```

Không được gọi Gemini, VieNeu inference hoặc mạng. Dùng fixture nhỏ cho:

- Reflow và lexical identity.
- Chunk limits.
- SQLite state transition.
- Artifact invalidation.
- EPUB edge cases.

## Tầng 2 — Integration local, không phí

- Import EPUB fixture nhỏ.
- Fake Gemini adapter trả punctuation sửa đúng/sai.
- Fake TTS adapter tạo WAV ngắn xác định trước.
- FFmpeg assemble/verify.
- Kill/restart worker giữa các stage.
- Corrupt/missing segment rồi resume.

Đã có coverage offline cho:

- Legacy/v1/v2 DB → schema version 3, legacy character override và future-version/checksum guards.
- Startup chuyển job dở sang `interrupted`.
- Retry reuse segment verified và chỉ gọi fake TTS cho segment pending.
- Cancel được quan sát trước inference.
- Backup manifest/hash, restore sang data root mới và no-overwrite guard.
- Corrupted backup/artifact được phát hiện.
- Manual/multi-voice casting, immutable resolved voice snapshot và verified-segment reuse.
- Shared Gemini cache hit/miss/corruption/cleanup.
- Story Audio Handoff V1 single/multi-voice, hash/path/duration và immutable export.

OS-level kill-process và FFmpeg failure injection vẫn là khoảng trống M1.

## Tầng 3 — Paid/slow smoke test (chỉ khi cần)

Chỉ chạy khi thay đổi `gemini.py`, `tts.py`, prompt contract, audio assembly hoặc model version.

Fixture mặc định:

- Một đoạn synthetic không chứa nội dung riêng tư cho Gemini.
- Một chương ngắn hoặc đoạn 1–2 segment cho VieNeu.
- Không chạy toàn bộ sách.
- Ghi model/prompt/voice/version vào test report, không ghi key.

Baseline hiện tại: 78 test offline; chương 858 đã hoàn thành 10 segment và M4A 118.710 ms. Handoff smoke job 3/chapter 1982 đã tạo video YouTube Auto 22,826 giây từ audio 22,810 giây.

Three-Voice UI smoke dùng isolated book 4/chapter 1983: preview Ngọc Lan/Gia Bảo/Mỹ Duyên đạt 14,16–15,12 giây; jobs 4–5 đạt 24.650/26.090 ms với narrator, male, female, unknown fallback và character override. Controlled retry job 4 render lại đúng segment Gia Bảo và reuse 7 segment verified; timeline mới chứa resolution metadata. Chưa đánh giá cảm nhận bằng tai trong smoke tự động.

## Release gate

- Unit tests đạt.
- Doctor không có `ERROR`.
- Không có active artifact thiếu file.
- DB `PRAGMA quick_check` trả `ok`.
- Migration/backup test đạt nếu schema đổi.
- Một end-to-end smoke đạt nếu Gemini/TTS contract đổi.
- `PROJECT_STATUS.md` và `CHANGELOG.md` được cập nhật.

## Regression cases phải giữ

- EPUB có hard-wrap giữa `không` và `ít.`.
- Gemini viết hoa chữ đầu nhưng token output phải trở lại đúng nguồn.
- Gemini thêm một từ phải bị chặn.
- Voice ID Unicode phải được giữ nguyên NFC.
- Retry segment có attempt count cũ phải thực sự chạy lại.
- 9/10 segment verified thì chỉ segment lỗi được tạo lại.
- FFmpeg lỗi không được gọi lại VieNeu cho segment hợp lệ.
- Casting/job cũ không đổi voice khi character override hoặc Book Voice Profile thay đổi.
- Resolver Three-Voice phải deterministic cho narrator, male, female, explicit override và unknown/needs-review.
- UI không tự clear legacy override, không duplicate resolver JavaScript và không tạo plan/job khi chỉ xem effective voice.
