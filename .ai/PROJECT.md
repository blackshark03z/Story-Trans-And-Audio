# Project

Updated: 2026-07-21 15:38:56 +07:00

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

DAILY-PROD-3 - Audio Library And Output Retrieval

## Current Authorized Task

DAILY-PROD-3A - Audio Library Completed Output List And Playback Entry

## MVP / Milestone Success Criteria

DAILY-PROD-3A is complete when:

- Audio Library lists chapters that have active production audio.
- Each chapter appears exactly once.
- Active audio is identified by `chapters.active_audio_artifact_id`.
- Output is not inferred from newest Job or latest completion time.
- Operator can open or play the active artifact through the existing safe route.
- QA state comes from current runtime/API/database state.
- Browsing the library does not modify artifacts, QA state, or production data.

## In Scope

- Read-only completed/active audio listing.
- Book/chapter identity.
- Current runtime QA state.
- Active artifact playback entry.
- Primary audio download/open-file entry.
- Focused offline tests.

## Out Of Scope / Later

- Chapter 369 casting or production.
- QA state reconciliation from historical documentation.
- Artifact regeneration.
- Targeted remediation.
- Range readiness.
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
