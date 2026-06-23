# Next Task

Current Sprint:
P1 Audio Quality

Current Task:
Disk estimate chính xác và cleanup dry-run

Status:
Ready for specification. Shared Gemini repair cache completed on 2026-06-23.

Definition of Done:
- Ước lượng dung lượng trước khi tạo job theo khoảng chương và output profile.
- Cleanup có dry-run rõ file/byte sẽ giải phóng trước khi apply.
- Không xóa verified artifact, active revision hoặc text blob còn được tham chiếu.
- Có offline tests cho estimate và cleanup safety.
- Doctor và toàn bộ offline tests đạt.

Do Not Work On:
- Voice cloning
- AI speaker detection
- Emotion/loudness normalization
- SRT/VTT
- Image Pipeline
- Video Pipeline
