# Project

Updated: 2026-07-22 14:11:49 +07:00

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

DAILY-PROD-5B - Batch Prepare Mutation Contract And Stale-Plan Guard

## MVP / Milestone Success Criteria

DAILY-PROD-5B is complete when:

- The existing single-chapter prepare lifecycle has been inspected.
- A PREPARE-only batch mutation contract is defined.
- The request requires a deterministic batch-plan fingerprint.
- Stale-plan rejection is defined.
- Explicit operator confirmation is mandatory.
- Idempotency, duplicate-request, partial-failure, retry, and per-chapter result behavior are defined.
- The task stops before implementing a mutation endpoint or mutating production data.

## In Scope

- Inspect existing single-job prepare behavior.
- Define PREPARE-only batch request/response contract.
- Define plan fingerprint, stale-plan rejection, explicit confirmation, idempotency, duplicate-request behavior, per-chapter results, partial-failure boundaries, retry behavior, and audit fields.
- Add contract-focused offline tests.

## Out Of Scope / Later

- Chapter 369 casting or production.
- QA state reconciliation from historical documentation.
- Artifact regeneration.
- Targeted remediation.
- Batch mutation endpoints.
- Batch approval, prepare, render, or QA execution.
- Batch execution endpoint implementation.
- Database or runtime mutation.
- New provider or TTS behavior.
- Schema migration, unless proven necessary and approved separately.

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
- Batch mutation remains unauthorized.
- The next task defines a PREPARE-only mutation contract and safety tests. It must stop before implementing an execution endpoint or mutating production data.
- Approval, prepare, and render start remain separate actions.
- Immutable plan/job/artifact history must be preserved.
- Runtime data must not be rewritten to match documentation.
- Protected untracked paths must remain untouched.

## Scope Guard

Do not expand beyond the active milestone/task without direct confirmation from the project owner.
