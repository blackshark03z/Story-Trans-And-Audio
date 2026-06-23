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

### Voice casting và backward compatibility

- Schema v3 dùng `voice_override_id` optional; `default_voice_id` vẫn là legacy compatibility field, không xóa hoặc đổi hàng loạt.
- CastingPlan/job đã tạo giữ nguyên `resolved_voice_id`. Retry phải dùng snapshot cũ.
- Three-Voice Profile core và UI casting đã có trong runtime.
- Khi profile được triển khai, đổi narrator/male/female/unknown fallback hoặc character override chỉ áp dụng cho casting/job mới.
- Utterance-level voice override hiện chưa tồn tại; không hướng dẫn người vận hành sửa JSON/DB để giả lập.

### Three-Voice workflow

```text
Create Book Voice Profile
→ preview narrator/male/female/fallback
→ configure character book-default/custom override
→ review effective voice/source/needs-review
→ save and approve casting
→ create job
```

Profile/override edit chỉ áp dụng cho casting plan và job mới. Book chưa có profile hiển thị empty state và không được tự tạo mặc định; legacy override chỉ bị clear khi người dùng chủ động chọn **Use book default** rồi lưu.

### Character Bible import

Chạy dry-run trước khi ghi dữ liệu:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\import_character_bible.py `
  --book-id 1 `
  --file character_bible.json `
  --dry-run
```

Apply chỉ khi dry-run không có invalid/conflict:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\import_character_bible.py `
  --book-id 1 `
  --file character_bible.json `
  --apply
```

Dùng `--json` để lấy structured plan, và `--update-existing` khi muốn cập nhật các field metadata được phép. Import không nhận path từ nội dung JSON, không lưu full JSON trong SQLite, không đổi Book Voice Profile, không tạo casting plan/job và không resolve lại job cũ. `null` trong `voice_override_id` không clear override hiện có.

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

## Backup và restore

Pause job trước; backup mặc định từ chối khi có job active:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\backup.py backups\my-backup
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\restore.py backups\my-backup --verify-only
```

Restore sang thư mục mới:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\restore.py `
  backups\my-backup D:\StoryAudio-Restore\data
```

- Không dùng `--exclude-work` nếu cần bảo toàn checkpoint WAV.
- Không dùng `--allow-active` trừ khi chấp nhận work snapshot có thể không đồng nhất.
- `--overwrite` không xóa destination cũ; nó chuyển thư mục cũ sang `pre-restore-*`.
- EPUB nguồn ngoài `data/` chưa nằm trong backup version 1.

## Khi cần báo lỗi

Thu thập tối thiểu:

- Job ID, chapter number, stage/status.
- `scripts/doctor.py` output.
- Error message trong job/chapter.
- Model/voice/prompt version, không gửi API key.
- Danh sách file liên quan và kích thước, không cần gửi toàn bộ audio/text trước.
## YouTube Auto handoff

Export một completed chapter bằng đúng job snapshot:

```powershell
python scripts\export_youtube_handoff.py --chapter-id 1982 --job-id 3
```

Bundle mặc định nằm trong `data\exports\youtube_auto\`. Chạy lại cùng identity sẽ verify và reuse; `--overwrite` phải được nêu rõ. Exporter copy audio, không symlink và không sửa source artifact.
