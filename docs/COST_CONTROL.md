# Cost Control Policy

Chi phí của Story Audio gồm Gemini punctuation API, thời gian VieNeu CPU, FFmpeg, dung lượng ổ đĩa và thời gian kỹ sư điều tra lỗi. Image/video/metadata/thumbnail thuộc YouTube Auto và không được đưa trở lại runner Story Audio.

## Nguyên tắc

1. **Preview trước batch:** hiển thị số chương, ký tự, chương đã hoàn tất, thời gian và dung lượng ước tính.
2. **Sample first:** profile/model/prompt mới chạy một chương trước batch lớn.
3. **Không tự chạy toàn sách:** phạm vi do người dùng xác nhận; mặc định bỏ qua chương hoàn tất.
4. **Idempotent theo hash:** cùng input và config phải reuse kết quả đã verify.
5. **Invalidation tối thiểu:** đổi format không gọi TTS; đổi ảnh không gọi audio; retry segment không render lại chương.
6. **Offline tests mặc định:** test tự động không dùng API hoặc inference thật.
7. **Giữ bằng chứng vừa đủ:** lưu hash/manifest/log cấu trúc; không giữ WAV tạm vô hạn.

## Cache key bắt buộc

### Gemini repair

```text
source_sha256 + model_id + prompt_version + repair_mode
```

Shared cache đã triển khai và còn pin repair contract, generation settings, block strategy cùng lexical validator version. Cache hit luôn verify hash và lexical identity.

### Gemini speaker assignment

```text
task_kind + text revision/hash + utterance/context hashes
+ Character Bible fingerprint + confirmed assignment context hash
+ prompt/model/settings/response schema
```

Chỉ gửi utterance cần hỗ trợ, context mặc định 3 trước/sau và batch tối đa 20 target. Approved casting bị bỏ qua trong `unassigned_only`. Cache hit phải validate lại structured response; payload hỏng là safe miss. Không chạy whole-book hoặc tự retry vô hạn.

### TTS synthesis

```text
text_revision_sha256 + engine_version + resolved_voice_id/reference_hash
+ temperature/top_k + chunker_version + silence/crossfade
```

Resolved voice phải đến từ immutable casting/job snapshot. Three-Voice Profile tương lai giảm chi phí quản lý bằng ba voice cấp book; optional character override chỉ dành cho ngoại lệ.

### Export

```text
master_audio_sha256 + format/codec/bitrate + post-processing settings
```

### YouTube Auto downstream

```text
handoff identity/hash + visual timeline/bible/profile revision
```

Fingerprint chi tiết của visual/image/video do YouTube Auto sở hữu.

## Paid smoke policy

- Không chạy paid smoke trong test suite mặc định.
- Gemini smoke dùng synthetic text ngắn, không phải cả chương.
- VieNeu smoke dùng 1–2 segment.
- Chỉ chạy lại khi prompt/model/adapter thay đổi.
- Ghi bằng chứng vào `PROJECT_STATUS.md`, không ghi key.

## Deferred / Only when needed

- Usage ledger, daily batch cap, provider budget/quota dashboard.
- Complex pricing snapshots và estimated-cost accounting.
- Chỉ ưu tiên khi nhu cầu vận hành thực tế chứng minh đây là blocker.

Nếu sau này cần usage ledger, không lưu secret hoặc full text. Provider event tối thiểu có thể gồm:

Không lưu secret hoặc full text. Mỗi provider event chỉ cần:

```text
date, provider, model, job_id, chapter_id, stage,
input_chars, output_chars, request_count, retry_count,
cache_hit, duration_ms, success, error_code, estimated_cost
```

Pricing thay đổi theo thời gian nên không hard-code vào business logic. `pricing_snapshot_version` không thuộc artifact fingerprint; thay giá không invalidates output.

## Checklist khi thêm stage

- Input/output artifact là gì?
- Cache key là gì?
- Thay cấu hình invalidates đến đâu?
- Retry granularity nhỏ nhất là gì?
- Có gọi dịch vụ ngoài hoặc đưa dữ liệu ra ngoài không?
- Có dry-run/fake adapter cho test không?
- Giới hạn batch/quota/disk là gì?
- Cleanup và retention policy là gì?

Không đưa stage mới vào runner khi chưa trả lời các câu hỏi trên.
