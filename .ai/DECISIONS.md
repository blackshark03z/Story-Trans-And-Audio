# Continuity Decisions

Updated: 2026-07-21 15:38:56 +07:00

## CONT-001 - Real state outranks checkpoint

Git, runtime, database, artifacts, and test output have higher authority than continuity documentation.

Checkpoint files guide takeover, but they do not replace verifying the real state.

## CONT-002 - Compact checkpoint inside repository

`.ai/PROJECT.md`, `.ai/STATE.md`, and `.ai/DECISIONS.md` are the first-read continuity layer for a new Tech Lead.

Detailed documentation and history remain in the existing canonical documentation.

## CONT-003 - Detailed mutable state lives in external capsule

Session/worker details, command logs, worker identity, and interruption recovery live at:

`D:\Youtube_AI_HANDOFFS\Story Audio`

The external capsule does not control strategic direction and does not outrank Git/runtime.

## CONT-004 - Audio Library uses active artifact binding

Audio Library must get chapter output from:

`chapters.active_audio_artifact_id`

It must not select output by newest Job, highest Job ID, or latest completion time.

## CONT-005 - Runtime QA state is displayed as-is

QA state displayed in Audio Library must come from runtime/API/database.

Historical documentation that records Human QA PASS must not be used to auto-upgrade or repair runtime QA state.

Mismatches must be recorded, not fixed in production data during DAILY-PROD-3A.

## CONT-006 - Audio Library is read-only retrieval

Loading, listing, filtering, playback, and download/open-file must not:

- create jobs;
- create previews;
- call provider/TTS;
- modify QA;
- create or replace active artifacts;
- regenerate audio.

## CONT-007 - Chapter 369 remains outside current task

Chapter 369 is a paused production operation.

DAILY-PROD-3A must not approve a plan, prepare a job, render, or create artifacts for Chapter 369.

## CONT-008 - No schema migration without proof and approval

Do not create a migration for Audio Library if the existing schema/API/helpers are sufficient.

If a migration is genuinely required, stop and ask for a decision first.

## References

- `docs/AI_TECH_LEAD_PROTOCOL.md`
- `docs/DECISIONS.md`
- `docs/DATA_MODEL.md`
- `docs/DAILY_PRODUCTION_WORKFLOW.md`
- `ROADMAP.md`
- `PROJECT_STATUS.md`
- `NEXT_TASK.md`
