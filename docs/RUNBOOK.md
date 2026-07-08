# Operations và Repair Runbook

## Start

```powershell
cd 'D:\Youtube\Story Trans And Audio'
.\run_app.ps1 --host 127.0.0.1 --port 8772 --no-browser
```

Story Audio production UI: `http://127.0.0.1:8772`
VieNeu Gradio riêng: `http://127.0.0.1:7861`
YouTube Auto: `http://127.0.0.1:8765` — do not stop or repurpose this port while switching Story Audio runtimes.

Notes:

- `run_app.ps1` sets `STORY_AUDIO_ALLOW_LIVE_DB=1` for the launched Story Audio process only. Do not persist this variable at user or machine scope.
- Canonical production root is `D:\Youtube\Story Trans And Audio\data`.
- Any isolated runtime must use a different `STORY_AUDIO_DATA_DIR`; isolated data is not merged back into canonical production automatically.
- The acceptance-to-production switch has been verified: stop only the acceptance app, then relaunch canonical Story Audio on `8772` and re-check `/api/runtime`.

## Health check

```powershell
Invoke-RestMethod http://127.0.0.1:8772/api/config
Invoke-RestMethod http://127.0.0.1:8772/api/runtime
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\doctor.py
```

Expect canonical production to report:

- `data_root = D:\Youtube\Story Trans And Audio\data`
- `is_canonical_live_data_root = true`
- `is_canonical_live_db = true`

UI runtime banner meanings:

- `CANONICAL PRODUCTION`: the app is pointed at `D:\Youtube\Story Trans And Audio\data`
- `ISOLATED / NON-PRODUCTION`: the app is using a disposable non-canonical `STORY_AUDIO_DATA_DIR`
- `RUNTIME UNKNOWN`: `/api/runtime` has not resolved yet or failed; primary mutation controls stay disabled until identity is known

Active output labels:

- `ACTIVE AUDIO` on a chapter means playback/download is backed by that chapter's bound active artifact.
- `ACTIVE OUTPUT` on a job means that job currently backs a chapter's active audio.
- `HISTORICAL` on a job means the job completed successfully but no longer backs the chapter's current audio.
- Source of truth is the existing DB binding `chapters.active_audio_artifact_id -> artifacts -> job_chapters`, not newest job ID or latest completion time.

Casting review entry points:

- From the chapter list, use `Review Character Voices` to open the selected chapter directly on the `Character Voices` workspace.
- Chapter rows show `CASTING REVIEW NEEDED` when the latest persisted casting plan is still a draft, and `CASTING APPROVED` when the latest plan is approved.
- Inside the chapter dialog, the `Character Voices` shortcut remains available in the header and the panel now separates `AI Draft / Suggestions`, `Casting Plan Review`, and `Render / Production Output`.
- The production-step banner at the top of Character Voices is the quickest source of truth for what you are looking at: `Draft Plan`, `Approved Plan`, `Active Audio`, or `Historical Job`, plus the current Casting Plan identity and any active Job / Plan binding.

## Production runner

Preflight only:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\run_production_chapter.py --data-root 'D:\IsolatedStoryAudio\data' --api-base 'http://127.0.0.1:8768' --book-id <BOOK_ID> --chapter-number <CHAPTER_NUMBER> --casting-plan-id <CASTING_PLAN_ID>
```

Submit explicit new job:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\run_production_chapter.py --data-root 'D:\IsolatedStoryAudio\data' --api-base 'http://127.0.0.1:8768' --book-id <BOOK_ID> --chapter-number <CHAPTER_NUMBER> --casting-plan-id <CASTING_PLAN_ID> --submit
```

Watch existing verified job:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\run_production_chapter.py --data-root 'D:\IsolatedStoryAudio\data' --api-base 'http://127.0.0.1:8768' --book-id <BOOK_ID> --chapter-number <CHAPTER_NUMBER> --casting-plan-id <CASTING_PLAN_ID> --job-id <JOB_ID> --watch
```

Resume interrupted or paused same job:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\run_production_chapter.py --data-root 'D:\IsolatedStoryAudio\data' --api-base 'http://127.0.0.1:8768' --book-id <BOOK_ID> --chapter-number <CHAPTER_NUMBER> --casting-plan-id <CASTING_PLAN_ID> --job-id <JOB_ID> --resume --watch
```

