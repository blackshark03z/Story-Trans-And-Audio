# Decision Log

Mỗi quyết định có ID ổn định. Khi thay đổi, thêm quyết định mới thay vì sửa lịch sử; ghi quyết định cũ là superseded.

## ADR-001 — Modular monolith

**Status:** Accepted
**Decision:** FastAPI, SQLite, worker và file storage nằm trong một ứng dụng có module boundary rõ.
**Why:** Một máy local, dễ cài và debug; microservice chưa mang lại lợi ích tương xứng.
**Consequence:** Worker crash có thể ảnh hưởng API process; tách worker là bước hardening sau này.

## ADR-002 — Text nằm ngoài SQLite

**Status:** Accepted
**Decision:** Full text lưu bất biến theo SHA-256 trong `data/blobs/text`; SQLite giữ metadata/path.
**Why:** Dễ version, deduplicate và tránh DB phình khi thêm nhiều sách.
**Consequence:** Backup phải gồm cả DB và blobs; cần garbage collector và integrity check.

## ADR-003 — Revision và Artifact bất biến

**Status:** Accepted
**Decision:** Sửa text/config tạo revision mới; output mới tạo artifact mới, không ghi đè artifact active.
**Why:** Audit, retry, invalidation và phục hồi đáng tin cậy.
**Consequence:** Cần retention/cleanup và active pointer.

## ADR-004 — Gemini chỉ phục hồi punctuation

**Status:** Accepted
**Decision:** Gemini chỉ thay punctuation/whitespace; exact source token spelling được khôi phục trước lexical validation.
**Why:** Giữ nguyên nội dung truyện và chống model tự rewrite.
**Consequence:** Sửa chính tả/quảng cáo phải là stage khác có audit.

## ADR-005 — Application sở hữu TTS chunk

**Status:** Accepted
**Decision:** App chia segment tối đa 256 ký tự thay vì để VieNeu tự chia nội bộ.
**Why:** Checkpoint, timeline và retry phải nhìn thấy từng đơn vị render.
**Consequence:** Prosody được tối ưu bằng sentence-aware chunk và silence, không bằng block 700 ký tự.

## ADR-006 — Một VieNeu worker

**Status:** Accepted
**Decision:** Một CPU/ONNX TTS worker trên máy hiện tại.
**Why:** Tránh tranh RAM/CPU và đơn giản hóa model lifecycle.
**Consequence:** Throughput tuần tự; Gemini/image concurrency được xem xét riêng sau này.

## ADR-007 — Audio MVP trước visual pipeline

**Status:** Accepted
**Decision:** MVP gồm Gemini + audio; alignment/image/video chưa ở runtime.
**Why:** Thu nhỏ bề mặt lỗi và xác minh checkpoint trước khi thêm dịch vụ ngoài.
**Consequence:** Timeline segment được lưu từ đầu để tránh làm lại nền móng.

## ADR-008 — Forward-only checksum migrations

**Status:** Accepted
**Decision:** Schema thay đổi bằng migration SQL tăng dần; migration đã apply được khóa bằng SHA-256 và không được sửa.
**Why:** DB local chứa checkpoint/artifact thật, nên startup phải deterministic và fail-safe khi code/DB lệch version.
**Consequence:** Không có downgrade tự động; cần backup trước migration và file migration mới cho mọi thay đổi.

## ADR-009 — Verified full backup và staging restore

**Status:** Accepted
**Decision:** Backup dùng SQLite Online Backup và manifest SHA-256; restore verify trước, dựng staging rồi atomic rename. `--overwrite` giữ destination cũ dưới tên `pre-restore-*`.
**Why:** DB và filesystem artifacts là một aggregate; copy riêng DB không thể phục hồi revision/checkpoint.
**Consequence:** Full backup tốn dung lượng; incremental/compression để sau khi có nhu cầu thực tế.

## ADR-010 — Casting revision và resolved voice snapshot

**Status:** Accepted
**Decision:** Character Voice nằm trong một CastingPlanRevision content-addressed riêng, pin approved TextRevision bằng offsets. Job snapshot toàn bộ resolved voices; segment bị giới hạn trong một speaker.
**Why:** Giữ TextRevision bất biến, ngăn default voice/casting edit làm đổi job đang chạy và tránh reuse audio nhầm voice.
**Consequence:** Mỗi thay đổi speaker tạo plan revision/job mới; schema v2 thêm character, casting plan và speaker metadata trên segment.

## ADR-011 — Shared Gemini repair cache không phải nguồn sự thật

**Status:** Accepted
**Decision:** Gemini punctuation output được cache bằng filesystem manifest content-addressed. Identity pin source hash, normalized model, prompt version, repair contract, block strategy, lexical validator và mọi generation setting ảnh hưởng output. Payload dùng chung content-addressed text blob.
**Why:** Hai job có cùng repair contract không nên trả phí/gọi mạng lặp lại, nhưng TextRevision và job checkpoint vẫn phải là nguồn sự thật có thể phục hồi khi cache bị xóa.
**Consequence:** Mọi cache hit phải verify manifest/key/blob/hash/character count và chạy lại lexical validation. Entry hỏng là safe miss; cleanup chỉ xóa manifest, không xóa blob. Không cần schema migration.

## ADR-012 — Story Audio và YouTube Auto giao tiếp bằng handoff filesystem có version

**Status:** Accepted
**Decision:** Hai codebase giữ độc lập. Story Audio là source of truth cho approved text, resolved speaker/voice, audio và speech timing; YouTube Auto là source of truth cho visual timeline, visual character bible, image, subtitle render, final video, metadata và thumbnail. Giao tiếp bằng `story-audio-youtube-handoff/v1` với relative paths và SHA-256; importer chỉ đọc, không sửa bundle.
**Why:** Giữ Audio MVP dễ bảo trì và phục hồi trong khi tái sử dụng visual pipeline đã tồn tại, không tạo DB/runtime coupling.
**Consequence:** V1 chỉ export một chapter/audio artifact, mặc định copy để bundle sống độc lập với cleanup nguồn. Character seed chỉ là identity/content hint; YouTube Auto vẫn tạo visual bible. Không dùng absolute path làm export identity.

## Khi nào cần ADR mới

- Đổi engine/storage/database/queue.
- Thay invariant hoặc state machine.
- Thêm dịch vụ trả phí/đưa dữ liệu ra ngoài.
- Thay artifact contract hoặc invalidation semantics.
- Chấp nhận technical debt ảnh hưởng dữ liệu/phục hồi.
