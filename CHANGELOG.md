# Changelog

Ghi thay Ä‘á»•i hÃ nh vi ngÆ°á»i dÃ¹ng, schema, artifact contract vÃ  váº­n hÃ nh. KhÃ´ng dÃ¹ng file nÃ y thay cho `PROJECT_STATUS.md`.

## Unreleased

### Added

- **Task 18AX - Chapter 368 final Human QA closed**: recorded `FINAL_REASSEMBLED_QA_PASS` / `HUMAN_QA_PASS` for the reassembled Chapter `368` production artifact.
  - **QA closure workflow**: used the supported `PUT /api/chapters/368/human-approval` route, which stores the active-output snapshot in `chapters.human_approval_json`; UI boundary is `Chốt bản audio cuối`. No direct DB edit or new route was used.
  - **Persisted result**: status `approved`, `recorded_at = 2026-07-19T06:41:58.344250+00:00`, `artifact_id = 84`, `job_id = 22`, `matches_active_artifact = true`, and chapter `human_qa_status = accepted`.
  - **Final artifact**: artifact `84` at `D:\Youtube\Story Trans And Audio\data\output\1-quang-am-chi-ngoai\chapter_0368\job_22\render_0002\chapter.m4a`; SHA-256 `6d4f27143aa99112cfbee706a6bdbf45f0adfdb0ff29be42477093bb5b43b90f`; size `7902953` bytes; duration `485050 ms`.
  - **Repair QA**: Repair Block `#1` remains accepted for Segments `665`/`666`; the repaired region is clear, natural, and production-acceptable; transitions into and out of the repair region are acceptable; no further regeneration or replacement job is required.
  - **Safety**: Job `22` remains the sole Chapter `368` production job, JobChapter `22` remains completed, all `49` segments remain verified, artifact `81` remains preserved as stale historical audio, and Chapters `369`/`370` remain untouched.
  - **Next task**: Task `18AY` — Resolve Chapter `369` Quote-Boundary Text Blocker.
- **Task 18AV - Chapter 368 repair block accepted and same-job reassembly completed**: accepted live Repair Block `#1` for Segments `665`/`666` and reassembled Chapter `368` on the same Job `22` without creating a replacement job.
  - **Accept flow**: added `POST /api/audio-repair-blocks/{repair_block_id}/accept`, wired the UI Accept button, and kept the candidate audio preserved at `data\work\job_22\chapter_0368\repair_blocks\repair_block_665_666_candidate_0001.wav`.
  - **Reassembly**: accept rebuilt the chapter master/timeline and produced new artifacts `82` (`chapter_master_wav`), `83` (`segment_timeline_json`), and active artifact `84` (`chapter_m4a`) for the same Job `22` / JobChapter `22`.
  - **Safety**: no segment rows, attempt rows, text revisions, speaker drafts, casting plans, or replacement jobs were mutated; the original artifact `81` became stale and `experiment_b_transcript/` plus `runs/` remained untouched.
  - **Verification**: runtime `http://127.0.0.1:8772`, database `D:\Youtube\Story Trans And Audio\data\app.db`, backup `D:\Youtube\Story Trans And Audio\backups\task18av_pre_ch368_repair_accept_20260719_130557`, and SQLite quick check `ok`.
  - **Next task**: Task `18AW` — Final Human Audio QA of Reassembled Chapter `368` Artifact.
- **Task 18AT - Chapter 368 adjacent-segment repair-block candidate**: implemented `audio_repair_blocks`, added migration `0011_audio_repair_blocks.sql`, exposed supported repair-block APIs/UI, and created one live candidate for Segments `665`/`666` on Job `22` / JobChapter `22`.
  - **Code**: repair-block synthesis now reconstructs the authoritative span from Text Revision `736`, enforces adjacent verified segments, rejects stale/mismatched plan pins, reuses the same live job identity, and supports JobChapter-level casting-plan pin fallback when segment rows keep `casting_plan_id = NULL`.
  - **API/UI**: added `POST /api/jobs/{job_id}/repair-blocks`, `GET /api/job-chapters/{job_chapter_id}/repair-blocks`, `POST /api/audio-repair-blocks/{repair_block_id}/reject`, candidate audio, and preview-only original-range audio for A/B review.
  - **Tests**: focused offline tests now cover candidate creation, duplicate reuse, rejection, plan/job mismatch rejection, JobChapter pin fallback, preview generation, UI review labels, migration schema presence, and compatibility with existing segment-regeneration tests.
  - **Live validation**: runtime restarted to schema `11`, backup created at `D:\Youtube\Story Trans And Audio\backups\task_18at_pre_live_candidate_20260719_123323`, and one live candidate `#1` was created for Segments `665`/`666` with `candidate_duration_ms = 15350` and `status = candidate`.
  - **Safety**: no duplicate repair block was created, no accept/reject action was taken, and no job, text revision, speaker draft, casting plan, or voice mutation occurred.
  - **Next task**: Task `18AU` — Human A/B Review of Chapter 368 Segments 665-666 Repair-Block Candidate.
- **Task 18AS - Chapter 368 repeated Segment 666 articulation failure diagnosed**: rejected Candidate `39` and selected segmentation remediation instead of creating Attempt `40`.
  - **Baseline**: branch `main`, `HEAD == origin/main == b91ba13f72824ae082981a7572387bedb330da24`; canonical runtime `http://127.0.0.1:8772` pointed to `D:\Youtube\Story Trans And Audio\data` and `D:\Youtube\Story Trans And Audio\data\app.db`; SQLite `quick_check = ok`; only protected untracked `experiment_b_transcript/` and `runs/` were present.
  - **Human verdict**: Candidate `39` was rejected because `phải rung động.` was not pronounced clearly or with complete production-acceptable articulation.
  - **Rejection**: exactly one supported `POST /api/segments/666/reject-candidate` call set Attempt `39` to `rejected` at `2026-07-19T05:13:16.581812+00:00`. Attempt `37` remains `active`; Attempt `38` remains `rejected`; Segment `666` remains `verified`; Artifact `81` remains `active`.
  - **Context diagnosis**: Revision `736` local context shows Segment `665` ends `...làm cho tâm thần người khác`, Segment `666` is exactly `phải rung động.`, and together they form one sentence: `...làm cho tâm thần người khác phải rung động.`
  - **Attempt comparison**: Attempt `37` active original was `9670 ms` and severely unintelligible; Attempt `38` was `2150 ms` with provider-hallucinated prefix; Attempt `39` was `1430 ms`, technically cleaner, but still not clearly articulated. All three used the same text, narrator `custom:26`, custom voice revision `6`, and provider/model `vieneu` / `v3turbo`.
  - **Classification**: `SHORT_FRAGMENT_SEGMENTATION_DEFECT`; Segment `666` is a dependent trailing fragment split away from Segment `665`, not an independent utterance.
  - **Selected path**: no Attempt `40`; no blind retry; no manual WAV concatenation; no Text Revision `736` mutation. Next work must define a supported targeted segmentation-remediation workflow for the Segment `665`/`666` boundary.
  - **Safety**: active artifact `81` and final M4A SHA-256 `14b106e52a2f1951ffa69633679ee8f1cb6a990dfbc73056fd0c39e4b27045f5` remain unchanged. No replacement job, chapter reassembly, text revision, speaker draft, Casting Plan, voice mutation, or new candidate was created.
  - **Next step**: Resolve Chapter `368` Segment `665`/`666` Short-Fragment Segmentation Defect Without Blind TTS Retry.
  - **Migration**: none.

- **Task 18AQ - Chapter 368 replacement candidate ready**: rejected Candidate `38` and created one clean replacement candidate `39` for Segment `666` without reassembling the chapter.
  - **Baseline**: branch `main`, `HEAD == origin/main == 23e458caa7d6dce1c111924efcb990026629d881`; canonical runtime `http://127.0.0.1:8772` pointed to `D:\Youtube\Story Trans And Audio\data` and `D:\Youtube\Story Trans And Audio\data\app.db`; SQLite `quick_check = ok`; only protected untracked `experiment_b_transcript/` and `runs/` were present.
  - **Human verdict**: Candidate `38` was rejected because only `phải rung động.` is clear and the preceding speech is unintelligible. The failure was classified as `PROVIDER_HALLUCINATED_PREFIX`.
  - **Rejection**: exactly one supported `POST /api/segments/666/reject-candidate` call set Attempt `38` to `rejected` at `2026-07-19T04:08:54.615174+00:00`. Attempt `37` remains `active`; Segment `666` remains `verified`; Artifact `81` remains `active`.
  - **Backup**: pre-replacement SQLite online backup created at `D:\Youtube\Story Trans And Audio\backups\task18aq_pre_ch368_segment666_attempt3_20260719T040915Z.sqlite3`; size `4009984` bytes; SHA-256 `509c22950abd8e662549899f10716422146441392cc65b068c6ef625128f0310`; quick_check `ok`.
  - **Replacement**: exactly one supported `POST /api/segments/666/regenerate` call created Attempt `39`, attempt number `3`, status `candidate`, path `D:\Youtube\Story Trans And Audio\data\work\job_22\chapter_0368\segments\segment_666_attempt_3.wav`, SHA-256 `48a6b6ead0442eaf1db21b766ef8a81794994053195480453981ad51084ae59e`, duration `1430 ms`.
  - **Technical validation**: candidate `39` decodes cleanly as mono 48 kHz PCM, size `137324` bytes, peak about `-7.36 dBFS`, RMS about `-21.00 dBFS`, clipped samples `0`, leading silence `134 ms`, trailing silence `488 ms`, longest silence `488 ms`, and non-empty voiced audio. It is not identical to Candidate `38`.
  - **A/B safety**: `/api/segments/666/attempts` now exposes active Attempt `37`, rejected Attempt `38`, and candidate Attempt `39`; UI still provides separate Accept/Reject actions and no accept/reject action was clicked.
  - **Active artifact safety**: active artifact `81` and final M4A SHA-256 `14b106e52a2f1951ffa69633679ee8f1cb6a990dfbc73056fd0c39e4b27045f5` remain unchanged. No replacement job, chapter reassembly, text revision, speaker draft, Casting Plan, or voice mutation occurred.
  - **Next step**: Human A/B Review of the Replacement Chapter `368` Segment `666` Candidate.
  - **Migration**: none.

- **Task 18AO - Chapter 368 targeted regeneration candidate ready**: mapped the Human QA failure at `02:39-02:47` and created exactly one pending targeted regeneration candidate for Segment `666`.
  - **Baseline**: branch `main`, `HEAD == origin/main == 2f843319edade689067f585eef49393ebf82e640`; canonical runtime `http://127.0.0.1:8772` pointed to `D:\Youtube\Story Trans And Audio\data` and `D:\Youtube\Story Trans And Audio\data\app.db`; SQLite `quick_check = ok`; only protected untracked `experiment_b_transcript/` and `runs/` were present.
  - **QA marker**: Human QA verdict `TARGETED_REMEDIATION_REQUIRED`; marker `02:39.000-02:47.000`; issue severe unintelligible speech / đọc không ra tiếng; severity major.
  - **Mapping**: marker crosses Segment `666` (`02:35.860-02:45.530`) and the first `1470 ms` of Segment `667`; the minimal defective set is Segment `666` only. Affected utterance is sequence `15`, stable utterance ID `u0015-4257cca30835`, source offsets `2473-2488`, exact text `phải rung động.`, narrator `custom:26`, custom voice revision `6`.
  - **Diagnosis**: Segment `666` source WAV `000015.wav` is abnormal for a `15`-character utterance: duration `9670 ms`, peak about `-8.37 dBFS`, RMS about `-24.08 dBFS`, longest silence `936 ms`, and `7` silences >= `200 ms`. The corresponding final M4A region has the same abnormal profile, while the Segment `667` overlap was technically normal.
  - **Classification**: `SOURCE_SYNTHESIS_UNINTELLIGIBLE`, not assembly-only, not boundary-only, and not multi-segment.
  - **Backup**: pre-mutation SQLite online backup created at `D:\Youtube\Story Trans And Audio\backups\task18ao_pre_ch368_targeted_regen_20260718T185634Z.sqlite3`; size `4009984` bytes; SHA-256 `be77502b25aa300de16106ee53beefd1a98a902367403057f523c9fcd09e1887`; quick_check `ok`.
  - **Candidate**: exactly one `POST /api/segments/666/regenerate` call created Attempt `38`, attempt number `2`, status `candidate`, path `D:\Youtube\Story Trans And Audio\data\work\job_22\chapter_0368\segments\segment_666_attempt_2.wav`, SHA-256 `26721277a58ea5026f4e7b49e941840b1d3ee2b096ec9d04066adfbf3f4371d6`, duration `2150 ms`.
  - **Technical validation**: candidate decodes as mono 48 kHz PCM, size `206444` bytes, peak about `-7.29 dBFS`, RMS about `-20.45 dBFS`, clipped samples `0`, leading silence `47 ms`, trailing silence `356 ms`, longest silence `603 ms`, and non-empty voiced audio.
  - **A/B safety**: original active Attempt `37` remains active; candidate Attempt `38` is pending and unaccepted; UI/API exposes original and candidate with separate Accept/Reject actions; neither action was clicked.
  - **Active artifact safety**: active artifact `81` and final M4A SHA-256 `14b106e52a2f1951ffa69633679ee8f1cb6a990dfbc73056fd0c39e4b27045f5` remain unchanged. No replacement job, full-chapter render, direct DB edit, text/casting/speaker/voice mutation, or adjacent-segment regeneration occurred.
  - **Next step**: Human A/B Review of Chapter `368` Targeted Regeneration Candidate.
  - **Migration**: none.

- **Task 18AM - Chapter 368 narrator-only render completed**: explicitly started existing prepared Job `22` through `POST /api/jobs/22/start` and monitored the same job to completion without creating a replacement job.
  - **Baseline**: branch `main`, `HEAD == origin/main == 88105602babea5e5fb0eaa192c7b51518e9168e0`; canonical runtime `http://127.0.0.1:8772` pointed to `D:\Youtube\Story Trans And Audio\data` and `D:\Youtube\Story Trans And Audio\data\app.db`; SQLite `quick_check = ok`; only protected untracked `experiment_b_transcript/` and `runs/` were present.
  - **Prepared state**: Job `22` was `prepared`, JobChapter `22` was `pending`, and both were pinned to Chapter `368`, active Text Revision `736`, approved narrator-only Casting Plan `23` revision `1`, plan SHA-256 `493e1f39bd353657f6deee0a9ac1124ae3ad47160d5bf7b1b09657f1de1ee9c0`, narrator voice `custom:26`, and custom voice revision `6`.
  - **Backup**: pre-start SQLite online backup created at `D:\Youtube\Story Trans And Audio\backups\task18am_pre_ch368_start_20260718T174859Z.sqlite3`; size `3870720` bytes; SHA-256 `dfe5e1657228a01c2c0ef3e644a5a5314cd4699b6c18f49a302415d7078b811b`; quick_check `ok`.
  - **Start/render**: exactly one supported start mutation was issued. Lifecycle observed on the same job was `scheduled -> synthesizing -> assembling -> completed`; Job `22` finished at `2026-07-18T18:00:53.109153+00:00`, and JobChapter `22` finished at `2026-07-18T18:00:53.085149+00:00`.
  - **Segments**: `49` segments verified, sequence range `1-49`, failed/pending/running segments `0`, repair blocks `0`, `segment_attempts` rows `0`, narrator `49`, `custom:26 -> 49`, custom voice revision `6 -> 49`, provider/model `vieneu` / `v3turbo`.
  - **Artifacts**: active artifact `81` `chapter_m4a` at `D:\Youtube\Story Trans And Audio\data\output\1-quang-am-chi-ngoai\chapter_0368\job_22\render_0001\chapter.m4a`; SHA-256 `14b106e52a2f1951ffa69633679ee8f1cb6a990dfbc73056fd0c39e4b27045f5`; size `8007414` bytes; authoritative duration `493840 ms`. Supporting artifacts `79` `chapter_master_wav` and `80` `segment_timeline_json` were verified.
  - **Technical QA**: independent decoded PCM duration `493845 ms`, AAC mono 48 kHz, mean volume about `-19.5 dB`, peak about `-0.97 dBFS`, clipped samples `0`, longest detected silence about `0.985 s` at `06:21.47`, and no decode corruption.
  - **Human QA markers**: prepared listening markers include seq `1`/segment `652`/`00:00.00` start, seq `7`/segment `658`/`01:02.90` longest, seq `13`/segment `664`/`02:05.88` duration outlier, seq `14`/segment `665`/`02:21.39` punctuation-heavy terminology, seq `15`/segment `666`/`02:35.86` quietest, seq `27`/segment `678`/`04:31.58` loudest, seq `32`/segment `683`/`05:17.05` shortest, seq `38`/segment `689`/`06:07.71` scene transition and longest-silence window, and seq `49`/segment `700`/`08:04.40` ending.
  - **Safety**: Text Revision `736`, Speaker Draft `14`, Casting Plan `23`, custom voice `26`, and voice revision `6` were not modified. Chapters `364`, `365`, `366`, and `367` remained unchanged at active artifacts `69`, `72`, `78`, and `75`; Chapters `369` and `370` remained untouched; no retry, no targeted remediation, no replacement job, and no direct DB edit occurred.
  - **Next step**: Chapter `368` Human Audio QA and Targeted Remediation Review.
  - **Migration**: none.

