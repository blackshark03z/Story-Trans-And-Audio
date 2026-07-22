# Project

Updated: 2026-07-23

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

DAILY-PROD-5B Phase 13 - Clone-Only Disabled Runtime Integration And Operator Authentication Boundary Acceptance

## MVP / Milestone Success Criteria

DAILY-PROD-5B Phases 1-12 are complete. Phase 12 proved clone migration/rollback and a disabled wiring skeleton. Phase 13 is bounded to clone-only disabled runtime integration and operator authentication contract work:

- A verified external clone preserves canonical source provenance and is the only migration target.
- Clone migration proves exact schema 12 -> 15, legacy/protected state, and postflight.
- Clone rollback restores the original clone hash and schema.
- Runtime wiring remains hard-default-off, unreachable, and constructs no mutation service.
- No canonical migration, enabled API/UI mutation, production Job, worker wake, provider/Gemini/TTS, or START_RENDER is authorized.
- Authentication remains `AUTH_MISSING_BLOCKS_PRODUCTION`; local binding is not operator authentication.

## In Scope

- Copy canonical DB read-only to a verified external temporary location.
- Rehearse explicit schema 12 -> 15 and rollback on the clone only.
- Add only an unreachable default-off runtime dependency wiring skeleton and tests.

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
- Runtime PREPARE wiring implementation, canonical activation, production PREPARE execution, API/UI mutation controls, worker wake, and START_RENDER.

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
- Phase 10 end-to-end adapter assembly is complete only through dependency injection on isolated/temporary databases.
- Phase 11 rollout design is complete in commit `bca068e`.
- Phase 12 clone rehearsal and disabled skeleton are complete in implementation commit `843f688`.
- Phase 13 clone-only disabled runtime integration and operator-authentication contract are authorized only within the exact task boundary.
- Production runtime PREPARE implementation remains unauthorized.
- Canonical schema 13/14 or later activation remains unauthorized.
- START_RENDER remains separate.
- Approval, prepare, and render start remain separate actions.
- Immutable plan/job/artifact history must be preserved.
- Runtime data must not be rewritten to match documentation.
- Protected untracked paths must remain untouched.

## Scope Guard

Do not expand beyond the active milestone/task without direct confirmation from the project owner.
