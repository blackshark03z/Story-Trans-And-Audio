# Next Task

Current Status:
Task 11D3B2 local implementation ready. The next approved engineering slice is Task 11D3B3.

Current Baseline:
- Branch `main`
- Current HEAD = local Task 11D3B2 working tree, pending local commit
- Task 11D2 acceptance evidence runtime: `D:\Youtube\StoryAudioAcceptanceRun1\data`
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Offline baseline last verified for this line of work: 877 tests passing, 1 skipped
- Task 11B2 disposable smoke root: `D:\Youtube\StoryAudioTask11B2Smoke\data`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`

Next Task:
Task 11D3B3 - Casting Review Discoverability and Active-Audio Operator Guidance

Why:
- Task 11D2 has already proved one real isolated chapter can pass the full operator workflow from approved casting through human listening acceptance.
- Task 11D3B1 closed the runtime-identity safety gap, and Task 11D3B2 now makes active chapter output versus historical job evidence explicit.
- The next most valuable slice is to make casting review entry points and operator guidance easier to discover so users can move from chapter selection to speaker review, casting approval, and active-audio verification without ambiguity.

Scope:
1. Improve operator discoverability around Chapter -> Character Voices -> Speaker Review -> Casting approval without changing backend contracts unless a proven UI blocker demands it.
2. Preserve both rollout safety additions already in place: runtime identity gating and active-audio-versus-history labeling.
3. Fix only workflow friction proven by live operator use; avoid speculative architecture work or new synthesis logic.
4. Do not add automatic QA pass/fail decisions, YouTube Auto handoff changes, or background approval behavior.
5. Continue to keep human listening and casting judgment as the final authority.

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