- **Task 18AL - Chapter 368 narrator-only production job prepared**: created exactly one durable prepared production job for Chapter `368` through `POST /api/jobs/prepare`, without starting TTS or worker execution.
  - **Baseline**: branch `main`, `HEAD == origin/main == 84409132cfb41b86bb0af454000e48671062ad12`; canonical runtime `http://127.0.0.1:8772` pointed to `D:\Youtube\Story Trans And Audio\data` and `D:\Youtube\Story Trans And Audio\data\app.db`; SQLite `quick_check = ok`; only protected untracked `experiment_b_transcript/` and `runs/` were present.
  - **Readiness**: Chapter `368` stayed on active approved Text Revision `736`; deterministic rebuild produced `49` utterances, quote spans `0`, speaker targets `0`, empty/punctuation-only utterances `0`, and duplicate/gap counts `0`. Speaker Draft `14` remained zero-target with review rows `0`.
  - **Approved plan**: Casting Plan `23` revision `1` remained approved with `approved_at = 2026-07-18T17:25:23.067196+00:00`, source Draft `14`, plan SHA-256 `493e1f39bd353657f6deee0a9ac1124ae3ad47160d5bf7b1b09657f1de1ee9c0`, assignments `49`, narrator `49`, character `0`, unknown `0`, unresolved `0`, and `custom:26 -> 49`.
  - **Voice/filesystem readiness**: custom voice `26` remained active and resolved to usable revision `6`, SHA-256 `b641e84e11583bfcbeb76f9a5615c605656e8151679d1286e8f4743c92218ace`; required asset exists; no stale Chapter `368` work/output/manifest path was found; D: free space was `6232121344` bytes.
  - **Backup**: pre-mutation SQLite online backup created at `D:\Youtube\Story Trans And Audio\backups\task18al_pre_ch368_prepare_20260718T173847Z.sqlite3`; size `3809280` bytes; SHA-256 `8f48663faa68b744df0cd642879028989edf28ae9cab7e2ad85d9a3756fcac5d`; quick_check `ok`.
  - **Prepare result**: exactly one `POST /api/jobs/prepare` call with `book_id = 1`, Chapter `368-368`, `voice_name = custom:26`, `output_format = m4a`, `repair_mode = off`, `skip_completed = true`, and `casting_plan_id = 23` created Job `22`, `status = prepared`, `created_at = 2026-07-18T17:39:08.259402+00:00`, with `started_at = null` and `finished_at = null`.
  - **Pins**: JobChapter `22` was created for Chapter `368`, `status = pending`, `text_revision_id = 736`, `casting_plan_id = 23`, `casting_plan_sha256 = 493e1f39bd353657f6deee0a9ac1124ae3ad47160d5bf7b1b09657f1de1ee9c0`, `artifact_id = null`, `started_at = null`, and `finished_at = null`.
  - **Snapshot**: immutable job snapshot contains Text Revision `736`, Casting Plan `23`, narrator voice `custom:26`, utterances `49`, narrator `49`, character `0`, unknown `0`, unresolved `0`, `custom:26 -> 49`, custom voice revision `6 -> 49`, and no resolved character voices.
  - **Worker/UI safety**: after multiple polling intervals Job `22` remained `prepared`; segments, attempts, repair blocks, artifacts, output/work paths, active audio, provider calls, Gemini calls, TTS preview, TTS synthesis, and worker execution all remained `0`. UI queue showed Job `#22` as `Đã chuẩn bị` with next action `Bắt đầu render`; that action was not clicked. A runtime restart was not forced because stopping the live runtime process was blocked by shell policy before execution, and no unsafe workaround was used.
  - **Chapter safety**: Chapters `364`, `365`, `366`, and `367` remained unchanged at active artifacts `69`, `72`, `78`, and `75`; Chapters `369` and `370` observations remained untouched; `experiment_b_transcript/` and `runs/` remained untouched.
  - **Next step**: explicitly start and monitor existing prepared Job `22` for Chapter `368`; do not prepare a second job.
  - **Migration**: none.

- **Task 18AK - Chapter 368 narrator-only Final Voice Map approved**: inspected and approved existing Casting Plan `23` revision `1` for Chapter `368` through the dedicated existing-plan approval workflow.
  - **Baseline**: branch `main`, `HEAD == origin/main == 92f8bf248bc4acdbd950b1b486d7c4820a2b215b`; canonical runtime `http://127.0.0.1:8772` pointed to `D:\Youtube\Story Trans And Audio\data` and `D:\Youtube\Story Trans And Audio\data\app.db`; SQLite `quick_check = ok`. Runtime was restarted through `run_app.ps1` because it was not listening.
  - **Pre-approval plan**: Plan `23` revision `1` was the only Chapter `368` Casting Plan, `status = draft`, `approved_at = null`, source speaker draft `14`, Text Revision `736`, created_at `2026-07-16T13:25:39.637907+00:00`, and plan SHA-256 `493e1f39bd353657f6deee0a9ac1124ae3ad47160d5bf7b1b09657f1de1ee9c0`.
  - **Approval boundary**: UI approval calls `POST /api/casting/${casting.id}/approve`; job preparation remains a separate action using `POST /api/jobs/prepare`. No approval-to-job or approval-to-render coupling was found.
  - **Plan content**: total assignments `49`, narrator `49`, character `0`, unknown `0`, unresolved `0`, effective voice counts `custom:26 -> 49`, no duplicate stable utterance ID, no sequence gap/duplicate, no empty or punctuation-only utterance, and no offset/hash mismatch against Revision `736`.
  - **Voice readiness**: custom voice `26` remained active and resolved to usable canonical revision `6`, audio SHA-256 `b641e84e11583bfcbeb76f9a5615c605656e8151679d1286e8f4743c92218ace`.
  - **Approval result**: exactly one `POST /api/casting/23/approve` call approved Plan `23` revision `1` in place. `approved_at = 2026-07-18T17:25:23.067196+00:00`; `archived_at = null`; content path and plan SHA-256 remained unchanged.
  - **Zero-target provenance**: Draft `14` remains non-stale with `target_count = 0`, `valid_count = 0`, `invalid_count = 0`, and review rows `0`; plan review metadata keeps `approved_count = 0`, `reviewed_utterance_ids = []`, `remaining_unreviewed_count = 0`, and `review_completed = true`. No fake review rows or dialogue rows were created.
  - **Render safety**: Chapter `368` still has audio status `not_created`, active audio `none`, jobs for chapter `0`, JobChapters `0`, segments `0`, attempts `0`, repair blocks `0`, artifacts `0`, output dirs `0`, and work dirs `0`. No Gemini/provider request, TTS preview, TTS synthesis, job preparation, job start, render, manifest, artifact, or audio output occurred.
  - **Chapter safety**: Chapters `364`, `365`, `366`, and `367` remained unchanged at active artifacts `69`, `72`, `78`, and `75`; Chapters `369` and `370` observations remained untouched; `experiment_b_transcript/` and `runs/` remained untouched.
  - **Next step**: prepare the real Chapter `368` narrator-only production job without starting TTS.
  - **Migration**: none.

- **Task 18AJ - Chapter 368 narrator-only Final Voice Map workflow implemented**: added and validated the zero-target staged-review path, then created exactly one live unapproved narrator-only Final Voice Map for Chapter `368`.
  - **Implementation**: commit `0fbcc984391c6dcc4b5f4c2101bcac026088818d` (`fix: support narrator-only casting plans`) allows `POST /api/chapters/{chapter_id}/speaker-review/casting-plan-draft` to accept `decisions = []` only for a non-stale, review-complete, zero-target Speaker Assignment Draft. The legacy approval route still requires at least one reviewed decision.
  - **Safety checks**: the backend verifies stored zero counts, empty review rows, empty assignments/invalid items, an active Text Revision that still rebuilds zero speaker targets, and no unrelated existing Casting Plan before creating a narrator-only draft. Repeated same-identity requests reuse the existing plan.
  - **UI**: Speaker Review now treats zero-target drafts as complete without fabricated decisions, enables the narrator-only draft action, and keeps approval/render separated.
  - **Tests**: focused tests cover narrator-only draft creation without provider/approval, idempotent duplicate prevention, nonzero empty-decision rejection, API acceptance of empty decisions for zero-target drafts, and UI readiness. `node --check ui/app.js` and `git diff --check` passed.
  - **Live baseline**: runtime `http://127.0.0.1:8772` pointed to canonical data root `D:\Youtube\Story Trans And Audio\data` and DB `D:\Youtube\Story Trans And Audio\data\app.db`; Chapter `368` remained on Text Revision `736`; Draft `14` was non-stale with `target_count = 0`, `valid_count = 0`, `invalid_count = 0`, and review rows `0`.
  - **Backup**: pre-mutation SQLite backup created at `D:\Youtube\Story Trans And Audio\backups\task18aj_pre_ch368_zero_target_plan\app_20260716T132510Z.db`; size `3809280` bytes; SHA-256 `c34df076a0aa353d174e9b3a111c508328b618ddc466063b018868069d61d947`; quick_check `ok`.
  - **Live result**: exactly one supported `POST /api/chapters/368/speaker-review/casting-plan-draft` call created Casting Plan `23` revision `1`, `status = draft`, `approved = false`, `approved_at = null`, source speaker draft `14`, Text Revision `736`, assignment count `49`, narrator `49`, character `0`, unknown `0`, unresolved `0`, and effective voice counts `custom:26 -> 49`.
  - **Render safety**: no approval, job preparation, job start, worker render, TTS preview, TTS synthesis, Gemini/provider call, segment, attempt, artifact, active audio, or output audio was created. Chapter `368` remains `audio_status = not_created`.
  - **Chapter safety**: Chapters `364`, `365`, `366`, and `367` remained unchanged at active artifacts `69`, `72`, `78`, and `75`; Chapters `369` and `370` remained untouched; `experiment_b_transcript/` and `runs/` remained untouched.
  - **Next step**: inspect and approve existing Chapter `368` narrator-only Final Voice Map `23`; do not prepare or start a job yet.
  - **Migration**: none.

- **Task 18AI - Chapter 368 zero-target speaker draft created**: created exactly one canonical provider-free Speaker Assignment Draft for Chapter `368` and stopped at the zero-target Final Voice Map workflow blocker.
  - **Baseline**: branch `main`, `HEAD == origin/main == e31b12d58943b56ca0c42bf32d1eb51ce6a96905`; canonical runtime `http://127.0.0.1:8772` pointed to `D:\Youtube\Story Trans And Audio\data` and `D:\Youtube\Story Trans And Audio\data\app.db`; SQLite `quick_check = ok`.
  - **Text state**: Chapter `368` stayed on active approved Text Revision `736`, parent/source Revision `735`, `kind = reflowed`, processor `lossless-reflow-v1`, content SHA-256 `c1e5c935f2df6e411086f87a6ff6c3b03795fe2005382a13cdde1c3376421564`, lexical SHA-256 `f5942c8d31af105fc39c7f0d03c9839d3f534559ee3cd6de56275fb90d230514`, char count `7831`.
  - **Zero-target validation**: deterministic utterances `49`, sequence range `1-49`, all roles `narrator`, quote spans `0`, speaker targets `0`, empty utterances `0`, punctuation-only utterances `0`, malformed quote targets `0`, gaps/overlaps `0`, duplicate sequence/stable IDs `0`, character counts min `15`, max `243`, median `175`.
  - **Provider boundary**: `targets = []` caused the provider/cache batch loop to be skipped. No Gemini request, provider request, API key lookup, provider cache hit/miss, or provider cache write occurred.
  - **Draft result**: exactly one `POST /api/chapters/368/speaker-assignment/draft` call created Draft `14`, `status = generated`, `stale = false`, `text_revision_id = 736`, `target_count = 0`, `valid_count = 0`, `invalid_count = 0`, `remaining_unreviewed_count = 0`, review rows `0`, assignments `[]`, invalid items `[]`, cache hit/miss `0/0`, created_at `2026-07-16T12:38:10.049602+00:00`.
  - **Narrator-only readiness**: expected future plan shape is total assignments `49`, narrator `49`, character `0`, unknown `0`, unresolved `0`, `custom:26 -> 49`, and `custom:25 -> 0`.
  - **Workflow blocker**: UI displays Draft `14` and `Draft này không có mục nào cần rà soát`, but `Tạo Final Voice Map draft` is disabled because the UI requires at least one reviewed decision; backend zero-target plan creation is also blocked because `create_casting_plan_draft_from_speaker_review(...)` rejects `decisions = []`.
  - **Safety**: no Text Revision, Casting Plan, job, JobChapter, segment, attempt, repair block, artifact, active audio, TTS preview, TTS synthesis, or render was created. Chapters `364-367`, `369`, and `370` remained unchanged; `experiment_b_transcript/` and `runs/` remained untouched.
  - **Next step**: implement and validate the zero-target narrator-only Final Voice Map workflow for Chapter `368` Draft `14`.
  - **Migration**: none.

- **Task 18AH - Next sequential production chapter selected**: completed an inspection-only pass beginning at Chapter `368` and selected Chapter `368` as the first eligible new production chapter.
  - **Baseline**: branch `main`, `HEAD == origin/main == cc22c09ba085d2bf7fd353931870648ad4392e14`; canonical runtime `http://127.0.0.1:8772` pointed to `D:\Youtube\Story Trans And Audio\data` and `D:\Youtube\Story Trans And Audio\data\app.db`; SQLite `quick_check = ok`.
  - **Completed chapter safety**: Chapters `364`, `365`, `366`, and `367` remained completed with active artifacts `69`, `72`, `78`, and `75`; none were mutated.
  - **Selected chapter**: Chapter `368` / ID `368` / `Chương 368`, active Text Revision `736`, parent/source Revision `735`, `kind = reflowed`, `status = approved`, processor `lossless-reflow-v1`, content SHA-256 `c1e5c935f2df6e411086f87a6ff6c3b03795fe2005382a13cdde1c3376421564`, lexical SHA-256 `f5942c8d31af105fc39c7f0d03c9839d3f534559ee3cd6de56275fb90d230514`, char count `7831`.
  - **Chapter 368 readiness**: content blob exists, is non-empty, and hash-matches; deterministic utterances `49`; quote spans `0`; speaker targets `0`; sequence range `1-49`; empty utterances `0`; punctuation-only utterances `0`; malformed quote targets `0`; offset gaps/overlaps `0`; duplicate sequences and duplicate stable IDs `0`.
  - **Existing state**: Chapter `368` has speaker drafts `0`, Casting Plans `0`, jobs `0`, JobChapters `0`, segments `0`, artifacts `0`, active audio `none`, and audio status `not_created`.
  - **Later chapter observations**: Chapter `369` was classified `BLOCKED_TEXT_REMEDIATION` due to a split quote around `"Pháp lực màu đỏ! Nhanh phá huỷ trận pháp!"`; Chapter `370` was classified `BLOCKED_TEXT_REMEDIATION` due to multiple split quote fragments including a punctuation-only quote segment. Chapters `371` and `372` also inspected as eligible, but sequential selection chooses Chapter `368` first.
  - **Safety**: no Text Revision, speaker draft, Casting Plan, job, JobChapter, segment, attempt, repair block, artifact, active audio, Gemini/provider request, TTS preview, or synthesis was created.
  - **Next step**: Generate one Speaker Assignment Draft for Chapter `368`.
  - **Migration**: none.

- **Task 18AG - Chapter 366 Human Audio QA closeout**: recorded `HUMAN_QA_PASS` and closed the Chapter `366` production cycle after sequential review of the complete final artifact.
  - **Accepted production identity**: active Text Revision `3984`, approved Casting Plan `22` revision `1`, source speaker draft `13`, completed Job `21`, completed JobChapter `21`, and active artifact `78`.
  - **Accepted artifact**: `D:\Youtube\Story Trans And Audio\data\output\1-quang-am-chi-ngoai\chapter_0366\job_21\render_0001\chapter.m4a`; SHA-256 `40014be7dd74a147cdd3c5c8029b2807a1cb0851b02cbab563e7ea823bcb4793`; file size `7082686` bytes; container duration `431020 ms`; independent decoded PCM duration `431040 ms`.
  - **Segment state**: all `51` segments were verified in sequence with `0` failed, `0` pending, `0` retries, and `0` repair blocks. No post-completion regeneration and no replacement job occurred.
  - **Human QA coverage**: chapter start and ending are complete; no repeated, missing, or reordered sentence was detected; no punctuation-only utterance exists; and the corrected quotation is audible as one complete utterance rather than a split target.
  - **Speaker QA markers**: all ten target windows were checked: `u0004-c739867fa093` seq `4` (`00:08.73-00:20.28`), `u0008` seq `8`, `u0009` seq `9`, `u0010` seq `10`, `u0011` seq `11`, `u0012` seq `12`, `u0015` seq `15`, `u0034` seq `34`, `u0043` seq `43`, and `u0046` seq `46`.
  - **Voice acceptance**: narrator rows use `custom:26`; named Hứa Thanh and Lão tổ Kim Cương Tông targets use `custom:25`; anonymous `u0004-c739867fa093` remains anonymous/unknown and uses the narrator fallback `custom:26`.
  - **Technical acceptance**: integrated loudness about `-20.3 LUFS`, LRA `4.8 LU`, true peak about `-0.1 dBFS`, decoded RMS about `-19.85 dBFS`, clipped samples `0`, longest silence about `1.08 s`, leading silence about `140 ms`, and trailing silence about `280 ms`.
  - **Remediation result**: no clipping, corruption, excessive silence, disruptive transition, loudness discontinuity, or assembly failure justified targeted remediation.
  - **Safety**: Chapters `364`, `365`, and `367` remained unchanged; `experiment_b_transcript/` and `runs/` remained untouched.
  - **Next step**: Inspect the next sequential production chapter beginning at Chapter `368`.
  - **Migration**: none.

- **Task 18AE - Chapter 366 production render completed**: started the existing prepared Job `21` exactly once, completed the same job without replacement, and left Human Audio QA as the next boundary.
  - **Start boundary**: `POST /api/jobs/21/start` transitioned Job `21` from `prepared` to the executable lifecycle with no duplicate job creation. Job `21` started at `2026-07-16T11:39:58.986729+00:00`; JobChapter `21` started at `2026-07-16T11:39:59.025735+00:00`.
  - **Lifecycle**: the canonical transitions observed were `scheduled -> synthesizing -> assembling -> completed`. Job `21` finished at `2026-07-16T11:53:24.514957+00:00`; JobChapter `21` finished at `2026-07-16T11:53:24.498679+00:00`.
  - **Segmentation**: `51` verified segments, `0` failed, `0` pending, `0` running, attempt total `51`, max attempt `1`, duration min `1110 ms`, max `16550 ms`, median `8470 ms`, and sum `431020 ms`.
  - **Voice routing**: narrator rows resolved to `custom:26`; all Hứa Thanh and Lão tổ Kim Cương Tông rows resolved to `custom:25`; the anonymous `u0004-c739867fa093` stayed `unknown` with `custom:26` fallback.
  - **Provider/synthesis**: `vieneu` / `v3turbo`, sample rate `48000`, mono output, no failed segment, no manual retry, no repair block, and no duplicate worker execution.
  - **Artifacts**: artifact `76` `chapter_master_wav`, artifact `77` `segment_timeline_json`, and active artifact `78` `chapter_m4a` are all bound to Job `21` / JobChapter `21`.
  - **Final audio**: `D:\Youtube\Story Trans And Audio\data\output\1-quang-am-chi-ngoai\chapter_0366\job_21\render_0001\chapter.m4a`; SHA-256 `40014be7dd74a147cdd3c5c8029b2807a1cb0851b02cbab563e7ea823bcb4793`; size `7082686` bytes; FFprobe duration `431.020000 s`; AAC mono 48 kHz; volumedetect max volume about `-0.2 dB`, mean volume about `-19.9 dB`.
  - **Human QA markers**: chapter start/end; all ten reviewed speaker targets; the anonymous `u0004-c739867fa093` row; the narrator/custom:26 to named/custom:25 boundaries; and the long-duration segments around the middle and tail of the chapter were noted for listening review.
  - **Safety**: Chapters `364`, `365`, and `367` remained unchanged; `experiment_b_transcript/` and `runs/` remained untouched.
  - **Next step**: Chapter `366` Human Audio QA and Targeted Remediation Review.

