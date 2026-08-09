# Project

Updated: 2026-07-25

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

DAILY-PROD-6 - Multi-Chapter Production Acceptance

## Current Authorized Task

Human-listen to active Artifacts 93 and 96 for Book 1 Chapters 372-373, then record acceptance or one precise remediation target for each chapter.

## MVP / Milestone Success Criteria

DAILY-PROD-5 is complete. The first normal-UI contiguous two-chapter pilot
completed on Job 26 with one PREPARE request, one explicit START, two completed
JobChapters, 111 verified Segments, zero retries, and active Artifacts 93/96.

The remaining DAILY-PROD-6 acceptance gate is:

- listen through both active artifacts;
- verify narrator/dialogue transitions and complete chapter boundaries;
- record one explicit Human QA decision per artifact;
- do not start a larger batch until both decisions are recorded.

## In Scope

- Human Audio QA for Artifacts 93 and 96.
- One precise remediation target only if a real audible defect is found.
- Final Daily-Use V1 declaration after both artifacts are accepted.

## Out Of Scope / Later

- Chapter 369 casting or production.
- A larger production batch.
- Automatic regeneration, replacement Job creation, or speculative hardening.
- Schema migration or provider/TTS work unless a QA defect later authorizes one
  bounded remediation.

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
- START_RENDER remains separate.
- Approval, prepare, and render start remain separate actions.
- Immutable plan/job/artifact history must be preserved.
- Runtime data must not be rewritten to match documentation.
- Protected untracked paths must remain untouched.
- Jobs 23-25, Artifacts 87/90, Revisions 3971/3985, and Chapter 369 remain
  protected historical state.

## Scope Guard

Do not expand beyond the active milestone/task without direct confirmation from the project owner.