Write manifest to explicit absolute path:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\run_production_chapter.py --data-root 'D:\IsolatedStoryAudio\data' --api-base 'http://127.0.0.1:8768' --book-id <BOOK_ID> --chapter-number <CHAPTER_NUMBER> --casting-plan-id <CASTING_PLAN_ID> --job-id <JOB_ID> --watch --manifest-out 'D:\IsolatedStoryAudio\data\manifests\job_<JOB_ID>_chapter_<CHAPTER_NUMBER>.json'
```

Notes:

- `--resume` la explicit mutation va chi dung cho job `paused` hoac `interrupted`; no khong retry failed jobs.
- Runner fail-closed neu `--data-root` tro vao canonical live root.
- `--watch` la read-only va khong tu dong resume/cancel/regenerate/accept/reject.

## Unified production workflow

Preflight only:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\run_production_workflow.py --data-root 'D:\IsolatedStoryAudio\data' --api-base 'http://127.0.0.1:8768' --book-id <BOOK_ID> --chapter-number <CHAPTER_NUMBER> --casting-plan-id <CASTING_PLAN_ID>
```

Completed job through checklist:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\run_production_workflow.py --data-root 'D:\IsolatedStoryAudio\data' --api-base 'http://127.0.0.1:8768' --book-id <BOOK_ID> --chapter-number <CHAPTER_NUMBER> --casting-plan-id <CASTING_PLAN_ID> --job-id <JOB_ID> --through checklist
```

Explicit submit:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\run_production_workflow.py --data-root 'D:\IsolatedStoryAudio\data' --api-base 'http://127.0.0.1:8768' --book-id <BOOK_ID> --chapter-number <CHAPTER_NUMBER> --casting-plan-id <CASTING_PLAN_ID> --submit --through checklist
```

Explicit resume:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\run_production_workflow.py --data-root 'D:\IsolatedStoryAudio\data' --api-base 'http://127.0.0.1:8768' --book-id <BOOK_ID> --chapter-number <CHAPTER_NUMBER> --casting-plan-id <CASTING_PLAN_ID> --job-id <JOB_ID> --resume --through checklist
```

Notes:

- Stdout ends with one final JSON object using schema `story-audio-production-workflow/v1`.
- Progress events are emitted as stderr JSON Lines.
- Default workflow outputs live under `data\workflow\job_<JOB_ID>_chapter_<CHAPTER_NUMBER>\`.
- The workflow never auto-resumes, regenerates, accepts, rejects, or makes the final QA decision; human listening remains the final authority.
- When comparing an accepted chapter against older evidence jobs, use the UI `ACTIVE OUTPUT` and `HISTORICAL` labels rather than guessing from job recency.
- Canonical production remains fail-closed by default. To run the unified workflow against `D:\Youtube\Story Trans And Audio\data`, the operator must pass `--allow-canonical-production`; creating a new canonical job still requires `--submit`, while downstream-only canonical outputs require an exact `--job-id`. Isolated mode behavior is unchanged.
- Canonical mode still verifies `/api/runtime`, exact data-root match, approved Casting Plan identity, and duplicate pending/running jobs before any submit occurs.
- Voice availability checks now accept both preset voice IDs and active usable custom voice IDs such as `custom:25`; missing, inactive, or revision-less custom voices still fail closed before submit.

Explicit canonical production submit:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\run_production_workflow.py --data-root 'D:\Youtube\Story Trans And Audio\data' --api-base 'http://127.0.0.1:8772' --book-id <BOOK_ID> --chapter-number <CHAPTER_NUMBER> --casting-plan-id <CASTING_PLAN_ID> --submit --through checklist --allow-canonical-production
```

Downstream-only canonical manifest / QA / checklist for an existing completed job:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\run_production_workflow.py --data-root 'D:\Youtube\Story Trans And Audio\data' --api-base 'http://127.0.0.1:8772' --book-id 1 --chapter-number 357 --casting-plan-id 18 --job-id 17 --through checklist --allow-canonical-production
```

## Casting review flow

Speaker review sequence:

1. `Select visible`
2. `Accept selected suggestions`
3. `Create/Update Casting Plan from AI Draft`

Notes:

- After step 2, decisions are still local-only until `Create/Update Casting Plan from AI Draft` creates a new immutable Casting Plan revision.
- If a Casting Plan already exists, treat the AI draft area as advanced tooling: it can create a newer plan, but it does not approve the current one and it does not render directly.
- Use `Jump to pending review` to reach the next unreviewed target and `Jump to Casting Plan approval` to return to the real plan-approval controls without scrolling the full utterance list.
- If Character Voices shows `Current active audio: Job X / Plan vY`, that is the playback source of truth for the current chapter audio.
- If the panel also warns `Current playback still uses the active historical plan until a new job is rendered`, the draft you are reviewing is newer than the chapter's currently active audio and has not been rendered yet.
- The plan approval button now includes the plan revision (`Approve Casting Plan vN`), and the render action shows the exact Casting Plan identity that will be rendered. Use those labels as the authoritative boundary between review and production output.
- Historical job diagnostics include `Open current Character Voices` so the operator can jump from an older evidence job back to the authoritative casting workspace for the chapter.

## Offline audio QA

Objective heuristics only, no live root:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\run_audio_qa.py --manifest 'D:\IsolatedStoryAudio\data\manifests\job_<JOB_ID>_chapter_<CHAPTER_NUMBER>.json' --output 'D:\IsolatedStoryAudio\data\qa\job_<JOB_ID>_chapter_<CHAPTER_NUMBER>_audio_qa.json'
```

