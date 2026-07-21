# Project

Updated: 2026-07-21 20:50:39 +07:00

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

DAILY-PROD-4 - Range Readiness And Exception Queue

## Current Authorized Task

DAILY-PROD-4A - Range Readiness Preflight And Exception Queue Contract

## MVP / Milestone Success Criteria

DAILY-PROD-4A is complete when:

- Operator can request a read-only chapter range within one book.
- Each chapter appears exactly once with one current readiness state and one next action.
- Exception queue is deterministic and contains only chapters requiring operator action.
- Summary counts match the chapter list and exception queue.
- Active output is identified by `chapters.active_audio_artifact_id`.
- Runtime QA state controls whether rendered audio is pending QA or complete.
- Preflight does not modify production data, jobs, drafts, plans, QA, artifacts, or audio.

## In Scope

- Read-only range readiness endpoint.
- Book/chapter range validation.
- Current runtime QA and active-output pointer semantics.
- Prepared/running/rendered/complete workflow precedence.
- Deterministic exception queue and summary counts.
- Focused and full offline validation.

## Out Of Scope / Later

- Chapter 369 casting or production.
- QA state reconciliation from historical documentation.
- Artifact regeneration.
- Targeted remediation.
- Batch workflow.
- Batch approval, prepare, render, or QA.
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
- Approval, prepare, and render start remain separate actions.
- Immutable plan/job/artifact history must be preserved.
- Runtime data must not be rewritten to match documentation.
- Protected untracked paths must remain untouched.

## Scope Guard

Do not expand beyond the active milestone/task without direct confirmation from the project owner.
