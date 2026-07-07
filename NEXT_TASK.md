# Next Task

Current Status:
Task 11D3B3 is complete locally on `main` and ready for final push verification. Production remains cleared for rollout (`PRODUCTION_GO`).

Current Baseline:
- Branch `main`
- Current HEAD = `55404fb6aec6b95d071432f5bf9e52c5c2c5c60b`
- Task 11D2 acceptance evidence runtime: `D:\Youtube\StoryAudioAcceptanceRun1\data`
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Offline baseline last verified for this line of work: 879 tests passing, 1 skipped
- Official rollout verdict: `PRODUCTION_GO`
- Second acceptance chapter before rollout: not required
- Task 11B2 disposable smoke root: `D:\Youtube\StoryAudioTask11B2Smoke\data`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Next Task:
Task 11D3B3 Final Push Verification

Why:
- Task 11D3B3 has already been implemented and verified locally: chapter rows now expose `Review Character Voices`, pending draft vs approved casting is labeled directly, Character Voices warns when playback still uses an older active plan, and historical diagnostics link back to the authoritative casting workspace.
- The immediate next step is to verify the exact local commit identity, keep protected untracked paths untouched, and fast-forward push the discoverability/operator-guidance update without changing runtime data.
- Production rollout status remains `PRODUCTION_GO`; this slice is about publishing already-verified operator clarity work, not adding new synthesis or approval behavior.

Scope:
1. Verify the local Task 11D3B3 commit identity and exact file scope before any push.
2. Confirm working tree cleanliness except protected untracked `experiment_b_transcript/` and `runs/`.
3. Fetch `origin`, require a normal fast-forward chain, dry-run `main:main`, then push exactly once without force/rebase/merge/tags.
4. Reconfirm canonical runtime app `8772`, custom voice visibility, and YouTube Auto isolation on `8765` remain unaffected by the push checkpoint.
5. Do not introduce additional code, docs, runtime mutations, or workflow changes during the push step.

Prerequisites For Any Next Task:
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Use `.\run_app.ps1 --host 127.0.0.1 --port 8772 --no-browser` for canonical production startup and verify `GET /api/runtime` before mutating.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local via `run_app.ps1`; do not persist it at user or machine scope.
- Require an explicit isolated `STORY_AUDIO_DATA_DIR` / data root for any new smoke or production-style run.
- Preserve live DB guardrails.
- Do not stop or repurpose port `8765`; it belongs to YouTube Auto.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Re-verify Git baseline before implementation.
- Preserve Chapter 357 acceptance evidence:
  - Text Revision `714`
  - Casting Plan `#6`
  - Job `#2`
  - final M4A under `D:\Youtube\StoryAudioAcceptanceRun1\data\output\1-quang-am-chi-ngoai\chapter_0357\job_2\render_0001\`
