# Roadmap

Roadmap mô tả thứ tự đầu tư, không phải cam kết thời gian. Ưu tiên được chọn theo: bảo vệ dữ liệu → khả năng phục hồi → chất lượng audio → tính năng mới.

## M0 — Audio MVP khả dụng (hoàn thành)

- EPUB import, content-addressed text và revision.
- Gemini punctuation repair có lexical validator.
- VieNeu TTS theo segment, checkpoint và resume.
- Một file audio mỗi chương.
- UI chọn khoảng chương và hàng đợi.

## M1 — Hardening

Điều kiện hoàn thành:

- DB cũ nâng cấp qua migration, không mất dữ liệu.
- Backup restore được trên một thư mục mới và hash khớp.
- Kill process ở Gemini/TTS/assemble đều resume đúng.
- UI hiển thị chính xác block/segment lỗi và hành động retry.
- Doctor không báo integrity error hoặc missing active artifact.

Hạng mục:

- Schema migration/versioning.
- Backup/restore + manifest.
- Integration/recovery test harness.
- Structured logging và diagnostic bundle không chứa secret/text đầy đủ.
- Cleanup dry-run, disk quota và orphan collector.

## M2 — Chất lượng text và audio

- Voice preview.
- Side-by-side punctuation diff.
- Shared Gemini repair cache.
- QA rule editor/versioning.
- Profile giọng/render có snapshot rõ ràng.
- SRT/VTT từ segment timeline.
- Đánh giá audio heuristic và sample review workflow.

## M3 — Alignment và subtitle

- Segment-level subtitle chuẩn hóa.
- Forced alignment provider interface.
- Word timestamps tùy chọn.
- Subtitle style/export profile.
- Invalidation đúng khi post-process speed thay đổi.

## M4 — Visual pipeline

- Book-level character/location bible.
- Scene plan 12–30 giây/ảnh.
- Visual profile cho tiên hiệp.
- Image provider adapters và perceptual duplicate check.
- Reuse timeline/prompt/composer từ `D:\Youtube\Youtube Auto`.

## M5 — Video và vận hành dài hạn

- FFmpeg compose, subtitle burn-in và final verification.
- Metadata/thumbnail.
- Remote worker hoặc resource scheduler khi thật sự cần.
- Batch scheduling theo ngày và notification.

## Không làm sớm

- Microservices, Redis/Celery hoặc nhiều DB server.
- Nhiều TTS worker trên máy CPU hiện tại.
- Render toàn bộ 1.980 chương tự động không có quota/confirm.
- Word alignment bắt buộc cho Audio MVP.
- Generic plugin system trước khi có adapter thứ hai thật sự.
