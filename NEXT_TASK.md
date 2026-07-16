# Next Task

Current Status:
Task 18S is complete in canonical production. Chapter `367` now has exactly one speaker-assignment draft ready for operator review: Draft `12`, generated on active approved Text Revision `734`, with `target_count = 4`, `valid_count = 4`, `invalid_count = 0`, and `remaining_unreviewed_count = 4`. No Casting Plan, job, TTS, or audio state exists for Chapter `367`.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Chapter `367` active approved Text Revision: `734`
- Chapter `367` speaker draft state: exactly one draft, Draft `12`
- Chapter `367` downstream production state: Casting Plans `0`, jobs `0`, segments `0`, attempts `0`, artifacts `0`, active audio `none`

Next Recommended Task:
Task 18T - Review Chapter 367 Speaker Assignments and Create an Unapproved Final Voice Map.

Why:
- Chapter `367` now has exactly one canonical speaker draft, and the next workflow boundary is human/operator review rather than regeneration.
- Draft `12` already contains four high-confidence suggestions with no invalid rows, so the next safe step is to review and convert that draft into a single unapproved Casting Plan / Final Voice Map.
- Creating another draft would be a duplicate mutation and is no longer allowed unless Draft `12` is proven absent or invalid.

Scope:
1. Re-verify canonical runtime and Chapter `367` baseline before mutation.
2. Reuse existing speaker draft `12` on Text Revision `734`; do not generate another draft.
3. Review the four draft suggestions row by row and record operator decisions.
4. Create exactly one unapproved Final Voice Map / Casting Plan draft from the reviewed speaker draft.
5. Stop before approval, job preparation, TTS, or audio render.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not generate another Chapter `367` speaker draft unless Draft `12` is proven absent or invalid.
- Do not approve the resulting Casting Plan during Task `18T`.
- Do not create any Chapter `367` job, segment, attempt, artifact, TTS preview, TTS synthesis, or audio output during Task `18T`.
- Keep Chapter `366` deferred and unchanged unless a later explicit targeted-remediation task selects it.
- Re-verify Git baseline before implementation.
