# Documentation Source-of-Truth Policy

**Created:** 2026-06-28
**Updated:** 2026-08-31
**Purpose:** Clarify which sources are authoritative for repository, runtime, roadmap, and task state.
**Status:** Active documentation authority policy.

Some older documents still contain mojibake/encoding debt. Encoding cleanup is a separate bounded documentation-maintenance task, not a feature prerequisite.

## Historical Reconciled Baseline (2026-08-25)

The 2026-08-25 read-only inspection found the canonical runtime stopped, the
canonical database at schema `16`, `PRAGMA quick_check = ok`, and no foreign-key
violations. Artifact `93` is stale historical `needs_fixes` evidence, not a
current QA target. Chapter `372` is bound to active, Human-QA-approved Artifact
`99`; Chapter `373` is bound to active Artifact `96` with Human QA still pending.
No production action is authorized by these historical documentation facts.
Verify live Git/runtime state before relying on any of them.

## Authority Hierarchy

Use this precedence when sources disagree:

1. Git worktree, Git history, runtime, database, and artifacts determine actual state.
2. `TASK.md` records the current bounded product objective and constraints.
3. `AGENTS.md` defines the Thin OS working model and product-safety rules.
4. `ROADMAP.md` defines current product direction and deferred product work.
5. `docs/DAILY_PRODUCTION_WORKFLOW.md` defines the target operator workflow and Daily Production UX acceptance direction.
6. `docs/DECISIONS.md` and `docs/DATA_MODEL.md` define stable architectural invariants and entity/state semantics.
7. `ARCHITECTURE.md` describes component boundaries; `README.md` and `docs/RUNBOOK.md` provide supported usage.
8. `PROJECT_STATUS.md`, `NEXT_TASK.md`, `.ai/`, Build OS packages, and external handoff capsules are historical evidence only.

## Task Classification

- `SYSTEM_ROADMAP`: implementation or hardening that directly advances an active roadmap milestone or explicitly requested reusable system change.
- `PRODUCTION_OPERATION`: operator-directed chapter production, QA, casting, repair, or editorial work.
- `AWAITING_OPERATOR_DECISION`: no work is authorized until the operator chooses a direction.

When a production chapter task is active, `NEXT_TASK.md` must label it as `PRODUCTION_OPERATION`.
When implementation/hardening is active, `NEXT_TASK.md` must label it as `SYSTEM_ROADMAP`.
When no work is authorized, `NEXT_TASK.md` must label it as `AWAITING_OPERATOR_DECISION`.

## Git And Runtime State

Always verify real state directly:

```powershell
git status --branch --short
git log -1 --format="%H %s"
git rev-parse origin/main
Invoke-RestMethod http://127.0.0.1:8772/api/runtime
```

Git commands are authoritative for:

- Current HEAD commit hash.
- Current branch name.
- Working tree state.
- Commit history.

Runtime facts are verified values, not permanent hard-coded truth. The current canonical Story Audio runtime is normally `http://127.0.0.1:8772`, but `/api/runtime` is the source of truth for the running process, data root, DB path, and schema.

## Documentation Roles

### ROADMAP.md

- Authoritative for strategic direction, current system phase, and deferred system work.
- Not authoritative for current Git/runtime/database state.
- Chapter production tasks do not belong here unless they prove a reusable system blocker.

### PROJECT_STATUS.md and NEXT_TASK.md

- Preserved snapshots of earlier runtime/product and Build OS work.
- Not authoritative for current product work, current Git/runtime state, or a new
  worker's instructions.
- They must never be used to revive a retired Build OS lifecycle.

### docs/DAILY_PRODUCTION_WORKFLOW.md

- Authoritative for the target daily-production operator experience and `DAILY-PROD` UX acceptance criteria.
- Not authoritative for actual implemented behavior until the corresponding roadmap milestone is complete.
- Does not override backend state machines, database migrations, or runtime safety guards.

### CHANGELOG.md

- Chronological behavior, schema, and operational history.
- Not a task queue or strategic roadmap.

### AGENTS.md

- Quick-start guide for AI agents and engineers: reading order, invariants, commands, and Definition of Done.
- Not authoritative for current HEAD, current schema, or current task.

### README.md And docs/RUNBOOK.md

- Operator setup and supported usage.
- Should point to `TASK.md` for current product work and `ROADMAP.md` for strategy.

### docs/DECISIONS.md And docs/DATA_MODEL.md

- Stable design decisions and entity/state semantics.
- Runtime/migrations determine the actual current schema version.

### ARCHITECTURE.md

- Component boundaries and data-flow reference.
- Historical design sections must be labelled as historical or planned when they are not current implementation facts.

## External Project Notes And ACTIVE_TASK Capsules

External notes and ACTIVE_TASK capsules are recovery aids and mutable session state. They are not strategic direction and do not outrank repository Git/runtime/live DB state.

Read them only after canonical repository documents and real state have been checked.

## Reading Order For New AI Agents

1. Run Git/runtime verification commands.
2. Read `AGENTS.md`, then `TASK.md`.
3. Read `ARCHITECTURE.md`, `README.md`, and the relevant durable product docs.
4. Read `ROADMAP.md` and `docs/DAILY_PRODUCTION_WORKFLOW.md` for direction and UX acceptance.
5. Consult `PROJECT_STATUS.md`, `NEXT_TASK.md`, or `.ai/` only as labelled historical evidence.
