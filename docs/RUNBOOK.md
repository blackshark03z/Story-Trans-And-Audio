# Operations và Repair Runbook

## Start

```powershell
cd 'D:\Youtube\Story Trans And Audio'
.\run_app.ps1
```

UI: `http://127.0.0.1:8766`
VieNeu Gradio riêng: `http://127.0.0.1:7861`

## Health check

```powershell
Invoke-RestMethod http://127.0.0.1:8766/api/config
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\doctor.py
```

Logs:

```text
logs/app.stderr.log
logs/app.stdout.log
```

Không copy log ra ngoài trước khi kiểm tra secret/path/text nhạy cảm.

## Stop an toàn

- Pause/cancel job từ UI trước.
- Dừng process đang listen cổng 8766 sau khi worker về ranh giới segment.
- Không xóa `.partial`, WAL hoặc `data/work` khi process còn chạy.

## Lỗi thường gặp

### Chưa có Gemini key

- Đặt `GEMINI_API_KEY`, hoặc dùng `secrets/gemini_api_key.txt`.
- UI chỉ báo configured/not configured.
- Resume job; block verified không bị gọi lại.

### Gemini lexical integrity failed

- Xem repaired block và source diff trong diagnostic tương lai.
- Không sửa DB status trực tiếp để bỏ qua validator.
- Retry một lần; nếu tiếp tục lỗi, dùng `needs_review` hoặc mode `off` cho chapter revision mới.

### Voice not found

- Tải lại danh sách preset voice.
- Không sửa voice giữa job đang chạy; tạo job revision mới.
- API hiện validate voice trước khi tạo job.

### Job bị interrupted

- Startup chuyển job đang chạy thành `interrupted`.
- Worker tự nhận lại, verify file và tiếp tục.
- Nếu không chạy, dùng Resume/Retry; không xóa segment đã verify.

### FFmpeg/FFprobe lỗi

- Chạy `ffmpeg -version` và `ffprobe -version`.
- Giữ segment WAV; chỉ retry assemble/export.
- Không gọi lại VieNeu nếu segment còn hợp lệ.

### Hết dung lượng

- Pause queue.
- Chạy doctor để xem dung lượng.
- Cleanup chỉ segment của chapter đã hoàn tất và hết retention.
- Không xóa active master/audio/timeline.

### Active artifact thiếu file

- Doctor sẽ báo ERROR.
- Đánh dấu artifact stale/failed qua repair tool tương lai; hiện không chỉnh DB thủ công nếu chưa backup.
- Re-export từ master nếu master còn; nếu không, resume từ segment.

## Backup tạm thời trước khi có backup command

Phương án an toàn nhất hiện tại:

1. Pause/cancel queue và dừng app.
2. Copy toàn bộ `data/` sang vị trí backup cùng filesystem hoặc ổ khác.
3. Copy `ARCHITECTURE.md`, `PROJECT_STATUS.md` và cấu hình không chứa secret.
4. Chạy doctor trên bản gốc sau khi mở lại.

Không backup riêng `app.db` mà bỏ `data/blobs`, vì revision sẽ mất nội dung.

## Khi cần báo lỗi

Thu thập tối thiểu:

- Job ID, chapter number, stage/status.
- `scripts/doctor.py` output.
- Error message trong job/chapter.
- Model/voice/prompt version, không gửi API key.
- Danh sách file liên quan và kích thước, không cần gửi toàn bộ audio/text trước.
