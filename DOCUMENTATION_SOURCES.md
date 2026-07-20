# Documentation Source-of-Truth Policy

**Created:** 2026-06-28
**Updated:** 2026-07-20
**Purpose:** Clarify which sources are authoritative for repository, runtime, roadmap, and task state.
**Status:** Active documentation authority policy.

Some older documents still contain mojibake/encoding debt. Encoding cleanup is a separate bounded documentation-maintenance task, not a feature prerequisite.

## Authority Hierarchy

Use this precedence when sources disagree:

1. Git worktree, Git history, runtime, database, and artifacts determine actual state.
2. `ROADMAP.md` defines strategic direction, current system milestone, and deferred system work.
3. `docs/DAILY_PRODUCTION_WORKFLOW.md` defines the target operator workflow and Daily Production UX acceptance direction.
4. `PROJECT_STATUS.md` gives the concise last verified product/runtime state and known blockers.
5. `NEXT_TASK.md` gives one executable next action and must directly support the current roadmap milestone or an explicitly requested production operation.
6. `CHANGELOG.md` is chronological behavior/schema/operations history only.
7. `docs/DECISIONS.md` and `docs/DATA_MODEL.md` define stable architectural invariants and entity/state semantics.
8. `ARCHITECTURE.md` describes component boundaries and may include clearly labelled historical design notes.
9. `README.md` and `docs/RUNBOOK.md` provide operator setup and supported usage.
10. External ACTIVE_TASK handoff capsules are mutable worker/session state, never strategic direction.

`NEXT_TASK.md` may not silently redefine `ROADMAP.md`.

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

### PROJECT_STATUS.md

- Authoritative for the last verified product/runtime state and known blockers.
- Not authoritative for current HEAD or working tree without fresh Git verification.
- Long task records are historical evidence unless repeated in the current-state summary.

### docs/DAILY_PRODUCTION_WORKFLOW.md

- Authoritative for the target daily-production operator experience and `DAILY-PROD` UX acceptance criteria.
- Not authoritative for actual implemented behavior until the corresponding roadmap milestone is complete.
- Does not override backend state machines, database migrations, or runtime safety guards.

### NEXT_TASK.md

- Authoritative for one currently authorized operation or decision checkpoint only when it conforms to `ROADMAP.md`.
- Not authoritative for strategic direction by itself.
- Must state task classification.

### CHANGELOG.md

- Chronological behavior, schema, and operational history.
- Not a task queue or strategic roadmap.

### AGENTS.md

- Quick-start guide for AI agents and engineers: reading order, invariants, commands, and Definition of Done.
- Not authoritative for current HEAD, current schema, or current task.

### README.md And docs/RUNBOOK.md

- Operator setup and supported usage.
- Should point to `ROADMAP.md` for strategy and `NEXT_TASK.md` for the authorized operation.

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
2. Read `ROADMAP.md`.
3. Read the current summary at the top of `PROJECT_STATUS.md`.
4. Read `NEXT_TASK.md`.
5. Read `AGENTS.md`.
6. For Daily Production UX work, read `docs/DAILY_PRODUCTION_WORKFLOW.md`.
7. Read relevant sections of `docs/DECISIONS.md`, `docs/DATA_MODEL.md`, `README.md`, `docs/RUNBOOK.md`, and `ARCHITECTURE.md` as needed.