Notes:

- Manifest path phai la absolute path tu isolated data root.
- `--output` la optional; neu bo qua, script se dung deterministic default filename duoi `data\qa\`.
- Script chi dung FFmpeg/FFprobe local va SQLite read-only; khong goi API mutate, Gemini, TTS, regenerate, accept, hay reject.
- Report la objective signal heuristics only; operator van la authority cho pronunciation, naturalness, va speaker correctness by ear.
- Canonical production root remains rejected by default; only pass `--allow-canonical-production` when the workflow or operator has already explicitly authorized canonical downstream generation for the exact completed job being audited.

## Listening checklist

Generate the deterministic local listening package from a verified manifest plus Task 11C1 QA report:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\build_listening_checklist.py --manifest 'D:\IsolatedStoryAudio\data\manifests\job_<JOB_ID>_chapter_<CHAPTER_NUMBER>.json' --qa-report 'D:\IsolatedStoryAudio\data\qa\job_<JOB_ID>_chapter_<CHAPTER_NUMBER>_audio_qa.json'
```

Notes:

- The checklist is offline and local-only: no DB/API mutation, no Gemini, no TTS, no regenerate, no accept/reject.
- Default output is deterministic under `data\listening\job_<JOB_ID>_chapter_<CHAPTER_NUMBER>\index.html`.
- Local review state stays in browser `localStorage`; review JSON export is browser-only and is not imported back into Story Audio.
- Human listening remains the final authority for pronunciation, naturalness, emotion, and speaker correctness.
- Canonical production root remains rejected by default; only pass `--allow-canonical-production` when the exact completed canonical job has already been explicitly approved for downstream manifest/QA/checklist generation.

Logs:

```text
logs/app.stderr.log
logs/app.stdout.log
```

Không copy log ra ngoài trước khi kiểm tra secret/path/text nhạy cảm.

## Stop an toàn

- Pause/cancel job từ UI trước.
- Dừng process đang listen cổng 8766 sau khi worker về ranh giới segment.
- Không xóa `.partial`, WAL hoặc `data/work` khi process còn chạy.

## Lỗi thường gặp

### Chưa có Gemini key

- Đặt `GEMINI_API_KEY`, hoặc dùng `secrets/gemini_api_key.txt`.
- UI chỉ báo configured/not configured.
- Resume job; block verified không bị gọi lại.

### Gemini lexical integrity failed

- Xem repaired block và source diff trong diagnostic tương lai.
- Không sửa DB status trực tiếp để bỏ qua validator.
- Retry một lần; nếu tiếp tục lỗi, dùng `needs_review` hoặc mode `off` cho chapter revision mới.

### Voice not found

- Tải lại danh sách preset voice.
- Không sửa voice giữa job đang chạy; tạo job revision mới.
- API hiện validate voice trước khi tạo job.

### Voice casting và backward compatibility

- Schema v3 dùng `voice_override_id` optional; `default_voice_id` vẫn là legacy compatibility field, không xóa hoặc đổi hàng loạt.
- CastingPlan/job đã tạo giữ nguyên `resolved_voice_id`. Retry phải dùng snapshot cũ.
- Three-Voice Profile core và UI casting đã có trong runtime.
- Khi profile được triển khai, đổi narrator/male/female/unknown fallback hoặc character override chỉ áp dụng cho casting/job mới.
- Utterance-level voice override hiện chưa tồn tại; không hướng dẫn người vận hành sửa JSON/DB để giả lập.

### Three-Voice workflow

```text
Create Book Voice Profile
→ preview narrator/male/female/fallback
→ configure character book-default/custom override
→ review effective voice/source/needs-review
→ save and approve casting
→ create job
```

