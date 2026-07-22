# Project

Updated: 2026-07-22 21:00:56 +07:00

## Product Goal

Story Audio is a local application that turns approved chapter text into production chapter audio, with immutable text/casting/voice snapshots, segment checkpoints, active audio artifacts, QA, and YouTube Auto Handoff.

## Target User

Local operator producing story chapter audio day to day.

## Current Product Direction

Modular Daily Production UX includes:

- Home
- Production
- Voice Library
- Books And Characters
- Audio Library
- Settings

Production must remain a sequential state-driven workflow with one primary next action.

## Current Strategic Milestone

DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout

## Current Authorized Task

DAILY-PROD-5B Phase 10 - Isolated End-to-End PREPARE Adapter Assembly And Recovery Acceptance

## MVP / Milestone Success Criteria

DAILY-PROD-5B Phases 1-9 are complete. Phase 10 is complete when the accepted isolated components are assembled behind the orchestrator on disposable schema-15 databases with durable terminal-result and restart acceptance:

- Orchestrator and owner-fenced transaction service are integrated through injection only.
- Durable APPLIED/REJECTED/FAILED result ordering and historical replay are proven.
- Duplicate, stale-plan, fencing, response-loss, rollback, ambiguous-outcome, and restart paths are fail-closed.
- No canonical migration, runtime orchestration wiring, API/UI execution path, production Job/JobChapter creation, worker wake, provider/Gemini/TTS call, or START_RENDER integration is implemented.

## In Scope

- Assemble existing isolated request/orchestrator/transaction/linkage/result modules.
- Use explicit dormant schema 12 -> 15 only on temporary databases.
- Prove durable terminal results, replay, concurrency, fencing, stale-plan, failure, response-loss, and restart behavior.

## Out Of Scope / Later

- Chapter 369 casting or production.
- QA state reconciliation from historical documentation.
- Artifact regeneration.
- Targeted remediation.
- Active migration registration or canonical production DB migration.
- Batch mutation endpoints.
- Batch approval, prepare, render, or QA execution.
- Batch execution endpoint implementation.
- Production database or runtime mutation.
- Real Job creation or JobChapter creation.
- Runtime adapter/orchestrator integration.
- Executable batch PREPARE pipeline wiring.
- Behavior-changing production pipeline calls.
- API integration.
- New provider or TTS behavior.
- Canonical schema migration, unless proven necessary and approved separately.

## Technical Context

- Backend: FastAPI
- Database: SQLite
- UI: HTML/CSS/JavaScript
- Test framework: Python unittest
- Authoritative interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`
- Canonical runtime, when running: `http://127.0.0.1:8772`
- Canonical repository: `D:\Youtube\Story Trans And Audio`

## Source Of Truth

1. Git worktree and history.
2. Runtime, database, and artifacts.
3. Verified command/test output.
4. `.ai/STATE.md`.
5. External handoff capsule.
6. Documentation summaries.
7. Assumptions.

## Run And Verify

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
git diff --stat
git diff --check

Invoke-RestMethod http://127.0.0.1:8772/api/runtime

$env:PYTHONUTF8='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' -m unittest discover -s tests -v
node --check ui\app.js
```

## Constraints

- Read-only inspection must not create provider cost, jobs, previews, artifacts, or audio.
- Explicit dormant schema 13-15 activation is authorized only for temporary or isolated databases.
- Canonical production migration remains unauthorized.
- PREPARE execution endpoint remains unauthorized.
- Phase 10 end-to-end adapter assembly is authorized only through dependency injection on isolated/temporary databases.
- Runtime batch PREPARE adapter/orchestrator integration remains unauthorized.
- Canonical schema 13/14 or later activation remains unauthorized.
- START_RENDER remains separate.
- Approval, prepare, and render start remain separate actions.
- Immutable plan/job/artifact history must be preserved.
- Runtime data must not be rewritten to match documentation.
- Protected untracked paths must remain untouched.

## Scope Guard

Do not expand beyond the active milestone/task without direct confirmation from the project owner.