- **Task 18AD - Chapter 366 production job prepared**: created exactly one durable prepared production job for Chapter `366` using the canonical prepare-only workflow and stopped before render execution.
  - **Readiness**: Chapter `366` remained on active approved Text Revision `3984`; approved Casting Plan `22` revision `1` remained pinned to Revision `3984`; source speaker draft `13` stayed review-complete; and the intentional anonymous `cái bóng` assignment remained `unknown` with `custom:26` fallback.
  - **Voice assets**: custom voice `25` exists with preferred synthesis revision `1`; custom voice `26` exists with usable revision `6`; no provider call was made during readiness checks.
  - **Backup**: pre-mutation SQLite backup created at `D:\Youtube\Story Trans And Audio\backups\task18ad_pre_ch366_prepare_20260716_182736.sqlite3`; size `3608576` bytes; SHA-256 `9adafc8faa01f9ae152b8566b20405a2d0c584e0529c6f6092920c5a78a2224d`; quick_check `ok`.
  - **Prepare request**: exactly one successful `POST /api/jobs/prepare` call created Job `21` / JobChapter `21` with Book `1`, Chapter `366`, `from_chapter = 366`, `to_chapter = 366`, `voice_name = custom:26`, `repair_mode = off`, `output_format = m4a`, `skip_completed = true`, and `casting_plan_id = 22`.
  - **Prepared state**: Job `21` is `prepared`, `created_at = 2026-07-16T11:28:07.302447+00:00`, `started_at = null`, `finished_at = null`; JobChapter `21` is `pending`, pinned to Text Revision `3984` and Casting Plan `22`.
  - **Snapshot**: casting snapshot SHA-256 remains `f693e76ce79f9fc76a926e4bf7e9fd69f97e55bdb163aea1fb8ea689bbdda6c8`; assignments remain total `51`, narrator `41`, character `9`, unknown `1`, unresolved `0`, with `custom:26 -> 42` and `custom:25 -> 9`.
  - **Worker isolation**: Job `21` stayed `prepared` across a polling interval; no worker execution, automatic transition, Gemini call, TTS preview, TTS synthesis, segment, attempt, repair block, artifact, manifest, or audio output occurred.
  - **UI**: Production Flow now exposes the existing prepared job and the explicit next action `Bắt đầu render`; that action was not clicked.
  - **Safety**: Chapters `364`, `365`, and `367` remained unchanged; `experiment_b_transcript/` and `runs/` remained untouched.
  - **Next step**: Explicitly start and monitor the existing Chapter `366` prepared Job `21`.
  - **Migration**: none.

- **Task 18AC - Chapter 366 Final Voice Map approved**: approved the existing Chapter `366` Final Voice Map / Casting Plan `22` revision `1` through the dedicated existing-plan approval workflow.
  - **Pre-approval state**: Chapter `366` stayed on active approved Text Revision `3984`; Speaker Assignment Draft `13` remained non-stale and review-complete; exactly one Chapter `366` Casting Plan existed, Plan `22` revision `1`, `status = draft`, `approved_at = null`.
  - **Approval boundary**: UI approval uses `POST /api/casting/{casting_plan_id}/approve`; job preparation/start remain separate through `POST /api/jobs/prepare` and `POST /api/jobs/{job_id}/start`. Backend approval marks the existing draft approved and validates it without creating jobs, job_chapters, segments, attempts, artifacts, manifests, or audio.
  - **Exact approval result**: exactly one `POST /api/casting/22/approve` call approved Plan `22` revision `1` in place. No successor revision and no duplicate plan were created. `approved_at = 2026-07-16T11:13:12.223006+00:00`.
  - **Provenance preserved**: approved plan remains pinned to Text Revision `3984`, source speaker draft `13`, review-complete provenance, and plan SHA-256 `f693e76ce79f9fc76a926e4bf7e9fd69f97e55bdb163aea1fb8ea689bbdda6c8`.
  - **Decisions preserved**: the intentional anonymous `cái bóng` assignment `u0004-c739867fa093` remains `unknown`, resolves through narrator fallback to `custom:26`, and was not reassigned to `Lão tổ Kim Cương Tông`.
  - **Counts unchanged**: total assignments `51`, narrator `41`, character `9`, unknown `1`, unresolved `0`, effective voices `custom:26 -> 42` and `custom:25 -> 9`.
  - **Safety**: Chapter `366` still has jobs `0`, job chapters `0`, segments `0`, segment attempts `0`, repair blocks `0`, artifacts `0`, and active audio `none`; no provider, TTS preview, TTS synthesis, worker wake, manifest, or audio output occurred.
  - **UI next step**: Production Flow now exposes the separate prepare-only action `Chuẩn bị job audio`; that action was not clicked.
  - **Next step**: Prepare the real Chapter `366` production job without starting TTS.
  - **Migration**: none.

- **Task 18AB - Chapter 366 speaker review completed and Final Voice Map draft created**: reviewed all ten rows from Speaker Assignment Draft `13` and created one unapproved Final Voice Map / Casting Plan draft for operator approval.
  - **Speaker draft**: Draft `13` remained non-stale on Text Revision `3984`, with `target_count = 10`, `valid_count = 10`, `invalid_count = 0`, and `remaining_unreviewed_count = 10` before submission; after staged review, `remaining_unreviewed_count = 0` and the draft is linked to review-complete plan provenance.
  - **Merged quote decision**: `u0004-c739867fa093` / seq `4` / `"Ăn...Hải Thi tộc...sắp đột phá...đột phá ngay."` remains `unknown` because the speaker is only identified as `cái bóng` and is not clearly resolved to a named character.
  - **Accepted rows**: `u0008`, `u0009`, `u0010`, `u0011`, `u0012`, and `u0043` were confirmed as `Lão tổ Kim Cương Tông` (`43`, `custom:25`); `u0015`, `u0034`, and `u0046` were confirmed as `Hứa Thanh` (`42`, `custom:25`).
  - **Casting Plan draft**: exactly one unapproved Casting Plan draft was created via the staged workflow, not the legacy approval route. Plan `22` revision `1` is `draft`, `approved_at = null`, `source_speaker_draft_id = 13`, `text_revision_id = 3984`, `assignment_count = 51`, narrator count `41`, character count `9`, unknown count `1`, unresolved count `0`, and effective voice counts `custom:26 -> 42` / `custom:25 -> 9`.
  - **Provenance**: `review_completed = true`, `decision_fingerprint = c5e6839780103b98bb6036847b058680665aab44549e53b58946e1ca34edf0c9`, and the operator note records why the merged quote stayed anonymous.
  - **Safety**: Chapter `366` still has zero jobs, job chapters, segments, segment attempts, repair blocks, artifacts, and active audio. Chapters `364`, `365`, and `367` remained unchanged.
  - **Next step**: Inspect and approve the existing Chapter `366` Final Voice Map.

- **Task 18AA - Chapter 366 quote-boundary text blocker resolved**: applied one supported targeted text correction to Chapter `366` and generated exactly one speaker-assignment draft for operator review.
  - **Original revision**: active approved Text Revision `732` (`reflowed`, parent/source `731`, processor `lossless-reflow-v1`) had the quote `"Ăn...Hải Thi tộc...sắp đột phá... đột phá ngay."` reconstructed as two speaker targets: `u0004-a47e93d44da7` / seq `4` and `u0005-3a156dbf3197` / seq `5`.
  - **Source comparison**: raw revision `731` already contained the same spacing boundary, so the correction was limited to punctuation-adjacent spacing and did not remove any lexical token.
  - **Backup**: pre-mutation backup copy validated at `D:\Youtube\Story Trans And Audio\backups\task18aa_pre_ch366_correction_20260716_172843.sqlite3\files\app.db`; size `3608576` bytes; SHA-256 `8c2ff467425cf04c3080b343df7b7a023ded0f32e695acc280f648ef7712c278`; SQLite `quick_check = ok`.
  - **Correction**: exactly one `POST /api/chapters/366/text-revisions/targeted-correction` call created Text Revision `3984` (`repaired`, parent `732`, processor `targeted-correction-v1`, status `approved`) by changing `"Ăn...Hải Thi tộc...sắp đột phá... đột phá ngay."` to `"Ăn...Hải Thi tộc...sắp đột phá...đột phá ngay."`
  - **Minimal diff**: content SHA-256 is `4febd781f26a50c1a602ad5d14c092f41f472ecddc222d38ad66dfe0bd7ab1e8`; lexical SHA-256 remains `465273d394e81fc6c72ade75d463c552717db31bff076c4b3e07b70376eae3a6`; character count changed `6896 -> 6895`.
  - **Boundary validation**: quote-span count stayed `8`, utterance count changed `52 -> 51`, target count changed `11 -> 10`, and merged quote `u0004-c739867fa093` / seq `4` / offsets `364-412` is now one complete target.
  - **Draft result**: exactly one `POST /api/chapters/366/speaker-assignment/draft` call created Draft `13` on revision `3984` using `gemini-2.5-flash` and `speaker-assignment-v2`; `target_count = 10`, `valid_count = 10`, `invalid_count = 0`, `remaining_unreviewed_count = 10`, `cache_hit_count = 0`, `cache_miss_count = 1`.
  - **Safety**: Chapter `366` still has Casting Plans `0`, jobs `0`, JobChapters `0`, segments `0`, attempts `0`, repair blocks `0`, artifacts `0`, and active audio `none`; Chapters `364`, `365`, and `367` remained unchanged.
  - **Next step**: Review Chapter `366` Speaker Assignments and Create an Unapproved Final Voice Map.
  - **Migration**: none.

- **Task 18Z - Chapter 367 human QA closeout**: recorded `HUMAN_QA_PASS` and closed the Chapter `367` routine production cycle after listening through the complete final artifact.
  - **QA verdict**: the final audio was reviewed sequentially; chapter start and end are complete; narrator `custom:26` remained stable; all four character utterances use `custom:25`; and the recovered Segment `573` / sequence `20` / text `"Quá ít."` is now audible and complete after same-job recovery.
  - **Artifact**: `D:\Youtube\Story Trans And Audio\data\output\1-quang-am-chi-ngoai\chapter_0367\job_20\render_0001\chapter.m4a`; SHA-256 `376afa0250cc14ce368e36ff3f9842b8c33139d3ab0250b55f3e6ce92938d808`; file size `6765624` bytes; authoritative/container duration `418180 ms`; independent decoded PCM duration `418197 ms`.
  - **Technical validation**: peak approximately `-1.42 dBFS`, RMS approximately `-20.37 dBFS`, clipped samples `0`, and longest detected silence approximately `1.03 s`. No clipping, corruption, repeated line, missing line, or disruptive voice/loudness transition remained.
  - **Production closeout**: Job `20` and JobChapter `20` are completed, artifact `75` is active, all `47` segments are verified, no replacement job was created, no segment was regenerated after completion, and no further remediation is required.
  - **QA markers**: `573` / seq `20` / `Hứa Thanh`; `575` / seq `22` / `Hứa Thanh`; `577` / seq `24` / `Lão tổ Kim Cương Tông`; `581` / seq `28` / `Hứa Thanh`.
  - **Next step**: Resolve Deferred Chapter `366` Quote-Boundary Text Blocker.

- **Task 18X - Chapter 367 same-job segment recovery completed**: retried the failed Chapter `367` Segment `573` on the same Job `20`, preserved the verified prefix, and completed the chapter without creating a replacement job.
  - **Recovery backup**: pre-recovery SQLite backup created at `D:\Youtube\Story Trans And Audio\backups\task18x_pre_ch367_segment573_recovery_20260716_163153.sqlite3`; size `3604480` bytes, SHA-256 `ad6015c481a3fe08d0da0cc45a508732b86f587fdf570e7705d6c453aa3d48ac`, quick_check `ok`.
  - **Root cause**: Segment `573` / sequence `20` / text `"Quá ít."` failed three times on the first render with `Excessive silence in synthesized audio: 83.0% silent (16.1s of 19.4s total), longest continuous silence: 10.1s`. Nearby short `custom:25` segments in Chapters `364` and `365` were normal, so this was classified as `TRUE_PROVIDER_SILENCE`, not a short-utterance policy false positive.
  - **Supported workflow**: `POST /api/segments/573/retry` was used once. It reset only the failed segment, kept segments `1-19` intact, queued the same Job `20`, and woke the worker. No replacement job, no direct DB edit, and no voice/text/casting mutation were used.
  - **Recovery result**: Segment `573` was verified successfully with `attempt_count = 1`, `wav_path = D:\Youtube\Story Trans And Audio\data\work\job_20\chapter_0367\segments\000020.wav`, `duration_ms = 1350`, and `audio_sha256 = 1441e15ebc9a944d46255cc5f4e10fb1f6f4d84f1fb88968eaf3eb4543552d80`.
  - **Final production state**: Job `20` completed, JobChapter `20` completed, all `47` segments verified, artifact `75` active, and Chapter `367` active audio points to artifact `75`.
  - **Final artifact**: `D:\Youtube\Story Trans And Audio\data\output\1-quang-am-chi-ngoai\chapter_0367\job_20\render_0001\chapter.m4a`; SHA-256 `376afa0250cc14ce368e36ff3f9842b8c33139d3ab0250b55f3e6ce92938d808`; size `6765624` bytes; decoded duration `418180 ms`; codec/container `AAC` in `M4A`; sample rate `48000`; channels `1`; peak about `0.6001`; RMS about `0.0678`; clipped samples `0`.
  - **Safety**: Chapters `364` and `365` remained unchanged, Chapter `366` stayed deferred, and no new Text Revision, Casting Plan, speaker draft, or replacement job was created.
  - **Next step**: Chapter `367` Human Audio QA and Targeted Remediation Review.

- **Task 18W - Chapter 367 prepared job started and blocked at segment 20**: started the existing prepared Chapter `367` Job `20` exactly once through the canonical start workflow, monitored it to terminal state, and recorded the same-job recovery boundary.
  - **Repository/runtime baseline**: task started on branch `main` with `HEAD == origin/main == 12809fa8cc2280f97f86f58596948baa47ef9910`; tracked worktree was clean and only protected untracked directories `experiment_b_transcript/` plus `runs/` were present.
  - **Pre-start state verified**: Job `20` was exactly `prepared`, JobChapter `20` was pending and pinned to Chapter `367`, active approved Text Revision `734`, approved Casting Plan `21` revision `1`, and casting plan SHA-256 `90de24d456b14a3e2dbfb0ce53383770c4ea4b356385e58cd0464a234ceb861d`; no segments, artifacts, output audio, or active audio existed.
  - **Backup evidence**: created `D:\Youtube\Story Trans And Audio\backups\task18w_pre_ch367_start_20260716_153900.sqlite3` immediately before start; size `3411968` bytes, SHA-256 `F777AD6273D8B9061A8D68B9D3161046699578DA0EFE1CC1684ECE6E768A737C`, and SQLite `quick_check = ok`.
  - **Exact supported mutation**: exactly one `POST /api/jobs/20/start` call transitioned the same Job `20` to `scheduled`; no legacy job creation, replacement prepare, manual worker method, or second start call was used.
  - **Lifecycle timestamps**: `job_start_requested` at `2026-07-16T08:51:20.384210+00:00`, `jobs.started_at = 2026-07-16T08:51:31.019812+00:00`, `job_chapters.started_at = 2026-07-16T08:51:31.046816+00:00`, `chapter_failed` at `2026-07-16T08:57:28.256914+00:00`, and `jobs.finished_at = 2026-07-16T08:57:28.266916+00:00`.
  - **Terminal blocker**: Job `20` ended `completed_with_errors`; JobChapter `20` ended `failed`. Segment `573` / sequence `20` / utterance `20`, text `"Quá ít."`, voice `custom:25`, failed after `3` attempts because generated audio was `83.0%` silent (`16.1s` of `19.4s`, longest continuous silence `10.1s`).
  - **Segmentation/voice routing**: deterministic segmentation produced `47` rows with sequence range `1-47`, no gaps, no duplicates, no empty segments, no punctuation-only segments, and character counts min `9`, max `256`, median `139`. Voice routing stayed correct with narrator `43 -> custom:26`, character `4 -> custom:25`, unresolved `0`.
  - **Partial synthesis result**: provider/model resolved as `vieneu` / `v3turbo`; `19` segments verified before the failure, `1` segment failed, `27` remained pending, and segment attempt counters total `22` (`19` one-attempt verified segments plus segment `20` at three attempts). The legacy `segment_attempts` table has `0` rows for this job.
  - **No final artifact**: artifacts `0`, active audio `none`, no Chapter `367` output directory exists, and no final path/hash/duration is available. The work directory contains only the first `19` verified WAV segment files.
  - **Safety**: no duplicate Chapter `367` job or JobChapter was created; Text Revision `734`, Casting Plan `21`, speaker draft `12`, Chapter `366`, Chapter `364` artifact `69`, and Chapter `365` artifact `72` remained unchanged.
  - **Next step**: recover the same Job `20` through a supported targeted retry/resume path for failed segment `573`, preserving verified segments and without creating a replacement job or changing text/casting/voice state.
  - **Migration**: none.

- **Task 18V - Chapter 367 prepared production job created**: created exactly one durable prepared job for Chapter `367` and stopped before any render-side execution.
  - **Readiness**: active approved Text Revision `734`, approved Casting Plan `21` revision `1`, speaker draft `12`, custom voice `25`, and custom voice `26` were all re-verified before mutation.
  - **Backup**: pre-mutation SQLite backup created at `D:\Youtube\Story Trans And Audio\backups\task18v_pre_ch367_prepare_20260716_153900.sqlite3`; size `3411968` bytes, SHA-256 `F777AD6273D8B9061A8D68B9D3161046699578DA0EFE1CC1684ECE6E768A737C`, quick_check `ok`.
  - **Prepare request**: exactly one `POST /api/jobs/prepare` call created Job `20` / JobChapter `20` with Book `1`, Chapter `367`, `from_chapter = 367`, `to_chapter = 367`, `voice_name = custom:26`, `repair_mode = off`, `output_format = m4a`, `skip_completed = true`, and `casting_plan_id = 21`.
  - **Prepared state**: Job `20` is `prepared`, `started_at = null`, `finished_at = null`, and pins Chapter `367`, Text Revision `734`, and Casting Plan `21` revision `1`.
  - **Snapshot**: the job chapter retains casting snapshot data with `47` assignments, narrator `43`, character `4`, unresolved `0`, `custom:26 -> 43`, and `custom:25 -> 4`.
  - **Safety**: no worker start, no Gemini call, no TTS call, no segment, no attempt, no artifact, and no output audio file were created. Chapter `366` remained deferred and unchanged.
  - **UI**: the queue visibly shows Job `#20` in prepared state and exposes `Bắt đầu render`; that action was not clicked.
  - **Next step**: explicitly start and monitor the existing Chapter `367` prepared job.
  - **Migration**: none.

