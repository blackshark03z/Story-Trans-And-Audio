# Next Task

Task classification:
SYSTEM_ROADMAP / READY_FOR_IMPLEMENTATION

Active task:
DAILY-PROD-1B - Production State Resolver And Resume Behavior

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-1A` added the modular static application shell. The next bounded step is to make Production state-driven instead of merely separated into a top-level area.

Current baseline:
- Branch `main`
- DAILY-PROD-1A implementation baseline before code changes: `d1e3bf439aeca43612eead90bfc9a21b70fac39d`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema: `12`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Completed chapters: `364` artifact `69`, `365` artifact `72`, `366` artifact `78`, `367` artifact `75`, and `368` artifact `84` are documented as `HUMAN_QA_PASS`.
- Chapter `369`: active Text Revision `738`, Speaker Assignment Draft `15` approved, Casting Plan `24` revision `1` draft/unapproved, no Jobs, no JobChapters, no production segments, no production attempts, no artifacts, no active audio, and audio status `not_created`.

Authorized implementation scope:
- Inspect the current Production UI state model and persisted API responses.
- Derive the current Production step from real chapter/book/runtime state.
- Present one primary action for the current valid step.
- Lock or hide future steps until their prerequisites are satisfied.
- Summarize completed steps instead of expanding all technical panels at once.
- Preserve route refresh/back/forward behavior from `DAILY-PROD-1A`.
- Preserve approval, prepare, and start boundaries.
- Reuse current backend APIs and persisted production state where possible.
- Route Chapter `369` read-only to its current Final Voice Map review state.

Do not implement in DAILY-PROD-1B:
- Custom voice assignment closure from `DAILY-PROD-2`.
- Dedicated full Audio Library behavior from `DAILY-PROD-3`.
- Complete range readiness and exception queue from `DAILY-PROD-4`.
- Batch approval, prepare, render, and QA closeout from `DAILY-PROD-5`.
- Multi-chapter production acceptance from `DAILY-PROD-6`.

Safety constraints:
- Do not call provider, Gemini, TTS, or preview synthesis during shell acceptance.
- Do not approve Casting Plan `24`.
- Do not create or start a Chapter `369` job.
- Do not create jobs, JobChapters, artifacts, audio, segments, or attempts.
- Do not modify Text Revision `738`, Speaker Draft `15`, Casting Plan `24`, voices, or Chapter `369` production state.
- Do not touch Chapters `364-368`.
- Do not touch `experiment_b_transcript/` or `runs/`.

Success criteria:
- Production derives and displays the correct current step from persisted state.
- Only one primary action is presented for the current valid step.
- Future steps cannot be activated early.
- Completed steps are summarized.
- Reopening or refreshing resumes at the correct step.
- Chapter `369` can be opened read-only and routes to its current Final Voice Map review state.
- Acceptance creates no plan approval, job, render, provider call, TTS call, preview, or audio artifact.

Reference docs:
- `ROADMAP.md`
- `docs/DAILY_PRODUCTION_WORKFLOW.md`
- `docs/DECISIONS.md` ADR-014
