# Project

Updated: 2026-07-22 11:53:06 +07:00

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

DAILY-PROD-5A - Batch Scope Plan And Mutation Safety Contract

## MVP / Milestone Success Criteria

DAILY-PROD-5A is complete when:

- Batch scope planning is defined before mutation.
- Eligibility and exclusions are explicit for each range readiness state.
- Operator confirmation is required before any future batch mutation.
- Idempotency, retry, partial-failure, and recovery behavior are documented.
- Existing single-chapter lifecycle boundaries remain authoritative.
- The task does not approve, prepare, start render, mutate QA, or call providers/TTS.

## In Scope

- Read-only batch scope plan contract.
- Eligibility and exclusion rules based on range readiness.
- Operator confirmation boundary for future batch actions.
- Idempotency, retry, partial-failure, and recovery semantics.
- Documentation and focused tests for the read-only contract, if implementation is authorized.

## Out Of Scope / Later

- Chapter 369 casting or production.
- QA state reconciliation from historical documentation.
- Artifact regeneration.
- Targeted remediation.
- Batch mutation endpoints.
- Batch approval, prepare, render, or QA execution.
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
- Batch mutation is not authorized until the plan contract and safety gates are complete.
- Approval, prepare, and render start remain separate actions.
- Immutable plan/job/artifact history must be preserved.
- Runtime data must not be rewritten to match documentation.
- Protected untracked paths must remain untouched.

## Scope Guard

Do not expand beyond the active milestone/task without direct confirmation from the project owner.
