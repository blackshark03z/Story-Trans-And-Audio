# Next Task

Current Status:
Task 11D2 complete. The next approved engineering slice is Task 11D3.

Current Baseline:
- Branch `main`
- Current HEAD = `origin/main` = `094a8787e29e2d709b302e8f524b3ed56cb383da`
- Task 11D2 acceptance evidence runtime: `D:\Youtube\StoryAudioAcceptanceRun1\data`
- Offline baseline last verified for this line of work: 863 tests passing, 1 skipped
- Task 11B2 disposable smoke root: `D:\Youtube\StoryAudioTask11B2Smoke\data`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Next Task:
Task 11D3 - Second Production Acceptance Run or Production Rollout Readiness Check

Why:
- Task 11D2 has already proved one real isolated chapter can pass the full operator workflow from approved casting through human listening acceptance.
- The next useful slice is either one more real-chapter acceptance to confirm repeatability or a small rollout-readiness audit if the team wants to promote the workflow from pilot to routine operation.

Scope:
1. Choose between a second isolated real-chapter acceptance run and a production rollout readiness pass.
2. Preserve the validated operator workflow: approved casting, explicit submit/resume, manifest, objective QA, and listening checklist.
3. Fix only blockers proven by repeated operator use; avoid speculative architecture work.
4. Do not add automatic QA pass/fail decisions or new synthesis logic.
5. Continue to keep human listening and casting judgment as the final authority.

Prerequisites For Any Next Task:
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Require an explicit isolated `STORY_AUDIO_DATA_DIR` / data root for any new smoke or production-style run.
- Preserve live DB guardrails.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Re-verify Git baseline before implementation.
- Preserve Chapter 357 acceptance evidence:
  - Text Revision `714`
  - Casting Plan `#6`
  - Job `#2`
  - final M4A under `D:\Youtube\StoryAudioAcceptanceRun1\data\output\1-quang-am-chi-ngoai\chapter_0357\job_2\render_0001\`
