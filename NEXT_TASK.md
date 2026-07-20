# Next Task

Task classification:
SYSTEM_ROADMAP / READY_FOR_IMPLEMENTATION

Active milestone:
DAILY-PROD-3 - Audio Library And Output Retrieval

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-1` and `DAILY-PROD-2` are complete. Production has a modular shell, read-only state resolver, isolated current-step panels, shared preset/custom voice selectors, Final Voice Map catalog provenance, and a bounded contextual Voice Library detour that returns to the originating voice-assignment context without auto-saving or starting production work. The DAILY-PROD-2B2-D1 real-browser closeout fixed the detour activation MutationObserver loop and verified isolated create/upload/return/save, cancel, stale-context rejection, and canonical Chapter 369 read-only return.

Current baseline for the next task:
- Branch `main`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema: `12`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Completed chapters: `364` artifact `69`, `365` artifact `72`, `366` artifact `78`, `367` artifact `75`, and `368` artifact `84` are documented as `HUMAN_QA_PASS`.
- Chapter `369`: active Text Revision `738`, Speaker Assignment Draft `15` approved, Casting Plan `24` revision `1` draft/unapproved, no Jobs, no JobChapters, no production segments, no production attempts, no artifacts, no active audio, and audio status `not_created`.

Authorized next milestone scope:
- Begin `DAILY-PROD-3` by making the Audio Library a useful retrieval surface for completed production output.
- Show completed/active audio in a non-technical list organized around book/chapter and QA state.
- Allow opening/playing the active artifact from Audio Library.
- Provide a clear download/open-file path for the primary production audio.
- Preserve immutable artifact, active-output, Human QA, and targeted-remediation boundaries.

Do not begin in this handoff:
- Chapter `369` Casting Plan approval or production mutation.
- Provider, Gemini, TTS, preview synthesis, job preparation/start, render, Human QA, targeted regeneration, or audio artifact mutation.
- Range readiness, exception queues, batch workflows, batch approval/prepare/render/QA, or multi-chapter production acceptance from later DAILY-PROD milestones.

Exact next task:
`DAILY-PROD-3A` - Audio Library Completed Output List And Playback Entry

Reference docs:
- `ROADMAP.md`
- `docs/DAILY_PRODUCTION_WORKFLOW.md`
- `docs/DECISIONS.md` ADR-014
