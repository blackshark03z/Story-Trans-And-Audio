# Next Task

Current Status:
Task 11D1 complete. The next approved engineering slice is Task 11D2.

Current Baseline:
- Branch `main`
- Task 11D1 implementation commit: `8b0d4485301c8aa03ccc447d72ba0991e15c77a1`
- Local HEAD now contains the Task 11D1 implementation commit plus pending documentation update; `origin/main` remains `95662c2d106ed161921c24625bf6fc722d3b61c4` until a dedicated push checkpoint
- Offline baseline last verified for this line of work: 855 tests passing
- Task 10 evidence runtime: `D:\Youtube\StoryAudioTask10PilotV2\data`
- Task 11B2 disposable smoke root: `D:\Youtube\StoryAudioTask11B2Smoke\data`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Next Task:
Task 11D2 - First Production Acceptance Run

Why:
- Task 11D1 has already consolidated production preflight, explicit submit/resume, manifest generation, objective QA, and deterministic listening checklist creation into one guarded operator entry point.
- The next step is to run that unified workflow on one new real chapter and close only the workflow blockers proven by real operator use.

Scope:
1. Run the unified production workflow on one new real isolated chapter.
2. Drive operator review through the generated listening checklist and exported review JSON only as a human aid.
3. Fix only proven workflow blockers discovered during that acceptance run.
4. Do not expand architecture, add new synthesis logic, or add automatic QA pass/fail decisions.
5. Do not start YouTube Auto handoff work yet.

Prerequisites For Any Next Task:
- Preserve the Task 11D1 implementation commit `8b0d4485301c8aa03ccc447d72ba0991e15c77a1`.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Require an explicit isolated `STORY_AUDIO_DATA_DIR` / data root for any new smoke or production-style run.
- Preserve live DB guardrails.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Re-verify Git baseline before implementation.
- Use isolated runtime/data roots for any new smoke or pilot work unless Tech Lead explicitly authorizes another target.
