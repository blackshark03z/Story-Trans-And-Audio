# Next Task

Task classification:
SYSTEM_ROADMAP / READY_FOR_IMPLEMENTATION

Active task:
DAILY-PROD-1C - Production Step View Isolation And Action-Hierarchy Closure

Current strategic state:
PRODUCTION_READY / DAILY_PRODUCTION_UX_ROADMAP

Current status:
`DAILY-PROD-1A` added the modular application shell. `DAILY-PROD-1B` added the pure Production state resolver, read-only scope restoration, completed/current/locked stage state, and one dominant primary Production action.

Current baseline for the next task:
- Branch `main`
- DAILY-PROD-1B implementation baseline before code changes: `8ecef8c5e1202818d06e7881435e84e3bdcce640`
- Canonical Story Audio runtime: `http://127.0.0.1:8772`
- Runtime schema: `12`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Completed chapters: `364` artifact `69`, `365` artifact `72`, `366` artifact `78`, `367` artifact `75`, and `368` artifact `84` are documented as `HUMAN_QA_PASS`.
- Chapter `369`: active Text Revision `738`, Speaker Assignment Draft `15` approved, Casting Plan `24` revision `1` draft/unapproved, no Jobs, no JobChapters, no production segments, no production attempts, no artifacts, no active audio, and audio status `not_created`.

Authorized implementation scope:
- Inspect whether `DAILY-PROD-1B` still leaves multiple detailed Production panels expanded at once after the resolver selects a current stage.
- If needed, isolate current-step panels so the resolved current step is the only expanded workflow panel by default.
- Keep completed steps available as read-only summaries.
- Ensure secondary controls do not visually compete with the resolver's one dominant primary action.
- Preserve approval, prepare, start, Human QA, and targeted-regeneration acceptance boundaries.
- Preserve the `#/production?book=<id>&chapter=<id>` restoration model from `DAILY-PROD-1B`.

Do not implement in DAILY-PROD-1C:
- Custom voice assignment closure from `DAILY-PROD-2`.
- Dedicated full Audio Library behavior from `DAILY-PROD-3`.
- Range readiness, exception queues, or batch workflows from later DAILY-PROD milestones.
- Any provider, Gemini, TTS, preview synthesis, production job, audio render, or Chapter `369` production mutation.

Success criteria:
- Production shows one current detailed workflow area by default.
- Completed stages are summarized/collapsible and do not compete with the current action.
- Future-stage mutation controls are not keyboard-focusable before prerequisites are satisfied.
- Chapter `369` remains read-only and continues resolving to Final Voice Map review.

Reference docs:
- `ROADMAP.md`
- `docs/DAILY_PRODUCTION_WORKFLOW.md`
- `docs/DECISIONS.md` ADR-014
