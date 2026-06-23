# Data Model và Contract

Source of truth cho schema thực thi hiện nằm trong `story_audio/db.py`. File này mô tả ý nghĩa và dependency; không copy nguyên SQL để tránh drift.

## Entity graph

```text
Book
├── Character
└── Chapter
    ├── TextRevision (raw → reflowed → repaired)
    ├── CastingPlanRevision → CastingPlanCharacter
    ├── QA Issue
    └── Artifact

Job
└── JobChapter
    ├── RepairBlock
    ├── Segment
    └── Artifact

SchemaMigration
└── version + name + checksum + applied_at
```

## Ownership

- `Book/Chapter`: logical EPUB structure.
- `TextRevision`: immutable pointer tới text blob.
- `RepairBlock`: checkpoint Gemini riêng của một job chapter.
- `Segment`: checkpoint VieNeu và WAV tạm.
- `Artifact`: file đã verify như master WAV, timeline hoặc M4A/MP3.
- `Job/JobChapter`: orchestration state, không phải nội dung nguồn.
- `SchemaMigration`: lịch sử schema bất biến; checksum ngăn sửa migration đã phát hành.
- `Character`: nhân vật thuộc một book, trỏ tới preset voice mặc định cho plan mới.
- `CastingPlanRevision`: JSON blob bất biến pin TextRevision và offset utterance; SQLite chỉ giữ metadata/hash/path.
- `JobChapter.voice_snapshot_json`: snapshot narrator/character voices và utterance assignment tại lúc tạo job.
- `Segment`: với multi-voice còn pin utterance, role, character, resolved voice và synthesis hash.

## Character Voice contract

```text
Approved TextRevision
  → CastingPlanRevision (draft → approved → archived)
  → immutable Job/JobChapter voice snapshot
  → speaker-bounded TTS Segment
  → master/export/timeline artifact
```

- Casting plan không sao chép full chapter text; utterance dùng offsets và text hash trỏ vào TextRevision.
- Approved plan không được ghi đè. Chỉnh casting tạo `plan_revision` mới.
- Default character voice chỉ ảnh hưởng plan mới; plan/job cũ giữ `resolved_voice_id` snapshot.
- Không segment nào chứa text từ hai speaker. Một utterance có thể sinh nhiều segment cùng voice.

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
| Casting assignment/resolved voice | Multi-voice segments, master, export, timeline; không invalidates TextRevision |
| M4A ↔ MP3/bitrate | Chỉ export artifact |
| Punctuation | TTS và downstream dù lexical hash không đổi |
| Visual profile sau này | Prompt, image, video; không invalidates audio |
| Một ảnh sau này | Chỉ final video liên quan |

## File layout

```text
data/app.db
data/blobs/text/<sha-prefix>/<sha>.txt
data/blobs/casting/<sha-prefix>/<sha>.json
data/cache/gemini_repairs/<key-prefix>/<cache-key>.json
data/exports/youtube_auto/<export-id>/
  handoff.json
  content.md
  audio/narration.<ext>
  speech_timeline.json
  character_seed.json
data/work/job_<id>/chapter_<number>/segments/*.wav
data/output/<book-id>-<slug>/chapter_<number>/job_<id>/render_<generation>/
  chapter_master.wav
  chapter.m4a|mp3
  segment_timeline.json
```

Mỗi lần assemble/retry tạo `render_<generation>` mới. Artifact verified cũ không bị ghi đè;
active pointer chỉ chuyển sang export generation mới sau khi verify.

## Shared Gemini repair cache

Cache là lớp tăng tốc có thể xóa hoàn toàn, không phải entity nguồn sự thật trong SQLite. Mỗi manifest schema v1 chứa canonical identity, cache-key SHA-256, source/repaired blob path và hash, character count, thời điểm tạo và trạng thái lexical validation. Identity gồm source hash, Gemini model, prompt version, repair contract version, block strategy version, lexical validator version và generation settings.

Lookup chỉ hit sau khi xác minh lại manifest/key, path nằm trong blob store, cả payload tồn tại đúng hash/count và lexical tokens không đổi. Manifest hỏng/mất trở thành miss; Gemini output hợp lệ được ghi atomically. TextRevision repaired vẫn pin parent reflowed revision và giữ nguyên invariant bất biến.

Cleanup dùng mtime như last-access gần đúng, mặc định TTL 180 ngày, tối đa 10.000 manifest và 256 MiB manifest. Cleanup không xóa `data/blobs/text`; backup cũng không phụ thuộc cache vì DB + blobs mới là aggregate cần phục hồi.

## YouTube Auto Handoff V1

`handoff.json` dùng schema `story-audio-youtube-handoff/v1`. Export identity pin chapter/job, TextRevision hash, optional CastingPlan hash, audio hash, speech timeline và character seed; mọi artifact dùng relative path và có size/SHA-256. Bundle là immutable derived export, không có foreign key trong SQLite và có thể verify độc lập.

`speech_timeline.json` dùng `story-audio-speech-timeline/v1`, integer milliseconds và segment-level speaker/character/voice/source-offset metadata. `character_seed.json` dùng `story-character-seed/v1`; không phải visual bible. Exporter luôn dùng TextRevision pin bởi audio artifact/job chapter, không dùng active revision mới nhất ngầm định.

Bundle được copy vào backup cùng `data/exports`; cleanup segment/cache không xóa bundle.

Không lưu absolute path trong API contract công khai. DB hiện giữ absolute artifact paths; nếu cần di chuyển project, M1 nên migration sang relative paths.

## Schema evolution rule

Schema hiện tại: **version 2**, migrations `0001_initial.sql` và `0002_character_voice.sql`.

Startup flow:

1. Bootstrap `schema_migrations`.
2. Từ chối DB có version lớn hơn code.
3. Verify name/checksum của migration đã apply.
4. Apply từng migration còn thiếu trong transaction.
5. Sau migration mới chuyển job dở dang thành `interrupted`.

Trước thay đổi schema tiếp theo phải:

1. Thêm file `story_audio/migrations/0002_<name>.sql`; không sửa `0001_initial.sql`.
2. Migration tăng dần, contiguous, idempotent và transaction-safe.
3. Backup DB trước migration.
4. Test upgrade từ fixture version trước.
5. Không xóa column/data trong cùng release thêm column thay thế.

## Backup/restore contract

Backup manifest version 1 chứa:

```text
created_at, app_version, schema_version, source_data_dir,
includes, file_count, total_size,
files[{path,size,sha256}]
```

- `app.db` được tạo bằng SQLite Online Backup API.
- `blobs`, `output` và mặc định `work` được đóng gói.
- Restore verify toàn bộ hash trước khi copy.
- Restore luôn dựng staging directory; destination hiện hữu chỉ được chuyển sang `pre-restore-*` khi có `--overwrite`.
- Absolute `artifacts.path` và `segments.wav_path` dưới source data root được remap sang destination mới.
- `books.source_path` có thể trỏ tới EPUB ngoài data root và không được remap/đóng gói ở version hiện tại.
