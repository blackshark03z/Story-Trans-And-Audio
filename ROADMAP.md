# Roadmap

Roadmap mô tả thứ tự đầu tư, không phải cam kết thời gian. Ưu tiên được chọn theo: bảo vệ dữ liệu → khả năng phục hồi → chất lượng audio → tính năng mới.

## M0 — Audio MVP khả dụng (hoàn thành)

- EPUB import, content-addressed text và revision.
- Gemini punctuation repair có lexical validator.
- VieNeu TTS theo segment, checkpoint và resume.
- Một file audio mỗi chương.
- UI chọn khoảng chương và hàng đợi.

## M1 — Hardening

Đã hoàn thành trong P0:

- Schema migration/versioning baseline v1.
- Full backup/verify/restore có manifest.
- Offline recovery tests cho restart/retry/cancel/corruption.

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

## M3 — Speech timing và YouTube Auto Handoff

- Segment-level subtitle chuẩn hóa.
- Forced alignment provider interface.
- Word timestamps tùy chọn.
- Versioned one-chapter filesystem handoff gồm approved text, resolved casting, audio, speech timing và character seed.
- Import verification/smoke contract với `D:\Youtube\Youtube Auto`.

## M4 — YouTube Auto Handoff

- Story Audio kết thúc tại immutable handoff manifest.
- YouTube Auto sở hữu visual scene timeline, visual character bible, prompt, image, subtitle render, compose, metadata và thumbnail.
- Hai codebase độc lập; không có DB coupling hoặc runtime dependency bắt buộc.

## Deferred / Only when needed

- Generic image provider framework hoặc video composer trong Story Audio.
- Metadata/thumbnail pipeline trong Story Audio.
- Multi-user/SaaS, remote worker, distributed locking và generic plugin system.
- Word alignment bắt buộc.
- Usage ledger/dashboard phức tạp.

## Không làm sớm

- Microservices, Redis/Celery hoặc nhiều DB server.
- Nhiều TTS worker trên máy CPU hiện tại.
- Render toàn bộ 1.980 chương tự động không có quota/confirm.
- Word alignment bắt buộc cho Audio MVP.
- Generic plugin system trước khi có adapter thứ hai thật sự.
