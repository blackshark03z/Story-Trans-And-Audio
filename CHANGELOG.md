# Changelog

Ghi thay đổi hành vi người dùng, schema, artifact contract và vận hành. Không dùng file này thay cho `PROJECT_STATUS.md`.

## Unreleased

- Thêm bộ tài liệu điều hành, testing, data model và runbook.
- Thêm công cụ chẩn đoán read-only `scripts/doctor.py`.

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
