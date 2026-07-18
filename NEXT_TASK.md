# Next Task

Current Status:
Task 18AM explicitly started the existing Chapter `368` narrator-only prepared Job `22` and monitored it to completion. Job `22` and JobChapter `22` are completed, active artifact `81` exists, and the final M4A is ready for human audio QA. No replacement job, manual retry, targeted remediation, text/casting/speaker mutation, or voice mutation was performed.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Completed chapters that must not be mutated:
  - Chapter `364`: `HUMAN_QA_PASS`, active artifact `69`
  - Chapter `365`: `HUMAN_QA_PASS`, active artifact `72`
  - Chapter `366`: `HUMAN_QA_PASS`, active artifact `78`
  - Chapter `367`: `HUMAN_QA_PASS`, active artifact `75`
- Chapter `368`: ID `368`, title `Chương 368`, active approved Text Revision `736`, parent/source Revision `735`, `kind = reflowed`, processor `lossless-reflow-v1`, content SHA-256 `c1e5c935f2df6e411086f87a6ff6c3b03795fe2005382a13cdde1c3376421564`, lexical SHA-256 `f5942c8d31af105fc39c7f0d03c9839d3f534559ee3cd6de56275fb90d230514`, char count `7831`
- Chapter `368` Speaker Assignment Draft: Draft `14`, `status = generated`, `stale = false`, `text_revision_id = 736`, `target_count = 0`, `valid_count = 0`, `invalid_count = 0`, remaining unreviewed `0`, review rows `0`, assignments `[]`, invalid items `[]`, cache hit/miss `0/0`
- Chapter `368` approved Final Voice Map / Casting Plan: Plan `23` revision `1`, `status = approved`, `approved_at = 2026-07-18T17:25:23.067196+00:00`, source speaker draft `14`, plan SHA-256 `493e1f39bd353657f6deee0a9ac1124ae3ad47160d5bf7b1b09657f1de1ee9c0`, assignment count `49`, narrator `49`, character `0`, unknown `0`, unresolved `0`, effective voice counts `custom:26 -> 49`
- Voice readiness: custom voice `26` remains active and resolves to canonical usable revision `6`, audio SHA-256 `b641e84e11583bfcbeb76f9a5615c605656e8151679d1286e8f4743c92218ace`
- Chapter `368` render job: Job `22`, `status = completed`, `created_at = 2026-07-18T17:39:08.259402+00:00`, `started_at = 2026-07-18T17:49:53.137483+00:00`, `finished_at = 2026-07-18T18:00:53.109153+00:00`, `current_stage = done`, `voice_name = custom:26`, `repair_mode = off`, `output_format = m4a`, `skip_completed = true`, `casting_plan_id = 23`
- Chapter `368` JobChapter: JobChapter `22`, `status = completed`, `chapter_id = 368`, `text_revision_id = 736`, `casting_plan_id = 23`, `casting_plan_sha256 = 493e1f39bd353657f6deee0a9ac1124ae3ad47160d5bf7b1b09657f1de1ee9c0`, `artifact_id = 81`, `started_at = 2026-07-18T17:49:53.174496+00:00`, `finished_at = 2026-07-18T18:00:53.085149+00:00`
- Render result: `49` verified segments, sequence range `1-49`, failed/pending/running segments `0`, repair blocks `0`, `segment_attempts` rows `0`, narrator `49`, `custom:26 -> 49`, custom voice revision `6 -> 49`
- Active final audio: artifact `81`, `D:\Youtube\Story Trans And Audio\data\output\1-quang-am-chi-ngoai\chapter_0368\job_22\render_0001\chapter.m4a`, SHA-256 `14b106e52a2f1951ffa69633679ee8f1cb6a990dfbc73056fd0c39e4b27045f5`, size `8007414` bytes, authoritative duration `493840 ms`, decoded PCM duration `493845 ms`, AAC mono 48 kHz
- Technical audio checks: peak about `-0.97 dBFS`, mean volume about `-19.5 dB`, clipped samples `0`, longest detected silence about `0.985 s` at `06:21.47`, no decode corruption detected
- Human QA markers for the next task: seq `1` / segment `652` / `00:00.00` start; seq `7` / segment `658` / `01:02.90` longest; seq `13` / segment `664` / `02:05.88` duration outlier; seq `14` / segment `665` / `02:21.39` punctuation-heavy terminology; seq `15` / segment `666` / `02:35.86` quietest; seq `27` / segment `678` / `04:31.58` loudest; seq `32` / segment `683` / `05:17.05` shortest; seq `38` / segment `689` / `06:07.71` scene transition and longest-silence window; seq `49` / segment `700` / `08:04.40` ending
- Chapter `368` execution state: active audio artifact `81`, audio status `completed`, no retry/regeneration after completion, no replacement job
- Pre-start backup for Task 18AM: `D:\Youtube\Story Trans And Audio\backups\task18am_pre_ch368_start_20260718T174859Z.sqlite3`, size `3870720` bytes, SHA-256 `dfe5e1657228a01c2c0ef3e644a5a5314cd4699b6c18f49a302415d7078b811b`, quick_check `ok`
- Future observations that must remain untouched: Chapter `369` and Chapter `370` have text-remediation observations

Next Recommended Task:
Task 18AN - Chapter 368 Human Audio QA and Targeted Remediation Review.

Why:
- Chapter `368` now has a completed narrator-only render and active artifact `81`.
- The next safe workflow boundary is human audio QA. Any remediation must be based on actual listening findings and use supported targeted remediation only if justified.

Scope:
1. Re-verify canonical runtime, repository baseline, Chapter `368`, completed Job `22`, JobChapter `22`, and active artifact `81`.
2. Listen to the complete final M4A sequentially.
3. Inspect the narrator-only QA markers listed above, including chapter start/end, shortest/longest, loudest/quietest, duration outliers, punctuation-heavy terminology, scene transition, and longest-silence window.
4. If and only if a human-audible issue is found, classify it for targeted remediation without creating a replacement job.
5. If the artifact passes, record `HUMAN_QA_PASS` and close Chapter `368`.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not modify Chapters `364`, `365`, `366`, or `367`.
- Do not mutate Chapters `369` or `370`.
- Do not prepare or start another Chapter `368` job.
- Do not retry/regenerate any segment unless human QA identifies a concrete issue and the supported targeted remediation workflow is explicitly selected.
- Do not modify Text Revision `736`, Speaker Draft `14`, Casting Plan `23`, custom voice `26`, or voice revision `6`.
- Do not edit production `data/app.db` directly.
- Re-verify Git baseline before beginning human QA closeout or remediation.
