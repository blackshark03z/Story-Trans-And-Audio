# Data Model và Contract

Source of truth cho schema thực thi hiện nằm trong `story_audio/db.py`. File này mô tả ý nghĩa và dependency; không copy nguyên SQL để tránh drift.

## Entity graph

```text
Book
├── Character
│   └── CharacterAlias
├── CharacterBibleImport
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
- `BookVoiceProfile`: tối đa một profile active cho mỗi book, chứa ba preset mặc định và unknown fallback policy.
- `Character`: nhân vật thuộc một book với optional `gender` và `voice_override_id`; `default_voice_id` chỉ còn là compatibility field cho schema v2/API cũ.
- `CharacterAlias`: alias queryable theo book/character, dùng cho matching Character Bible và speaker assignment sau này.
- `CharacterBibleImport`: provenance tối thiểu cho lần import đã áp dụng, không lưu full JSON.
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
- Voice character hiện tại chỉ ảnh hưởng plan mới; plan/job cũ giữ `resolved_voice_id` snapshot.
- Không segment nào chứa text từ hai speaker. Một utterance có thể sinh nhiều segment cùng voice.

## Three-Voice Profile and Character Bible — schema v4

### Storage thực tế

- `book_voice_profiles`: một row/book với narrator, male dialogue, female dialogue, unknown policy, optional explicit unknown voice, `config_version` và timestamps.
- `characters.voice_override_id`: nullable; `NULL` nghĩa là dùng Book Voice Profile.
- `characters.gender`: nullable/manual `male | female | unknown`; resolver không tự ghi inferred gender trở lại.
- `characters.default_voice_id TEXT NOT NULL`: legacy compatibility field. Migration v3 giữ nguyên và copy giá trị không rỗng sang `voice_override_id`.
- `characters.external_key` + `external_key_normalized`: imported identity, unique per book when present.
- `characters.canonical_name` + `canonical_name_normalized`: display identity used for matching; legacy rows are backfilled from `display_name`.
- `characters.role`, `age_group`, `description`, `speech_style`, `visual_notes`, `notes`: Character Bible metadata. Role is queryable; metadata is plain text only and not rendered as HTML.
- `characters.bible_schema`, `bible_source_sha256`, `bible_source_label`, `bible_imported_at`, `bible_last_imported_at`: per-character provenance for applied imports.
- `character_aliases`: queryable alias rows with normalized alias and source hash; aliases are not silently generated from generic pronouns.
- `character_bible_imports`: applied import summaries by book/source hash.
- `casting_plans.narrator_voice_id`: narrator voice pin trong immutable CastingPlanRevision.
- `jobs.voice_name`: narrator/single-voice lựa chọn tại lúc tạo job.
- `job_chapters.voice_snapshot_json` và `jobs.casting_snapshot_json`: resolved narrator/character voices của job multi-voice.
- `segments.resolved_voice_id`: voice cuối cùng dùng để tổng hợp; retry reuse giá trị này.
- Resolution metadata (`resolution_source`, gender, `needs_review`, profile ID/version và preset ref) nằm trong immutable casting JSON/job snapshot, không phụ thuộc profile mutable khi retry. Timeline artifact mới sao chép metadata này từ snapshot; timeline/artifact cũ không bị rewrite.

### Model runtime

```text
BookVoiceProfile
├── book_id
├── narrator_voice_id
├── male_dialogue_voice_id
├── female_dialogue_voice_id
├── unknown_fallback          # narrator | male_dialogue | female_dialogue | explicit_voice
├── unknown_voice_id?         # bắt buộc khi policy=explicit_voice
└── config_version

