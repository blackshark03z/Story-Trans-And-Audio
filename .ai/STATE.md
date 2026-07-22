# DAILY-PROD Checkpoint State

Updated: 2026-07-22 17:06:00 +07:00

## Current Phase

`DAILY-PROD-5B Phase 4` - Isolated Schema 13 Activation And Request Store Integration Validation.

## Completed Checkpoint

`DAILY-PROD-5B Phase 3` is complete.

- Commit: `e4684905c6e7b3efd23cfef89a7da9dadf0f75e1`
- Subject: `feat: add dormant PREPARE request persistence`
- Dormant migration: `story_audio/migrations/dormant/0013_batch_prepare_requests.sql`
- Durable request store: `story_audio/batch_prepare_store.py`
- Default/latest schema: `12 / 12`
- Dormant proposed schema: `13`
- Migration activation: `MIGRATION_13_IMPLEMENTED_DORMANT`

## Authorization Boundary

Isolated schema-13 activation:

- `AUTHORIZED`

Canonical schema activation:

- `NOT_AUTHORIZED`

PREPARE execution:

- `NOT_AUTHORIZED`

START_RENDER:

- `NOT_AUTHORIZED`

## Phase 3 Acceptance

- Dormant schema-13 migration artifact implemented.
- Routine startup does not auto-discover or auto-apply schema 13.
- `batch_prepare_requests` request identity, uniqueness, state, result, and reconciliation fields implemented.
- Durable create-or-replay behavior implemented.
- Payload conflict detection implemented as deterministic `REQUEST_ID_CONFLICT`.
- Atomic state transitions use guarded compare-and-transition updates.
- Historical APPLIED/REJECTED/FAILED result replay is implemented.
- Stale APPLYING listing is read-only and deterministic by caller-provided cutoff.
- Result payloads are schema-versioned, JSON object only, public-field bounded, and capped at 16 KiB encoded bytes.
- Store does not auto-migrate and does not call `prepare_job`, create Jobs/JobChapters, wake worker, or call providers/TTS/Gemini.

## Validation

- Focused migration/store/affected suite: `133` tests PASS.
- Full offline suite: `1239` tests PASS, `1` skipped.
- Doctor: PASS, `critical_errors=0`, expected warning remains `speaker_assignment_drafts: drafts=15 invalid=9`.
- Canonical runtime: `http://127.0.0.1:8772`
- Runtime schema/latest schema: `12 / 12`
- Canonical DB read-only quick_check: `ok`
- Canonical DB hash: `dba41f6eb3eaba5de4a4d9964f41ee93bb730ac8c2d6fd47df202479ad203b23`
- Canonical DB size: `4009984` bytes
- Canonical DB mtime: `2026-07-20T12:31:47.429225`
- Canonical `batch_prepare_requests` table: absent
- Counts unchanged: speaker drafts `15`, casting plans `23`, jobs `21`, job chapters `21`, segments `688`, artifacts `84`
- Chapter 369 unchanged: active Text Revision `738`, Casting Plan `24` revision `1` draft/unapproved, jobs `0`, artifacts `0`, active audio none, audio status `not_created`

## Current Task

`DAILY-PROD-5B Phase 4` - Isolated Schema 13 Activation And Request Store Integration Validation.

## Next Exact Action

1. Build a production-like temporary schema-12 fixture.
2. Explicitly activate dormant schema 13.
3. Validate restart persistence and historical replay.
4. Validate concurrent request and transition races.
5. Validate stale APPLYING detection and failure recovery.
6. Prove canonical DB remains byte-for-byte unchanged.
7. Stop before canonical activation or execution integration.
