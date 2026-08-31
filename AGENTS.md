# Story Audio operating map

Story Audio is a local EPUB-to-audio product. Its operator journey is Home →
Production → Audio, with contextual setup and monitoring views returning to the
same selected production scope.

## Working model

Normal product development is native: inspect, make a bounded edit, run focused
offline tests, inspect the resulting UI when it changes, and make ordinary Git
commits. The Thin Build OS may be used for a cold-start, a read-only scope check,
or an explicitly consequential boundary; it does not create task lifecycle state.
Do not use or reintroduce legacy Build OS lifecycle commands, generations,
leases, adoption, recovery, or record-commit workflows. Historical Build OS
documents remain evidence only.

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
