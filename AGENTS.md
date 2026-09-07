# Story Audio operating map

Story Audio is a local EPUB-to-audio product. Its operator journey is Home →
Production → Audio, with contextual setup and monitoring views returning to the
same selected production scope.

## Working model

Use the Convergent AI Development System (CADS) as an event-routed advisory
standard, not as a lifecycle engine. Keep exactly one active Product Goal and
Critical User Journey (CUJ) in `TASK.md`; internal commits/checkpoints are
evidence, not new phases or completion claims.

Route work by event:

- unclear/new owner outcome -> Product Goal Framing;
- normal bounded implementation -> Goal Execution;
- a user-visible blocker/regression in the active journey -> Systematic Debugging,
  remove the first real blocker, then immediately resume the same CUJ/fixture;
- before `FIXED`, `DONE`, `READY`, or equivalent -> Product Acceptance; and
- after Goal acceptance when residue/worktrees need closure -> Workspace Hygiene.

For user-facing work, conditionally apply the CADS product skills in this order:
`user-facing-workflow.md` when journey/navigation/discoverability is changing,
`frontend-design.md` for visible implementation or material restyling, and
`ui-quality-review.md` before user-facing acceptance or when the Owner reports
that the UI is hard to find, understand, operate, recover, or trust. Then apply
`skills/product/ui-ux-review.md` only as the Story Audio adapter for runtime,
fixture, encoding, and served-asset checks; it is not a parallel UX standard.

For implementation prefer `REUSE -> WIRE -> FIX -> REPLACE_AND_DELETE -> ADD`.
Classify findings only as `BLOCKER` when they prevent the current CUJ/acceptance
or threaten a must-preserve invariant; otherwise record them as `DEFERRED_DEBT`.
Focused tests support a checkpoint but never replace the owner-visible journey.
For a multi-step user-facing Goal, isolated feature/subsystem PASS results must
never be composed into Journey PASS; representative end-to-end CUJ evidence is
required on the supported product surface. For this user-facing product only the
Owner can establish `PRODUCT_ACCEPTED`.

The Owner is not responsible for supplying missing engineering expertise. The AI
Tech Lead must investigate material engineering concerns from the Goal, source,
runtime evidence, and supported operating context; resolve ordinary engineering
choices within established intent; and ask the Owner only for missing product
facts, material trade-offs, or consequential choices that cannot reasonably be
recovered or inferred. Translate technical choices into observable product
consequences, and treat unresolved technical uncertainty as `UNVERIFIED` rather
than asking the Owner to certify engineering facts.

Normal product development remains native: inspect current source, make the
smallest coherent edit, run focused verification, and resume the same acceptance
fixture. Do not reintroduce legacy Build OS lifecycle commands, generations,
leases, adoption, recovery, or record-commit workflows. Historical Build OS
material remains evidence only.

For Story Audio user-facing changes, preserve these project-specific interaction
invariants:

- a mutation may show success only after the authoritative postcondition is
  reconciled; never convert an `APPLIED` transport result into user-visible
  success when the requested voice/scope/state did not actually persist;
- in-place saves, polling and validation refreshes preserve scroll position,
  focus and disclosure state unless navigation is the explicit user action;
- polling/status UI is idempotent and bounded: replace current status in place;
  do not append duplicate progress cards. Explicit history, when useful, lives in
  a bounded scroll region;
- before user-facing acceptance, inspect the rendered owner viewport for UTF-8
  integrity, pathological wrapping, overflow, hierarchy and reachable actions in
  addition to automated browser evidence.

These are Story Audio adapters to CADS User-Facing Workflow / Frontend Design /
UI Quality Review, not changes to the universal CADS Standard.

## Product safety

- The canonical production runtime is `http://127.0.0.1:8772`; its DB is
  `data/app.db` in the owner checkout. Do not touch it incidentally.
- `data/`, `backups/`, `runs/`, and `experiment_b_transcript/` are protected.
  Do not delete, stage, or mutate them without explicit authority.
- Text Revisions, Casting Plans, Jobs, Job snapshots, and verified Artifacts are
  immutable product records. PREPARE and START_RENDER are separate, explicit
  operations. Human Audio QA remains a human decision.
- Offline checks must not call Gemini, VieNeu inference, paid services, or the
  canonical runtime. Never commit, log, or persist secrets.
- Use one writer per worktree. Preserve owner work; do not reset, rebase,
  force-push, or use destructive Git operations.

## Current context

`TASK.md` records the active product objective. `ARCHITECTURE.md` and
`docs/DAILY_PRODUCTION_WORKFLOW.md` define durable product behavior; Git and
tests are the truth for current implementation. `README.md` is the operator and
developer entry point. Treat old `NEXT_TASK.md`, `PROJECT_STATUS.md`, `.ai/`,
and Build OS package material as historical unless a current source verifies it.