Profile/override edit chỉ áp dụng cho casting plan và job mới. Book chưa có profile hiển thị empty state và không được tự tạo mặc định; legacy override chỉ bị clear khi người dùng chủ động chọn **Use book default** rồi lưu.

### Character Bible import

Chạy dry-run trước khi ghi dữ liệu:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\import_character_bible.py `
  --book-id 1 `
  --file character_bible.json `
  --dry-run
```

Apply chỉ khi dry-run không có invalid/conflict:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\import_character_bible.py `
  --book-id 1 `
  --file character_bible.json `
  --apply
```

Dùng `--json` để lấy structured plan, và `--update-existing` khi muốn cập nhật các field metadata được phép. Import không nhận path từ nội dung JSON, không lưu full JSON trong SQLite, không đổi Book Voice Profile, không tạo casting plan/job và không resolve lại job cũ. `null` trong `voice_override_id` không clear override hiện có.

### Gemini Speaker Assignment Draft

```text
Prepare Character Bible
→ generate speaker draft
→ filter và inspect confidence/context
→ chọn suggestion, alternative hoặc manual speaker
→ preview effective voice
→ approve reviewed decisions thành Casting Plan revision
→ review phần còn lại trên đúng base plan
→ tạo job thủ công sau khi casting đã đúng
```

Smoke một utterance, không tự apply vào casting:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\speaker_assignment_draft.py `
  --chapter-id 1982 --mode reanalyze --utterance-id u0001-a99461c9571c
```

`unassigned-only` bỏ qua utterance đã confirmed; **Regenerate Draft** dùng `reanalyze` để xem lại toàn chương. Mọi kết quả Gemini vẫn cần review. Approval chỉ tạo Casting Plan revision, không tạo job/audio và không sửa Character Bible hay Book Voice Profile.

Approve từng phần phải tiếp tục từ current approved base plan. Draft stale do TextRevision, Character Bible hoặc external Casting Plan change vẫn xem được nhưng nút approve bị khóa. Exact repeat cùng decision set là idempotent; muốn sửa quyết định đã approve, chọn lại trên current base để tạo revision mới, không sửa blob cũ.

### Job bị interrupted

- Startup chuyển job đang chạy thành `interrupted`.
- Worker tự nhận lại, verify file và tiếp tục.
- Nếu không chạy, dùng Resume/Retry; không xóa segment đã verify.

### FFmpeg/FFprobe lỗi

- Chạy `ffmpeg -version` và `ffprobe -version`.
- Giữ segment WAV; chỉ retry assemble/export.
- Không gọi lại VieNeu nếu segment còn hợp lệ.

### Hết dung lượng

- Pause queue.
- Chạy doctor để xem dung lượng.
- Cleanup chỉ segment của chapter đã hoàn tất và hết retention.
- Không xóa active master/audio/timeline.

### Active artifact thiếu file

- Doctor sẽ báo ERROR.
- Đánh dấu artifact stale/failed qua repair tool tương lai; hiện không chỉnh DB thủ công nếu chưa backup.
- Re-export từ master nếu master còn; nếu không, resume từ segment.

## Backup và restore

Pause job trước; backup mặc định từ chối khi có job active:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\backup.py backups\my-backup
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\restore.py backups\my-backup --verify-only
```

Restore sang thư mục mới:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\restore.py `
  backups\my-backup D:\StoryAudio-Restore\data
```

- Không dùng `--exclude-work` nếu cần bảo toàn checkpoint WAV.
- Không dùng `--allow-active` trừ khi chấp nhận work snapshot có thể không đồng nhất.
- `--overwrite` không xóa destination cũ; nó chuyển thư mục cũ sang `pre-restore-*`.
- EPUB nguồn ngoài `data/` chưa nằm trong backup version 1.

## Khi cần báo lỗi

Thu thập tối thiểu:

- Job ID, chapter number, stage/status.
- `scripts/doctor.py` output.
- Error message trong job/chapter.
- Model/voice/prompt version, không gửi API key.
- Danh sách file liên quan và kích thước, không cần gửi toàn bộ audio/text trước.
## YouTube Auto handoff

Export một completed chapter bằng đúng job snapshot:

```powershell
python scripts\export_youtube_handoff.py --chapter-id 1982 --job-id 3
```

Bundle mặc định nằm trong `data\exports\youtube_auto\`. Chạy lại cùng identity sẽ verify và reuse; `--overwrite` phải được nêu rõ. Exporter copy audio, không symlink và không sửa source artifact.
