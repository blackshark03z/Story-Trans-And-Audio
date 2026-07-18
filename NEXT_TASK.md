# Next Task

Current Status:
Task 18AO mapped the Chapter `368` Human QA failure at `02:39-02:47` to Segment `666` / sequence `15` and created exactly one targeted regeneration candidate, Attempt `38`, without accepting it. Active artifact `81` remains unchanged and Chapter `368` is not closed.

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
- Render result before targeted remediation: `49` verified segments, sequence range `1-49`, failed/pending/running segments `0`, repair blocks `0`, narrator `49`, `custom:26 -> 49`, custom voice revision `6 -> 49`
- Active final audio: artifact `81`, `D:\Youtube\Story Trans And Audio\data\output\1-quang-am-chi-ngoai\chapter_0368\job_22\render_0001\chapter.m4a`, SHA-256 `14b106e52a2f1951ffa69633679ee8f1cb6a990dfbc73056fd0c39e4b27045f5`, size `8007414` bytes, authoritative duration `493840 ms`, decoded PCM duration `493845 ms`, AAC mono 48 kHz
- Human QA failure: `TARGETED_REMEDIATION_REQUIRED`, marker `02:39.000-02:47.000`, severe unintelligible speech / đọc không ra tiếng, major severity
- Defective source segment: Segment `666`, sequence `15`, utterance ID `u0015-4257cca30835`, source offsets `2473-2488`, timeline `02:35.860-02:45.530`, exact text `phải rung động.`, narrator `custom:26`, custom voice revision `6`
- Root cause: `SOURCE_SYNTHESIS_UNINTELLIGIBLE`; source WAV `000015.wav` itself is defective/abnormal for the short utterance. The marker crosses into Segment `667` for `1470 ms`, but Segment `667` overlap was not selected for regeneration.
- Original active attempt: Attempt `37`, status `active`, SHA-256 `28b3a912a538338e0af84fc4499c15c52f32252538af624c8370d5cfc0a89f4e`, duration `9670 ms`
- Pending candidate: Attempt `38`, status `candidate`, path `D:\Youtube\Story Trans And Audio\data\work\job_22\chapter_0368\segments\segment_666_attempt_2.wav`, SHA-256 `26721277a58ea5026f4e7b49e941840b1d3ee2b096ec9d04066adfbf3f4371d6`, duration `2150 ms`, mono 48 kHz, peak about `-7.29 dBFS`, RMS about `-20.45 dBFS`, clipped samples `0`
- A/B readiness: `/api/segments/666/attempts` exposes active Attempt `37` and candidate Attempt `38`; UI has separate Accept and Reject actions. Neither action has been clicked, and no reassembly has occurred.
- Active artifact safety: artifact `81` remains active and unchanged with SHA-256 `14b106e52a2f1951ffa69633679ee8f1cb6a990dfbc73056fd0c39e4b27045f5`; active final M4A has not been replaced
- Technical audio checks: peak about `-0.97 dBFS`, mean volume about `-19.5 dB`, clipped samples `0`, longest detected silence about `0.985 s` at `06:21.47`, no decode corruption detected
- Human QA markers for the next task: seq `1` / segment `652` / `00:00.00` start; seq `7` / segment `658` / `01:02.90` longest; seq `13` / segment `664` / `02:05.88` duration outlier; seq `14` / segment `665` / `02:21.39` punctuation-heavy terminology; seq `15` / segment `666` / `02:35.86` quietest; seq `27` / segment `678` / `04:31.58` loudest; seq `32` / segment `683` / `05:17.05` shortest; seq `38` / segment `689` / `06:07.71` scene transition and longest-silence window; seq `49` / segment `700` / `08:04.40` ending
- Chapter `368` execution state: active audio artifact `81`, audio status `completed`, no retry/regeneration after completion, no replacement job
- Pre-start backup for Task 18AM: `D:\Youtube\Story Trans And Audio\backups\task18am_pre_ch368_start_20260718T174859Z.sqlite3`, size `3870720` bytes, SHA-256 `dfe5e1657228a01c2c0ef3e644a5a5314cd4699b6c18f49a302415d7078b811b`, quick_check `ok`
- Future observations that must remain untouched: Chapter `369` and Chapter `370` have text-remediation observations

Next Recommended Task:
Task 18AP - Human A/B Review of Chapter 368 Targeted Regeneration Candidate.

Why:
- Chapter `368` has a pending targeted candidate for the confirmed Human QA defect.
- The next safe workflow boundary is Human A/B listening of original Attempt `37` versus candidate Attempt `38`; technical validation alone is not acceptance.

Scope:
1. Re-verify canonical runtime, repository baseline, Chapter `368`, Segment `666`, active Attempt `37`, candidate Attempt `38`, and active artifact `81`.
2. Listen A/B to original active audio and candidate audio for Segment `666`, with at least five seconds of context before/after in the chapter.
3. If candidate `38` is better and acceptable, use the supported Accept workflow only once; verify same-job reassembly and new active artifact.
4. If candidate `38` is not acceptable, use the supported Reject workflow or record the precise blocker; do not submit another blind attempt.
5. Do not close Chapter `368` until the repaired artifact is re-reviewed.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not modify Chapters `364`, `365`, `366`, or `367`.
- Do not mutate Chapters `369` or `370`.
- Do not prepare or start another Chapter `368` job.
- Do not submit another regeneration attempt while candidate Attempt `38` is pending.
- Do not accept or reject candidate Attempt `38` without Human A/B listening.
- Do not modify Text Revision `736`, Speaker Draft `14`, Casting Plan `23`, custom voice `26`, or voice revision `6`.
- Do not edit production `data/app.db` directly.
- Re-verify Git baseline before beginning Human A/B review or any candidate action.
