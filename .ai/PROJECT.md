# Project

Updated: 2026-07-22 18:17:10 +07:00

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

DAILY-PROD-5B Phase 5 - Isolated PREPARE Orchestration And Reconciliation Contract

## MVP / Milestone Success Criteria

DAILY-PROD-5B Phase 4 is complete. Phase 5 is complete when:

- A pure orchestration contract coordinates request intake, current-plan revalidation, durable create-or-replay, atomic `PLANNED -> APPLYING` ownership, pre-mutation fingerprint revalidation, injected future Job-transaction dependency, durable APPLIED/REJECTED/FAILED recording, ambiguous timeout replay, and stale APPLYING reconciliation.
- Orchestration tests use fakes and temporary or isolated databases only.
- No API route, canonical schema activation, `prepare_job`/`create_job` invocation, real Job/JobChapter creation, UI work, provider/Gemini/TTS call, or START_RENDER integration is implemented.

## In Scope

- Define pure PREPARE orchestration state flow.
- Define request-store, current-plan, and future Job-transaction dependency interfaces.
- Define durable ownership acquisition and pre-mutation fingerprint revalidation.
- Define durable result persistence ordering, timeout replay, stale APPLYING reconciliation, and operator-review outcomes.
- Add pure/offline orchestration tests with fake or isolated dependencies.

## Out Of Scope / Later

- Chapter 369 casting or production.
- QA state reconciliation from historical documentation.
- Artifact regeneration.
- Targeted remediation.
- Canonical production DB migration.
- Batch mutation endpoints.
- Batch approval, prepare, render, or QA execution.
- Batch execution endpoint implementation.
- Production database or runtime mutation.
- Real Job creation or JobChapter creation.
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
- Explicit schema-13 activation is authorized only for temporary or isolated databases.
- Canonical production migration remains unauthorized.
- PREPARE execution endpoint remains unauthorized.
- START_RENDER remains separate.
- Approval, prepare, and render start remain separate actions.
- Immutable plan/job/artifact history must be preserved.
- Runtime data must not be rewritten to match documentation.
- Protected untracked paths must remain untouched.

## Scope Guard

Do not expand beyond the active milestone/task without direct confirmation from the project owner.
