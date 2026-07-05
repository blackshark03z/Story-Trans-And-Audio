# Trạng thái dự án

**Cập nhật:** 2026-07-05T18:05 (Asia/Saigon)
**Milestone:** Task 10 Complete
**Trạng thái:** main tại `6fa018076ad7c146b55d05a8c6bf619abd2176f2`; Task 10 production pilot passed trên runtime cô lập; baseline code repository unchanged

File này ghi lại baseline đã xác minh. **Git là nguồn quyền cuối cùng** về current HEAD, branch và working tree. Chạy `git status` và `git log -1` để xác định trạng thái hiện tại. File này chỉ ghi lại baseline code/test đã verified tại một commit cụ thể.

## Baseline đã xác minh

**Last verified against commit:** `6fa018076ad7c146b55d05a8c6bf619abd2176f2`
**Last verified branch:** `main`
**Last verified date:** 2026-07-05

**Last verified focused Task 10 baseline:**
- Full offline test suite baseline: 723 tests passing
- Verification command: `unittest discover -s tests`
- Verified at commit: `6fa018076ad7c146b55d05a8c6bf619abd2176f2`
- Verified date: 2026-07-05

- EPUB: `Quang_Am_Chi_Ngoai.epub`.
- Import: 1 sách, 1.980 chương, khoảng 12,6 triệu ký tự.
- Storage: text blobs theo SHA-256; SQLite chỉ giữ metadata/path.
- QA import: 600 issue được ghi để review.
- Gemini key: được nhận diện; không lưu trong DB/log.
- VieNeu: v3 Turbo CPU/ONNX, 10 preset voice.
- FFmpeg/FFprobe: hoạt động.
- Schema migration: version 7 (`0007_voice_snapshot`), checksum-locked.
- Code supports: schema version 7.
- Full offline test suite: 377 tests passing (92 new snapshot tests added in Phase 3B).
- Live DB: schema version 7, SHA-256 `A17D3DF726DAD98A7A9777D55A8E68147E06995308EF35169A5E18AC3CD1D9FA` (verified 2026-06-28).
- End-to-end smoke: chương 858, giọng Ngọc Lan, Gemini `all_selected`.
- Kết quả smoke: 10/10 segment, M4A dài 118.710 ms, artifact active.
- Multi-voice real-TTS smoke: isolated book 3 / chapter 1982, casting plan 2, job 3.
- Kết quả multi-voice: Ngọc Lan + Gia Bảo + Thái Sơn; 8 utterance/8 segment; M4A sau retry 22.810 ms.
- Controlled retry: render lại đúng segment 20 trong 2,47 giây; 7 segment còn lại giữ nguyên hash/mtime.
- Audio signal check: không có silence trên 0,8 giây ở -45 dB; mean volume ba voice lệch tối đa 3,2 dB.
- Backup smoke: 3.989 file, 60.216.155 byte, manifest/hash/SQLite verify đạt.
- Restore smoke: sang data root mới, 13 đường dẫn được remap, deep integrity đạt.
- Shared Gemini cache benchmark local: chapter 858/784/363 (1.958/6.198/18.641 ký tự) hit + hash + lexical validation lần lượt khoảng 22/44/121 ms; không gọi mạng.
- Fake pipeline một block: miss + lưu revision khoảng 66 ms; job/chapter thứ hai shared-cache hit khoảng 54 ms; fake Gemini chỉ được gọi một lần.
- Three-Voice UI smoke: isolated book 4/chapter 1983, jobs 4–5, 8 utterance; profile v1→v2 và controlled retry giữ snapshot cũ.
- Preview thật: Ngọc Lan 14,16s, Gia Bảo 14,48s, Mỹ Duyên 15,12s; fallback reuse Ngọc Lan cache.
- Three-Voice real-TTS: job 4 dài 24.650 ms, job 5 dài 26.090 ms; narrator/male/female/unknown/override và timeline resolution metadata đều đạt.
- Character Bible Import Core: JSON V1 dry-run/apply CLI + backend API, schema v4, alias/external-key/role/metadata/provenance storage, idempotent re-import.
- Character Bible smoke: isolated book 5, dry-run create 3, first apply create 3 + 2 aliases, second apply match 3/no writes; API read and voice resolution verified.
- Character Bible UI + Handoff Integration: UI JSON dry-run/apply, metadata editor/aliases/provenance display, and YouTube Auto `character_seed.json` exports canonical metadata/aliases/notes.
- Gemini Speaker Assignment Draft Core: deterministic target/context, Character Bible candidates, structured V1 response, strict validation, Shared Gemini Cache, immutable schema-v5 draft persistence và API/CLI.
- Real Gemini speaker smoke: chapter 1982, one target, draft #1 valid 1/1 với `needs_review=true`; lần hai cache hit/reuse cùng fingerprint/content.
- Speaker Review real smoke: isolated book 7/chapter 1985, 15 utterance; Draft #3 valid 15/15 với 7 high, 8 medium và alternatives cho các dòng hội thoại.
- Review smoke đã chọn suggestion, Gemini alternative, manual character và unknown correction; partial approval tạo plan #5, final approval tạo plan #6, exact repeat reuse plan #6.
- Approval không tạo job/audio; jobs #1–#5, Book Voice Profile, Character Bible và immutable draft hash giữ nguyên.
- Handoff regression thật: bundle mới export hai lần cùng reuse identity `3255141aa34f`; bundle cũ `93ff2e0a367a` và bundle metadata mới đều verify/import lại trong YouTube Auto với `Reused: True`.
- Long-Chapter Validation Phase 1: chọn `Quang Âm Chi Ngoại` chapter 56, TextRevision #112, 210 utterance, 101 speaker-review targets.
- Preflight Phase 1 thêm Character Bible tối thiểu cho Đỗ Nhược (#21) và Cảnh Minh (#22), Book Voice Profile v1 Ngọc Lan/Đức Trí/Mỹ Duyên; hai character import lỗi mã hóa (#19/#20) đã bị deactivate và không tham gia candidate.
- Gemini draft #4 dùng `gemini-2.5-flash`, prompt `speaker-assignment-v2`, 6 batch, 101/101 valid, 0 invalid, content hash `ed43ff4e...`, input fingerprint `df56fd73...`.
- Review UI thật: partial approval tạo plan #7 với 15 decision; final approval tạo plan #8 với 86 decision còn lại, 0 remaining; exact repeat reuse plan #8.
- Accuracy smoke Phase 1: 40/40 mẫu thủ công đúng, gồm 29 dialogue/target và 11 narrator/background; TextRevision hash, Character Bible fingerprint, draft hash giữ nguyên; job/segment/artifact vẫn 5/42/24, không render audio.
- Long-Chapter Validation Phase 2: tạo job #6 thủ công từ Casting Plan #8, render VieNeu thật chapter 56 với 210/210 segment verified, final M4A render_0002 dài 752.310 s.
- Phase 2 voice distribution đúng snapshot: Ngọc Lan 110 segment, Đức Trí 56 segment, Mỹ Duyên 44 segment; sequence 1-210 liên tục, không thiếu/duplicate.
- Phase 2 controlled retry dùng `retry_segment` cho segment #247; 4 segment đối chứng giữ nguyên hash/mtime, segment retry đổi hash/mtime, render_0001 vẫn còn và final cũ chuyển `stale`, render_0002 là `active`.
- Phase 2 validation: TextRevision #112 hash match, Casting Plan #8 hash match, speaker draft/casting plan không tăng, Doctor `critical_errors=0`, 119 offline tests và JS syntax check đạt.
- Doctor deep after schema v5: SQLite quick check OK, draft/cache/blob integrity OK, `critical_errors=0`; Character/Casting/Job/Segment/Artifact/TextRevision rows giống backup v4 trước migration.
- Phase 3A/3B Custom Voice Backend: Schema v7, voice_ref.py resolution, 14-field immutable snapshots, snapshot-based TTS synthesis, fail-closed legacy policy, offline test coverage 377 tests (92 new snapshot tests), real VieNeu smoke (preset 1.04s + custom 4.31s).
- Task 10 supporting pilot: Chapter 804 workflow validation hoàn tất trên runtime cô lập V2 với pause/restart/resume, controlled regeneration, A/B review, reject workflow; không accept candidate nào; final M4A 503.800 s giữ nguyên.
- Task 10 production pilot: Chapter 629 dùng Character Bible + Gemini draft + editorial review + approved immutable Casting Plan #2, sửa đúng 1 attribution (`u0093-80d1bb797c28` → Hứa Thanh), render 119/119 segment verified, final M4A 824.420 s (13m44.420s).
- Chapter 629 voice distribution đúng snapshot: Ngọc Lan 90, Đức Trí 26, Mỹ Duyên 3; narrator/male/female đều được render thật; open candidate attempts = 0.
- Chapter 629 QA hoàn tất: objective audio QA đã ghi lại trong captures; operator đã nghe full chapter và kết luận `OPERATIONAL_PASS`; không có segment nào cần regenerate.
- Runtime evidence nằm ở `D:\Youtube\StoryAudioTask10PilotV2\captures`; live DB `D:\Youtube\Story Trans And Audio\data\app.db` và V1 DB đều không đổi trong toàn bộ Task 10.

## Shared Gemini cache contract

- Key pin source SHA-256, model, prompt version, punctuation-only contract, block splitter, lexical validator và generation settings.
- Thứ tự reuse: approved repaired TextRevision → job repair-block checkpoint → shared cache → Gemini API.
- Cache hit luôn verify manifest/key/blob/hash/count và lexical tokens; entry hỏng/mất là safe miss.
- Manifest nằm trong `data/cache/gemini_repairs/`; repaired payload dùng text blob bất biến. Cleanup TTL/quota chỉ xóa manifest và mặc định dry-run.

## Quyết định voice casting Personal Edition

Audio casting mặc định dùng ba nhóm voice cấp book: narrator, male dialogue và female dialogue; unknown fallback mặc định về narrator. Character identity tách khỏi voice identity và chỉ nhân vật quan trọng mới có optional voice override. Resolver deterministic và snapshot profile/version/source vào casting/job mới; plan/job cũ không bị resolve lại. Custom voice được quản lý ở cấp Global Library, lưu trữ nguyên bản audio và transcript để clone voice qua VieNeu reference-audio engine.

## Chức năng đã hoàn thành

- [x] Import EPUB và SHA deduplication.
- [x] Sửa số chương sai dựa trên spine/href.
- [x] Raw/reflowed/repaired TextRevision.
- [x] Lossless hard-wrap reflow và QA issue.
- [x] Gemini punctuation repair theo block với lexical integrity validation.
- [x] Khôi phục exact token spelling/casing từ nguồn.
- [x] Lexical integrity validation.
- [x] Chọn một chương hoặc khoảng từ–đến.
- [x] Chọn preset voice, Gemini mode và M4A/MP3.
- [x] Cửa sổ undo 10 giây.
- [x] Checkpoint Gemini block và TTS segment.
- [x] Pause, resume, cancel và retry.
- [x] Master WAV, audio export và segment timeline.
- [x] Artifact/revision và dependency cơ bản.
- [x] Audio player trong chapter dialog.
- [x] Cleanup segment sau retention 24 giờ.
- [x] Schema version và migration runner tự động khi startup.
- [x] Fail-safe khi DB mới hơn code hoặc checksum migration bị đổi.
- [x] Backup/verify/restore có manifest và SQLite snapshot nhất quán.
- [x] Recovery tests offline cho restart, retry, cancel và artifact corruption.
- [x] Diagnostic UI ba cấp cho job, chapter và segment; retry riêng phần lỗi.
- [x] Voice preview preset 10–20 giây với file cache độc lập, không tạo job/artifact.
- [x] Character Voice MVP: character manager, manual casting revision và multi-voice render.
- [x] Real VieNeu multi-voice smoke và controlled retry/reuse verification.
- [x] Text Revision Diff raw/reflowed/repaired với Inline và Side-by-side UI.
- [x] Shared Gemini repair cache theo source/model/prompt/repair contract, có lexical revalidation và cleanup dry-run.
- [x] Story Audio → YouTube Auto Handoff V1 một chương, manifest SHA-256, speech timing và character seed.
- [x] Three-Voice Profile Core: book profile, optional character override, gender-aware resolver và immutable job snapshot.
- [x] Three-Voice Profile UI and Casting Integration: profile/preview, default/custom character voice và effective resolution trong Manual Casting.
- [x] Book-level Character Bible Import Core: JSON schema V1, dry-run/apply, deterministic matching/conflict detection, idempotency, CLI/API and Doctor checks.
- [x] Gemini Speaker Assignment Draft Core: immutable draft, cache, strict candidates/confidence/alternatives và no auto-apply.
- [x] Speaker Assignment Review and Approval UI: filter/bulk review, alternatives/manual correction, effective voice preview, partial immutable approval, stale protection và idempotency.
- [x] Custom Reference Voice Storage & API: Schema v6, Global custom_voices, immutable revisions, content-addressed audio blob storage, and isolated offline API tests.
- [x] Custom Voice Preview: Immutable revision preview, reference audio/transcript integrity, content-addressed cache, backward-compatible API, minimal UI and 450 offline tests.
- [x] Custom Reference Voice Library UI: Global library panel, logical voice create/list/select/deactivate/reactivate, immutable audio/transcript revision upload (multipart), revision history, exact revision selection (radio + summary), Reference Audio playback (separate from preview), custom Preview Text (optional, 500 char max), short preview support (>0s, no 10s minimum), cache isolation, compact standalone Preset Voice Preview restored, redundant custom preview panel removed (Custom Voice Library is single custom-reference workflow), smoke/test books hidden by default with "Show test data" checkbox, full-width vertical form labels, responsive two-column upload layout. Real manual smoke passed: preset preview functional, two revisions, exact selection, Reference Audio, short custom text synthesis, cache behavior verified. Test isolation verified: live DB unchanged during automated runs. 613 tests passing (3 known pre-existing failures in brittle minified JS assertions). **Work merged into main via PR #2.**
- [x] Custom Voice Backend Resolution & Snapshot Support: voice_ref.py `custom:<id>` parser, CustomVoiceContext catalog, resolver integration in casting/profile/pipeline, 14-field immutable snapshot, snapshot-based TTS synthesis, fail-closed legacy policy, 377 offline tests (92 new snapshot tests), real VieNeu smoke (preset + custom). **Migration 0007, Phase 3A/3B complete.**
- [x] Multi-voice Segment Regeneration: Isolated segment re-synthesis with immutable voice snapshots, A/B candidate comparison, Accept/Reject workflows, and segment_attempts history tracking. Voice preservation verified: Character An → Đức Trí assignment preserved across regeneration. Vietnamese multi-voice pilot passed (Book 19, Job 16, 20/20 segments verified, Ngọc Lan/Đức Trí/Mỹ Duyên voices). Real regeneration smoke: Segment 350 generated candidate with correct Đức Trí voice, manual rejection workflow passed. 708 offline tests passing. **feat/segment-regeneration complete, ready for merge.**
- [x] Manual Casting Draft Character Assignment Fix: Hybrid API supporting offset-based (new) and utterance-ID (existing) manual character assignments. When authoritative offset spans are split by the utterance chunker, all child utterances inherit the source character assignment. Partial coverage allowed; uncovered text defaults to narrator. Strict validation returns clear 4xx errors. Manual offset mode does not call Gemini. Vietnamese smoke: 750-char text, 5 offset-based spans, 20 utterances (10 narrator / 4 An via book_male / 6 Bình via book_female), Book Voice Profile resolution verified. 723 offline tests passing (13 new offset-based tests). **fix/casting-draft-character-assignments complete.**

## Hạn chế hiện tại

- **Custom Voice UI Integration**: Backend resolution, snapshot, và TTS synthesis hoàn tất. UI library panel và preview hoàn tất. **UI voice selects (Book Voice Profile narrator/male/female, Character Override, Manual Casting) chưa load custom voices từ `/api/custom-voices`**. Người dùng chỉ chọn được preset voices qua browser. Đây là ứng viên tiếp theo sau Task 10, nhưng chưa được Tech Lead ưu tiên chính thức sau khi pilot đóng.
- Gemini và TTS chạy tuần tự trong một orchestration worker; chưa prefetch 2–5 chương.
- Shared Gemini cache vẫn chạy tuần tự; hai process có thể cùng gọi Gemini trước khi atomic write cùng một key (kết quả cuối vẫn hợp lệ).
- Cleanup cache hiện có CLI dry-run/apply nhưng chưa có quota/dashboard UI; text blob không bị xóa theo cache manifest.
- Text diff giới hạn 500.000 ký tự kết hợp; payload trên 50.000 ký tự có warning và collapse mặc định.
- Cleanup chưa có dry-run/quota dashboard trên UI.
- Review/Approval chưa có undo cho Casting Plan đã approve; sửa quyết định bằng một revision mới. Draft stale vẫn xem được để audit nhưng không approve được.
- Gender vẫn là dữ liệu manual; Gemini speaker draft không tự tạo/sửa character hoặc gender.
- Loudness giữa preset có chênh nhẹ (smoke đo tối đa 3,2 dB mean); chưa normalization theo đúng phạm vi.
- Backup là full snapshot, chưa incremental/compress và có thể lớn khi thư viện tăng.
- Restore remap artifact/work paths trong data root nhưng không đóng gói EPUB nguồn nằm ngoài `data/`.
- Recovery test dùng fake TTS và startup state transition; chưa có OS-level kill-process harness.
- Story Audio không tự xây image/video/metadata/thumbnail; các bước này thuộc YouTube Auto qua handoff bundle.
- Handoff V1 chỉ hỗ trợ một chapter và segment-level timing; chưa có forced word alignment.
- Worker là một thread trong API process; chưa tách service/process riêng.

## Ưu tiên tiếp theo

### P0 — Trước khi thêm tính năng lớn

- [x] Thêm database schema version và migration runner.
- [x] Thêm backup/restore có manifest và integrity verification.
- [x] Thêm integration tests cho restart, retry, cancel và artifact corruption.
- [x] Thêm job/chapter/segment diagnostic UI để người dùng thấy lỗi cụ thể và retry an toàn.

### P1 — Hoàn thiện Audio MVP

- [x] Voice preview 10–20 giây.
- [x] Text diff raw → reflowed → repaired.
- [x] Gemini cache dùng chung theo source hash + model + prompt version.

Các hạng mục vận hành/quota và alignment không cấp thiết được tập trung trong `ROADMAP.md` thay vì lặp backlog tại đây.

### P2 — Personal Edition voice

- [x] YouTube Auto Handoff V1.
- [x] Three-Voice Profile Core.
- [x] Three-Voice Profile UI and Casting Integration.
- [x] Book-level Character Bible Import.
- [x] Character Bible UI and Handoff Integration.
- [x] Gemini Speaker Assignment Draft Core.
- [x] Speaker Assignment Review and Approval UI.
- [x] Long-Chapter End-to-End Validation and Hardening.
  - [x] Phase 1: preflight, real long-chapter Gemini draft, review, partial/final approval.
  - [x] Phase 2: VieNeu render, recovery/retry, audio QA.
  - [x] Phase 3: Handoff export/import and downstream compatibility smoke.
- [x] Phase 2B2B: Custom Reference Voice Resolution and Assignment Validation (commit 64c7ea4949b4c5c37b01cc05bb2eddd686691066).
- [x] Phase 3A: Job/Casting Snapshot Pinning (Migration 0007).
- [x] Phase 3B: Immutable Voice Snapshots with TTS Integration (377 tests, VieNeu smoke).
- [ ] **UI Integration**: Load custom voices into Book Voice Profile / Character Override / Manual Casting voice selects.

## Quy tắc cập nhật tiến độ

- Chỉ đánh dấu `[x]` sau khi có test hoặc artifact xác minh.
- Việc chưa rõ phạm vi đưa vào `ROADMAP.md`, không nhét vào P0.
- Bug đang ảnh hưởng dữ liệu hoặc resume phải nằm trong Hạn chế hiện tại.
- Quyết định thay đổi invariant phải ghi thêm vào `docs/DECISIONS.md`.
- Thay đổi phát hành hoặc hành vi người dùng phải thêm vào `CHANGELOG.md`.

## Nhật ký milestone

| Ngày | Milestone | Bằng chứng |
|---|---|---|
| 2026-06-23 | Audio MVP đầu tiên | Import 1.980 chương; job #1 completed |
| 2026-06-23 | Gemini contract smoke | Sửa punctuation, token nguồn được bảo toàn |
| 2026-06-23 | Resume theo segment | Reuse 9/10 segment và chỉ tạo lại segment lỗi |
| 2026-06-23 | P0 hardening | Schema v1; backup/restore thật và 18 test offline đạt |
| 2026-06-23 | M2 Diagnostic UI | Job/chapter/segment diagnostics; retry giữ nguyên verified segment; 23 test offline đạt |
| 2026-06-23 | M2 Voice Preview | Preset preview cache theo voice/text/settings/engine; fake TTS; 28 test offline đạt |
| 2026-06-23 | M2 Character Voice MVP | Schema v2; manual casting; multi-voice snapshot/segments/timeline; 38 test offline đạt |
| 2026-06-23 | Three-Voice Profile Core | Schema v3; profile/override/resolver/snapshot; 73 test offline và Doctor deep đạt |
| 2026-06-23 | Three-Voice UI + Casting | Profile/preview/default-custom/effective voice; jobs 4–5 real TTS; 78 test offline đạt |
| 2026-06-23 | Multi-voice real-TTS smoke | Job 3; 3 voices; 8/8 segment; retry 1 segment và reuse 7; M4A 22.810 ms |
| 2026-06-23 | Text Revision Diff | Structured read-only API; Inline/Side-by-side; 50 tests; chapter 18.649 chars ≈330 ms live API |
| 2026-06-23 | Shared Gemini repair cache | Filesystem manifest + text blob; lexical revalidation; corrupt-as-miss; cleanup/doctor; 60 tests |
| 2026-06-23 | YouTube Auto Handoff V1 | Job 3/chapter 1982; 22.810s M4A; 8 timing items; 2 character seeds; imported/composed final 22.826s |
| 2026-06-24 | Character Bible Import Core | Schema v4; 92 offline tests; smoke book 5 dry-run/apply/apply-lại; Doctor deep critical_errors=0 |
| 2026-06-24 | Character Bible UI + Handoff Integration | UI dry-run/apply + metadata editor; Handoff seed exports canonical metadata; 94 offline tests + JS syntax check |
| 2026-06-24 | Gemini Speaker Assignment Draft Core | Schema v5; 101 offline tests; real Gemini draft #1 + cache hit/reuse; Doctor deep critical_errors=0 |
| 2026-06-24 | Speaker Assignment Review and Approval UI | 119 offline tests; Draft #3, 15 utterance; partial plans #5–#6; exact approval repeat reused #6; no job/audio mutation |
| 2026-06-25 | Long-Chapter Validation Phase 1 | Chapter 56; Draft #4 101/101 valid; UI plans #7–#8; idempotent repeat reused #8; 40/40 accuracy smoke; no job/audio mutation |
| 2026-06-25 | Long-Chapter Validation Phase 2 | Job #6 from plan #8; 210/210 real VieNeu segments; M4A render_0002 752.310 s; retry segment #247 reused verified peers; Doctor/tests pass |
| 2026-06-25 | Long-Chapter Validation Phase 3 | Bundle identity `050ac2f2a73bda7b84beb7c1e9bd5b06d9fd3a00773214fa91616c451e8f9280`; export #2 reused identity; 752310 ms / 210 utterances / 2 characters; legacy bundles verify/import; Story Audio 119 tests / Doctor pass; YouTube Auto 96 tests pass |
| 2026-06-26 | Custom Voice Backend Core | Schema v6; global library, immutable revisions, content-addressed storage, FastAPI routes, and 28 isolated API tests |
| 2026-06-27 | Custom Reference Voice Resolution | voice_ref.py + CustomVoiceContext; casting/profile integration; 290 offline tests pass |
| 2026-06-27 | Phase 3A: Snapshot Pinning | Migration 0007; pipeline pins 14 snapshot columns; 305 tests pass |
| 2026-06-28 | Phase 3B: Immutable Voice Snapshots | 14-field SegmentSynthesisInput, snapshot-based TTS, fail-closed legacy policy, 377 tests (92 new), real VieNeu smoke (preset + custom) |
| 2026-06-28 | Custom Voice UI Library | PR #2 merged; 613 tests pass (3 pre-existing failures); library panel, revision upload/selection, Reference Audio, preview, smoke passed |

| 2026-07-01 | Multi-voice Segment Regeneration | Book 19/Job 16 Vietnamese pilot 20/20 verified; Segment 350 candidate preserved Đức Trí voice; manual rejection passed; 708 tests pass; Books 14-18 Task 8C duplicates cleaned |
| 2026-07-01 | Manual Casting Draft Character Assignment Fix | Hybrid offset-based + utterance-ID API; 5 offset spans → 20 utterances (10/4/6 distribution); Book Voice Profile resolution verified; 723 tests pass (13 new); fix/casting-draft-character-assignments branch |
| 2026-07-05 | Task 10 Chapter 804 Workflow Validation | Runtime cô lập V2; pause/restart/resume pass; Segment 50/51 A/B + reject workflow pass; không accept candidate; final M4A 503.800 s giữ nguyên |
| 2026-07-05 | Task 10 Chapter 629 Production Pilot | Character Bible + Gemini review + immutable Casting Plan #2; 119/119 verified; Ngọc Lan/Đức Trí/Mỹ Duyên distribution 90/26/3; final M4A 824.420 s; operator full-chapter `OPERATIONAL_PASS` |
