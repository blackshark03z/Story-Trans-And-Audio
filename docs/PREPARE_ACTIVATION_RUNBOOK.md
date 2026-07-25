# Production PREPARE Activation Runbook

## Current State

Canonical activation is complete. The production database is schema `15`;
authenticated PREPARE and separately gated START_RENDER have completed real
one-chapter and two-chapter canaries. Normal startup still performs no automatic
migration.

This file now preserves historical activation/rollback evidence. Do not rerun
the migration or pre-activation rollback commands against the current canonical
database. Current daily startup is documented in `docs/RUNBOOK.md`.

## Verified Package

The accepted preflight package is:

```text
D:\Youtube_AI_HANDOFFS\Story Audio\prepare_activation\run_20260723_readiness_v3
```

It contains:

- `canonical-schema12-backup.db`
- `prepare-activation-preflight.json`

Verified canonical evidence:

- schema 12;
- SHA-256 `dba41f6eb3eaba5de4a4d9964f41ee93bb730ac8c2d6fd47df202479ad203b23`;
- size `4009984`;
- `quick_check=ok`;
- `foreign_key_check=ok`;
- no WAL/SHM;
- no active/prepared job;
- Chapter 369 unchanged.

## Backup / Preflight

Run only with Story Audio stopped and PREPARE flags unset/default-disabled:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' `
  'D:\Youtube\Story Trans And Audio\scripts\prepare_activation.py' `
  --backup 'D:\Youtube_AI_HANDOFFS\Story Audio\prepare_activation\run_20260723_readiness_v3\canonical-schema12-backup.db'
```

The destination must not already exist. The verified `v3` package has already
completed this step; do not overwrite it.

## Explicit Migration

Keep PREPARE disabled and the app stopped. After explicit operator approval:

```powershell
$env:STORY_AUDIO_ALLOW_LIVE_DB='1'
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' `
  'D:\Youtube\Story Trans And Audio\scripts\prepare_activation.py' `
  --backup 'D:\Youtube_AI_HANDOFFS\Story Audio\prepare_activation\run_20260723_readiness_v3\canonical-schema12-backup.db' `
  --execute-migration `
  --confirm 'ACTIVATE_CANONICAL_SCHEMA_15'
```

The command fails closed if the canonical hash changed after preflight, flags
are enabled, active jobs exist, sidecars exist, migration hashes differ, or the
backup cannot be verified.

## Production Configuration

Daily production configuration is stored in ignored
`secrets/production-runtime.env`. `run_app.ps1` accepts only the documented
production keys, rejects duplicate/unknown entries, hashes the raw
`PREPARE_OPERATOR_TOKEN` in child-process memory, clears the temporary byte
buffer, and never prints token material.

The local file configures production mode, PREPARE feature/mutation gates,
operator window, schema readiness, authentication, render enablement, and kill
switch. Never commit the file, token, or token hash.

Normal startup:

```powershell
cd 'D:\Youtube\Story Trans And Audio'
.\run_app.ps1 --host 127.0.0.1 --port 8772 --no-browser
```

Verify the UI shows schema/auth/PREPARE/render ready before mutation. PREPARE
must still create non-executable work, and START_RENDER must still be a second
explicit action against that exact Job.

## Canary

The first production request must meet every rule:

- exactly one book;
- one to three contiguous chapters;
- target phase exactly `PREPARE`;
- every selected chapter appears in the plan's included list;
- every selected chapter has approved text, approved Casting Plan, and resolved voices;
- no existing prepared/live/conflicting job;
- Chapter 369 is not selected;
- operator types the exact `book_id:from-to` confirmation;
- no START_RENDER action follows the request.

Success is one durable request, one prepared Job, one JobChapter per selected
chapter, one committed linkage/attempt record, zero Segments, zero Artifacts,
no worker wake, and no provider/TTS activity.

## Kill Switch

Stop the app, set this entry in ignored `secrets/production-runtime.env`, and
restart:

```text
PREPARE_KILL_SWITCH_ACTIVE=true
```

The readiness endpoint and UI must show `KILL_SWITCHED`; PREPARE, START_RENDER,
and mutation-service construction must remain blocked.

## Rollback

The historical full-file rollback below was permitted only after schema
activation and before any PREPARE state was accepted. Production PREPARE state
now exists, so this command is no longer authorized for the canonical database.
It remains documented as activation evidence only.

```powershell
$env:STORY_AUDIO_ALLOW_LIVE_DB='1'
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' `
  'D:\Youtube\Story Trans And Audio\scripts\prepare_activation.py' `
  --backup 'D:\Youtube_AI_HANDOFFS\Story Audio\prepare_activation\run_20260723_readiness_v3\canonical-schema12-backup.db' `
  --rollback `
  --confirm 'RESTORE_CANONICAL_SCHEMA_12'
```

If any request/linkage/attempt row or changed legacy count exists, automatic
full-file rollback is blocked. Activate the kill switch and reconcile instead.
