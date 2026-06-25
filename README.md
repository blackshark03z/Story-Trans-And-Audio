# Story Audio Personal Edition

Ứng dụng cục bộ chuyển EPUB thành audio theo chương bằng VieNeu-TTS, có Gemini punctuation repair, immutable revision, manual/multi-voice casting và checkpoint cấp segment. Story Audio kết thúc ở audio + speech timing + YouTube Auto Handoff; image/video/metadata thuộc repository YouTube Auto.

Kiến trúc voice Personal Edition dùng ba voice mặc định cấp book (narrator, male dialogue, female dialogue), unknown fallback và optional character override. Core và UI casting đã có trong schema v3.

## Chạy

```powershell
.\run_app.ps1
```

Sau đó mở `http://127.0.0.1:8766`.

## Quy trình sử dụng

1. Nhập EPUB trong phần **Thư viện**.
2. Chọn sách và kiểm tra nội dung chương.
3. Chọn khoảng **Từ chương → Đến chương**.
4. Trong tab **Character Voices**, import Character Bible JSON nếu có, review dry-run/apply, tạo Book Voice Profile, preview từng slot và chọn nhân vật dùng book default hoặc custom override.
5. Khi cần hỗ trợ xác định người nói, tạo Gemini Speaker Assignment Draft trong **Character Voices**, review confidence/alternatives, preview effective voice rồi approve các quyết định đã chọn thành Casting Plan revision mới.
6. Approval không tự tạo job hoặc audio. Sau khi Casting Plan đúng, người dùng chủ động tạo job như bình thường.
7. Chọn chế độ Gemini punctuation, định dạng rồi bấm **Kiểm tra phạm vi**.
8. Thêm vào hàng đợi; có 10 giây để hủy nếu chọn nhầm.
9. Theo dõi checkpoint, pause/resume hoặc retry phần lỗi.

## API key

Ứng dụng ưu tiên biến môi trường `GEMINI_API_KEY`, sau đó tìm:

```text
secrets/gemini_api_key.txt
gemini_api_key.txt
```

Các đường dẫn này đã bị Git bỏ qua. Key không được lưu vào SQLite hoặc trả về UI.

## Dữ liệu

```text
data/app.db            SQLite metadata/checkpoint
data/blobs/text/       Text bất biến theo SHA-256
data/blobs/speaker_assignment/  Speaker draft JSON bất biến theo SHA-256
data/work/             Segment WAV đang xử lý
data/output/           Master WAV, M4A/MP3 và timeline
data/exports/youtube_auto/  Immutable Handoff V1 bundles
```

Text chương không được lưu đầy đủ trong SQLite. DB chỉ lưu revision metadata và đường dẫn blob. Resolved voice của job/casting cũ là snapshot bất biến và không được resolve lại khi cấu hình mặc định thay đổi.

## Tài liệu điều hành

- [Trạng thái hiện tại](PROJECT_STATUS.md)
- [Roadmap](ROADMAP.md)
- [Quyết định kiến trúc](docs/DECISIONS.md)
- [Data model](docs/DATA_MODEL.md)
- [Testing strategy](docs/TESTING.md)
- [Chính sách kiểm soát chi phí](docs/COST_CONTROL.md)
- [Runbook vận hành và sửa lỗi](docs/RUNBOOK.md)
- [Hướng dẫn cho phiên làm việc tiếp theo](AGENTS.md)
- [Changelog](CHANGELOG.md)

Chẩn đoán read-only:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\doctor.py
```

## Backup và restore

Nên pause job trước khi backup. Mặc định backup gồm DB, text blobs, output, YouTube Auto exports và WAV checkpoint:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\backup.py backups\my-backup
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\restore.py backups\my-backup --verify-only
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\restore.py backups\my-backup D:\StoryAudio-Restore\data
```

Restore không ghi đè destination hiện hữu. Dùng `--overwrite` chỉ khi có chủ ý; destination cũ vẫn được giữ dưới tên `pre-restore-*`.
