# Data Model và Contract

Source of truth cho schema thực thi hiện nằm trong `story_audio/db.py`. File này mô tả ý nghĩa và dependency; không copy nguyên SQL để tránh drift.

## Entity graph

```text
Book
└── Chapter
    ├── TextRevision (raw → reflowed → repaired)
    ├── QA Issue
    └── Artifact

Job
└── JobChapter
    ├── RepairBlock
    ├── Segment
    └── Artifact
```

## Ownership

- `Book/Chapter`: logical EPUB structure.
- `TextRevision`: immutable pointer tới text blob.
- `RepairBlock`: checkpoint Gemini riêng của một job chapter.
- `Segment`: checkpoint VieNeu và WAV tạm.
- `Artifact`: file đã verify như master WAV, timeline hoặc M4A/MP3.
- `Job/JobChapter`: orchestration state, không phải nội dung nguồn.

## State contract

### Job

```text
scheduled → running/repairing/synthesizing/assembling → completed
                      ↘ paused → queued
                      ↘ completed_with_errors
                      ↘ cancelled
```

### Unit checkpoint

```text
pending → running → verified
             ↘ failed → pending (retry)
```

`verified` chỉ hợp lệ khi file/checksum hoặc repaired blob tương ứng tồn tại.

### Artifact

```text
staging → verified → active
                   ↘ stale → soft_deleted → cleaned
```

Hiện implementation tạo record sau verify nên `staging` chưa được persist đầy đủ; đây là điểm cần hoàn thiện trong M1.

## Invalidation matrix

| Thay đổi | Invalidates |
|---|---|
| Raw/reflowed/repaired text | TTS segments, master, export, timeline và mọi downstream |
| Voice/temperature/chunker | TTS segments, master, export, timeline |
| M4A ↔ MP3/bitrate | Chỉ export artifact |
| Punctuation | TTS và downstream dù lexical hash không đổi |
| Visual profile sau này | Prompt, image, video; không invalidates audio |
| Một ảnh sau này | Chỉ final video liên quan |

## File layout

```text
data/app.db
data/blobs/text/<sha-prefix>/<sha>.txt
data/work/job_<id>/chapter_<number>/segments/*.wav
data/output/<book-id>-<slug>/chapter_<number>/job_<id>/
  chapter_master.wav
  chapter.m4a|mp3
  segment_timeline.json
```

Không lưu absolute path trong API contract công khai. DB hiện giữ absolute artifact paths; nếu cần di chuyển project, M1 nên migration sang relative paths.

## Schema evolution rule

Hiện chưa có migration framework. Trước thay đổi schema tiếp theo phải:

1. Thêm `schema_version`.
2. Thêm migration tăng dần, idempotent và transaction-safe.
3. Backup DB trước migration.
4. Test upgrade từ fixture 0.1.0.
5. Không xóa column/data trong cùng release thêm column thay thế.
