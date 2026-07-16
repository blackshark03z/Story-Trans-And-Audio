# Next Task

Current Status:
Task 18AG recorded `HUMAN_QA_PASS` and closed the Chapter `366` production cycle. No remediation, retry, replacement job, or post-completion regeneration is required.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Chapter `365` production state: completed with `HUMAN_QA_PASS`, Job `19`, JobChapter `19`, active artifact `72`
- Chapter `367` production state: completed with `HUMAN_QA_PASS`, Job `20`, JobChapter `20`, active artifact `75`
- Chapter `366` active approved Text Revision: `3984`, parent `732`, `kind = repaired`, processor `targeted-correction-v1`, content SHA-256 `4febd781f26a50c1a602ad5d14c092f41f472ecddc222d38ad66dfe0bd7ab1e8`, lexical SHA-256 `465273d394e81fc6c72ade75d463c552717db31bff076c4b3e07b70376eae3a6`, char count `6895`
- Chapter `366` approved Casting Plan: Plan `22` revision `1`, approved at `2026-07-16T11:13:12.223006+00:00`, source speaker draft `13`, text_revision_id `3984`
- Chapter `366` production state: Job `21`, JobChapter `21`, both `completed`, pinned to Text Revision `3984` and Casting Plan `22` revision `1`
- Chapter `366` active artifact: artifact `78`, final audio `D:\Youtube\Story Trans And Audio\data\output\1-quang-am-chi-ngoai\chapter_0366\job_21\render_0001\chapter.m4a`
- Chapter `366` final audio identity: SHA-256 `40014be7dd74a147cdd3c5c8029b2807a1cb0851b02cbab563e7ea823bcb4793`, file size `7082686` bytes, container duration `431020 ms`, independent decoded PCM duration `431040 ms`
- Chapter `366` downstream state: segments `51` verified / `0` failed / `0` pending, attempts/retries `0`, repair blocks `0`, no replacement job
- Chapter `366` Human Audio QA: complete final artifact reviewed sequentially; start/end complete; all `51` segments in sequence; no repeated, missing, or reordered sentence; corrected quotation rendered as one complete utterance; no punctuation-only utterance; no clipping, corruption, excessive silence, loudness discontinuity, or assembly failure
- Chapter `366` speaker/voice QA: narrator `custom:26`; named Hứa Thanh and Lão tổ Kim Cương Tông targets `custom:25`; anonymous `u0004-c739867fa093` remains anonymous/unknown with `custom:26`; all ten speaker targets checked
- Chapter `366` technical QA: integrated loudness approximately `-20.3 LUFS`, LRA `4.8 LU`, true peak `-0.1 dBFS`, decoded RMS `-19.85 dBFS`, clipped samples `0`, longest silence `1.08 s`, leading silence `140 ms`, trailing silence `280 ms`
- Completed chapter safety: Chapters `364`, `365`, `366`, and `367` must not be mutated by the next inspection task

Next Recommended Task:
Task 18AH - Inspect the Next Sequential Production Chapter Beginning at Chapter 368.

Why:
- Chapter `366` is now production-complete and accepted by Human Audio QA.
- Chapters `365`, `366`, and `367` are closed production artifacts, and Chapter `364` must remain untouched.
- The next safe routine boundary is to inspect the next sequential chapter beginning at Chapter `368`, not to reopen or regenerate completed chapters.

Scope:
1. Re-verify canonical runtime and repository baseline.
2. Inspect Chapter `368` readiness/state and surrounding sequential context.
3. Determine the next safe canonical production step without beginning render work unless the task explicitly authorizes it.
4. Preserve protected directories and completed chapters.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not regenerate, retry, or replace Chapter `366` audio.
- Do not modify Text Revision `3984`, Casting Plan `22`, speaker draft `13`, characters, voices, segments, attempts, artifacts, or active audio state.
- Do not mutate Chapters `364`, `365`, `366`, or `367`.
- Re-verify Git baseline before implementation.