- **Task 18U - Chapter 367 Final Voice Map approved**: approved the already-existing Chapter `367` Final Voice Map through the dedicated existing-plan approval workflow without creating any render-side state.
  - **Pre-approval state verified**: speaker draft `12` was non-stale and review-complete on active approved Text Revision `734`; Casting Plan `21` revision `1` existed as the only draft plan with `approved_at = null`.
  - **Exact approval result**: approved exactly Casting Plan `21` revision `1`; no successor revision and no duplicate plan were created. `approved_at` is `2026-07-16T08:16:25.730916+00:00`.
  - **Provenance preserved**: approved plan remains pinned to Text Revision `734` and source speaker draft `12`, with staged speaker-review metadata and the same four reviewed utterance IDs.
  - **Plan counts unchanged**: `assignment_count = 47`, `role_counts = narrator 43 / character 4 / unknown 0`, `unresolved_count = 0`, and `effective_voice_counts = custom:26 -> 43 / custom:25 -> 4`.
  - **Reviewed voice decisions**: `u0020-125ccd5575ff` -> `Hứa Thanh` (`42`, `custom:25`), `u0022-afff3155c7f8` -> `Hứa Thanh` (`42`, `custom:25`), `u0024-e81a37929088` -> `Lão tổ Kim Cương Tông` (`43`, `custom:25`), and `u0028-cd96d6372bc6` -> `Hứa Thanh` (`42`, `custom:25`).
  - **UI next-step state**: after approval, Production Flow exposes the separate prepare-only action `Chuẩn bị job audio (Technical: Casting Plan #21 / v1)` and does not start rendering automatically.
  - **Safety**: Chapter `367` still has no jobs, job chapters, segments, attempts, artifacts, active audio, TTS previews, TTS synthesis, or audio outputs. Chapter `366` remained deferred and unchanged.
  - **Next step**: prepare the real Chapter `367` production job without starting TTS.
  - **Migration**: none.

- **Task 18T - Chapter 367 Final Voice Map draft created from reviewed speaker draft**: converted the existing Chapter `367` speaker draft `12` into one unapproved Final Voice Map / Casting Plan draft and stopped before approval.
  - **Review completion**: all four draft rows were addressed exactly once with no overrides required. Decisions were `u0020-125ccd5575ff` -> `Hứa Thanh` (`42`, `custom:25`), `u0022-afff3155c7f8` -> `Hứa Thanh` (`42`, `custom:25`), `u0024-e81a37929088` -> `Lão tổ Kim Cương Tông` (`43`, `custom:25`), and `u0028-cd96d6372bc6` -> `Hứa Thanh` (`42`, `custom:25`).
  - **Plan creation**: exactly one staged request `POST /api/chapters/367/speaker-review/casting-plan-draft` created Casting Plan `21` revision `1` with `status = draft`, `approved_at = null`, `archived_at = null`, `source_speaker_draft_id = 12`, `assignment_count = 47`, `remaining_unreviewed_count = 0`, `unresolved_count = 0`, `role_counts = narrator 43 / character 4 / unknown 0`, and `effective_voice_counts = custom:26 -> 43 / custom:25 -> 4`.
  - **Safety**: Chapter `367` still has no jobs, job chapters, segments, attempts, artifacts, active audio, TTS previews, TTS synthesis, or audio outputs. Chapter `366` remained deferred and unchanged.
  - **Next step**: inspect and approve the existing Chapter `367` Final Voice Map draft `21`.
  - **Migration**: none.

- **Task 18S - Chapter 367 initial speaker-assignment draft generated**: created exactly one canonical speaker-assignment draft for Chapter `367` and stopped at the operator review boundary.
  - **Repository/runtime baseline**: task started on branch `main` with `HEAD == origin/main == 3ec4940e4d831d07f1a58b1d854f64fa98256fad`; tracked worktree was clean and only protected untracked directories `experiment_b_transcript/` plus `runs/` were present.
  - **Chapter baseline verified**: Chapter `367` still had active approved Text Revision `734` (parent `733`, `reflowed/approved`, processor `lossless-reflow-v1`), content SHA-256 `75a92fa534d759f4929fb9633827d4aea3a25a59dd50dc566dfd2968da37c4c7`, lexical SHA-256 `d76891b4d57ee88f4fb27fbc6c9afd8848c7a30cd8b03544213f5b061f5cb8ef`, character count `6866`, deterministic utterance count `47`, speaker target count `4`, and zero pre-existing speaker drafts, Casting Plans, jobs, segments, attempts, artifacts, or active audio.
  - **Boundary validation passed**: reconstructed exactly four valid target utterances with no empty, punctuation-only, or malformed split target: `u0020-125ccd5575ff` `"Quá ít."`, `u0022-afff3155c7f8` `"Lần trước không phải ngươi đã tràn ra khí tức Hải Thi Tộc sao, làm lại một lần nữa cho ta."`, `u0024-e81a37929088` `"Kêu ngươi làm thì ngươi làm ngay đi."`, and `u0028-cd96d6372bc6` `"Quả nhiên giống như ta phán đoán."`
  - **Character/voice readiness**: reused existing Book `1` characters `42` `Hứa Thanh` and `43` `Lão tổ Kim Cương Tông`; book voice strategy stayed unchanged with narrator `custom:26`, male dialogue `custom:25`, female dialogue `custom:26`, and narrator fallback for unknown.
  - **Exact supported mutation**: exactly one `POST /api/chapters/367/speaker-assignment/draft` call created Draft `12` on Text Revision `734` using `model_id = gemini-2.5-flash`, `prompt_version = speaker-assignment-v2`, and `mode = unassigned_only`.
  - **Draft result**: Draft `12` is `generated`, `stale = false`, `target_count = 4`, `valid_count = 4`, `invalid_count = 0`, `remaining_unreviewed_count = 4`, `cache_hit_count = 0`, and `cache_miss_count = 1`.
  - **Generated suggestions**: `u0020-125ccd5575ff` and `u0022-afff3155c7f8` both resolve to `Hứa Thanh` (`character_id = 42`, `custom:25`, confidence `1.0`); `u0024-e81a37929088` resolves to `Lão tổ Kim Cương Tông` (`character_id = 43`, `custom:25`, confidence `1.0`); `u0028-cd96d6372bc6` resolves to `Hứa Thanh` (`42`, `custom:25`, confidence `1.0`) in internal-thought context.
  - **Safety**: post-generation Chapter `367` still has Casting Plans `0`, approved Casting Plans `0`, jobs `0`, job_chapters `0`, segments `0`, attempts `0`, artifacts `0`, active audio `none`, and no TTS preview/synthesis calls or audio outputs. Chapters `366`, `364`, and `365` remained unchanged.
  - **Deferred chapter note**: Chapter `366` remains intentionally blocked by its malformed quote boundary and was not mutated.
  - **Next step**: review Draft `12` and create one unapproved Final Voice Map without generating another speaker draft.
  - **Migration**: none.

- **Task 18Q - Chapter 365 Human Audio QA closeout**: closed the routine Chapter 365 production cycle with final human acceptance and no remediation.
  - **Final verdict**: recorded `HUMAN_QA_PASS` for canonical Chapter `365`.
  - **Accepted production identity**: closeout preserves active Text Revision `3983`, approved Casting Plan `20` revision `1`, source speaker draft `11`, completed Job `19`, completed JobChapter `19`, and active artifact `72`.
  - **Accepted artifact**: final output remains `D:\\Youtube\\Story Trans And Audio\\data\\output\\1-quang-am-chi-ngoai\\chapter_0365\\job_19\\render_0001\\chapter.m4a`, SHA-256 `4bc75234a5ff804f9dc985af2e46fff2d440f78a061ca749b12e9adcf0375f83`, authoritative duration `408980 ms`, independently decoded duration `408981 ms`, and size `6647393` bytes.
  - **Human review coverage**: complete final audio was reviewed sequentially; chapter start and ending were confirmed not audibly truncated; the corrected internal-thought sentence rendered as one complete utterance; and no punctuation-only utterance exists in the final audio.
  - **Five Hứa Thanh QA markers accepted**: segment `523` / seq `17` / `00:02:28.800`, segment `538` / seq `32` / `00:04:37.610`, segment `540` / seq `34` / `00:04:49.270`, segment `545` / seq `39` / `00:05:41.300`, and segment `552` / seq `46` / `00:06:44.510` all used the expected Hứa Thanh voice and were contextually acceptable.
  - **Technical acceptance**: loudness and duration outliers were reviewed and accepted; seq `34` peaks around `-0.90 dBFS` but is not clipped or distorted; no disruptive loudness transition remains; clipped samples remain `0`; overall level remains about `-19.93 dBFS`; and the `1 ms` duration variance is normal decoder/container rounding.
  - **No remediation required**: no segment was regenerated, no retry was added, no new job was created, no revision/casting/voice state changed, and Chapter `364` remained untouched.
  - **Lifecycle validation**: Chapter 365 now serves as real-production validation that the prepared-job lifecycle works end-to-end through prepare, explicit start, successful render, artifact activation, and final `HUMAN_QA_PASS`.
  - **Next routine step**: move on to selecting and preparing the next sequential canonical production chapter rather than reopening Chapter 365.
  - **Migration**: none.

- **Task 18O - Existing Chapter 365 prepared job started and rendered to completion**: completed the first canonical production start of the prepared-only lifecycle by starting the already-pinned Chapter 365 Job `19`, monitoring it to completion, and stopping at the Human Audio QA boundary.
  - **Repository/runtime baseline**: task started on branch `main` with `HEAD == origin/main == eebd8650437c850fa324880180fa9dc58f93fb13`; tracked worktree was clean and only protected untracked directories `experiment_b_transcript/` plus `runs/` were present.
  - **Pre-start state verified**: canonical runtime `http://127.0.0.1:8772` still pointed to the live Story Audio root and DB, `POST /api/jobs/{job_id}/start` was confirmed live, and Job `19` still existed exactly once in `prepared` with JobChapter `19` pinned to Chapter `365`, Text Revision `3983`, Casting Plan `20`, and plan SHA `3186a20b403a7a39a4da064c784f849ae59913156c3f1d667cbc5bc74a845d28`.
  - **Backup evidence**: created `backups\\task18o_pre_ch365_start_20260716_132718.sqlite3` immediately before mutation; backup size `3248128` bytes, SHA-256 `de2ab05faa6b4ee60dfc33f94a4988d2e94e060ae5178c77f54e0966b46c7e0e`, and SQLite `quick_check = ok`.
  - **Exact supported mutation**: exactly one `POST /api/jobs/19/start` call transitioned the existing prepared row into the executable lifecycle. No new Job and no new JobChapter were created.
  - **Lifecycle timestamps**: audit `job_start_requested` was recorded at `2026-07-16T06:27:22.680747+00:00`; `jobs.started_at = 2026-07-16T06:27:33.334422+00:00`; `job_chapters.started_at = 2026-07-16T06:27:33.360429+00:00`; `job_chapters.finished_at = 2026-07-16T06:38:14.776740+00:00`; `jobs.finished_at = 2026-07-16T06:38:14.802745+00:00`.
  - **Execution path**: canonical state transitions observed were `prepared -> scheduled -> synthesizing -> assembling -> completed`. No duplicate worker execution, no second Chapter 365 job, and no failure/interruption state occurred.
  - **Segmentation result**: deterministic segmentation produced exactly `47` utterance segments from the pinned Casting Plan. Segment text stats were `min 15 / max 244 / median 158` characters, with no empty segments, no punctuation-only segments, and no invalid offsets.
  - **Voice routing result**: narrator segments `42` all resolved to `custom:26`; Hứa Thanh segments `5` all resolved to `custom:25`; unresolved `0`; no unintended fallback voice appeared. Runtime segment synthesis used provider `vieneu` and model `v3turbo`.
  - **Attempt/retry result**: all `47` segment rows finished as `verified` with `attempt_count = 1`, so the full chapter succeeded in one pass with no retries or failures. The legacy `segment_attempts` table remained unused for this successful render and still contains `0` Chapter 365 rows.
  - **Artifact result**: Job `19` produced artifact `70` (`chapter_master_wav`), artifact `71` (`segment_timeline_json`), and artifact `72` (`chapter_m4a`). Final active output is `D:\\Youtube\\Story Trans And Audio\\data\\output\\1-quang-am-chi-ngoai\\chapter_0365\\job_19\\render_0001\\chapter.m4a`, SHA-256 `4bc75234a5ff804f9dc985af2e46fff2d440f78a061ca749b12e9adcf0375f83`, size `6647393` bytes, duration `408980 ms`, `48000` Hz, mono, AAC-LC in M4A.
  - **Media validation**: decoder duration exactly matched stored duration; the master WAV peak stayed about `-0.9 dBFS`, RMS about `-19.93 dBFS`, and no clipping was detected; Chapter `365` active audio is now artifact `72`, while Chapter `364` remained unchanged at active artifact `69`.
  - **Human QA boundary**: prepared review markers for chapter start/end, all five Hứa Thanh utterances, and several duration/loudness outliers. No targeted regeneration was performed in Task 18O.
  - **Migration**: none.

- **Task 18N - Real Chapter 365 production job prepared without starting TTS**: completed the first canonical production use of the new two-stage job lifecycle by preparing the real Chapter 365 job and stopping cleanly before render execution.
  - **Repository/runtime baseline**: task started on branch `main` with `HEAD == origin/main == 3b6f1310fcf1ccbdcf5cb182e27b42b6e4840bde`; tracked worktree was clean and only protected untracked directories `experiment_b_transcript/` plus `runs/` were present.
  - **Runtime recovery**: canonical runtime `http://127.0.0.1:8772` still pointed to the live Story Audio root and DB, but initially served stale pre-Task-18M API code. The old listener on port `8772` was replaced through the supported repository launcher before mutation, and the required routes `POST /api/jobs/prepare` plus `POST /api/jobs/{job_id}/start` were then confirmed live.
  - **Preflight state verified**: Chapter 365 still had active approved Text Revision `3983`, approved Casting Plan `20` revision `1`, Book Voice Profile narrator `custom:26` / male dialogue `custom:25`, and zero Chapter 365 jobs, job_chapters, segments, attempts, repair blocks, artifacts, or audio outputs before mutation.
  - **Backup evidence**: created `backups\\task18n_pre_ch365_prepare_20260716_131349.sqlite3` before mutation; backup size `3178496` bytes, SHA-256 `463711f9cde945d7adc9b32d584afb92c69a989cffd5c160af445ff16959744e`, and SQLite `quick_check = ok`.
  - **Exact supported mutation**: exactly one `POST /api/jobs/prepare` call created exactly one real Chapter 365 prepared job using Book `1`, Chapter `365`, `voice_name = custom:26`, `repair_mode = off`, `output_format = m4a`, `skip_completed = true`, and approved `casting_plan_id = 20`.
  - **Committed prepared state**: the response created Job `19` with `status = prepared`. Authoritative DB state confirms the same row pins Chapter `365`, Text Revision `3983`, Casting Plan `20`, and `job_chapters.casting_plan_sha256 = 3186a20b403a7a39a4da064c784f849ae59913156c3f1d667cbc5bc74a845d28`.
  - **No execution after prepare**: after creation, Job `19` remained `prepared` with `started_at = null`, `finished_at = null`, and Chapter 365 still had segments `0`, attempts `0`, repair blocks `0`, artifacts `0`, and active audio `null`. No Gemini call, TTS synthesis, render start, or `/api/jobs/{job_id}/start` call was performed.
  - **UI confirmation**: the live queue now shows Job `#19` for Chapter `365` in prepared state with the pinned summary (`custom:26`, `off`, `M4A`) and the separate operator action `Bắt đầu render`.
  - **Next boundary**: Chapter 365 now has a durable prepared production identity. The next valid operational step is to start the existing prepared job rather than prepare another one.
  - **Migration**: none.

- **Task 18M - Prepared job lifecycle separated from render start**: added a canonical two-stage production lifecycle so production jobs can be prepared durably before any worker execution begins.
  - **Root cause fixed**: `POST /api/jobs` previously created `jobs.status='scheduled'` and immediately called `worker.wake()`, while the worker actively selected scheduled jobs. There was no durable non-executable preparation state.
  - **New lifecycle**: added explicit backend services `prepare_job(...)` and `start_prepared_job(...)`.
  - **Prepared state**: prepare now creates exactly one `jobs` row plus one `job_chapters` row with `jobs.status='prepared'`, pinned Text Revision / Casting Plan / voice snapshot identity, and no worker wake, no Gemini call, no TTS call, no segment, no attempt, no artifact, and no audio output.
  - **Start state**: `start_prepared_job(...)` atomically transitions the same prepared row to `scheduled`, preserves the existing undo window, and only then allows the worker to consume it.
  - **New API routes**: added `POST /api/jobs/prepare` and `POST /api/jobs/{job_id}/start` with explicit `400/404/409` handling for stale inputs, missing jobs, duplicate prepares, conflicting live jobs, and repeated or invalid starts.
  - **Worker exclusion**: prepared jobs are durable and restart-safe because the worker still selects only `scheduled`, `queued`, and `interrupted`; `prepared` is never executable until explicit start occurs.
  - **Segmentation boundary**: chose **Option B**. Prepare stores immutable pins only; deterministic segmentation still occurs after explicit start, so the execution boundary stays single-source and cannot silently diverge from a preview/prepared boundary.
  - **Legacy compatibility**: legacy `POST /api/jobs` still creates exactly one executable job, but it now internally reuses the same row through prepare-then-start rather than relying on immediate create-and-wake coupling.
  - **UI separation**: approved plans with no job now surface `Chuẩn bị job audio`; prepared jobs surface the pinned prepared state plus `Bắt đầu render`; rendering no longer starts automatically during preparation.
  - **Retry/duplicate safety**: duplicate prepare and conflicting live jobs now fail closed instead of creating overlapping production identity rows, while repeated start on the same prepared job returns conflict safely.
  - **Verification**: `tests.test_prepared_jobs`, `tests.test_speaker_review_ui`, `tests.test_casting`, `tests.test_voice_profile`, and `tests.test_diagnostics` passed; `node --check ui/app.js` passed.
  - **Production safety**: Task 18M changed code/tests/docs only. Canonical Chapter 365 production data was not mutated.
  - **Migration**: none.

