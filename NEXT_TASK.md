# Next Task

Task classification:
SYSTEM_ROADMAP / READY_FOR_IMPLEMENTATION

Active task:
DAILY-PROD-2B - Production Casting Selectors And Contextual Voice Return

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-1` is complete, and `DAILY-PROD-2A` has implemented the reusable preset/custom voice catalog and assignment selector foundation. Book Voice Profile and Character Manager assignment controls now consume one read-only catalog, preserve stable `custom:<voice_id>` refs, show effective custom synthesis revision provenance, and keep Voice Library management separate from assignment.

Current baseline for the next task:
- Branch `main`
- DAILY-PROD-2A implementation baseline before code changes: `13e9352d3523e9af5a02dbfe81922129fa8a5218`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema: `12`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Completed chapters: `364` artifact `69`, `365` artifact `72`, `366` artifact `78`, `367` artifact `75`, and `368` artifact `84` are documented as `HUMAN_QA_PASS`.
- Chapter `369`: active Text Revision `738`, Speaker Assignment Draft `15` approved, Casting Plan `24` revision `1` draft/unapproved, no Jobs, no JobChapters, no production segments, no production attempts, no artifacts, no active audio, and audio status `not_created`.

Authorized next subtask scope:
- Continue `DAILY-PROD-2` by making Production casting/voice-map selectors return to the same canonical catalog and provenance model.
- Ensure contextual casting review controls distinguish reusable Book/Character assignment from one-off current-plan review.
- Preserve immutable Casting Plan and job snapshot boundaries: saved reusable voice changes must affect only future plan/job creation, never historical plan/job/audio snapshots.
- Keep Voice Library isolated as the management surface for custom voice creation, reference audio, preferred revisions, and preview generation.
- Keep Chapter `369` deferred unless a future explicit production task authorizes mutation.

Do not begin in this handoff:
- Chapter `369` Casting Plan approval or production mutation.
- Provider, Gemini, TTS, preview synthesis, job preparation/start, render, Human QA, or targeted regeneration.
- Range readiness, exception queues, batch workflows, or Audio Library closure from later DAILY-PROD milestones.

Reference docs:
- `ROADMAP.md`
- `docs/DAILY_PRODUCTION_WORKFLOW.md`
- `docs/DECISIONS.md` ADR-014
