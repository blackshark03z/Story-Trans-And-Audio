# Next Task

Task classification:
SYSTEM_ROADMAP / READY_FOR_IMPLEMENTATION

Active task:
DAILY-PROD-2 - Custom Voice Assignment UI Closure

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-1` is complete. The app now has isolated top-level areas, a read-only Production state resolver, route/scope resume, completed/current/locked canonical stages, centralized current-stage panel ownership, inactive panel `hidden`/`inert`/ARIA isolation, and one dominant Production action.

Current baseline for the next task:
- Branch `main`
- DAILY-PROD-1C implementation baseline before code changes: `18e6db8fceab032813a675308ed0abb8da01237e`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema: `12`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Completed chapters: `364` artifact `69`, `365` artifact `72`, `366` artifact `78`, `367` artifact `75`, and `368` artifact `84` are documented as `HUMAN_QA_PASS`.
- Chapter `369`: active Text Revision `738`, Speaker Assignment Draft `15` approved, Casting Plan `24` revision `1` draft/unapproved, no Jobs, no JobChapters, no production segments, no production attempts, no artifacts, no active audio, and audio status `not_created`.

Authorized next milestone scope:
- Close the custom voice assignment UI gap from `DAILY-PROD-2`.
- Keep Voice Library, book-level defaults, character overrides, and contextual Production voice readiness coherent.
- Make existing usable custom voices easy to select without breaking immutable Casting Plan and job snapshot boundaries.
- Preserve the current Production stage isolation from `DAILY-PROD-1C`.

Do not begin in this handoff:
- Chapter `369` production mutation or Casting Plan approval.
- Provider, Gemini, TTS, preview synthesis, job preparation/start, render, Human QA, or targeted regeneration.
- Range readiness, exception queues, batch workflows, or Audio Library closure from later DAILY-PROD milestones.

Reference docs:
- `ROADMAP.md`
- `docs/DAILY_PRODUCTION_WORKFLOW.md`
- `docs/DECISIONS.md` ADR-014
