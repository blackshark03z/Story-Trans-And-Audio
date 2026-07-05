# Next Task

Current Status:
Task 11B2 complete. The next approved engineering slice is Task 11C.

Current Baseline:
- Branch `main`
- Task 11B2 implementation commit: `50a2a397b1626ca8abaa1d1ffab5755fdebf5eac`
- Local HEAD before future push should include the Task 11B2 implementation/docs commits; `origin/main` remains `9e7d8700938f93e4e383e9ba4b19f9bc7d546a52` until a dedicated push checkpoint
- Offline baseline last verified for this line of work: 774 tests passing
- Task 10 evidence runtime: `D:\Youtube\StoryAudioTask10PilotV2\data`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Next Task:
Task 11C — Objective Audio QA and Listening Package

Why:
- Task 11B2 established the guarded operational runner path: exact job identity, explicit watch/resume semantics, completed-job terminal validation, and production manifest generation.
- The next operational step is objective local audio QA that consumes the completed-job manifest without mutating jobs, segments, or chapter artifacts.

Scope:
1. Consume the Task 11B2 production manifest as the authoritative input.
2. Run deterministic FFmpeg/local metrics for whole-chapter and per-segment audio.
3. Rank clipping, loudness, silence, and duration risks without changing audio.
4. Generate a deterministic listening checklist HTML/package for human review.
5. Include representative narrator/male/female/unknown segments in the review set.
6. Keep human listening as the final quality authority.
7. Do not add automatic regenerate, Accept, or Reject behavior.

Prerequisites For Any Next Task:
- Preserve the Task 11B2 implementation commit `50a2a397b1626ca8abaa1d1ffab5755fdebf5eac`.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Require an explicit isolated `STORY_AUDIO_DATA_DIR` / data root for any new smoke or production-style run.
- Preserve live DB guardrails.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Re-verify Git baseline before implementation.
- Use isolated runtime/data roots for any new smoke or pilot work unless Tech Lead explicitly authorizes another target.
