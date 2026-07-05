# Next Task

Current Status:
Task 11B1 complete. The next approved engineering slice is Task 11B2.

Current Baseline:
- Branch `main`
- Task 11B1 implementation commit: `556023a94670730cafa995aa30d70a389f4a995a`
- Local HEAD before future push should include the Task 11B1 implementation/docs commits; `origin/main` remains `8dd7920ed4641c4423f29f9940a5062bab065c45` until a dedicated push checkpoint
- Offline baseline last verified for this line of work: 759 tests passing
- Task 10 evidence runtime: `D:\Youtube\StoryAudioTask10PilotV2\data`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Next Task:
Task 11B2 — Production Runner Progress, Resume and Final Manifest

Why:
- Task 11B1 established the guarded submit contract: isolated-root enforcement, runtime identity verification, exact Casting Plan readback, Unicode-safe request serialization, duplicate-job protection, immutable binding verification, and structured CLI errors.
- The next operational step is to exercise progress visibility and controlled resume on the same guarded runner path before expanding automation further.

Scope:
1. Identify and report an existing active production-style job under the isolated runtime.
2. Perform a controlled resume of that same job without creating a second parallel job.
3. Capture progress checkpoints and terminal-state evidence from the runner/API.
4. Verify final artifact paths, sizes, and SHA-256 manifest outputs.
5. Stop before objective QA/listening package work.
6. Do not add automatic regenerate/Accept/Reject behavior.

Prerequisites For Any Next Task:
- Preserve the Task 11B1 implementation commit `556023a94670730cafa995aa30d70a389f4a995a`.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Require an explicit isolated `STORY_AUDIO_DATA_DIR` / data root for any new smoke or production-style run.
- Preserve live DB guardrails.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Re-verify Git baseline before implementation.
- Use isolated runtime/data roots for any new smoke or pilot work unless Tech Lead explicitly authorizes another target.
