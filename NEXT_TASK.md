# Next Task

Current Status:
Task 18T is complete in canonical production. Chapter `367` now has exactly one unapproved Final Voice Map draft: Casting Plan `21` revision `1`, created from speaker draft `12` on active approved Text Revision `734`. No job, TTS, or audio state exists for Chapter `367`.

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
- Chapter `367` downstream production state: Casting Plans `1` draft, approved Casting Plans `0`, jobs `0`, segments `0`, attempts `0`, artifacts `0`, active audio `none`

Next Recommended Task:
Task 18U - Inspect and Approve the Existing Chapter 367 Final Voice Map.

Why:
- Chapter `367` now has exactly one canonical speaker draft, and the next workflow boundary is human/operator review rather than regeneration.
- Draft `12` has already been converted into unapproved Casting Plan `21` revision `1`, so the next safe step is operator inspection and approval of that existing draft plan.
- Creating another draft or another plan would be a duplicate mutation and is no longer allowed unless the current draft plan is proven absent or invalid.

Scope:
1. Re-verify canonical runtime and Chapter `367` baseline before mutation.
2. Open the existing unapproved Final Voice Map draft `21` revision `1`.
3. Inspect the reviewed assignments and verify the counts/voices before approval.
4. Approve the existing plan only if it still matches the review decisions and no stale state exists.
5. Stop before job preparation, TTS, or audio render.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not generate another Chapter `367` speaker draft unless Draft `12` is proven absent or invalid.
- Do not create another Casting Plan during Task `18U`.
- Do not create any Chapter `367` job, segment, attempt, artifact, TTS preview, TTS synthesis, or audio output during Task `18U`.
- Keep Chapter `366` deferred and unchanged unless a later explicit targeted-remediation task selects it.
- Re-verify Git baseline before implementation.
