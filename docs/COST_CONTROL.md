# Cost Control Policy

Chi phí gồm API Gemini/image, thời gian VieNeu CPU, FFmpeg, dung lượng ổ đĩa và thời gian kỹ sư điều tra lỗi.

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

Hiện cache mới ở cấp `job_chapter`; shared cache giữa job là hạng mục P1.

### TTS synthesis

```text
text_revision_sha256 + engine_version + voice_id/reference_hash
+ temperature/top_k + chunker_version + silence/crossfade
```

### Export

```text
master_audio_sha256 + format/codec/bitrate + post-processing settings
```

### Visual sau này

```text
scene_text_sha256 + bible revision + visual_profile revision
+ model/provider/seed
```

## Paid smoke policy

- Không chạy paid smoke trong test suite mặc định.
- Gemini smoke dùng synthetic text ngắn, không phải cả chương.
- VieNeu smoke dùng 1–2 segment.
- Chỉ chạy lại khi prompt/model/adapter thay đổi.
- Ghi bằng chứng vào `PROJECT_STATUS.md`, không ghi key.

## Batch guardrails cho M1

- `max_chapters_per_job` và confirm lần hai khi vượt ngưỡng.
- `max_gemini_requests_per_day` hoặc soft budget cảnh báo.
- Disk hard threshold và estimated temp/output bytes.
- Circuit breaker khi tỷ lệ Gemini/TTS failure vượt ngưỡng.
- Dừng batch sau N chương đầu nếu profile mới có lỗi.

## Usage ledger cần thêm

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
