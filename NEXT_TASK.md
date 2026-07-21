# Next Task

Task classification:
SYSTEM_ROADMAP / READY_FOR_IMPLEMENTATION

Active milestone:
DAILY-PROD-4 - Range Readiness And Exception Queue

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-1`, `DAILY-PROD-2`, and `DAILY-PROD-3` are complete. Production has a modular shell, read-only state resolver, isolated current-step panels, shared preset/custom voice selectors, contextual Voice Library detour/return, and a read-only Audio Library for completed active outputs with playback/download.

Current baseline for the next task:
- Branch `main`
- Last verified commit: `85040745081f6b01b84fb3f1d68fcce7c9797ed1`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema: `12`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Audio Library runtime smoke at the UI checkpoint returned `16` items, bad URL count `0`, chapters `364-368` present, and Chapter `369` absent because it has no active audio artifact.
- Runtime QA currently reports chapters `364-367` as `pending` and chapter `368` as `accepted`; display this runtime state as-is.
- Chapter `369`: active Text Revision `738`, Speaker Assignment Draft `15` approved, Casting Plan `24` revision `1` draft/unapproved, no Jobs, no JobChapters, no production segments, no production attempts, no artifacts, no active audio, and audio status `not_created`.

Exact next task:
`DAILY-PROD-4A` - Range Readiness Preflight And Exception Queue Contract

Operator pain:
Operators can now produce one chapter and retrieve completed audio, but they still do not have a safe range-level readiness view that says which chapters can be skipped, which chapters are blocked, and which exact exception queue must be handled before later batch prepare/render work.

Allowed scope:
- Add or refine read-only range preflight contracts needed to evaluate a selected book/chapter range.
- Reuse existing per-chapter production state, active artifact, text, speaker, voice, Casting Plan, prepared-job, render, and QA facts.
- Return a non-technical exception queue grouped by required operator action.
- Include completed/active-output skip decisions.
- Add focused offline tests and documentation for the contract.

Excluded scope:
- Do not approve Speaker Drafts or Casting Plans.
- Do not prepare or start jobs.
- Do not render, regenerate, retry, assemble, or mutate audio/artifacts.
- Do not perform Human QA mutation.
- Do not call provider, Gemini, VieNeu/TTS, or preview synthesis.
- Do not implement batch approval, batch prepare, batch render, or multi-chapter QA closeout.
- Do not resolve Chapter `369` production/editorial work unless a later task explicitly selects it.

Acceptance criteria:
- A selected range can be inspected with read-only APIs/helpers.
- Already completed chapters are identified from active artifact state, not newest-job heuristics.
- Chapters needing text, speaker, voice, Final Voice Map, prepare/start/render/QA, or unresolved-state attention are classified deterministically.
- The exception queue is grouped by operator action and contains enough identity/provenance to open the correct existing workflow step later.
- Passive range inspection performs no mutation and creates no provider cost.
- Focused offline tests pass, `git diff --check` passes, and no protected paths are touched.

Chapter 369 boundary:
Chapter `369` remains paused and unchanged unless explicitly included in a selected range for read-only inspection. Read-only inspection may report its current `CASTING_REVIEW`/unapproved Casting Plan state, but must not approve, prepare, render, or create artifacts.

Reference docs:
- `ROADMAP.md`
- `docs/DAILY_PRODUCTION_WORKFLOW.md`
- `docs/DECISIONS.md` ADR-014
