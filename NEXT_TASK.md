# Next Task

Current Status:
Task 11C2 complete. The next approved engineering slice is Task 11D.

Current Baseline:
- Branch `main`
- Task 11C2 implementation commit: `26b8f50acabed3f5f4a7a8c89e62128469221a1d`
- Local HEAD now contains the Task 11C2 implementation commit plus pending documentation update; `origin/main` remains `940a3d7e1aa7ea36a7b02c4a1602768d260d25f4` until a dedicated push checkpoint
- Offline baseline last verified for this line of work: 835 tests passing
- Task 10 evidence runtime: `D:\Youtube\StoryAudioTask10PilotV2\data`
- Task 11B2 disposable smoke root: `D:\Youtube\StoryAudioTask11B2Smoke\data`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Next Task:
Task 11D - Production Workflow Consolidation and Operator Entry Point

Why:
- Tasks 11B1, 11B2, 11C1, and 11C2 now exist as separate guarded operator tools: production submit/watch/resume, deterministic manifest generation, objective QA JSON, and deterministic listening checklist HTML.
- The next step is to consolidate those slices into one clear operator entry point without changing synthesis semantics or taking quality decisions away from the human reviewer.

Scope:
1. Compose Task 11B1 + 11B2 + 11C1 + 11C2 into one operator workflow with explicit checkpoints and machine-readable outputs.
2. Provide one guarded entry point that can preflight, watch, emit manifest, run objective QA, and build the local listening checklist in sequence.
3. Keep every mutating step explicit and isolated; do not add hidden auto-resume, auto-regenerate, or review import/apply behavior.
4. Keep objective QA and listening checklist advisory only; human listening remains final authority.
5. Do not add new synthesis logic, new casting logic, or YouTube Auto handoff work in this slice.

Prerequisites For Any Next Task:
- Preserve the Task 11C2 implementation commit `26b8f50acabed3f5f4a7a8c89e62128469221a1d`.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Require an explicit isolated `STORY_AUDIO_DATA_DIR` / data root for any new smoke or production-style run.
- Preserve live DB guardrails.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Re-verify Git baseline before implementation.
- Use isolated runtime/data roots for any new smoke or pilot work unless Tech Lead explicitly authorizes another target.