Character
├── display_name
├── gender                    # male | female | unknown
├── voice_override_id?        # optional
└── default_voice_id          # legacy compatibility only
```

Profile được sửa in-place và tăng `config_version`, nhưng chỉ ảnh hưởng casting/job mới. Missing preset trong dữ liệu cũ được báo bằng validation metadata; đọc profile không làm app crash và không tự fallback sang voice khác.

### Voice resolution đã triển khai

```text
utterance override (nếu tương lai có)
→ character voice override
→ narrator profile voice
→ male/female dialogue profile voice
→ unknown fallback
```

- `character_id=null, gender=male` → male dialogue voice.
- Character đã biết, gender unknown, không override → unknown fallback.
- Không biết character và gender → unknown fallback + `needs_review=true`.
- Hệ thống hiện chưa có utterance-level voice override; không được giả định field này tồn tại.

Resolver tạo resolved voice trước khi tạo casting/job và ghi vào immutable snapshot. Profile/override thay đổi không invalidates hoặc resolve lại plan/job cũ. Utterance-level override chưa tồn tại; priority hiện bắt đầu từ character override.

### Book-level Character Bible — schema v4

Required identity fields: `external_key`, `canonical_name`, `aliases`, `gender`, `role`.

Optional content fields: `age_group`, `description`, `speech_style`, `visual_notes`, `notes`, `voice_override_id`.

Import dùng JSON schema `story-audio-character-bible/v1`, có dry-run không ghi DB và apply idempotent. Matching priority trong một book:

```text
1. Existing imported external_key.
2. Exact normalized canonical name.
3. Unique normalized alias match.
4. No match -> create.
```

Conflict không tự merge. Re-import cùng nội dung không tạo duplicate character/alias và không cập nhật timestamp khi không có thay đổi. UI hỗ trợ chọn JSON, dry-run, apply, xem summary/conflict và sửa metadata nhân vật.

Character Bible không yêu cầu `default_voice_id` hoặc voice hint chi tiết cho mọi character. Nhân vật phụ mặc định kế thừa voice theo gender. Đây là book-level identity source; `character_seed.json` trong Handoff V1 là per-chapter export seed cho YouTube Auto, có sao chép canonical metadata/aliases/notes của nhân vật xuất hiện trong timeline nhưng không thay thế model này.

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

## Speaker Assignment Draft — schema v5

`speaker_assignment_drafts` là index cho draft bất biến, pin `book_id`, `chapter_id`, approved `text_revision_id/hash`, Character Bible fingerprint, confirmed assignment context, model, prompt version, generation settings và response schema. Structured payload dùng `story-audio-speaker-assignment-draft/v1` tại `data/blobs/speaker_assignment/`; SQLite chỉ giữ path/hash, summary và trạng thái.

`speaker_assignment_draft_characters` giữ character references để Doctor kiểm tra ownership. Draft chỉ có các trạng thái `generated`, `partially_invalid`, `failed`, `superseded`; không có `approved/applied`. Mọi assignment luôn `needs_review=true` và không tự tạo/sửa Character, CastingPlan, BookVoiceProfile hoặc Job.

TextRevision hoặc Character Bible đổi làm input fingerprint đổi. Draft cũ vẫn đọc được để audit nhưng không còn current cho input mới. Cùng input và cùng validated provider payload reuse content hash/draft hiện có.

### Review và approval trên schema v5

Review không cần bảng mutable mới. Mỗi approval tạo một immutable `casting_plans` JSON mới và ghi provenance trong `source_metadata.source = "gemini_speaker_review"`: draft ID/fingerprint, base Casting Plan ID, canonical decision fingerprint, idempotency key, reviewed utterance IDs và remaining count.

Partial approval dùng plan approved hiện tại làm base và chỉ overlay các utterance đã quyết định; assignment, offsets, text hash và resolved voice ngoài phạm vi được giữ nguyên. Exact repeat cùng draft/base/decision fingerprint trả lại plan đã có. TextRevision, Character Bible hoặc base plan thay đổi làm approval bị conflict; draft vẫn đọc được để audit. Ghi chú này mô tả giai đoạn schema v5 lịch sử; schema hiện tại phải được xác minh bằng runtime và migrations.

## Shared Gemini cache

Cache là lớp tăng tốc có thể xóa hoàn toàn, không phải entity nguồn sự thật trong SQLite. Repair manifest pin source/repaired blob và lexical contract. Speaker-assignment manifest dùng cùng subsystem/root, pin task kind, request fingerprint, model, prompt, response schema và generation settings rồi trỏ tới validated JSON blob.

Lookup chỉ hit sau khi xác minh manifest/key/path/hash và validation riêng của task. Manifest hoặc payload speaker hỏng/sai schema trở thành safe miss rồi mới được gọi Gemini lại. TextRevision repaired và SpeakerAssignmentDraft vẫn là nguồn audit bất biến độc lập với cache.

Cleanup dùng mtime như last-access gần đúng, mặc định TTL 180 ngày, tối đa 10.000 manifest và 256 MiB manifest. Cleanup không xóa `data/blobs/text`; backup cũng không phụ thuộc cache vì DB + blobs mới là aggregate cần phục hồi.

## YouTube Auto Handoff V1

`handoff.json` dùng schema `story-audio-youtube-handoff/v1`. Export identity pin chapter/job, TextRevision hash, optional CastingPlan hash, audio hash, speech timeline và character seed; mọi artifact dùng relative path và có size/SHA-256. Bundle là immutable derived export, không có foreign key trong SQLite và có thể verify độc lập.

`speech_timeline.json` dùng `story-audio-speech-timeline/v1`, integer milliseconds và segment-level speaker/character/voice/source-offset metadata. `character_seed.json` dùng `story-character-seed/v1`; không phải visual bible, nhưng có canonical name, aliases, gender, role, age group, description, speech style, visual notes, notes và resolved preset hint cho những nhân vật xuất hiện trong timeline. Exporter luôn dùng TextRevision pin bởi audio artifact/job chapter, không dùng active revision mới nhất ngầm định; Character Bible metadata đổi sẽ tạo export identity mới và không sửa bundle cũ.

Bundle được copy vào backup cùng `data/exports`; cleanup segment/cache không xóa bundle.

Không lưu absolute path trong API contract công khai. DB hiện giữ absolute artifact paths; nếu cần di chuyển project, M1 nên migration sang relative paths.

## Schema evolution rule

Schema hiện tại không được hard-code trong tài liệu này. Xác minh bằng `/api/runtime`, Doctor, và danh sách `story_audio/migrations/`. Tại lần reconciliation 2026-07-20, canonical runtime báo schema `12` và migrations có đến `0012_speaker_draft_reviews.sql`.

Startup flow:

1. Bootstrap `schema_migrations`.
2. Từ chối DB có version lớn hơn code.
3. Verify name/checksum của migration đã apply.
4. Apply từng migration còn thiếu trong transaction.
5. Sau migration mới chuyển job dở dang thành `interrupted`.

Trước thay đổi schema tiếp theo phải:

1. Thêm file migration kế tiếp sau migration cao nhất hiện có trong `story_audio/migrations/`; không sửa migration đã phát hành.
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