- **Task 18K - Chapter 365 Final Voice Map approved on canonical production**: approved the already-existing Chapter 365 Final Voice Map through the dedicated existing-plan approval workflow without creating any render-side state.
  - **Repository/runtime baseline**: task started on branch `main` with `HEAD == origin/main == 0ce4e6446fbb76950d35d2828305b58cd7563a7e`; tracked worktree was clean and only protected untracked directories `experiment_b_transcript/` plus `runs/` were present.
  - **Pre-approval state verified**: canonical runtime `http://127.0.0.1:8772` still pointed to the live Story Audio data root/DB, Chapter 365 still had active Text Revision `3983`, reviewed non-stale speaker draft `11`, stale historical draft `10`, and exactly one draft Casting Plan `20` revision `1`.
  - **Approval boundary verified**: UI action `Duyệt bản đồ giọng cuối & tiếp tục tạo audio (v1)` uses `POST /api/casting/{casting_plan_id}/approve`; backend `approve_plan(...)` only archives any older approved plan, marks the requested draft approved, and re-validates the plan. It does not create jobs, job_chapters, segments, attempts, artifacts, manifests, or audio.
  - **Final Voice Map inspection**: plan content was re-verified before approval with `47` assignments, narrator `42`, Hứa Thanh `5`, unknown `0`, unresolved `0`, effective voices `custom:26 -> 42` and `custom:25 -> 5`, no punctuation-only utterance, and stable offsets preserved for the five Hứa Thanh targets.
  - **Exact approval result**: approved exactly Plan `20` revision `1`; no successor revision and no duplicate plan were created. `approved_at` is `2026-07-15T13:39:48.199756+00:00`.
  - **Provenance preserved**: approved plan remains pinned to Text Revision `3983`, and plan source metadata still records staged speaker-review provenance from draft `11` plus the same five reviewed utterance IDs.
  - **UI next-step state**: after approval the canonical chapter state now satisfies the Production Flow branch that advances to `Bước 5: Tạo audio chương`; no render action was invoked during Task 18K.
  - **Production safety**: after approval, Chapter 365 still has jobs `0`, job_chapters `0`, segments `0`, segment attempts `0`, artifacts `0`, repair blocks `0`, manifests `0`, provider calls `0`, TTS previews `0`, TTS synthesis calls `0`, audio outputs `0`, and no new Text Revision.
  - **Migration**: none.

- **Task 18J - Chapter 365 draft-only Final Voice Map created on canonical production**: completed the first production use of the staged speaker-review workflow by reviewing Draft `11` and creating exactly one unapproved Final Voice Map / Casting Plan draft for Chapter 365.
  - **Repository/runtime baseline**: task started on branch `main` with `HEAD == origin/main == de23c16c4a82401558ec6c72186b3d04ac0ea77e`; tracked worktree was clean and only protected untracked directories `experiment_b_transcript/` plus `runs/` were present.
  - **Runtime recovery**: canonical runtime `http://127.0.0.1:8772` initially exposed stale pre-Task-18I API code, so that process was replaced through the supported repository launcher before mutation; only after restart did `POST /api/chapters/{chapter_id}/speaker-review/casting-plan-draft` become available on the live API.
  - **Exact reviewed assignments**: reused existing speaker draft `11` on Text Revision `3983` and accepted all five targets as character `42` (`Hứa Thanh`): `u0017-d3809b48d599`, `u0032-fe2bc9743573`, `u0034-9634d7a009f0`, `u0039-99e8b095900e`, and `u0046-8cad60adce11`.
  - **Voice resolution verified**: narrator remained `custom:26`, Hứa Thanh resolved to `custom:25`, and unused unknown fallback remained narrator `custom:26` under Book Voice Profile `5` version `2`.
  - **Draft-only plan creation**: exactly one staged request created Casting Plan `20` revision `1` with `status = draft`, `approved_at = null`, `text_revision_id = 3983`, and provenance `source_speaker_draft_id = 11`.
  - **Plan counts**: the resulting immutable Final Voice Map contains `47` assignments with narrator `42`, Hứa Thanh `5`, unknown `0`, effective voice counts `custom:26 -> 42` and `custom:25 -> 5`, and `unresolved_count = 0`.
  - **UI readiness**: Chapter 365 Production Flow now opens the existing unapproved Final Voice Map instead of prompting to regenerate speaker assignments; the separate approval action exposed to the operator is `Duyệt bản đồ giọng cuối & tiếp tục tạo audio (v1)`.
  - **Production safety**: after Task 18J, Chapter 365 still has approved Casting Plans `0`, jobs `0`, job_chapters `0`, segments `0`, segment attempts `0`, artifacts `0`, repair blocks `0`, no new Text Revision after `3983`, and no TTS preview/synthesis or audio output.
  - **Migration**: none.

- **Task 18I - Staged speaker review and draft-only Final Voice Map workflow**: separated operator speaker-review completion from Casting Plan approval so Chapter 365 and future chapters can produce a draft-only Final Voice Map before any approval or render step.
  - **Root cause fixed**: `story_audio.speaker_review.approve_speaker_review(...)` previously created a Casting Plan draft and immediately called `approve_plan(...)`, collapsing review, draft creation, and approval into one mutation path.
  - **New staged service**: added `create_casting_plan_draft_from_speaker_review(...)`, which reuses existing draft/base identity rules, requires all review rows to be covered, creates exactly one draft-only Casting Plan, verifies that every utterance has a resolved voice, and never auto-approves.
  - **New API route**: added `POST /api/chapters/{chapter_id}/speaker-review/casting-plan-draft` with `speaker_draft_id`, `expected_draft_fingerprint`, `expected_text_revision_id`, `decisions`, `idempotency_key`, and optional `operator_note`.
  - **Duplicate/retry behavior**: exact same review identity reuses the existing draft-only plan instead of creating duplicates; conflicting idempotency reuse still fails closed.
  - **Compatibility preserved**: legacy route `/api/chapters/{chapter_id}/speaker-assignment/drafts/{draft_id}/approve` remains available and still performs the old one-step approval path for callers that explicitly use it.
  - **UI separation**: the speaker-review action is now presented as `Tạo Final Voice Map draft`, enablement requires complete local row coverage via `reviewReadyForCastingPlan(...)`, and success messaging tells the operator to inspect/approve separately in the Final Voice Map section.
  - **Verification**: `node --check ui/app.js` passed; focused tests `tests.test_speaker_assignment`, `tests.test_speaker_review_api`, and `tests.test_speaker_review_ui` passed at `42/42`.
  - **Production safety**: Task 18I was implementation-only. No canonical Chapter 365 mutation, no new speaker draft, no live Casting Plan, no approval, no job, and no audio render were performed while verifying this change.
  - **Migration**: none.

- **Task 18G - Canonical Chapter 365 targeted correction and one fresh speaker draft**: recorded the exact supported production mutation that repaired the malformed internal-thought punctuation on Chapter 365 and regenerated one clean speaker-assignment draft without creating casting or audio state.
  - **Repository/runtime baseline**: task started on branch `main` with `HEAD == origin/main == 6776c257e86e2f06d01d4f1be509b45c0e946a5a`; tracked worktree was clean and only protected untracked directories `experiment_b_transcript/` plus `runs/` were present.
  - **Runtime recovery**: canonical runtime `http://127.0.0.1:8772` was first confirmed to be serving pre-Task-18F code, so that stale process was replaced with the repository runtime before mutation; only after restart did the supported route `POST /api/chapters/{chapter_id}/text-revisions/targeted-correction` appear in the loaded API surface.
  - **Backup evidence**: created `backups\\task18g_pre_ch365_targeted_correction_20260715_191351.sqlite3` before mutation; backup DB SHA-256 `7138beefed3480032e6cf8d6abceaeab4d94d2e169e87d2e0a8984ab6b29323e`, backup DB size `3178496` bytes, and SQLite `quick_check = ok`.
  - **Exact supported correction**: the active approved Text Revision `730` contained one exact match of `"Không biết so với đội trưởng, sức mạnh của ta bây giờ đã như thế nào.... ."` and was corrected once through the supported API to `"Không biết so với đội trưởng, sức mạnh của ta bây giờ đã như thế nào..."`.
  - **Revision result**: the API created one new immutable approved Text Revision `3983` with `parent_revision_id = 730`, `kind = repaired`, `processor_version = targeted-correction-v1`, `content_sha256 = e0e76f8d80a2c2fbee49676db4175cac1bb3e6e779d343021e8cfc3e174bd1a6`, `lexical_sha256 = 72115486b4e139682fc9388f48e58d39633a1c9475ceaf19e4a5f46efbb609cc`, and `char_count = 6480`.
  - **Minimal diff proof**: authoritative diff between revisions `730` and `3983` showed one changed block, lexical integrity preserved, `punctuation_removed = 2`, and character count reduced from `6483` to `6480`; no wording changed outside the malformed punctuation removal.
  - **Speaker-draft boundary repair confirmed**: draft `10` stayed immutable on revision `730` and became stale via normal revision mismatch; read-only request inspection on revision `3983` showed exactly five quote/thought targets, no punctuation-only utterance, and the corrected internal-thought line collapsed into one full target.
  - **Single generation request**: exactly one new speaker-assignment draft `11` was generated through the canonical workflow on revision `3983`; result was `reused = false`, `cache_hit_count = 0`, `cache_miss_count = 1`, `status = generated`, `target_count = 5`, `valid_count = 5`, and `invalid_count = 0`.
  - **Review-ready output**: draft `11` reconstructs five unreviewed rows, all currently suggested as character `42` (`Hứa Thanh`) with resolved voice `custom:25` from Book Voice Profile `5` version `2`.
  - **Production safety preserved**: Chapter 365 still has zero Casting Plans, zero approved plans, zero jobs, zero job chapters, zero segments, zero segment attempts, zero artifacts, zero active audio outputs, and zero repair blocks after Task 18G.
  - **Migration**: none.

- **Task 18F - Canonical targeted text correction workflow**: added a supported operator/API path for exact immutable chapter-text correction without using the render-time Gemini repair pipeline.
  - **Architecture gap closed**: before this task, Story Audio could inspect and diff chapter TextRevisions, but the only built-in path that created a new approved revision was the job-driven Gemini repair pipeline. That path was unsuitable for exact operator fixes because it is AI-mediated, runtime-coupled, and can create repair/job state.
  - **New backend workflow**: added `story_audio.text_correction.apply_targeted_text_correction(...)`, which validates one exact literal match against the current active approved TextRevision, applies one substitution, creates one new immutable approved TextRevision, and activates it atomically.
  - **API contract**: added `POST /api/chapters/{chapter_id}/text-revisions/targeted-correction` with `base_revision_id`, `expected_text`, `replacement_text`, and `reason`.
  - **Immutability and provenance**: the workflow reuses revision kind `repaired`, preserves provenance through `parent_revision_id`, marks the new revision `approved`, and tags its origin with processor version `targeted-correction-v1`.
  - **Retry and stale-base safety**: zero-match and multi-match requests fail without mutation; a base revision from another chapter returns not found; unapproved or non-active base revisions fail safely; retrying after success against the old base returns conflict instead of creating a duplicate revision.
  - **Downstream compatibility**: existing speaker-assignment drafts remain immutable. When the active TextRevision changes, draft stale detection continues to work through the existing revision-mismatch mechanism without mutating historical draft rows.
  - **Audit boundary**: the correction reason is recorded through `audit_events` together with revision provenance and hashed replacement identifiers, without logging full chapter text or invoking any external provider.
  - **UI scope**: backend/API support only for Task 18F. Minimal operator UI was deferred to keep the implementation focused and avoid broad production-flow redesign.
  - **Verification**: focused isolated tests passed for success, validation failures, rollback safety, API contract/classification, retry conflict behavior, and speaker-draft stale compatibility; existing speaker-assignment review coverage remained green.
  - **Production safety**: no real Chapter 365 correction was executed during this task, and canonical `data/app.db` / jobs / artifacts / output state were left untouched.
  - **Migration**: none.

- **Task 18A/18B - Chapter 364 canonical production pilot closeout**: recorded the completed production pilot, targeted remediation result, and final human sequential listening verdict for canonical Chapter 364 without changing source code or creating any further render attempts.
  - **Canonical evidence**: Book `Quang Âm Chi Ngoại`, Chapter `364`, Text Revision `728`, approved Casting Plan `19` rev `1`, Job `18` completed, active artifact `69`.
  - **Final accepted output**: `D:\Youtube\Story Trans And Audio\data\output\1-quang-am-chi-ngoai\chapter_0364\job_18\render_0002\chapter_final.m4a` with SHA-256 `3B9748DE4B1F5E8259B7BB0498A996D53F4E52428B0CB68E4633EA25D66BFDCC` and authoritative duration `363590 ms`.
  - **Duration note**: independently decoded duration `363605 ms` differs by `15 ms`, which was accepted as normal container/decoder rounding rather than a content defect.
  - **Targeted remediation evidence**: only Segment `498` / seq `42` was regenerated; candidate attempt `36` was accepted after improving local loudness continuity without introducing clipped samples. No other reviewed marker required regeneration.
  - **Final QA verdict**: `HUMAN_QA_PASS`. The complete final artifact was reviewed sequentially, all seven flagged review locations were checked, and no remaining audible issue justified further remediation.
  - **Migration**: none.

- **Task 13C - Step-by-step production flow UI**: reshaped the Character Voices workspace from a guide-like dashboard into a real operator step flow that mirrors the chapter production order without changing backend behavior.
  - **Wizard-style flow**: the top of Character Voices now renders `Production Flow` as a stepper with eight explicit steps: `Select Chapter`, `Text Ready`, `Character Bible / Characters`, `Voice Assignment / Casting`, `Approve Casting Plan`, `Render Audio`, `QA Checklist`, and `Human QA Verdict`.
  - **Actionable step details**: each step now explains its purpose, current status, what the operator needs to do now, what happens after, and whether `Back`, `Continue`, or `Next` is the correct move.
  - **Blocker-first guidance**: when a step cannot advance, the UI now shows clear reasons such as missing approved text, missing casting plan, draft-only plan state, or existing active audio that should route the operator to QA instead of routine rerender.
  - **Safer default path**: when a Casting Plan already exists, the step flow prefers reviewing that plan instead of regenerating AI draft suggestions; when active audio already exists, the normal path moves to QA rather than render.
  - **Verification**: `node --check ui/app.js` passed; focused Character Voices / active-output UI coverage passed at 22/22; full offline suite passed at 907/907 with 1 expected Windows symlink-privilege skip.
  - **Migration**: none.

- **Task 13B - Guided operator production flow**: added an operator-facing guide inside Character Voices so a non-developer can tell what to use first, what each major area is for, and what the recommended next step is for the current chapter state.
  - **Visible flow guide**: Character Voices now opens with `Start Here / Production Flow`, spelling out the normal production path from chapter selection through text review, Character Bible, AI speaker suggestions when needed, Casting Plan review/approval, render, QA checklist, and human QA or targeted segment regeneration.
  - **Chapter next-action banner**: the workspace now shows `Recommended Next Action` driven by current chapter/casting state, covering `no text`, `text not approved`, `no casting plan`, `casting plan draft`, `casting plan approved`, `job running`, `active audio ready for qa`, and optional `human qa accepted` when that state is present in chapter detail.
  - **Plain-language area descriptions**: Book Voice Profile, Character Bible, AI Speaker Draft, Casting Plan Review, and Render / Production Output now explain what to use them for, when to use them, and when not to use them.
  - **Advanced/debug labeling**: AI speaker-draft tooling and diagnostics now read explicitly as `Advanced / Debug`, helping operators distinguish routine production flow from troubleshooting-only tools such as historical jobs, raw diagnostics, and segment attempts.
  - **Verification**: `node --check ui/app.js` passed; focused Character Voices / active-output UI coverage passed at 20/20; full offline suite passed at 905/905 with 1 expected Windows symlink-privilege skip.
  - **Migration**: none.

- **Task 13A - Simplified Character Voices production UI**: reshaped the chapter production workspace so operators can distinguish AI speaker suggestions, Casting Plan review, and render-ready production output without confusing one approval step for another.
  - **Clear production stages**: Character Voices now shows a persistent production-step banner plus distinct sections for `AI Draft / Suggestions`, `Casting Plan Review`, and `Render / Production Output`.
  - **Draft-vs-plan warning**: when a Casting Plan already exists, speaker-draft tools are visually de-emphasized and the panel warns `AI Draft tools can create a new plan; use Casting Plan Review to approve the current plan.`
  - **Safer labels**: the speaker-draft approval action now reads as creating/updating a Casting Plan from the AI draft, the plan-approval button includes the exact revision identity (`Approve Casting Plan vN`), and the render action shows the exact Casting Plan identity that will be rendered.
  - **Correct jump target**: `Jump to Casting Plan approval` now scrolls to the real plan-approval controls instead of the speaker-draft review controls.
  - **Production-output guidance**: when active audio already exists, Character Voices now keeps the active Job / Plan context visible while clarifying that speaker drafts do not render directly and that playback stays on the active historical plan until a newer approved plan is rendered.
  - **Verification**: `node --check ui/app.js` passed; focused Character Voices UI coverage passed at 17/17; full offline suite passed at 902/902 with 1 expected Windows symlink-privilege skip.
  - **Migration**: none.

