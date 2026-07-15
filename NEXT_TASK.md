# Next Task

Current Status:
Task 18A and Task 18B are complete on `main`. Chapter 364 is now the completed canonical production pilot after targeted audio remediation and final sequential human review.

Current Baseline:
- Branch `main`
- Current HEAD = `506a7f83a2dd9c555539e36a58f40ff333cf0583`
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Authoritative Chapter 364 Evidence:
- Book: `Quang Âm Chi Ngoại`
- Chapter ID: `364`
- Text Revision: `728`
- Casting Plan: `19` rev `1` approved
- Job: `18` completed
- Active artifact: `69`
- Final audio: `D:\Youtube\Story Trans And Audio\data\output\1-quang-am-chi-ngoai\chapter_0364\job_18\render_0002\chapter_final.m4a`
- SHA-256: `3B9748DE4B1F5E8259B7BB0498A996D53F4E52428B0CB68E4633EA25D66BFDCC`
- Authoritative duration: `363590 ms`
- Independent decoded duration: `363605 ms`
- Human verdict: `HUMAN_QA_PASS`
- Accepted remediation: Segment `498` / seq `42`, candidate attempt `36`
- No other reviewed segment was regenerated

Next Recommended Task:
Task 18C - Select and Prepare the Next Routine Canonical Production Chapter

Why:
- Chapter 364 closes the current pilot loop: canonical production flow, targeted remediation, and final human QA are all now proven on a second real chapter.
- The highest-value next step is to move from pilot validation into routine operation by selecting the next real canonical chapter and preparing it up to review-ready production state without reworking the finished 357/364 evidence.
- This should confirm that the workflow is repeatable chapter-to-chapter, not only recoverable on already-known pilot material.

Scope:
1. Audit canonical production chapters read-only and shortlist the next real candidate with approved text, no conflicting running job, and no ambiguous active output state.
2. Prefer a chapter with clear production value and manageable casting complexity rather than synthetic or already-accepted evidence chapters.
3. Prepare the selected chapter through the existing guided production flow up to casting/voice review readiness.
4. Do not mutate finished evidence chapters 357 or 364 unless a later explicit remediation task requires it.
5. Preserve the Chapter 364 acceptance evidence exactly as recorded above.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Re-verify Git baseline before implementation.
