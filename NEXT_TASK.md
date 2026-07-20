# Next Task

Task classification:
SYSTEM_ROADMAP / READY_FOR_IMPLEMENTATION

Active task:
DAILY-PROD-2B2 - Contextual Voice Detour And Return

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-1` is complete. `DAILY-PROD-2A` implemented the reusable preset/custom voice catalog for Book Voice Profile and Character Manager assignment selectors. `DAILY-PROD-2B1` closed the existing Final Voice Map review gap: plan voice usage now derives from the same catalog truth, custom voices show effective revision provenance, unavailable legacy selections are preserved/flagged, unknown fallback remains separate from speaker identity, and loading the review remains read-only.

Current baseline for the next task:
- Branch `main`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema: `12`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Completed chapters: `364` artifact `69`, `365` artifact `72`, `366` artifact `78`, `367` artifact `75`, and `368` artifact `84` are documented as `HUMAN_QA_PASS`.
- Chapter `369`: active Text Revision `738`, Speaker Assignment Draft `15` approved, Casting Plan `24` revision `1` draft/unapproved, no Jobs, no JobChapters, no production segments, no production attempts, no artifacts, no active audio, and audio status `not_created`.

Authorized next subtask scope:
- Continue `DAILY-PROD-2` by implementing the bounded contextual detour:
  - start from a Production voice-assignment context;
  - navigate to Voice Library to create a custom voice and upload/reference a revision through existing supported workflows;
  - return safely to the originating Production scope/context;
  - refresh the read-only voice catalog and make the newly usable voice available for explicit operator selection.
- Preserve immutable Casting Plan, prepared-job, render, artifact, and QA boundaries.
- Keep selection, saving, approval, preparation, and render start as separate explicit actions.

Do not begin in this handoff:
- Chapter `369` Casting Plan approval or production mutation.
- Provider, Gemini, TTS, preview synthesis, job preparation/start, render, Human QA, targeted regeneration, or audio artifact mutation.
- Range readiness, exception queues, batch workflows, or Audio Library closure from later DAILY-PROD milestones.

Reference docs:
- `ROADMAP.md`
- `docs/DAILY_PRODUCTION_WORKFLOW.md`
- `docs/DECISIONS.md` ADR-014