- **Task 12D - Canonical Chapter 357 human QA result recorded**: officially recorded the operator's full-chapter listening verdict for canonical Chapter 357 without modifying production audio, artifacts, or database state.
  - **Recorded verdict**: canonical Chapter 357 Job `17` is now marked `HUMAN_QA_PASS_WITH_MINOR_PRONUNCIATION_NOTES`.
  - **Binding preserved**: the recorded acceptance is tied to Casting Plan `18`, active artifact `48`, and final M4A SHA `024e9f8cc1a646095eb84fad71d532fc04875e9eb34609a397e44c6f3153b675`.
  - **Evidence package preserved**: downstream manifest / QA / listening checklist under `data\workflow\job_17_chapter_357\` remain the supporting package for that accepted run.
  - **Notes boundary**: detailed pronunciation notes are not persisted by Story Audio automatically; checklist review notes remain browser-local unless the operator explicitly exports review JSON or pastes the notes elsewhere for archival.
  - **Migration**: none.

- **Task 12C3 - Canonical downstream QA/checklist guard**: extended the existing explicit canonical-production opt-in so downstream manifest/QA/listening-checklist generation can run against a completed canonical job without weakening the default fail-closed guardrails.
  - **Default refusal preserved**: `story_audio/audio_qa.py` and `story_audio/listening_checklist.py` still reject the canonical production root unless the operator passes explicit canonical approval through `--allow-canonical-production`.
  - **Downstream-only canonical path**: `story_audio/production_workflow.py` now permits canonical downstream generation for an already completed job only when the operator provides both `--allow-canonical-production` and an exact `--job-id`; new canonical job creation still requires `--submit`.
  - **Identity re-verification**: before writing downstream outputs, the workflow now re-reads the manifest and re-checks Job / Chapter / Text Revision / Casting Plan identity, completed terminal state, and the active final artifact path plus SHA-256 so canonical downstream runs stay fail-closed on mismatches.
  - **Read-only boundary**: downstream-only canonical mode writes expected workflow outputs under `data\workflow\job_<JOB_ID>_chapter_<CHAPTER_NUMBER>\` without submitting, rendering, retrying, regenerating, accepting, or rejecting anything in production state.
  - **Verification**: focused production-workflow/audio-QA/listening-checklist coverage passed at 92/92 with 1 expected Windows symlink-privilege skip, and the full offline suite passed at 898/898 with 1 skipped.
  - **Migration**: none.

- **Task 12C2 - Custom voices in production workflow checks**: extended canonical/unified workflow preflight so Casting Plans can reference both preset voice IDs and active usable custom voice IDs without weakening the existing fail-closed guardrails.
  - **Voice catalog expansion**: `story_audio/production_runner.py` now resolves availability from both `/api/voices` and `/api/custom-voices`, then verifies that custom IDs such as `custom:25` and `custom:26` point to active voices with a usable preferred or latest synthesis revision.
  - **Strict failures preserved**: missing custom voices, inactive custom voices, or custom voices without a usable revision still stop preflight before submit; the error now reports generic `unavailable voice(s)` rather than incorrectly calling them preset-only failures.
  - **Canonical preflight coverage**: focused runner/workflow/custom-voice tests passed at 85/85, and the full offline suite passed at 893/893 with 1 expected Windows symlink-privilege skip. Coverage includes preset-only plans, mixed preset/custom plans, missing custom IDs, inactive custom voices, revision-less custom voices, and canonical preflight passing with Chapter 357 style voice bindings without submitting a job.
  - **Migration**: none.

- **Task 12C1 - Explicit canonical mode for unified production workflow**: added a strongly-guarded opt-in path for running the existing unified workflow against canonical production without weakening the default isolated fail-closed behavior.
  - **Default safety preserved**: `scripts/run_production_workflow.py` still refuses the canonical live root unless the operator passes explicit CLI confirmation `--allow-canonical-production`.
  - **Canonical submit guard**: canonical mode also requires explicit `--submit`; it does not auto-enable from environment alone and does not permit a silent watch-only or resume-only canonical path.
  - **Runtime/binding checks preserved**: canonical mode still runs the same `/api/runtime` identity check, exact data-root match, approved Casting Plan verification, Text Revision/chapter binding verification, voice availability checks, and duplicate pending/running job detection before any submit occurs.
  - **Operator evidence**: final workflow payload now records `CANONICAL PRODUCTION MODE`, canonical data root, casting-plan revision/SHA, and created job identity when submission succeeds.
  - **Isolated mode unchanged**: isolated production workflow semantics, output paths, and fail-closed behavior are unchanged.
  - **Verification**: focused workflow/runner tests passed at 69/69, and the full offline suite passed at 887/887 with 1 expected Windows symlink-privilege skip. Coverage includes canonical rejection by default, explicit canonical allow path, canonical runtime mismatch rejection, missing casting-plan CLI rejection, and unchanged isolated behavior.
  - **Migration**: none.

- **Task 11D3B3 - Casting review discoverability and active-audio operator guidance**: improved the operator path from chapter selection into Character Voices and made it harder to confuse a fresh casting draft with the chapter's currently active audio.
  - **Direct chapter CTA**: chapter rows now expose a `Review Character Voices` button that opens the selected chapter directly on the `Character Voices` workspace instead of requiring row-open plus manual tab discovery.
  - **Casting-state badges**: chapter rows surface `CASTING REVIEW NEEDED` when the latest persisted casting plan is still `draft`, and `CASTING APPROVED` when the latest plan is `approved`; this status comes from casting-plan context, not job recency or job status.
  - **Character Voices guidance**: the panel now shows plan revision/status in place, a short `Review assignments before rendering` reminder for draft plans, jump shortcuts to pending-review rows and approval controls, and a persistent note that speaker-review decisions stay local until final approval.
  - **Active-audio warning**: when a chapter already has active playback, Character Voices now identifies the bound active Job / Casting Plan and warns when the operator is reviewing a newer draft that has not yet produced the current audio.
  - **Historical diagnostics shortcut**: historical job diagnostics now provide `Open current Character Voices` so the operator can jump straight from old evidence back to the authoritative casting workspace.
  - **Verification**: `node --check ui/app.js` passed; focused active-output/speaker-review/runtime UI coverage passed at 22/22; full offline suite passed at 879/879 with 1 expected Windows symlink-privilege skip.
  - **Live verification**: restarted only Story Audio on `http://127.0.0.1:8772`, confirmed `/api/runtime` still reports canonical production root `D:\Youtube\Story Trans And Audio\data`, verified the new CTA opens the chapter directly into `Character Voices`, and preserved the 4-voice Custom Voice Library plus `ACTIVE OUTPUT` / `HISTORICAL` labels. Port `8765` (YouTube Auto) remained untouched.
  - **Migration**: none.

- **Task 11D3C - Final production GO decision**: Recorded the final readiness verdict after the runtime-safety and active-output-clarity rollout work.
  - **Decision**: official verdict is `PRODUCTION_GO`.
  - **Basis**: Task 11D3B1 and Task 11D3B2 are pushed and complete, canonical production on `http://127.0.0.1:8772` is verified, and Chapter 357 Job 2 already passed full human listening.
  - **Rollout boundary**: no second acceptance chapter is required before production rollout.
  - **Next task**: `Task 11D3B3 - Casting Review Discoverability and Active-Audio Operator Guidance`.
  - **Migration**: none.

- **Task 11D3B2 - Active output versus historical job clarity**: surfaced the existing chapter artifact binding throughout the API and operator UI so production users can tell which completed job currently backs chapter playback and which jobs are historical evidence only.
  - **Source of truth**: active output is resolved from `chapters.active_audio_artifact_id`, then joined through `artifacts.job_chapter_id` to the owning `job_id` and `casting_plan_id`; the UI no longer needs to infer "current" audio from newest job ID or latest completion time.
  - **API/view-model additions**: chapter list/detail and job list/detail responses now expose active-output metadata including active artifact ID, active Job ID, JobChapter ID, and Casting Plan revision when the binding is trustworthy.
  - **Operator labels**: chapter rows show `ACTIVE AUDIO`; jobs that back the bound chapter artifact show `ACTIVE OUTPUT`; other completed jobs for the same chapter show `HISTORICAL`; diagnostics add explicit active-versus-historical banners without changing persisted business status in SQLite.
  - **Playback safety**: chapter playback/download continues to use the active artifact path already bound on the chapter, so this task changes clarity only and does not alter render, submit, candidate, or approval semantics.
  - **Verification**: focused active-output and runtime/diagnostics UI coverage passed, segment-regeneration UI compatibility stayed green, and the full offline suite passed at 877/877 with 1 expected Windows symlink-privilege skip.
  - **Migration**: none.

- **Task 11D3B1 - Runtime identity banner and operator safety guard**: Added an always-visible runtime identity banner to the operator UI and fail-closed mutation gating while runtime identity is still unknown.
  - **Runtime banner**: `ui/index.html`, `ui/styles.css`, and `ui/app.js` now surface `CANONICAL PRODUCTION`, `ISOLATED / NON-PRODUCTION`, or `RUNTIME UNKNOWN` in the header, with a short data-root display and full canonical/isolated path available via tooltip.
  - **Identity source**: the UI now loads `GET /api/runtime` during initialization and never silently assumes the runtime is production while that request is pending or fails.
  - **Fail-closed operator safety**: primary mutation controls stay disabled until runtime identity resolves, including EPUB import, queue submission, speaker-draft generation/regeneration, Character Bible apply/clear, casting draft save, casting approval, job render, and retry/regenerate-style actions.
  - **No backend contract change**: canonical and isolated runtimes are both still allowed to mutate once identity resolves; this task does not change API authorization or schema.
  - **Verification**: focused runtime/UI tests 237/237 pass; full offline suite 870/870 pass with 1 expected Windows symlink-privilege skip.
  - **Live verification**: restarted only Story Audio on `http://127.0.0.1:8772`, confirmed `/api/runtime` still points to canonical root `D:\Youtube\Story Trans And Audio\data`, rendered DOM shows `CANONICAL PRODUCTION`, and canonical Custom Voice Library inventory remains 4 active voices. Port `8765` (YouTube Auto) was left untouched.
  - **Migration**: none.

- **Task 11D2 - Chapter 357 production acceptance pass**: Recorded the first real end-to-end acceptance run of the unified production workflow on an isolated runtime without changing application code.
  - **Accepted chapter**: `Quang Âm Chi Ngoại` Chapter `357`, Text Revision `714`, approved Casting Plan `#6` / revision `6`, chunker `utterance-v3`.
  - **Speaker validation**: human review confirmed seq `42–44` and `90–92` as `Lão tổ Kim Cương Tông -> Đức Trí`; seq `41`, `45`, and `93` remained `Narrator -> Ngọc Lan`.
  - **Production run**: unified workflow submitted Job `#2`, watched it to completion, then generated production manifest, objective QA JSON, and deterministic listening checklist with matching Job/Text Revision/Casting Plan bindings.
  - **Acceptance result**: Job `#2` / JobChapter `#2` completed with `96/96` verified segments, voice distribution `Ngọc Lan 90` / `Đức Trí 6`, and final accepted M4A at `D:\Youtube\StoryAudioAcceptanceRun1\data\output\1-quang-am-chi-ngoai\chapter_0357\job_2\render_0001\chapter.m4a`.
  - **Human authority**: operator listened to the full chapter and marked the run PASS; Job `#1` remains preserved as earlier casting-evidence only and is not the accepted render.
  - **Migration**: none.

- **Task 11D2C - Punctuation-aware utterance splitter v3**: Improved deterministic utterance splitting so long lines prefer natural punctuation boundaries before raw whitespace and no longer strand one-word or very short orphan tails when a better cut exists.
  - **Chunking behavior**: `story_audio/casting.py` now prefers sentence punctuation (`.?!…`), then clause punctuation (`,;:`), then whitespace within the lookback window before `tts_max_chars`; every chunk still remains within the existing maximum.
  - **Offset safety**: no text is lost or duplicated, offsets remain deterministic, and manual offset-based casting continues to map rebuilt utterances to the same character assignments.
  - **Versioning**: `CHUNKER_VERSION` advanced to `utterance-v3`, and `story_audio/speaker_assignment.py` now pins that exact version in draft request identity so v1/v2 semantics are not silently reused through cache or downstream review artifacts.
  - **Verification**: focused casting/speaker tests 48/48 pass; full offline suite 863/863 pass with 1 expected Windows symlink-privilege skip.
  - **Operational evidence**: isolated Chapter 357 review rebuild on Text Revision `714` confirmed the repaired boundary `... làm được điều này,` / `chỉ cần ta bố trí một phen thì cửa hàng rất khó phát hiện.` with no plan approval and no TTS render.

- **Task 11D1 - Unified production workflow operator entry point**: Added one guarded local workflow that composes Task 11B1 submit/watch/resume behavior, Task 11B2 manifest generation, Task 11C1 objective audio QA, and Task 11C2 deterministic listening checklist output.
  - **Workflow core**: `story_audio/production_workflow.py` orchestrates preflight, guarded runner execution, manifest validation, objective QA generation, and listening checklist generation while reusing existing cores instead of shelling into internal CLIs.
  - **Mutation guardrails**: default mode is preflight-only; `--submit` and `--resume` are explicit and mutually exclusive; paused or interrupted jobs do not auto-resume; failed/cancelled/error terminal states stop downstream work.
  - **Completed-job reuse**: an already completed verified job can continue through manifest, QA, and checklist stages without creating a duplicate job.
  - **Structured output**: stdout ends with one final JSON object using schema `story-audio-production-workflow/v1`; progress events are emitted as stderr JSON Lines; downstream identity mismatches fail closed.
  - **Operator entrypoint**: added `scripts/run_production_workflow.py`.
  - **Verification**: focused workflow tests 20/20 pass; related regressions 149/149 pass with 1 skipped; full offline suite 855/855 pass with 1 skipped.
  - **Disposable smoke**: completed-job Chapter 629 workflow smoke passed with manifest SHA-256 `6bb1fb09a37740a8fbebbc8fec648b92d21ec0db2a3f61250386f9fe3df7bdbb`, workflow QA SHA-256 `831b7d021a711ba24cbc715b577ef54d3baf1a5e0aeb4badcb0ac21104712ead`, and checklist SHA-256 `dcec99be33e57daf15983305d8fd5de8b5e9e755832cb7e0ca9b0fac59126f7f`.
  - **Safety boundary**: no automatic QA decision, no regenerate, no accept/reject, no new synthesis logic, and no migration.

- **Task 11C2 - Deterministic listening checklist HTML**: Added an offline operator listening package built from the Task 11B2 production manifest plus the Task 11C1 QA JSON without mutating jobs, segments, artifacts, or databases.
  - **Checklist core**: `story_audio/listening_checklist.py` validates exact manifest/QA schema and identity, rejects the canonical live root, re-verifies chapter/segment artifacts by path plus SHA-256, enforces isolated-root relative audio URLs, and emits deterministic UTF-8 HTML.
  - **Deterministic queue**: the package always includes integrity failures, hard-clipping segments, top-risk shortlist items, one representative sample per realized voice, and first/last segment coverage with deterministic dedupe and selection reasons.
  - **Local review workflow**: the HTML includes chapter overview, master/final audio controls, per-segment audio controls, operator checklists, localStorage-scoped progress state, reset action, and browser-only JSON export schema `story-audio-listening-review/v1`.
  - **Safety model**: no CDN, no network calls, no base64 audio, no `eval`, no API mutation routes, and no review import/apply path. Conflicting output and unknown existing package files fail closed.
  - **CLI**: added `scripts/build_listening_checklist.py` as the operator-facing entrypoint.
  - **Verification**: focused listening checklist tests 21/21 pass with 1 privilege-related symlink skip plus a mock symlink rejection test; related regressions 108/108 pass; full offline suite 835/835 pass.
  - **Disposable smoke**: Chapter 629 disposable runtime produced `D:\Youtube\StoryAudioTask11B2Smoke\data\listening\job_2_chapter_629\index.html` with package SHA-256 `6f55fb206eea5f5dc508df7ba4d48e4a847c3a6ee020531f41d44bca07108329`; second unchanged run reused the identical bytes. No source DB/audio mutation occurred.
  - **Migration**: none.

- **Task 11C1 - Objective audio QA reporting**: Added offline QA analysis for completed-job production manifests without mutating jobs, segments, artifacts, or databases.
  - **QA core**: `story_audio/audio_qa.py` reads a `story-audio-production-manifest/v1`, opens SQLite read-only, re-verifies manifest artifacts by SHA-256, validates timeline/segment bindings, and emits deterministic UTF-8 JSON with chapter, segment, and voice-level metrics.
  - **Signal analysis**: FFmpeg/FFprobe plus direct PCM WAV analysis now report duration, sample rate, channels, exact integer PCM support (8/16/24/32-bit), mean/max loudness, full-scale peak evidence, hard-clipping sample count/ratio, longest full-scale run, near-clipping sample count/ratio, and silence spans.
  - **Risk heuristics**: shortlist scoring covers clipping, loudness jumps, long internal silence, context-aware trailing silence, speech-rate outliers, and very long segments while preserving quantitative reasons in the report.
  - **Determinism**: writes are atomic, reread-verified, reused when identical, and fail closed on conflicting existing output. Default report path remains deterministic under the isolated data root.
  - **CLI**: added `scripts/run_audio_qa.py` as the operator-facing offline entrypoint.
  - **Verification**: focused audio QA tests 40/40 pass, related production runner/manifest/API regressions 51/51 pass, operational/live-guard tests 17/17 pass, full offline suite 814/814 pass.
  - **Disposable smoke**: Chapter 629 manifest on `D:\Youtube\StoryAudioTask11B2Smoke` produced deterministic report `job_2_chapter_629_audio_qa.json` with SHA-256 `f1f889e776c2b88d5bad997b75a4438e9b4ab977cf45cf4bbad92138a74b1581`; second unchanged run reused the identical bytes. No source DB/audio mutation occurred.
  - **Migration**: none.

- **Task 11B2 - Production runner monitoring, controlled resume, and final manifest**: Extended the guarded production runner to support exact canonical job selection, structured `--watch` progress, explicit same-job `--resume`, completed-job terminal validation, and final manifest generation.
  - **Runner behavior**: `story_audio/production_runner.py` now resolves one verified existing/new job, refuses hidden auto-resume, blocks active-job resume, keeps `--watch` read-only, and returns structured timeout / operator-interrupt / terminal-validation diagnostics.
  - **Terminal validation**: completed jobs must prove exact segment counts, zero failed/pending/running, continuous sequence coverage, immutable Text Revision and Casting Plan bindings, no open candidate attempts, same-job render ownership, artifact presence, and recomputed SHA-256 integrity.
  - **Historical compatibility**: completed historical jobs with nullable `segments.casting_plan_id` are accepted only when `job_chapter` binding plus immutable snapshot evidence prove the same Casting Plan; this does not relax job/revision/plan ownership checks.
  - **Manifest**: added schema `story-audio-production-manifest/v1` with runtime/job/chapter identity, immutable bindings, terminal counts, artifact metadata, recomputed hashes, and segment integrity summary. Writes are UTF-8, atomic, reread-verified, reused when identical, and fail closed on conflicting existing content.
  - **Verification**: focused runner/API/manifest 51/51 pass, operational/live-guard 17/17 pass, full offline suite 774/774 pass.
  - **Disposable smoke**: isolated completed-job verification on `D:\Youtube\StoryAudioTask11B2Smoke` validated Job 2 / Chapter 629 manifest output, exact Text Revision/Casting Plan bindings, 119/119 verified segments, and expected WAV/timeline/M4A hashes with no authoritative runtime mutation.
  - **Migration**: none.

