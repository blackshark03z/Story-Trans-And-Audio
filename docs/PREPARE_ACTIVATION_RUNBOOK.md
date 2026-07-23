# Production PREPARE Activation Runbook

## Current State

Production PREPARE code is installed but hard-disabled. Canonical schema remains
12. Normal startup does not apply migrations 13-15. `PRODUCTION` mode is
PREPARE-only: it does not start the worker and blocks legacy job prepare/start
routes.

Do not execute this runbook until the operator explicitly approves canonical
activation.

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

Set these values only in the process shell that launches Story Audio. Never
persist the raw operator token or commit it:

```powershell
$PrepareOperatorToken = Read-Host 'Temporary PREPARE operator token'
$TokenBytes = [Text.Encoding]::UTF8.GetBytes($PrepareOperatorToken)
$env:PREPARE_OPERATOR_TOKEN_SHA256 = [Convert]::ToHexString(
  [Security.Cryptography.SHA256]::HashData($TokenBytes)
).ToLowerInvariant()
$env:PREPARE_RUNTIME_MODE='PRODUCTION'
$env:PREPARE_FEATURE_AVAILABLE='true'
$env:PREPARE_MUTATION_ENABLED='true'
$env:PREPARE_OPERATOR_WINDOW_OPEN='true'
$env:PREPARE_CANONICAL_SCHEMA_READY='true'
$env:PREPARE_KILL_SWITCH_ACTIVE='false'
$env:PREPARE_OPERATOR_AUTH_ENABLED='true'
$env:PREPARE_OPERATOR_ID='daily-prepare-operator'
$env:PREPARE_OPERATOR_TOKEN_VERSION='canary-v1'
$env:PREPARE_OPERATOR_AUTH_LOCAL_TEST_MODE='false'
Remove-Item Env:PREPARE_CLONE_MUTATION_TEST_AUTHORIZED -ErrorAction SilentlyContinue
.\run_app.ps1 --host 127.0.0.1 --port 8772 --no-browser
```

Enter `$PrepareOperatorToken` in the PREPARE UI, then clear the shell variable
after the canary:

```powershell
Remove-Variable PrepareOperatorToken,TokenBytes -ErrorAction SilentlyContinue
```

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

Stop the app, set the kill switch, and restart in PREPARE-only mode:

```powershell
$env:PREPARE_KILL_SWITCH_ACTIVE='true'
.\run_app.ps1 --host 127.0.0.1 --port 8772 --no-browser
```

The readiness endpoint and UI must show `KILL_SWITCHED`; the mutation service
must not be constructed.

## Rollback

Rollback is permitted only after schema activation and before any PREPARE state
is accepted. Keep the app stopped and every PREPARE flag disabled:

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
