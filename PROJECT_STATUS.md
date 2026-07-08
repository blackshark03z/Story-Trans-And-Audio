# Trạng thái dự án

**Cập nhật:** 2026-07-08T23:05 (Asia/Saigon)
**Milestone:** Task 13C Step-by-Step Production Flow UI
**Trạng thái:** official verdict remains `PRODUCTION_GO`; Chapter 357 canonical Job `17` remains the accepted production evidence, and the Character Voices operator UI now exposes a step-by-step production flow with explicit step status, blockers, and next/continue navigation before any further production mutation

File này ghi lại baseline đã xác minh. **Git là nguồn quyền cuối cùng** về current HEAD, branch và working tree. Chạy `git status` và `git log -1` để xác định trạng thái hiện tại. File này chỉ ghi lại baseline code/test đã verified tại một commit cụ thể.

## Baseline đã xác minh

**Last verified against commit:** `4b82cdd57c6626b03c086146c4e9a12e5543f60d`
**Last verified branch:** `main`
**Last verified date:** 2026-07-08

**Last verified focused Task 13C baseline:**
- Focused Character Voices / production-flow UI coverage: 22 tests passing
- Full offline test suite baseline: 907 tests passing, 1 skipped
- Verification command: `unittest discover -s tests`
- Verified at commit: `4b82cdd57c6626b03c086146c4e9a12e5543f60d`
- Verified date: 2026-07-08

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
- Task 11B1 complete tại implementation commit `556023a94670730cafa995aa30d70a389f4a995a`: thêm guarded production chapter runner CLI `scripts/run_production_chapter.py` + `story_audio.production_runner`, endpoint read-only `GET /api/runtime`, endpoint exact-ID `GET /api/casting/{casting_plan_id}`, explicit isolated data root enforcement, Unicode-safe JSON submit (`ensure_ascii=True`), duplicate-job protection, immutable binding verification, và structured CLI error contract.
- Task 11B1 verification: focused runner/API 36/36 pass, operational/live-guard 17/17 pass, full offline suite 759/759 pass.
- Task 11B1 disposable integration smoke PASS trên runtime cô lập: verified runtime identity, exact Casting Plan lookup, duplicate Chapter 629 job detection trả `already_completed`, Unicode payload path pass, runtime mismatch fail-closed exit `3`, authoritative V2 runtime/data không đổi, và không tạo production job thật trong bước verify này.
- Task 11B2 complete tại implementation commit `50a2a397b1626ca8abaa1d1ffab5755fdebf5eac`: runner hỗ trợ exact existing/new job selection, structured `--watch` progress, explicit same-job `--resume`, terminal validation cho completed job, và final manifest schema `story-audio-production-manifest/v1`.
- Task 11B2 terminal validation kiểm tra exact segment counts, sequence continuity, immutable Text Revision/Casting Plan bindings, no open candidate attempts, artifact ownership trong isolated data root, timeline count/order, và persisted hash/path integrity.
- Task 11B2 compatibility rule: completed historical jobs có `segments.casting_plan_id = NULL` vẫn được chấp nhận chỉ khi `job_chapter` binding và immutable voice snapshot chứng minh đúng Casting Plan; không nới lỏng ownership theo job/revision/plan.
- Task 11B2 verification: focused runner/API/manifest 51/51 pass, operational/live-guard 17/17 pass, full offline suite 774/774 pass.
- Task 11B2 disposable completed-job smoke PASS trên runtime `D:\Youtube\StoryAudioTask11B2Smoke`: watch-only existing Job 2 / Chapter 629 tạo manifest `job_2_chapter_629.json`, xác minh Text Revision `1258`, Casting Plan `2`, 119/119 verified segments, artifact SHA-256 đúng, và không mutate authoritative V2 runtime/data.
- Task 11C1 complete tại implementation commit `9cc41720b7da755dd11302e053573dbb9272cd1a`: thêm `story_audio/audio_qa.py`, CLI `scripts/run_audio_qa.py`, và focused tests cho objective audio QA offline dựa trên production manifest.
- Task 11C1 objective QA đo chapter/segment duration, loudness, clipping, silence, speech-rate và representative voice summaries; report deterministic, UTF-8, atomic, fail-closed khi conflict, và không gọi API mutate / regenerate / accept / reject.
- Task 11C1 clipping semantics: report tách `peak_reaches_full_scale`, `hard_clipping_sample_count`, `hard_clipping_sample_ratio`, `longest_full_scale_run_samples`, `near_clipping_sample_count`, và `near_clipping_sample_ratio`; WAV PCM integer 8/16/24/32-bit được phân tích trực tiếp, codec unsupported bị reject rõ ràng.
- Task 11C1 silence semantics: trailing silence vẫn được đo khách quan nhưng risk shortlist dùng context chapter/voice median thay vì flood toàn bộ segment padding; report vẫn giữ distribution chapter-level để operator review.
- Task 11C1 determinism smoke PASS trên root disposable `D:\Youtube\StoryAudioTask11B2Smoke`: report mặc định `job_2_chapter_629_audio_qa.json` được tạo lại sau khi loại stale disposable report cũ, rồi chạy lần hai reuse byte-identical với cùng SHA-256 `f1f889e776c2b88d5bad997b75a4438e9b4ab977cf45cf4bbad92138a74b1581`.
- Task 11C1 smoke evidence Chapter 629: 119 segment, 3 voices, master/final 824420/824427 ms, master mean volume `-15.95 dBFS`, peak `0.0 dBFS`, risk counts `hard_clipping=11`, `near_clipping=14`, `long_internal_silence=38`, `long_trailing_silence=6`, `speech_rate_outlier=15`, `very_long_segment=22`, `adjacent_loudness_jump=1`, `loudness_outlier=2`.
- Task 11C1 no-mutation verification: disposable DB/master/timeline/final hashes giữ nguyên; representative segment WAV hashes (sequence 1/50/119) khớp persisted SHA; live DB, V1 DB và V2 DB không đổi.
- Task 11C2 complete tại implementation commit `26b8f50acabed3f5f4a7a8c89e62128469221a1d`: thêm `story_audio/listening_checklist.py`, CLI `scripts/build_listening_checklist.py`, và focused tests cho deterministic offline HTML listening package dựa trên production manifest + Task 11C1 QA report.
- Task 11C2 listening package là local human-review aid only: header identity, chapter overview, master/final audio controls, deterministic priority queue, localStorage-scoped review state, và browser-only review JSON export schema `story-audio-listening-review/v1`.
- Task 11C2 fail-closed contract: manifest/QA/job/chapter/Text Revision/Casting Plan/data-root identity phải khớp; live root, traversal, symlink escape, conflicting output, artifact mismatch và unsafe relative path đều bị chặn.
- Task 11C2 deterministic smoke PASS trên Chapter 629 disposable runtime: package `D:\Youtube\StoryAudioTask11B2Smoke\data\listening\job_2_chapter_629\index.html`, 25 selected cards, 11/11 hard-clipping segments included, first/last segment included, 3 realized voices represented, byte-identical reuse on second run, no DB/audio mutation.
- Task 11C2 human boundary: operator listening vẫn là authority cuối cùng; package không import review JSON trở lại app, không mutate DB/API, và không tự regenerate / accept / reject bất kỳ segment nào.
- Task 11D1 complete tại implementation commit `8b0d4485301c8aa03ccc447d72ba0991e15c77a1`: thêm `story_audio/production_workflow.py`, CLI `scripts/run_production_workflow.py`, va focused tests cho unified operator workflow noi ket preflight, guarded runner, production manifest, objective audio QA va deterministic listening checklist.
- Task 11D1 workflow contract: mac dinh `--through preflight`; `--submit` va `--resume` la explicit mutation flags va mutually exclusive; paused/interrupted jobs khong auto-resume; completed jobs co the tiep tuc xuong manifest/qa/checklist ma khong tao duplicate job.
- Task 11D1 output contract: stdout chi in mot final JSON object schema `story-audio-production-workflow/v1`; progress logs dung stderr JSON Lines; downstream manifest/qa/checklist phai cung runtime identity, data root, job/chapter/Text Revision/Casting Plan bindings va fail-closed khi conflict.
- Task 11D1 disposable smoke PASS tren Chapter 629 completed-job path: workflow reuse completed Job 2 de tao manifest SHA-256 `6bb1fb09a37740a8fbebbc8fec648b92d21ec0db2a3f61250386f9fe3df7bdbb`, workflow QA SHA-256 `831b7d021a711ba24cbc715b577ef54d3baf1a5e0aeb4badcb0ac21104712ead`, va checklist SHA-256 `dcec99be33e57daf15983305d8fd5de8b5e9e755832cb7e0ca9b0fac59126f7f`; no mutation ghi nhan PASS.
- Task 11D2C complete tại implementation commit `f96ac056a0d213ffc3fb834e7e03917900019b7d`: utterance splitter bump len `utterance-v3`, uu tien sentence punctuation roi clause punctuation roi whitespace, tranh orphan-tail mot tu/cum rat ngan, va giu deterministic text offsets cho manual offset casting.
- Task 11D2C verification: focused casting/speaker tests 48/48 pass; full offline suite 863/863 pass, 1 skipped; speaker-assignment request identity pin `CHUNKER_VERSION` moi nen draft/cache khong reuse semantics `utterance-v1`.
- Chapter 357 isolated review verification: Text Revision `714` duoc rebuild draft voi chunker `utterance-v3`; boundary `... lam duoc dieu nay,` / `chi can ta bo tri mot phen thi cua hang rat kho phat hien.` duoc human review xac nhan; chua approve Casting Plan va chua render TTS.
- Task 11D2 complete tren runtime isolated `D:\Youtube\StoryAudioAcceptanceRun1\data`: human review approved reviewed speaker decisions tao Casting Plan #6 / revision 6 (`utterance-v3`, 96 utterance, voice distribution Ngoc Lan 90 / Duc Tri 6).
- Chapter 357 production acceptance PASS: Job #2 / JobChapter #2 render tu Casting Plan #6, 96/96 segment verified, final M4A `D:\Youtube\StoryAudioAcceptanceRun1\data\output\1-quang-am-chi-ngoai\chapter_0357\job_2\render_0001\chapter.m4a`, human nghe toan bo va ket luan PASS.
- Acceptance evidence xac nhan speaker correctness cho seq 42-44 va 90-92 = Lao to Kim Cuong Tong -> Duc Tri; seq 41, 45, 93 = Narrator -> Ngoc Lan. Job #1 duoc giu nguyen lam evidence cho casting cu va khong phai ban accepted.
- Unified workflow da duoc validate end-to-end tren chapter that: preflight -> explicit submit -> watch -> manifest -> objective QA -> listening checklist, khong con blocker acceptance.
- Task 11D3A rollout-readiness audit concluded runtime identity visibility was the highest-value pre-rollout fix: operators needed an always-visible canonical vs isolated indicator and fail-closed behavior while runtime identity was still unknown.
- Task 11D3B1 local implementation ready: UI header now shows persistent runtime identity (`CANONICAL PRODUCTION`, `ISOLATED / NON-PRODUCTION`, or `RUNTIME UNKNOWN`) with short data-root display plus full-path tooltip sourced from `GET /api/runtime`.
- Task 11D3B1 safety behavior: while runtime identity is unresolved or `/api/runtime` fails, primary mutation controls stay disabled for import, queue submit, speaker-draft generation/regeneration, Character Bible apply/clear, casting draft save, casting approval, job render, and segment/job retry-style actions; canonical and isolated runtimes are re-enabled after identity resolves.
- Task 11D3B1 operator verification: restarted only Story Audio on port `8772`, kept YouTube Auto on `8765` untouched, confirmed `/api/runtime` still points to canonical root `D:\Youtube\Story Trans And Audio\data`, and rendered DOM shows banner `CANONICAL PRODUCTION` with short path `...\Youtube\Story Trans And Audio\data`.
- Task 11D3B1 custom-voice verification: canonical production runtime still reports 4 active custom voices (`Hứa Thanh`, `Chanlee`, `Lý Sư Thúc`, `Experiment B - Transcript Test`); no production books, chapters, jobs, casting plans, custom voices, or artifacts were mutated during this task.
- Task 11D3B1 verification: focused runtime/UI contract tests 237/237 pass; full offline suite 870/870 pass with 1 expected Windows symlink-privilege skip.
- Task 11D3B2 local implementation ready: chapter lists, chapter detail audio cards, jobs list, and job diagnostics now distinguish the chapter's active artifact-backed output from completed historical jobs without changing DB status semantics.
- Task 11D3B2 source of truth is the existing canonical binding `chapters.active_audio_artifact_id -> artifacts.id -> artifacts.job_chapter_id -> job_chapters.job_id / casting_plan_id`; UI no longer has to infer current output from newest job ID, completion time, or `completed` status alone.
- Task 11D3B2 operator labels: chapter rows with real bound audio show `ACTIVE AUDIO`; completed jobs backing that audio show `ACTIVE OUTPUT`; completed jobs for the same chapter that are no longer bound show `HISTORICAL`; job diagnostics add an explicit `ACTIVE CHAPTER OUTPUT` or `HISTORICAL JOB` banner.
- Task 11D3B2 safety boundary: playback and download still use the chapter's active artifact endpoint, not a guessed latest job; no submit, render, regenerate, approve, or other production-data mutation path changed.
- Task 11D3B2 verification: focused active-output/runtime/diagnostics UI tests passed, segment-regeneration UI compatibility remained green, and the full offline suite passed at 877/877 with 1 expected Windows symlink-privilege skip.
- Task 11D3B1 and Task 11D3B2 are pushed and complete on `main` at `0f6cc33c333710e4c1841a5b442d4c9e8125dd5b`; canonical runtime remains `http://127.0.0.1:8772` and YouTube Auto remains isolated on `http://127.0.0.1:8765`.
- Task 11D3C final readiness re-audit completed with readiness score `8.5/10` and official decision `PRODUCTION_GO`.
- Chapter 357 Job 2 remains the authoritative acceptance evidence: Text Revision `714`, Casting Plan `#6`, Job `#2`, full human listening PASS.
- Task 11D3B3 local implementation ready on top of `55404fb6aec6b95d071432f5bf9e52c5c2c5c60b`: chapter rows now expose a direct `Review Character Voices` CTA plus `CASTING REVIEW NEEDED` / `CASTING APPROVED` badges from latest casting-plan context rather than job heuristics.
- Task 11D3B3 operator guidance: Character Voices now shows plan revision + status in-context, short draft guidance (`Review assignments before rendering`), jump shortcuts for pending review and approval controls, a local-only note after bulk review (`Decisions are local until final approval.`), and latest approval revision feedback after speaker-review approval.
- Task 11D3B3 active-audio guardrail: when a chapter already has active playback, Character Voices now surfaces `Current active audio: Job X / Plan vY`; if the operator is reviewing a newer draft than the active plan, the panel warns that playback still uses the historical active plan until a new job is rendered.
- Task 11D3B3 diagnostics guidance: historical job diagnostics now include a direct `Open current Character Voices` action so the operator can jump from old evidence back to the authoritative casting workspace without guessing.
- Task 11D3B3 verification: focused active-output/speaker-review/runtime UI coverage passed at 22/22, full offline suite passed at 879/879 with 1 expected Windows symlink-privilege skip, and live production verification on `8772` preserved the canonical runtime banner, 4 active custom voices, and active/historical output labels while leaving YouTube Auto on `8765` untouched.
- No second acceptance chapter is required before rollout. The next highest-value task is `Task 13D - Live Canonical Operator Walkthrough for Step-by-Step Production Flow`.
- Task 12C1 added explicit canonical unified-workflow mode behind `--allow-canonical-production`. The mode still fail-closes by default, requires explicit `--submit`, keeps exact approved Casting Plan identity checks, verifies `/api/runtime` canonical binding, and blocks duplicate pending/running jobs before any canonical production mutation.
- Task 12C2 local implementation extends production workflow voice-availability preflight to accept both preset voices and active usable custom voices (`custom:<id>`). Canonical Chapter 357 Plan 18 style bindings no longer fail just because the plan references `custom:25` / `custom:26`; missing, inactive, or no-revision custom voices still fail closed.
- Task 12C3 local implementation threads explicit canonical approval through downstream manifest/QA/checklist generation. `audio_qa` and `listening_checklist` still refuse canonical production by default, but the unified workflow can now run downstream-only for an already completed canonical job when the operator passes `--allow-canonical-production` together with an explicit `--job-id`.
- Task 12C3 downstream safety remains fail-closed: before QA/checklist, the workflow now re-reads the manifest and verifies job/chapter/Text Revision/Casting Plan identity, final active artifact ID/path/hash, and completed terminal state; downstream-only canonical mode does not submit, render, retry, regenerate, accept, or reject anything.
- Task 12C4 canonical downstream outputs for Chapter 357 / Job 17 completed successfully under `D:\Youtube\Story Trans And Audio\data\workflow\job_17_chapter_357\`: manifest SHA `a746b7b97e73ec1e2fc1348f8d9cf2a0c0aba484b178a6639a88634f99dbae76`, QA JSON SHA `ccb2a59c12d15acc264f9ee634af467419a9d265965aaf598f6db485f2a517b3`, and checklist SHA `8dc58df50d91be88527605910d0061a642dce9b15e9cb19c3ac50ada2c7f1e43`.
- Task 12D records the human verdict for canonical Chapter 357 as `HUMAN_QA_PASS_WITH_MINOR_PRONUNCIATION_NOTES`. Binding remains Chapter 357 -> Job 17 -> Casting Plan 18 -> active artifact 48 -> final M4A SHA `024e9f8cc1a646095eb84fad71d532fc04875e9eb34609a397e44c6f3153b675`; no production audio, artifact, or DB state was changed while recording this result.
- The checklist's detailed operator notes are not persisted in Story Audio or the repository by default. Listening review state lives in browser `localStorage`, and detailed notes only become portable if the operator explicitly exports review JSON from the checklist page.
- Task 13A local implementation simplifies Character Voices for routine production use without changing backend semantics: the panel now shows a persistent production-step banner, separates `AI Draft / Suggestions`, `Casting Plan Review`, and `Render / Production Output`, de-emphasizes AI draft tools when a Casting Plan already exists, and makes render/approval labels carry exact Casting Plan identity.
- Task 13A operator guardrails: `Jump to Casting Plan approval` now targets the real plan-approval controls instead of the speaker-draft decision area; the speaker-draft approval action now clearly reads as creating/updating a Casting Plan from AI review rather than approving the plan itself.
- Task 13A verification: `node --check ui/app.js` pass; focused Character Voices UI tests 17/17 pass; full offline suite 902/902 pass with 1 expected Windows skip. No production DB, audio, artifact, job, or casting-plan data was mutated during this task.
- Task 13B local implementation adds operator-friendly guided flow without changing backend semantics: Character Voices now opens with a visible `Start Here / Production Flow` guide, plain-language descriptions for Book Voice Profile / Character Bible / AI Speaker Draft / Casting Plan Review / Render areas, and stronger `Advanced / Debug` labeling for diagnostics and speaker-draft tooling.
- Task 13B next-action guidance: the chapter workspace now shows `Recommended Next Action` based on current chapter/casting state (`no text`, `text not approved`, `no casting plan`, `casting plan draft`, `casting plan approved`, `job running`, `active audio ready for qa`, and optional `human qa accepted` when that state is available in chapter detail).
- Task 13B verification: `node --check ui/app.js` pass; focused Character Voices / active-output UI tests 20/20 pass; full offline suite 905/905 pass with 1 expected Windows skip. No production DB, audio, artifact, job, or casting-plan data was mutated during this task.
- Task 13C local implementation turns the top-level Character Voices guide into a true step-by-step operator flow: `Select Chapter`, `Text Ready`, `Character Bible / Characters`, `Voice Assignment / Casting`, `Approve Casting Plan`, `Render Audio`, `QA Checklist`, and `Human QA Verdict`.
- Task 13C flow behavior: each step now shows plain-language purpose, current status, required operator inputs, what happens after, and explicit `Back` / `Continue` / `Next` controls. `Next` blocks with a visible reason when prerequisites are missing, and the flow no longer suggests AI draft generation or rerender as the normal path when an existing Casting Plan or active audio already exists.
- Task 13C verification: `node --check ui/app.js` pass; focused Character Voices / active-output UI tests 22/22 pass; full offline suite 907/907 pass with 1 expected Windows skip. No production DB, audio, artifact, job, or casting-plan data was mutated during this task.

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
- [x] Task 11B1: Guarded production chapter runner with isolated-root enforcement, runtime/casting read endpoints, duplicate protection, immutable binding verification, and structured CLI errors.
- [x] Task 11B2: Production runner progress monitoring, controlled same-job resume, terminal validation, and final production manifest generation.
- [x] Task 11C1: Objective audio QA reporting from completed-job production manifests.
- [x] Task 11C2: Deterministic offline HTML listening checklist package with local review state and browser-only review JSON export.
- [x] Task 11D1: Unified production workflow operator entry point composing preflight, guarded submit/resume, manifest, objective QA, and deterministic listening checklist.
- [x] Task 11D2C: Punctuation-aware utterance splitter v3 with orphan-tail fix, offset-preserving deterministic boundaries, and Chapter 357 review-ready rebuild.
- [x] Task 11D2: First production acceptance run passed on Chapter 357 with approved Casting Plan #6, Job #2 completed, objective QA package generated, and human full-chapter listening PASS.

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
| 2026-07-05 | Task 11B1 Guarded Production Runner | Implementation commit `556023a94670730cafa995aa30d70a389f4a995a`; read-only runtime identity + exact Casting Plan endpoints; guarded isolated submit path; duplicate Chapter 629 detection returned `already_completed`; 759/759 offline tests pass |
| 2026-07-06 | Task 11B2 Production Runner Monitoring + Manifest | Implementation commit `50a2a397b1626ca8abaa1d1ffab5755fdebf5eac`; explicit watch/resume, terminal validation, final manifest schema `story-audio-production-manifest/v1`; disposable completed-job smoke PASS; 774/774 offline tests pass |
| 2026-07-06 | Task 11C1 Objective Audio QA | Implementation commit `9cc41720b7da755dd11302e053573dbb9272cd1a`; offline manifest-driven QA JSON, deterministic byte-identical reuse smoke on Chapter 629, and 814/814 offline tests pass |
| 2026-07-06 | Task 11C2 Deterministic Listening Checklist | Implementation commit `26b8f50acabed3f5f4a7a8c89e62128469221a1d`; offline HTML listening package, localStorage review state, browser-only review JSON export, Chapter 629 disposable smoke, and 835/835 offline tests pass |
| 2026-07-06 | Task 11D1 Unified Production Workflow | Implementation commit `8b0d4485301c8aa03ccc447d72ba0991e15c77a1`; unified workflow schema `story-audio-production-workflow/v1`, explicit submit/resume flags, completed-job downstream reuse, Chapter 629 disposable smoke, and 855/855 offline tests pass |
| 2026-07-06 | Task 11D2C Punctuation-Aware Utterance Split | Implementation commit `f96ac056a0d213ffc3fb834e7e03917900019b7d`; chunker `utterance-v3` prefers sentence punctuation, then clause punctuation, then whitespace; orphan-tail fix preserves offsets and Chapter 357 review boundary; 863/863 offline tests pass, 1 skipped |
| 2026-07-07 | Task 11D2 Production Acceptance Pass | main/origin `094a8787e29e2d709b302e8f524b3ed56cb383da`; Chapter 357 / Text Revision 714 / Casting Plan #6 / Job #2 completed 96/96; final M4A 13m50.170s; human full-chapter listening PASS; unified workflow validated end-to-end |
