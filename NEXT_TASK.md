# Next Task

Current Status:
Task 18AE started and completed the real Chapter `366` production job. Human Audio QA is now the next boundary.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Chapter `367` active approved Text Revision: `734`
- Chapter `367` speaker draft state: exactly one draft, Draft `12`
- Chapter `367` approved Casting Plan: `21` revision `1`, approved at `2026-07-16T08:16:25.730916+00:00`
- Chapter `367` job state: Job `20`, JobChapter `20`, status `completed`, started_at `2026-07-16T08:51:31.019812+00:00`, finished_at `2026-07-16T09:38:49.583451+00:00`
- Chapter `367` downstream production state: Casting Plans `1` approved / `0` draft, jobs `1` completed, job_chapters `1` completed, segments `47` verified / `0` failed / `0` pending, segment attempt counters total `0`, legacy `segment_attempts` rows `0`, repair blocks `0`, artifacts `3` (`1` active), active audio `artifact 75`
- Chapter `366` active approved Text Revision: `3984`, parent `732`, `kind = repaired`, processor `targeted-correction-v1`, content SHA-256 `4febd781f26a50c1a602ad5d14c092f41f472ecddc222d38ad66dfe0bd7ab1e8`, lexical SHA-256 `465273d394e81fc6c72ade75d463c552717db31bff076c4b3e07b70376eae3a6`, char count `6895`
- Chapter `366` text correction: before `"Ăn...Hải Thi tộc...sắp đột phá... đột phá ngay."`; after `"Ăn...Hải Thi tộc...sắp đột phá...đột phá ngay."`; one U+0020 boundary space removed, no lexical token changed
- Chapter `366` boundary validation: quote-span count `8`, utterance count `51`, speaker target count `10`, merged quotation `u0004-c739867fa093` / seq `4` / offsets `364-412`
- Chapter `366` speaker draft state: exactly one current non-stale draft, Draft `13`, `status = generated`, `target_count = 10`, `valid_count = 10`, `invalid_count = 0`, `remaining_unreviewed_count = 0`, `cache_hit_count = 0`, `cache_miss_count = 1`
- Chapter `366` Final Voice Map state: exactly one approved Casting Plan, Plan `22` revision `1`, `status = approved`, `approved_at = 2026-07-16T11:13:12.223006+00:00`, source speaker draft `13`, `text_revision_id = 3984`, `approved_item_count = 10`, `remaining_unreviewed_count = 0`
- Chapter `366` row decisions: merged quote `u0004-c739867fa093` stays `unknown` / `cái bóng`; `u0008`, `u0009`, `u0010`, `u0011`, `u0012`, and `u0043` -> `Lão tổ Kim Cương Tông`; `u0015`, `u0034`, and `u0046` -> `Hứa Thanh`
- Chapter `366` assignment counts: total `51`, narrator `41`, character `9`, unknown `1`, unresolved `0`, effective voices `custom:26 -> 42` and `custom:25 -> 9`
- Chapter `366` production state: Job `21`, JobChapter `21`, status `completed`, started_at `2026-07-16T11:39:58.986729+00:00`, finished_at `2026-07-16T11:53:24.514957+00:00`, active artifact `78`, pinned to Text Revision `3984` and Casting Plan `22` revision `1`
- Chapter `366` downstream state: Casting Plans `0` draft / `1` approved, jobs `1` completed, job_chapters `1` completed, segments `51` verified / `0` failed / `0` pending, segment attempts total `51`, repair blocks `0`, artifacts `3` (`1` active), active audio `artifact 78`
- Segment 573 recovery QA: segment `573`, sequence `20`, utterance `20`, character `Hứa Thanh`, voice `custom:25`, retried once through `POST /api/segments/573/retry`, verified successfully, and then reviewed as audible and complete in the final artifact
- Final audio: `D:\Youtube\Story Trans And Audio\data\output\1-quang-am-chi-ngoai\chapter_0367\job_20\render_0001\chapter.m4a`; SHA-256 `376afa0250cc14ce368e36ff3f9842b8c33139d3ab0250b55f3e6ce92938d808`; file size `6765624` bytes; authoritative/container duration `418180 ms`; independent decoded PCM duration `418197 ms`
- QA findings: chapter start/end complete, narrator `custom:26` stable, all four character utterances use `custom:25`, no punctuation-only utterance, no repeated/missing/reordered sentence, no disruptive voice transition or loudness discontinuity, no clipping or technical corruption, peak approximately `-1.42 dBFS`, RMS approximately `-20.37 dBFS`, longest detected silence approximately `1.03 s`, and no further remediation required

Next Recommended Task:
Task 18AF - Chapter 366 Human Audio QA and Targeted Remediation Review.

Why:
- Chapter `366` now has one completed production render ready for sequential human QA.
- The next safe boundary is listening review, not another render or replacement job.
- Creating another Chapter `366` speaker draft, casting plan, or duplicate job would be a duplicate or premature mutation.

Scope:
1. Re-verify canonical runtime and Chapter `366` completed render state before review.
2. Listen through the completed Chapter `366` audio and check the QA markers.
3. Record any targeted remediation blockers only if a real audio defect is found.
4. Stop before any regeneration or replacement job creation.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not generate another Chapter `366` speaker draft unless Draft `13` is proven absent or invalid.
- Do not create another Casting Plan or approve a different plan.
- Do not create another prepared job during Task `18AF`; only review artifact `78` if all guards pass.
- Do not mutate Chapters `364`, `365`, or `367`.
- Re-verify Git baseline before implementation.
