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

## Khi nào cần ADR mới

- Đổi engine/storage/database/queue.
- Thay invariant hoặc state machine.
- Thêm dịch vụ trả phí/đưa dữ liệu ra ngoài.
- Thay artifact contract hoặc invalidation semantics.
- Chấp nhận technical debt ảnh hưởng dữ liệu/phục hồi.