- **Task 11B1 — Guarded production chapter runner**: Added a production-oriented local runner that defaults to preflight-only mode and only submits with explicit `--submit`.
  - **Runner core**: `story_audio/production_runner.py` validates an absolute isolated data root, rejects the canonical live root, proves API/data-root identity, resolves chapter by book + chapter number, verifies immutable approved Casting Plan bindings, detects duplicate jobs by pinned identity, and returns structured CLI errors including `internal_error` exit `8`.
  - **CLI entrypoint**: `scripts/run_production_chapter.py` exposes the guarded runner without shell-generated JSON.
  - **Read-only API support**: added `GET /api/runtime` for local runtime identity and `GET /api/casting/{casting_plan_id}` for exact-ID Casting Plan fetch needed by the runner.
  - **Unicode safety**: mutating JSON requests are serialized with `ensure_ascii=True` and UTF-8 bytes so operator payloads do not depend on terminal encoding.
  - **Verification**: focused runner/API 36/36 pass, related operational/live-guard 17/17 pass, full offline suite 759/759 pass.
  - **Disposable smoke**: isolated verification runtime confirmed identity/read-only contracts, Chapter 629 duplicate job detection returned `already_completed`, runtime mismatch failed closed with exit `3`, and no real production job was created.
  - **Migration**: none.

- **Task 10 complete — Long Chapter Production Pilot**: Closed the production pilot with evidence only, no application code changes.
  - **Chapter 804 workflow validation** completed on isolated runtime V2: pause/restart/resume, controlled regeneration, A/B review, and Reject workflow all passed; no candidate was accepted; final chapter artifact remained 503.800 s.
  - **Chapter 629 production pilot** completed end-to-end: Character Bible apply, Gemini speaker draft, full editorial review, one corrected attribution, approved immutable Casting Plan #2, three-voice render, and final artifacts verified.
  - **Render result**: Job #2 / JobChapter #2 completed with 119/119 verified segments, duration 824.420 s, and realized voices Ngọc Lan 90 / Đức Trí 26 / Mỹ Duyên 3.
  - **QA result**: objective audio QA package generated, then operator listened to the full chapter and marked `OPERATIONAL_PASS`; no pronunciation, pacing, speaker-switching, clipping, volume, or pause issue justified regeneration.
  - **Evidence runtime**: `D:\Youtube\StoryAudioTask10PilotV2\data` with captures in `D:\Youtube\StoryAudioTask10PilotV2\captures`.
  - **Repository baseline**: Task 10 closeout was verified against `main` at `6fa018076ad7c146b55d05a8c6bf619abd2176f2`; no repo code change was required for that closeout.

- **Manual Casting Draft Character Assignment Fix**: Hybrid API endpoint for preserving manual character assignments by text offsets. The POST `/api/chapters/{chapter_id}/casting/draft` endpoint now supports both offset-based (new authoritative manual mode) and utterance-ID-based (existing auto-draft mode) assignments.
  - **Root cause**: Previous implementation regenerated utterances via `split_utterances()` and matched assignments only by `utterance_id`. UI/manual span IDs did not reliably match regenerated IDs, causing manual assignments to be rejected, ignored, or silently defaulted to narrator.
  - **Offset-based assignments**: Use `start_offset` and `end_offset` to specify character spans within the approved TextRevision. When an authoritative span is split into multiple utterances by the chunker, every child utterance inherits the source `role`, `character_id`, resolved voice, and resolution metadata.
  - **Validation**: XOR constraint (exactly one of utterance_id or offsets required), integer offsets within text bounds, ordered non-overlapping spans, active character validation, role/character_id consistency checks. Invalid requests return clear 400 errors with specific messages.
  - **Coverage behavior**: Partial coverage allowed; uncovered text defaults to narrator. Manual offset mode does not call Gemini.
  - **Backward compatibility**: Existing utterance-ID workflow unchanged. Empty assignments (auto-draft) still supported. Approved Casting Plans remain immutable.
  - **Vietnamese smoke validation**: 750-character "Ngôi Nhà Bỏ Hoang" text, 5 offset-based character dialogue spans (3 An, 2 Bình), uncovered narrator spans. Result: 20 utterances with 10 narrator, 4 An (resolved via book_male → Đức Trí), 6 Bình (resolved via book_female → Mỹ Duyên). Distribution difference from expected 13/3/4 is correct: some submitted dialogue spans split into multiple child utterances, all inheriting character assignment.
  - Test coverage: 723 offline tests passing (13 new offset-based tests in `tests/test_offset_casting.py`).
  - Live DB remained unchanged during isolated smoke testing.

- **Multi-voice Segment Regeneration**: Isolated segment re-synthesis for verified segments without re-running entire jobs. Users can generate candidate attempts using immutable segment snapshots (text, voice, settings), listen to original (active) and candidate side-by-side, then Accept (rebuilds chapter artifacts) or Reject (keeps original). Full attempt history preserved for audit and rollback.
  - `segment_attempts` table tracks active attempt, candidates, rejected attempts, and superseded attempts with timestamps.
  - On first regeneration, system transactionally seeds existing verified output as active Attempt 1, then creates candidate as Attempt 2.
  - POST `/api/segments/{segment_id}/regenerate` validates segment status, job idle state, loads immutable snapshot via `load_segment_synthesis_input()`, synthesizes candidate WAV, and records attempt with status='candidate'.
  - Accept workflow (`/api/segments/{segment_id}/accept-candidate`) rebuilds chapter artifacts with candidate, atomically promotes candidate to active, marks old active as superseded, updates segment pointers, and creates new render directory.
  - Reject workflow (`/api/segments/{segment_id}/reject-candidate`) marks candidate as rejected, retains WAV for audit, does not modify active segment or artifacts.
  - List workflow (`/api/segments/{segment_id}/attempts`) returns active, candidate, and history with legacy state repair for pre-seeding segments.
  - Voice preservation verified: Character An → Đức Trí assignment preserved across regeneration (immutable snapshot guarantees correct voice used).
  - Vietnamese multi-voice pilot passed: Book 19, Chapter 1996, Job 16 with 20/20 segments verified, Ngọc Lan (narrator) / Đức Trí (male An) / Mỹ Duyên (female Bình) voices.
  - Real regeneration smoke: Segment 350 generated candidate (1510ms) from original (1750ms), manual rejection workflow passed, active Attempt 1 preserved.
  - Test coverage: 708 offline tests passing (includes segment regeneration, voice preview, casting/speaker review, migration tests).

### Planned

- **Chapter Output Package for YouTube Auto**: Segment-level timeline.json with speaker labels, timestamps derived from final assembled audio, subtitles.srt with relative timestamps, manifest.json with chapter metadata and artifact references. Real handoff smoke test validation with full chapter render and portable bundle structure.

### Backlog

- Make smoke-title filter more conservative so legitimate book titles containing the word "smoke" are not accidentally hidden.

### Added

- **Task 18AT - Chapter 368 adjacent-segment repair-block candidate**: implemented `audio_repair_blocks`, added migration `0011_audio_repair_blocks.sql`, exposed supported repair-block APIs/UI, and created one live candidate for Segments `665`/`666` on Job `22` / JobChapter `22`.
  - **Code**: repair-block synthesis now reconstructs the authoritative span from Text Revision `736`, enforces adjacent verified segments, rejects stale/mismatched plan pins, reuses the same live job identity, and supports JobChapter-level casting-plan pin fallback when segment rows keep `casting_plan_id = NULL`.
  - **API/UI**: added `POST /api/jobs/{job_id}/repair-blocks`, `GET /api/job-chapters/{job_chapter_id}/repair-blocks`, `POST /api/audio-repair-blocks/{repair_block_id}/reject`, candidate audio, and preview-only original-range audio for A/B review.
  - **Tests**: focused offline tests now cover candidate creation, duplicate reuse, rejection, plan/job mismatch rejection, JobChapter pin fallback, preview generation, UI review labels, migration schema presence, and compatibility with existing segment-regeneration tests.
  - **Live validation**: runtime restarted to schema `11`, backup created at `D:\Youtube\Story Trans And Audio\backups\task_18at_pre_live_candidate_20260719_123323`, and one live candidate `#1` was created for Segments `665`/`666` with `candidate_duration_ms = 15350` and `status = candidate`.
  - **Safety**: no duplicate repair block was created, no accept/reject action was taken, and no job, text revision, speaker draft, casting plan, or voice mutation occurred.
  - **Next task**: Task `18AU` — Human A/B Review of Chapter 368 Segments 665-666 Repair-Block Candidate.
- **Custom Reference Voice Library UI (Complete)**: Global library interface for managing custom reference voices. Logical voice management (create, list, select, deactivate/reactivate), immutable revision upload (multipart audio + transcript), revision history display, exact revision selection (radio buttons + summary), Reference Audio playback (GET `/api/custom-voice-revisions/{id}/audio` with SHA-256 verification), custom Preview Text (optional, max 500 chars, empty uses default), short custom preview support (removed 10s minimum, accepts >0s to 20s), cache isolation by revision + text. Compact standalone Preset Voice Preview restored after UI consolidation. UI usability consolidation eliminates redundant custom preview panel; Custom Voice Library remains single custom-reference workflow. Smoke/test books hidden by default with "Show test data" checkbox. Custom Voice input fields use full-width vertical labels and responsive two-column upload layout. Test coverage: 613 tests passing (3 known pre-existing failures in brittle minified-JavaScript assertions unrelated to changes). Real manual smoke passed: preset preview functional, two revisions uploaded, exact selection works, Reference Audio plays, custom short text synthesis succeeds, cache hit/miss verified. Test isolation verified: live DB unchanged during automated runs. No migration required (schema v6 sufficient). **Work merged into main via PR #2.**

- **Custom Voice Preview**: Immutable custom voice revision preview with exact revision ID, reference audio/transcript integrity verification, content-addressed preview cache, and backward-compatible preset request API.
  - `VoicePreviewService.create_custom()` validates revision metadata, checks SHA-256 integrity for reference audio/transcript, synthesizes preview WAV, and stores in content-addressed cache with atomic manifest.
  - `TtsService.synthesize()` extended with optional `reference_audio_path` and `reference_transcript` parameters for custom-reference synthesis preview (routing validation prevents mixing modes).
  - POST `/api/voice-previews` accepts XOR selector: `voice_id` (preset) or `custom_voice_revision_id` (custom), maps domain exceptions to HTTP 404/400/503 without leaking internal details.
  - Custom Voice Preview UI panel with logical custom voice selector, immutable revision selector, preview button, audio player, and status display. JavaScript converts revision ID to integer and sends exact `custom_voice_revision_id` (no `voice_type` or `preview_text`).
  - Test coverage: 27 UI contract tests, 16 API integration tests, 29 service tests, 23 TTS tests. Total: 450 tests passing (41.9s).
  - Real VieNeu custom preview smoke not performed; accepted residual risk with comprehensive offline test coverage.
  - Live DB remained unchanged; no migration required.

- **Phase 3B: Immutable voice synthesis snapshots** for preset and custom-reference voices with strict version-1 validation, fail-closed legacy policy, and deterministic retry behavior.
  - `SegmentSynthesisInput` dataclass with 14 immutable snapshot fields including voice provider/model, synthesis settings JSON, text SHA-256, and custom reference audio/transcript integrity.
  - `load_segment_synthesis_input()` validates snapshots before TTS, performs SHA-256 integrity checks, and loads managed-storage reference audio without database lookups.
  - `TtsService.synthesize()` dual API: snapshot-based path (Phase 3B) and temporary legacy path for non-pipeline callers.
  - Pipeline integration: `_process_chapter` loads snapshots once per segment outside retry loop; retry operations preserve all 14 snapshot fields while resetting only wav_path/audio_sha256/duration_ms/verified_at.
  - Test coverage: 92 new tests across snapshot validation (preset 23, custom 20), TTS integration (17), pipeline integration (12), plus updated casting/recovery mocks (20 tests modified). Total: 377 tests passing.
  - Real smoke validation: VieNeu v3turbo preset (1.04s) and custom-reference (4.31s) synthesis in offline mode with integrity failure detection.
  - E2 waiver: Full pipeline/retry smoke deferred due to temporary DB fixture complexity; accepted residual risk with existing mocked integration coverage.
  - Live DB remained at schema version 6; code supports schema version 7.

### Documentation

- Äá»“ng bá»™ README, AGENTS, ROADMAP, NEXT_TASK vÃ  ARCHITECTURE sau khi Long-Chapter Validation hoÃ n táº¥t; sá»­a Ä‘Ã¡nh sá»‘ quy trÃ¬nh README vÃ  gáº¯n nhÃ£n cÃ¡c ghi chÃº kiáº¿n trÃºc lá»‹ch sá»­ chÆ°a/khÃ´ng triá»ƒn khai.

### Added

- **Task 18AT - Chapter 368 adjacent-segment repair-block candidate**: implemented `audio_repair_blocks`, added migration `0011_audio_repair_blocks.sql`, exposed supported repair-block APIs/UI, and created one live candidate for Segments `665`/`666` on Job `22` / JobChapter `22`.
  - **Code**: repair-block synthesis now reconstructs the authoritative span from Text Revision `736`, enforces adjacent verified segments, rejects stale/mismatched plan pins, reuses the same live job identity, and supports JobChapter-level casting-plan pin fallback when segment rows keep `casting_plan_id = NULL`.
  - **API/UI**: added `POST /api/jobs/{job_id}/repair-blocks`, `GET /api/job-chapters/{job_chapter_id}/repair-blocks`, `POST /api/audio-repair-blocks/{repair_block_id}/reject`, candidate audio, and preview-only original-range audio for A/B review.
  - **Tests**: focused offline tests now cover candidate creation, duplicate reuse, rejection, plan/job mismatch rejection, JobChapter pin fallback, preview generation, UI review labels, migration schema presence, and compatibility with existing segment-regeneration tests.
  - **Live validation**: runtime restarted to schema `11`, backup created at `D:\Youtube\Story Trans And Audio\backups\task_18at_pre_live_candidate_20260719_123323`, and one live candidate `#1` was created for Segments `665`/`666` with `candidate_duration_ms = 15350` and `status = candidate`.
  - **Safety**: no duplicate repair block was created, no accept/reject action was taken, and no job, text revision, speaker draft, casting plan, or voice mutation occurred.
  - **Next task**: Task `18AU` — Human A/B Review of Chapter 368 Segments 665-666 Repair-Block Candidate.
- Speaker Assignment Review UI trong Character Voices vá»›i draft selector, confidence/needs-review filters, bulk actions, Gemini alternatives, manual character/narrator/unknown decisions vÃ  effective voice preview.
- Immutable partial approval táº¡o Casting Plan revision má»›i, giá»¯ nguyÃªn assignment ngoÃ i pháº¡m vi Ä‘Ã£ review, há»— trá»£ base-plan compare-and-swap vÃ  deterministic decision fingerprint.
- Approval idempotency theo draft/base/decision identity; exact repeat tráº£ láº¡i plan cÅ©, cÃ²n key trÃ¹ng vá»›i quyáº¿t Ä‘á»‹nh khÃ¡c bá»‹ tá»« chá»‘i.
- Stale protection cho TextRevision, Character Bible fingerprint vÃ  confirmed Casting Plan context; draft cÅ© váº«n Ä‘á»c Ä‘Æ°á»£c Ä‘á»ƒ audit.
- Doctor kiá»ƒm tra review metadata liÃªn káº¿t Ä‘Ãºng draft/chapter/base plan, fingerprint vÃ  idempotency identity.
- Gemini Speaker Assignment Draft Core vá»›i deterministic utterance selection, context trÆ°á»›c/sau, Character Bible candidates vÃ  confirmed casting context.
- Structured response `story-audio-speaker-assignment-draft/v1` gá»“m candidate, confidence, alternatives, concise reason, confidence level vÃ  `needs_review=true`.
- Migration `0005_speaker_assignment_drafts` lÆ°u immutable draft index; payload náº±m trong content-addressed JSON blob, khÃ´ng náº±m trong Casting Plan.
- Shared Gemini Cache há»— trá»£ task `speaker_assignment`, validate payload á»Ÿ cáº£ miss/hit vÃ  coi cache há»ng lÃ  safe miss.
- API POST/GET vÃ  CLI `scripts/speaker_assignment_draft.py`; Doctor kiá»ƒm tra ownership, schema, hash, fingerprint vÃ  character references.
- Prompt boundary tÃ¡ch system instruction khá»i untrusted chapter/alias/Character Bible data vÃ  cáº¥m táº¡o character má»›i hoáº·c suy luáº­n tá»« voice.

- Character Bible JSON importer for `story-audio-character-bible/v1` with CLI dry-run/apply and structured backend dry-run/apply API.
- Character Bible UI in the casting panel with JSON file selection, dry-run plan preview, apply action, conflict blocking and import summary.
- Custom Reference Voice API and Global Repository. Immutable custom voice revisions and atomic content-addressed audio/transcript storage.
- Character Manager metadata editor for canonical identity, aliases, gender, role, age group, description, speech style, visual notes, notes and import provenance display.
- Migration `0004_character_bible` adds queryable character identity fields, aliases, role/age metadata and import provenance without storing full JSON in SQLite.
- Deterministic matching by external key, canonical name and unique alias, with conflict detection and idempotent re-import.
- Doctor checks for duplicate external keys, orphan aliases, alias/book mismatch and invalid Character Bible enums.

- Book Voice Profile vá»›i narrator, male dialogue, female dialogue vÃ  configurable unknown fallback.
- Optional character voice override, manual gender metadata vÃ  deterministic voice resolver cÃ³ resolution source/needs-review.
- Minimal profile/override/resolve API Ä‘á»ƒ chuáº©n bá»‹ cho UI task tiáº¿p theo.
- Book Voice Profile UI vá»›i empty/invalid state, bá»‘n preview slot, fallback policy vÃ  profile version.
- Character Manager há»— trá»£ gender, Use book default/Use custom voice, effective voice vÃ  resolution source.
- Manual Casting hiá»ƒn thá»‹ resolved voice, gender vÃ  needs-review; preview resolution read-only khÃ´ng táº¡o plan/job.

### Changed

