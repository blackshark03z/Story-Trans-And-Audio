# Testing Strategy

Mục tiêu là bắt lỗi phục hồi và dữ liệu với chi phí thấp nhất. Test mặc định phải offline, nhanh và không nạp model.

## Tầng 1 — Offline unit tests (mỗi thay đổi)

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' -m unittest discover -s tests -v
node --check ui\app.js
```

Authoritative interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`
Current offline baseline for the main branch after Task 11D1: `855/855` passing.

Focused Task 11C1 QA tests:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' -m unittest tests.test_audio_qa -v
```

Focused Task 11C2 listening checklist tests:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' -m unittest tests.test_listening_checklist -v
```

Focused Task 11D1 unified workflow tests:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' -m unittest tests.test_production_workflow -v
```

Không được gọi Gemini, VieNeu inference hoặc mạng. Dùng fixture nhỏ cho:

- Reflow và lexical identity.
- Chunk limits.
- SQLite state transition.
- Artifact invalidation.
- EPUB edge cases.

## Tầng 2 — Integration local, không phí

- Import EPUB fixture nhỏ.
- Fake Gemini adapter trả punctuation sửa đúng/sai.
- Fake TTS adapter tạo WAV ngắn xác định trước.
- FFmpeg assemble/verify.
- Kill/restart worker giữa các stage.
- Corrupt/missing segment rồi resume.

Đã có coverage offline cho:

- Legacy/v1/v2/v3 DB → schema version 4, legacy character override, Character Bible fields and future-version/checksum guards.
- Startup chuyển job dở sang `interrupted`.
- Retry reuse segment verified và chỉ gọi fake TTS cho segment pending.
- Cancel được quan sát trước inference.
- Backup manifest/hash, restore sang data root mới và no-overwrite guard.
- Corrupted backup/artifact được phát hiện.
- Manual/multi-voice casting, immutable resolved voice snapshot và verified-segment reuse.
- Shared Gemini cache hit/miss/corruption/cleanup.
- Story Audio Handoff V1 single/multi-voice, hash/path/duration và immutable export.
- Character Bible JSON parsing, dry-run read-only behavior, deterministic matching/conflicts, idempotent apply, backup/restore and Doctor integrity checks.
- Speaker draft deterministic selection/fingerprint, strict candidate/response validation, partial invalid handling, Shared Gemini Cache hit/corruption, injection boundaries, immutable persistence và no-casting/job-mutation.
- Speaker review list/detail, context, confidence/alternative/manual decisions, safe DOM rendering, effective voice resolver, stale-state rejection, partial approval, base preservation, deterministic ordering và idempotent repeat.
- Doctor review linkage checks và no-mutation assertions cho Character Bible, Book Voice Profile, immutable draft, jobs và audio.

OS-level kill-process và FFmpeg failure injection vẫn là khoảng trống M1.

## Tầng 3 — Paid/slow smoke test (chỉ khi cần)

Chỉ chạy khi thay đổi `gemini.py`, `tts.py`, prompt contract, audio assembly hoặc model version.

Fixture mặc định:

- Một đoạn synthetic không chứa nội dung riêng tư cho Gemini.
- Một chương ngắn hoặc đoạn 1–2 segment cho VieNeu.
- Không chạy toàn bộ sách.
- Ghi model/prompt/voice/version vào test report, không ghi key.

Baseline hiện tại: full offline suite `835/835` pass với interpreter authoritative `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`; ngoài ra vẫn giữ các smoke lịch sử như chương 858 hoàn thành 10 segment/M4A 118.710 ms và handoff smoke job 3/chapter 1982 tạo video YouTube Auto 22,826 giây từ audio 22,810 giây.

Task 11C1 added synthetic WAV-based offline coverage for clipping, silence, sample-width support, deterministic report reuse, and no-mutation guarantees. These tests stay local and do not call Gemini, TTS inference, hay app server.

Task 11C2 added deterministic offline HTML listening-package coverage: manifest/QA identity validation, live-root rejection, traversal/symlink rejection, percent-encoded relative audio URLs, deterministic queue ordering/dedupe, byte-identical output reuse, safe HTML escaping, localStorage/export contract, and no-network/no-mutation guarantees. Chapter 629 disposable smoke verified package generation and byte-identical reuse without mutating DB or source audio.

Task 11D1 added unified workflow coverage for preflight-only default behavior, explicit submit/resume mutual exclusion, completed-job downstream reuse, paused-job no-auto-resume behavior, fail-closed stage sequencing, structured stdout/stderr contracts, and guarantees that the workflow does not introduce regenerate, accept, reject, or automatic QA decisions. Disposable Chapter 629 smoke verified the end-to-end operator workflow without DB or source-audio mutation.

Three-Voice UI smoke dùng isolated book 4/chapter 1983: preview Ngọc Lan/Gia Bảo/Mỹ Duyên đạt 14,16–15,12 giây; jobs 4–5 đạt 24.650/26.090 ms với narrator, male, female, unknown fallback và character override. Controlled retry job 4 render lại đúng segment Gia Bảo và reuse 7 segment verified; timeline mới chứa resolution metadata. Chưa đánh giá cảm nhận bằng tai trong smoke tự động.

Character Bible smoke dùng isolated book 5: dry-run tạo 3 planned characters; apply lần đầu tạo 3 character và 2 alias; apply lại cùng file match 3 và không ghi thêm. API character read trả metadata mới; voice resolver cho Smoke An/Smoke Bình/Người Áo Đen lần lượt dùng male default, female default và unknown fallback. Jobs #3/#4/#5 giữ nguyên casting snapshot hash.

Speaker Assignment real smoke dùng chapter 1982 và một utterance: lần đầu Gemini `gemini-2.5-flash` tạo draft #1 valid 1/1; lần hai hit Shared Gemini Cache và reuse cùng fingerprint/content. Draft giữ `needs_review=true`; bảng Character/Casting/Job/Segment/Artifact/TextRevision giống backup v4 trước migration.

Speaker Review smoke dùng isolated book 7/chapter 1985 với 15 utterance, narrator, male/female dialogue, alias, ambiguous/unknown và prompt-injection text. Gemini prompt v2 tạo Draft #3 valid 15/15 (7 high, 8 medium). UI đã chọn suggestion, alternative, manual character, unknown correction và để lại skipped rows; partial approval tạo plan #5, final approval tạo plan #6, exact repeat reuse plan #6. Approval không tạo job/audio; voice preview resolve Smoke An thành Đức Trí từ Book male default.

Handoff regression thật: export mới chạy hai lần cùng reuse identity `3255141aa34f`; bundle cũ `93ff2e0a367a` và bundle mới đều qua verifier, rồi importer thật trong YouTube Auto trả `Reused: True` cho `story-audio-old-bundle-verify` và `story-audio-rich-metadata-smoke`.

## Release gate

- Unit tests đạt.
- Doctor không có `ERROR`.
- Không có active artifact thiếu file.
- DB `PRAGMA quick_check` trả `ok`.
- Migration/backup test đạt nếu schema đổi.
- Một end-to-end smoke đạt nếu Gemini/TTS contract đổi.
- `PROJECT_STATUS.md` và `CHANGELOG.md` được cập nhật.

## Regression cases phải giữ

- EPUB có hard-wrap giữa `không` và `ít.`.
- Gemini viết hoa chữ đầu nhưng token output phải trở lại đúng nguồn.
- Gemini thêm một từ phải bị chặn.
- Voice ID Unicode phải được giữ nguyên NFC.
- Retry segment có attempt count cũ phải thực sự chạy lại.
- 9/10 segment verified thì chỉ segment lỗi được tạo lại.
- FFmpeg lỗi không được gọi lại VieNeu cho segment hợp lệ.
- Casting/job cũ không đổi voice khi character override hoặc Book Voice Profile thay đổi.
- Resolver Three-Voice phải deterministic cho narrator, male, female, explicit override và unknown/needs-review.
- UI không tự clear legacy override, không duplicate resolver JavaScript và không tạo plan/job khi chỉ xem effective voice.
- Audio QA report không được mutate source DB/audio, không được mở live root, và phải reuse byte-identical output khi input/threshold không đổi.
