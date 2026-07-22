# Project

Updated: 2026-07-22 19:42:07 +07:00

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

DAILY-PROD-5B Phase 7 - Dormant Request-to-Job Linkage Persistence And Repository Contract

## MVP / Milestone Success Criteria

DAILY-PROD-5B Phase 6 is complete. Phase 7 is complete when:

- A dormant schema artifact defines request-to-Job linkage after schema 13.
- Isolated schema upgrades preserve existing schema-13 PREPARE request records.
- A pure linkage repository enforces one request to at most one Job and one Job to at most one request.
- Linkage records persist versioned transaction evidence, plan fingerprint, chapter snapshot digest, prepared status, and no-worker/no-render evidence.
- Create/replay/conflict lookup is deterministic under concurrency.
- No active migration registration, canonical schema activation, pipeline integration, real Job/JobChapter creation, API route, UI work, provider/Gemini/TTS call, PREPARE execution, or START_RENDER integration is implemented.

## In Scope

- Inspect dormant migration conventions.
- Create a dormant request-to-Job linkage migration after schema 13.
- Create pure linkage repository/store code.
- Enforce unique request identity and unique Job relation for linkage records.
- Persist bounded transaction-evidence metadata.
- Add isolated migration, repository, concurrency, rollback, and canonical path protection tests using temporary databases only.

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
- Real adapter implementation.
- Pipeline integration.
- Pipeline calls.
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
- Explicit schema-13 activation is authorized only for temporary or isolated databases.
- Canonical production migration remains unauthorized.
- PREPARE execution endpoint remains unauthorized.
- Real Job transaction adapter implementation remains unauthorized.
- Dormant request-to-Job linkage persistence is authorized only for isolated/temporary databases.
- Linkage pipeline integration remains unauthorized.
- START_RENDER remains separate.
- Approval, prepare, and render start remain separate actions.
- Immutable plan/job/artifact history must be preserved.
- Runtime data must not be rewritten to match documentation.
- Protected untracked paths must remain untouched.

## Scope Guard

Do not expand beyond the active milestone/task without direct confirmation from the project owner.