- Speaker assignment prompt tÄƒng lÃªn `speaker-assignment-v2` vÃ  yÃªu cáº§u alternatives khi cÃ²n candidate há»£p lá»‡; cache identity thay Ä‘á»•i theo prompt version.
- Manual Casting há»— trá»£ explicit `Unknown`; approval khÃ´ng tá»± táº¡o job, audio hoáº·c sá»­a Book Voice Profile/Character Bible.
- Casting plan/job má»›i snapshot resolved preset, resolution source vÃ  Book Voice Profile ID/version; retry tiáº¿p tá»¥c dÃ¹ng snapshot cÅ©.
- Custom voices are now managed at the Global Library level rather than book-level to maximize reusability across projects.
- Migration `0003_three_voice_profile` báº£o toÃ n `characters.default_voice_id` vÃ  sao chÃ©p giÃ¡ trá»‹ cÅ© thÃ nh legacy override.
- Segment timeline má»›i mang resolution source, resolved gender, needs-review vÃ  profile ID/version tá»« immutable job snapshot.
- YouTube Auto `character_seed.json` now exports Character Bible canonical metadata, aliases, notes and resolved preset hints; metadata changes produce a new immutable bundle without mutating old exports.

### Verified

- Long-Chapter Validation Phase 2 trÃªn job #6/chapter 56: Casting Plan #8 táº¡o job thá»§ cÃ´ng, VieNeu tháº­t render 210/210 segment verified, final M4A render_0002 dÃ i 752.310 s.
- Long-Chapter Validation Phase 3 trÃªn job #6/chapter 56/artifact #30: export handoff bundle identity `050ac2f2a73bda7b84beb7c1e9bd5b06d9fd3a00773214fa91616c451e8f9280` láº§n Ä‘áº§u táº¡o manifest 752310 ms / 210 utterances / 2 characters; export #2 reused cÃ¹ng identity; legacy bundles `93ff2e0a367a` vÃ  `3255141aa34f` verify/import/reuse Ä‘áº¡t; Story Audio 119 offline tests / Doctor deep `critical_errors=0`; YouTube Auto 96 tests / import 7/7 Ä‘áº¡t.
- 28 isolated API offline tests verify strict boundaries for Custom Voice routes. 244 full suite offline tests and Doctor run clean with Schema v6.
- Phase 2 voice/timing QA: Ngá»c Lan 110, Äá»©c TrÃ­ 56, Má»¹ DuyÃªn 44; 210 utterance sequence liÃªn tá»¥c, final AAC mono 48 kHz, audio sample RMS/peak dÆ°Æ¡ng.
- Phase 2 retry/reuse: `retry_segment` cho segment #247 táº¡o render_0002, 4 segment Ä‘á»‘i chá»©ng giá»¯ nguyÃªn hash/mtime, render_0001 váº«n tá»“n táº¡i vÃ  final cÅ© chuyá»ƒn `stale`.
- Phase 2 immutability: TextRevision #112 hash match, Casting Plan #8 hash match, speaker draft/casting plan khÃ´ng tÄƒng, YouTube Auto khÃ´ng bá»‹ ghi trong Phase 2.
- Long-Chapter Validation Phase 1 trÃªn `Quang Ã‚m Chi Ngoáº¡i` chapter 56: Draft #4 generated 101/101 valid báº±ng Gemini tháº­t, 6 batch, prompt `speaker-assignment-v2`.
- Review UI tháº­t táº¡o plan #7 partial 15 decision vÃ  plan #8 final 86 decision; exact repeat reused plan #8 vá»›i cÃ¹ng decision fingerprint, khÃ´ng táº¡o job/audio.
- Accuracy smoke Phase 1 Ä‘áº¡t 40/40 máº«u thá»§ cÃ´ng; TextRevision #112, Character Bible fingerprint, draft payload hash giá»¯ nguyÃªn; jobs/segments/artifacts váº«n 5/42/24.
- Real Gemini/UI smoke trÃªn book 7/chapter 1985: Draft #3 valid 15/15, 7 high + 8 medium; suggestion, alternative, manual correction, unknown vÃ  skipped rows Ä‘Æ°á»£c review qua hai approval revision.
- Plan #5 partial vÃ  plan #6 final; exact repeat reuse plan #6 vá»›i cÃ¹ng decision fingerprint. Job count giá»¯ nguyÃªn 5 vÃ  khÃ´ng cÃ³ audio má»›i.
- Handoff má»›i export hai láº§n cÃ¹ng identity/reuse; bundle cÅ© vÃ  bundle giÃ u metadata Ä‘á»u verify/import tháº­t láº¡i vÃ o `D:\Youtube\Youtube Auto`.
- 119 offline tests, JavaScript syntax check, schema v5, SQLite quick check vÃ  Doctor deep `critical_errors=0`.
- Real Gemini smoke chapter 1982/utterance `u0001-a99461c9571c`: draft #1 generated, valid 1/1, model `gemini-2.5-flash`; láº§n hai cache hit vÃ  reuse cÃ¹ng fingerprint/content.
- Backup tháº­t trÆ°á»›c migration v5: 4.060 file / 76.112.399 byte, schema v4. Character, casting, job, segment, artifact vÃ  TextRevision tables khÃ´ng Ä‘á»•i sau smoke.

- 94 offline tests pass; schema v4; JavaScript syntax check passes; SQLite quick check and Doctor deep `critical_errors=0`.
- Character Bible smoke on isolated book 5: dry-run creates 3, first apply creates 3/2 aliases, second apply matches 3 with no writes; API character read and voice resolution verified.
- UI contract covers safe metadata rendering for Character Bible import and character cards; handoff regression verifies old bundles stay immutable when metadata changes.
- Jobs #3/#4/#5 casting snapshot hashes stayed unchanged after Character Bible import.

- 78 offline tests, JavaScript syntax check, schema v3, SQLite quick check vÃ  Doctor deep `critical_errors=0`.
- Real VieNeu smoke jobs 4â€“5: profile v1/v2, five resolution paths, controlled retry reuse 7/8 segment vÃ  verified M4A/timeline.

- ThÃªm bá»™ tÃ i liá»‡u Ä‘iá»u hÃ nh, testing, data model vÃ  runbook.
- ThÃªm cÃ´ng cá»¥ cháº©n Ä‘oÃ¡n read-only `scripts/doctor.py`.

### Added

- **Task 18AT - Chapter 368 adjacent-segment repair-block candidate**: implemented `audio_repair_blocks`, added migration `0011_audio_repair_blocks.sql`, exposed supported repair-block APIs/UI, and created one live candidate for Segments `665`/`666` on Job `22` / JobChapter `22`.
  - **Code**: repair-block synthesis now reconstructs the authoritative span from Text Revision `736`, enforces adjacent verified segments, rejects stale/mismatched plan pins, reuses the same live job identity, and supports JobChapter-level casting-plan pin fallback when segment rows keep `casting_plan_id = NULL`.
  - **API/UI**: added `POST /api/jobs/{job_id}/repair-blocks`, `GET /api/job-chapters/{job_chapter_id}/repair-blocks`, `POST /api/audio-repair-blocks/{repair_block_id}/reject`, candidate audio, and preview-only original-range audio for A/B review.
  - **Tests**: focused offline tests now cover candidate creation, duplicate reuse, rejection, plan/job mismatch rejection, JobChapter pin fallback, preview generation, UI review labels, migration schema presence, and compatibility with existing segment-regeneration tests.
  - **Live validation**: runtime restarted to schema `11`, backup created at `D:\Youtube\Story Trans And Audio\backups\task_18at_pre_live_candidate_20260719_123323`, and one live candidate `#1` was created for Segments `665`/`666` with `candidate_duration_ms = 15350` and `status = candidate`.
  - **Safety**: no duplicate repair block was created, no accept/reject action was taken, and no job, text revision, speaker draft, casting plan, or voice mutation occurred.
  - **Next task**: Task `18AU` — Human A/B Review of Chapter 368 Segments 665-666 Repair-Block Candidate.
- Story Audio â†’ YouTube Auto Handoff V1 exporter/verifier cho má»™t completed chapter.
- Bundle báº¥t biáº¿n gá»“m pinned `content.md`, copied narration audio, integer-ms speech timeline, character identity seed vÃ  SHA-256 manifest.
- Doctor kiá»ƒm tra export bundle; backup bao gá»“m `data/exports/youtube_auto`; 7 offline exporter tests.
- Shared Gemini punctuation-repair cache táº¡i `data/cache/gemini_repairs/`, khÃ³a canonical theo source hash, model, prompt, repair contract, block strategy, lexical validator vÃ  output settings.
- Cache manifest atomic trá» tá»›i content-addressed text blobs; cache hit xÃ¡c minh schema/key/hash/character count vÃ  cháº¡y láº¡i lexical validation.
- Cleanup cache máº·c Ä‘á»‹nh dry-run (`scripts/cleanup_gemini_cache.py`), TTL 180 ngÃ y, giá»›i háº¡n 10.000 manifest/256 MiB vÃ  khÃ´ng xÃ³a text blob.
- Doctor shallow/deep bÃ¡o cache manifest há»ng hoáº·c file táº¡m á»Ÿ má»©c warning; 10 fake-Gemini/cache regression tests offline.
- Text Revision Diff tab trong chapter dialog vá»›i preset raw/reflowed/repaired, Inline vÃ  Side-by-side.
- Read-only revision metadata/diff API vá»›i block matching, token/punctuation operations vÃ  lexical integrity summary.
- Whitespace toggle, unchanged collapse/expand, large-payload warning vÃ  explicit 500.000-character limit.
- 12 offline regression tests cho punctuation, whitespace, paragraph, Unicode, blob integrity, XSS vÃ  large text.
- Character manager theo book vÃ  Manual Casting panel trong chapter dialog.
- Immutable content-addressed Casting Plan Revision pin approved TextRevision báº±ng utterance offsets.
- Multi-voice job snapshot, speaker-bounded segments vÃ  timeline speaker metadata.
- Migration `0002_character_voice` cÃ¹ng offline upgrade/backward-compatibility tests.
- Voice Preview cho preset voice vá»›i máº«u Ä‘á»c 10â€“20 giÃ¢y vÃ  audio player ngay táº¡i mÃ n hÃ¬nh táº¡o job.
- Preview cache Ä‘á»™c láº­p táº¡i `data/cache/previews/`, khÃ³a theo voice, text, settings vÃ  engine version.
- Cache integrity verification, tá»± render láº¡i file há»ng vÃ  cleanup policy 30 ngÃ y/tá»‘i Ä‘a 100 entry.
- 5 fake-TTS tests offline; preview khÃ´ng táº¡o database, job hay chapter artifact.
- Diagnostic UI ba cáº¥p cho job, chapter vÃ  segment, gá»“m tráº¡ng thÃ¡i file/hash, lá»—i vÃ  metadata checkpoint.
- Retry action theo chapter hoáº·c segment lá»—i; verified segment Ä‘Æ°á»£c giá»¯ nguyÃªn vÃ  khÃ´ng cho retry trá»±c tiáº¿p.
- 5 offline tests cho aggregation, file corruption diagnostics vÃ  retry invariants.
- Schema migration runner vá»›i báº£ng `schema_migrations`, checksum vÃ  future-version guard.
- Baseline migration `0001_initial` cho cáº£ DB má»›i vÃ  DB 0.1.0 chÆ°a version.
- `scripts/backup.py`: SQLite Online Backup, blobs/output/work vÃ  manifest SHA-256.
- `scripts/restore.py`: verify-only, staging restore, path remap vÃ  overwrite cÃ³ pre-restore copy.
- Shared integrity checker cho doctor vÃ  integration tests.
- Offline integration tests cho legacy migration, restart recovery, retry reuse, cancel, backup/restore vÃ  artifact corruption.

### Changed

- Documented ADR-013 and synchronized README, architecture, runbook, testing and cost-control guidance for the planned Personal Edition three-voice profile; this is an architecture decision only, not an implemented feature.
- Gemini API chá»‰ Ä‘Æ°á»£c gá»i sau khi job checkpoint, approved repaired TextRevision vÃ  shared cache Ä‘á»u khÃ´ng reuse Ä‘Æ°á»£c; cache há»ng trá»Ÿ thÃ nh safe miss.
- Audit phÃ¢n biá»‡t `gemini_cache_hit`, `gemini_cache_miss`, `gemini_cache_invalid`, `gemini_api_call` vÃ  `gemini_checkpoint_reuse` mÃ  khÃ´ng lÆ°u source text/API key.
- Audio assembly dÃ¹ng thÆ° má»¥c `render_<generation>` Ä‘á»ƒ retry khÃ´ng ghi Ä‘Ã¨ artifact verified cÅ©.
- Doctor kiá»ƒm tra schema version, verified segments vÃ  hash blob khi dÃ¹ng `--deep`.
- App tá»« chá»‘i khá»Ÿi Ä‘á»™ng náº¿u DB má»›i hÆ¡n code hoáº·c migration Ä‘Ã£ apply bá»‹ sá»­a checksum.

### Verified

- 67 offline tests Ä‘áº¡t; JavaScript syntax Ä‘áº¡t.
- Live diff API trÃªn chapter 18.649 kÃ½ tá»± hoÃ n thÃ nh khoáº£ng 330 ms vÃ  khÃ´ng tráº£ internal path.
- VieNeu v3 Turbo multi-voice smoke: job 3, 3 preset voices, 8 utterance/segment, M4A 22.810 ms.
- Controlled retry render láº¡i má»™t segment trong 2,47 giÃ¢y vÃ  reuse nguyÃªn hash/mtime cá»§a 7 segment cÃ²n láº¡i.
- Timeline speaker metadata, job voice snapshot, artifact hashes vÃ  duration tolerance 1.000 ms Ä‘á»u Ä‘áº¡t.
- Backup tháº­t 3.989 file / 60.216.155 byte verify Ä‘áº¡t.
- Restore sang data root má»›i remap 13 path vÃ  deep integrity Ä‘áº¡t.

## [2026-06-27] Phase 3A: Job/Casting Snapshot Pinning (Migration 0007)

**Commit**: `7705bc3737644037c701ea87533811d7204b1b44`
**Branch**: `fix/epub-inline-unicode-extraction`

### Added
- `story_audio/pipeline.py` — `_prepare_segments` now pins 14 snapshot columns (from migration 0007) during segment creation.
- `tests/test_voice_snapshot.py` — New offline test suite for snapshot logic with 11 focused isolated tests.

### Changed
- `story_audio/pipeline.py` — Modified `_prepare_segments` to build the full 25-column segments row. Lazily resolves and pins exact custom reference `custom_voice_revision_id`, `reference_audio_sha256`, `reference_audio_storage_key`, `reference_transcript`, and `reference_transcript_sha256`. Also deterministically serializes `synthesis_settings_json`.

### Verified
- 305/305 offline tests pass, including historical legacy migration tests (v2 test fixture regression fixed).
- Doctor confirms code supports schema 7.
- Live database remains schema version 6 and was not migrated (no live DB mutation occurred).

### Notes
- Snapshot persistence is complete (Phase 3A closed).
- Retry does NOT yet consume snapshots (planned for Phase 3B).
- Reference audio is NOT yet passed to VieNeu (planned for Phase 3B).
- Next task is Phase 3B: TTS + Retry Integration.

## [2026-06-27] Resolve custom reference voice assignments

**Commit**: `64c7ea4949b4c5c37b01cc05bb2eddd686691066`
**Branch**: `fix/epub-inline-unicode-extraction`

### Added
- `story_audio/voice_ref.py` — New module. Custom voice logical reference parser (`custom:<id>`), `CustomVoiceContext` catalog, availability check, deterministic latest revision selection, and `resolve_custom_ref` with structured output (kind=`custom_reference`).
- `tests/test_voice_ref.py` — 31 offline tests: `custom:<id>` parsing, context build, resolution, voice profile integration, casting draft integration (preset backward compat + custom narrator + mixed plan), and live DB guard.

### Changed
- `story_audio/casting.py` — `create_casting_draft`, `casting_context`, and validation now accept optional `custom_voice_context: CustomVoiceContext | None`. `_is_allowed_voice` helper added. All preset-only voice checks extended to allow custom references.
- `story_audio/voice_profile.py` — `set_book_voice_profile`, `profile_validation`, `set_character_voice_override`, and `resolve_voice` extended with `custom_voice_context` parameter. `resolve_voice` now returns `custom_reference` kind dict for custom refs.
- `pyproject.toml` — Added `python-multipart>=0.0.18` to declared dependencies.

### Notes
- All preset voice resolution paths are fully backward compatible.
- No migration, no schema change, no live DB access during development.
- Full offline suite: 290/290 pass.

## 0.1.0 â€” 2026-06-23

### Added

- **Task 18AT - Chapter 368 adjacent-segment repair-block candidate**: implemented `audio_repair_blocks`, added migration `0011_audio_repair_blocks.sql`, exposed supported repair-block APIs/UI, and created one live candidate for Segments `665`/`666` on Job `22` / JobChapter `22`.
  - **Code**: repair-block synthesis now reconstructs the authoritative span from Text Revision `736`, enforces adjacent verified segments, rejects stale/mismatched plan pins, reuses the same live job identity, and supports JobChapter-level casting-plan pin fallback when segment rows keep `casting_plan_id = NULL`.
  - **API/UI**: added `POST /api/jobs/{job_id}/repair-blocks`, `GET /api/job-chapters/{job_chapter_id}/repair-blocks`, `POST /api/audio-repair-blocks/{repair_block_id}/reject`, candidate audio, and preview-only original-range audio for A/B review.
  - **Tests**: focused offline tests now cover candidate creation, duplicate reuse, rejection, plan/job mismatch rejection, JobChapter pin fallback, preview generation, UI review labels, migration schema presence, and compatibility with existing segment-regeneration tests.
  - **Live validation**: runtime restarted to schema `11`, backup created at `D:\Youtube\Story Trans And Audio\backups\task_18at_pre_live_candidate_20260719_123323`, and one live candidate `#1` was created for Segments `665`/`666` with `candidate_duration_ms = 15350` and `status = candidate`.
  - **Safety**: no duplicate repair block was created, no accept/reject action was taken, and no job, text revision, speaker draft, casting plan, or voice mutation occurred.
  - **Next task**: Task `18AU` — Human A/B Review of Chapter 368 Segments 665-666 Repair-Block Candidate.
- FastAPI UI/API táº¡i cá»•ng 8766.
- EPUB import cho 1.980 chÆ°Æ¡ng.
- Content-addressed text storage vÃ  TextRevision.
- Gemini punctuation repair theo block vá»›i lexical integrity validation.
- VieNeu v3 Turbo segment worker.
- SQLite checkpoint, pause/resume/cancel/retry.
- Artifact cho master WAV, M4A/MP3 vÃ  timeline.
- Audio player vÃ  cleanup retention.

### Verified

- 8 offline unit tests.
- End-to-end chÆ°Æ¡ng 858, 10 segment, M4A 118.710 ms.
- Resume test giá»¯ 9 segment há»£p lá»‡ vÃ  táº¡o láº¡i má»™t segment lá»—i.`r`n
