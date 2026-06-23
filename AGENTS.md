# Hướng dẫn làm việc với repository

File này dành cho kỹ sư và các phiên Codex tiếp theo. Mục tiêu là giảm thời gian khám phá lại dự án, tránh sửa sai invariant và không tiêu tốn API ngoài ý muốn.

## Thứ tự đọc

1. `PROJECT_STATUS.md` — trạng thái thật và việc tiếp theo.
2. `README.md` — cách chạy và sử dụng.
3. `docs/DECISIONS.md` — những quyết định không nên tự ý đảo ngược.
4. `docs/DATA_MODEL.md` — entity, state và invalidation.
5. Chỉ đọc phần liên quan trong `ARCHITECTURE.md`; không cần nạp toàn bộ khi sửa lỗi nhỏ.

## Bản đồ mã nguồn

```text
story_audio/api.py       HTTP API và lifecycle ứng dụng
story_audio/pipeline.py  Job orchestration, checkpoint, assemble/export
story_audio/epub.py      EPUB parser và import revision
story_audio/text.py      Reflow, QA, lexical validation, chunking
story_audio/gemini.py    Gemini punctuation repair contract
story_audio/gemini_cache.py Shared repair cache, integrity và manifest cleanup
story_audio/tts.py       VieNeu adapter
story_audio/db.py        SQLite schema và connection policy
story_audio/storage.py   Content-addressed text blobs
story_audio/casting.py   Character, immutable casting plan và deterministic utterance
story_audio/text_diff.py Read-only TextRevision block/token diff engine
story_audio/migrations/  Forward-only SQL migrations
story_audio/backup.py    Backup/verify/restore core
story_audio/integrity.py Shared integrity diagnostics
ui/                      UI HTML/CSS/JavaScript
tests/                   Offline unit tests
```

## Invariant bắt buộc

- Không lưu full chapter text trong SQLite. Text nằm trong `data/blobs/text/<prefix>/<sha>.txt`.
- Text revision và artifact đã verify là bất biến; thay đổi tạo revision mới.
- Job pin text/config/voice snapshot; không đổi âm thầm giữa lúc chạy.
- Ứng dụng sở hữu TTS segment, tối đa 256 ký tự với VieNeu v3 Turbo hiện tại.
- Gemini chỉ sửa punctuation/whitespace. Sau sửa, token nguồn phải được khôi phục và lexical validator phải đạt.
- Không đánh dấu artifact hoàn tất trước khi file tồn tại, hash được tính và FFprobe verify.
- Retry phải reuse đơn vị đã verify; không render lại toàn chương nếu chỉ một segment lỗi.
- Không log, commit, trả qua API hoặc lưu DB API key.
- Không để test mặc định gọi Gemini, VieNeu inference hoặc dịch vụ có phí.
- Không xóa dữ liệu người dùng, artifact hoặc revision khi chưa có yêu cầu rõ ràng.

## Lệnh chuẩn

```powershell
# Unit tests offline
$env:PYTHONUTF8='1'
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' -m unittest discover -s tests -v

# Chẩn đoán read-only
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\doctor.py

# Backup / verify / restore
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\backup.py backups\my-backup
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\restore.py backups\my-backup --verify-only
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\restore.py backups\my-backup D:\restore\data

# Chạy ứng dụng
.\run_app.ps1
```

## Trước khi sửa schema

- Đọc mục P0 trong `PROJECT_STATUS.md`.
- Không chỉ sửa `SCHEMA` rồi giả định DB cũ tự cập nhật.
- Phải thêm migration có version và test upgrade từ DB fixture trước đó.
- Cập nhật `docs/DATA_MODEL.md` và `CHANGELOG.md`.

## Definition of Done

- Unit tests offline đạt.
- Không có secret mới trong status/diff/log.
- Resume/retry không làm mất checkpoint.
- File mới có owner rõ ràng trong bản đồ mã nguồn hoặc tài liệu.
- `PROJECT_STATUS.md`, `CHANGELOG.md` và quyết định kiến trúc được cập nhật nếu thay đổi hành vi.
- Smoke test có phí chỉ chạy khi người dùng yêu cầu hoặc thay đổi trực tiếp Gemini/VieNeu pipeline.
