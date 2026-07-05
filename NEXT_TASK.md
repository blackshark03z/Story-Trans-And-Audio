# Next Task

Current Status:
Task 11C1 complete. The next approved engineering slice is Task 11C2.

Current Baseline:
- Branch `main`
- Task 11C1 implementation commit: `9cc41720b7da755dd11302e053573dbb9272cd1a`
- Local HEAD before future push should include the Task 11C1 implementation/docs commits; `origin/main` remains `d825b26cf7c6db278ddda1c44caa7000f48ce265` until a dedicated push checkpoint
- Offline baseline last verified for this line of work: 814 tests passing
- Task 10 evidence runtime: `D:\Youtube\StoryAudioTask10PilotV2\data`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Next Task:
Task 11C2 — Deterministic Listening Checklist HTML

Why:
- Task 11C1 established objective offline QA JSON from completed-job manifests with deterministic clipping/loudness/silence/duration metrics and byte-identical reuse.
- The next operator-facing step is a local listening package that consumes the production manifest plus Task 11C1 QA JSON without mutating jobs, segments, or chapter artifacts.

Scope:
1. Consume the Task 11B2 production manifest plus Task 11C1 QA JSON as authoritative inputs.
2. Generate a local self-contained HTML listening package for human review.
3. Present chapter overview plus prioritized risk samples from the QA shortlist.
4. Include representative narrator/male/female/unknown samples where present.
5. Embed or link local audio controls for chapter and segment review.
6. Add operator review fields/checklist and notes without mutating runtime state.
7. Keep human listening as the final quality authority.
8. Do not add automatic regenerate, Accept, or Reject behavior.

Prerequisites For Any Next Task:
- Preserve the Task 11C1 implementation commit `9cc41720b7da755dd11302e053573dbb9272cd1a`.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Require an explicit isolated `STORY_AUDIO_DATA_DIR` / data root for any new smoke or production-style run.
- Preserve live DB guardrails.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Re-verify Git baseline before implementation.
- Use isolated runtime/data roots for any new smoke or pilot work unless Tech Lead explicitly authorizes another target.
