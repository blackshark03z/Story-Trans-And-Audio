# Story Audio Personal Edition

Ứng dụng cục bộ chuyển EPUB thành audio theo chương bằng VieNeu-TTS, có Gemini punctuation repair, immutable revision, manual/multi-voice casting và checkpoint cấp segment. Story Audio kết thúc ở audio + speech timing + YouTube Auto Handoff; image/video/metadata thuộc repository YouTube Auto.

Kiến trúc voice Personal Edition dùng ba voice mặc định cấp book (narrator, male dialogue, female dialogue), unknown fallback và optional character override. Core và UI casting đã có trong schema v3.

Current application state: the production backend and existing browser UI are functional and have completed routine chapter production. Active product direction is a modular Daily Production UX: Home, Production, Voice Library, Books And Characters, Audio Library, and Settings, with Production guided by one sequential next-action workflow. This is the target direction and is implemented only as its `DAILY-PROD` roadmap milestones complete.

Canonical target workflow: [docs/DAILY_PRODUCTION_WORKFLOW.md](docs/DAILY_PRODUCTION_WORKFLOW.md).

## Operator quick start

Run these commands from the repository root. They are the only canonical
operator paths for the local production runtime.

| Task | Command |
| --- | --- |
| Start | `./run_app.ps1` |
| Restart | `./scripts/restart_canonical_launcher.ps1` |
| Health / Doctor | `& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\doctor.py` |
| Focused operational checks | `& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' -m unittest tests.test_operational_scripts tests.test_canonical_launcher_restart_helper tests.test_storage_cleanup -v` |
| List safe cleanup candidates | `& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\storage_cleanup.py --dry-run` |

The canonical runtime is `http://127.0.0.1:8772`. `run_app.ps1` is the only
production launcher; the restart helper verifies that it is restarting the
canonical Story Audio process before it acts. Do not use a raw Python command
to start the canonical database.

`storage_cleanup.py` is list-only by default and refuses unknown, tracked,
protected, or DB-referenced paths. Its destructive mode requires an explicit
confirmation and refuses to run while the canonical runtime is listening:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\storage_cleanup.py `
  --execute --confirm DELETE_PROVEN_ORPHANED_STORAGE
```

Never delete or stage `data/`, `backups/`, `runs/`, or
`experiment_b_transcript/` as cleanup. `data/` contains canonical production
metadata and evidence; it is deliberately visible in Git status so it cannot
be hidden accidentally.

Deeper operational detail is in [docs/RUNBOOK.md](docs/RUNBOOK.md); architecture,
data-model, and test references are linked below.

## Chạy

```powershell
.\run_app.ps1
```

Sau đó mở `http://127.0.0.1:8772`.

Runtime canonical hiện tại của Story Audio là `http://127.0.0.1:8772`. Luôn xác minh tiến trình đang chạy bằng `/api/runtime` trước khi thao tác production.

## Quy trình sử dụng

Current supported workflow:

1. Nhập EPUB trong phần **Thư viện**.
2. Chọn sách và kiểm tra nội dung chương.
3. Chọn khoảng **Từ chương → Đến chương**.
4. Trong tab **Character Voices**, import Character Bible JSON nếu có, review dry-run/apply, tạo Book Voice Profile, preview từng slot và chọn nhân vật dùng book default hoặc custom override.
5. Khi cần hỗ trợ xác định người nói, tạo Gemini Speaker Assignment Draft trong **Character Voices**.
6. Review từng row và lưu quyết định row review.
7. Duyệt Speaker Draft bằng approve-only; bước này không tạo Casting Plan, job hoặc audio.
8. Tạo Final Voice Map / Casting Plan draft từ Speaker Draft đã duyệt.
9. Duyệt Casting Plan riêng. Approval không tự tạo job hoặc audio.
10. Chuẩn bị job audio riêng để pin Text Revision, Casting Plan và voice snapshot mà chưa render.
11. Bắt đầu render bằng hành động riêng khi người vận hành đã sẵn sàng.
12. Theo dõi checkpoint, pause/resume hoặc retry phần lỗi.

Target daily-production workflow:

1. Open **Home** and continue the current production scope.
2. Use **Production** to select chapter scope, resolve only required exceptions, review the Final Voice Map, prepare, explicitly start render, and complete Human QA.
3. Use **Voice Library** only for reusable voice management and previews.
4. Use **Books And Characters** only for book, Character Bible, narrator/default/fallback voice policy, and character override setup.
5. Use **Audio Library** for completed output playback, details, download, and QA/remediation entry.
6. Use **Settings** for provider, runtime, diagnostics, paths, and maintenance.

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
- [Roadmap](ROADMAP.md) - chiến lược và phase hiện tại
- [Next Task](NEXT_TASK.md) - hành động hoặc quyết định đang được ủy quyền
- [Documentation source-of-truth policy](DOCUMENTATION_SOURCES.md)
- [Daily Production workflow](docs/DAILY_PRODUCTION_WORKFLOW.md)
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
