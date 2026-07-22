# DAILY-PROD-5B Phase 12 Clone Rehearsal

## 1. Status And Authorization

Phase 12 is complete for the authorized clone-only scope. The implementation is
`EXTERNAL_CLONE_ONLY`, `DEFAULT_OFF_ONLY`, and does not activate production
PREPARE. The source baseline remained schema 12.

Authorization used:

- `CANONICAL_CLONE_MIGRATION_REHEARSAL_AUTHORIZED`
- `DISABLED_RUNTIME_WIRING_SKELETON_AUTHORIZED`
- `EXTERNAL_LOCAL_CLONE_CREATION_AUTHORIZED`
- `CLONE_ONLY_SCHEMA_12_TO_15_ACTIVATION_AUTHORIZED`
- `CLONE_ONLY_FULL_FILE_ROLLBACK_REHEARSAL_AUTHORIZED`
- `DEFAULT_OFF_RUNTIME_CONFIGURATION_IMPLEMENTATION_AUTHORIZED`

The following remained unauthorized: `NO_CANONICAL_ACTIVATION`,
`NO_ENABLED_PREPARE_ROUTE`, `NO_PRODUCTION_PREPARE`,
`NO_PRODUCTION_JOB_CREATION`, and `START_RENDER_NOT_AUTHORIZED`.

## 2. Canonical Source Safety

The canonical source was resolved and opened through a SQLite read-only URI.
The clone tool rejects source aliases and destinations inside the repository,
`data/`, protected paths, or the canonical database parent. The canonical
runtime was not restarted. Source SHA-256 was
`dba41f6eb3eaba5de4a4d9964f41ee93bb730ac8c2d6fd47df202479ad203b23`, size was
`4009984` bytes, schema/latest was `12/12`, and `quick_check` was `ok` before
and after the rehearsal.

## 3. Clone Mechanism

The tool uses SQLite online backup from a read-only source connection to a new
writable file under the approved external rehearsal root. It records source
facts before and after backup and compares logical facts on the clone. It does
not use the application `Database` class, which is intentionally writable and
WAL-oriented.

## 4. Clone Evidence

The real rehearsal clone preserved the source logical baseline:

- speaker assignment drafts: `15`
- casting plans: `23`
- jobs: `21`
- job chapters: `21`
- segments: `688`
- artifacts: `84`
- Chapter 369: Text Revision `738`, Casting Plan `24` revision `1` draft,
  jobs/artifacts `0`, audio `not_created`
- dormant request, linkage, and execution-attempt rows: absent

Evidence is bounded and stores path references, hashes, schema facts, counts,
and status only. It does not store full rows, chapter text, credentials, owner
tokens, or raw SQL.

## 5. Migration Hashes

The explicit allowlist and SHA-256 values were:

- 13 `0013_batch_prepare_requests.sql`:
  `6021e82a08627f897f3c02ae6f316da78ca8ba55fbc5cb153faf6999637282ba`
- 14 `0014_batch_prepare_job_links.sql`:
  `ad6108f18c1b4a113ddd68b3d067a8884ff9e5f1c6df5d8c729b0e31ad5486aa`
- 15 `0015_batch_prepare_execution_attempts.sql`:
  `6b5b00e8b013c7876c4faef4c480c0926c3ee8df8304a1c3b3544d80e9fdd706`

Normal startup discovery remains schema 12; these files remain dormant.

## 6. Schema 12 To 15 Rehearsal

The clone was migrated in exact order `13 -> 14 -> 15`, with one transaction
per stage and predecessor-schema checks. The final clone reached schema 15.
Each stage was closed and reopened for fact collection.

## 7. Postflight Verification

Postflight passed with `quick_check=ok` and `foreign_key_check=ok`. All expected
dormant tables, indexes, foreign keys, and CHECK constraints were verified.
Legacy counts, jobs, job chapters, segments, artifacts, audio state, and
Chapter 369 facts were unchanged. No request, linkage, or attempt rows were
created, and no production Job was created.

## 8. Failure Injection

Failure was injected independently inside stages 13, 14, and 15. The clone
remained respectively at schema 12, 13, and 14 after transaction rollback,
with `quick_check=ok` and `foreign_key_check=ok`. No canonical effect occurred.
An uncertain migration window uses full-file rollback rather than SQL
downgrade. Postflight rejection is also fail-closed in the validation API.

## 9. Backup

The pre-migration clone backup was made from a closed schema-12 clone by a
temporary-file copy followed by atomic rename. Its SHA-256 was verified equal
to the clone before migration, and its schema and quick check were verified.

## 10. Full-File Rollback

The migrated clone was closed and moved to an external failed-clone archive.
The verified schema-12 backup was copied to a same-directory temporary file,
hash-checked, and atomically replaced into the clone path. Stale `-wal` and
`-shm` sidecars were archived with the failed clone and cannot attach to the
restored file.

## 11. Restored Clone Verification

Rollback restored schema 12, `quick_check=ok`, `foreign_key_check=ok`, the
logical baseline, and the exact pre-migration backup hash. Dormant tables and
rows were absent after restore. A repeated rollback call returned the stable
already-restored result without replacing another file. Nothing was restored
to the canonical path.

## 12. Disabled Runtime Wiring

`story_audio/batch_prepare_runtime_wiring.py` is a pure descriptor. It imports
no API, database, migration, worker, adapter, store, or provider module. It
accepts dependency factories only to prove they are not called. It constructs
no mutation service, request store, linkage store, attempt store, transaction
service, or isolated adapter.

## 13. Feature-Flag Defaults

Feature availability, mutation enablement, operator window, and canonical
schema readiness default to false. Recognized boolean values are bounded to
`true/false`, `1/0`, and `enabled/disabled`; unknown values make configuration
invalid and disabled.

## 14. Kill Switch

The kill switch defaults active and has precedence over all other flags. The
public status never reports production readiness or execution authorization.
Writable database access, migration execution, job creation, worker wake, and
START_RENDER remain false.

## 15. Authentication Blocker

Authentication remains `AUTH_MISSING_BLOCKS_PRODUCTION`. Local binding is not
treated as operator authentication, no identity is fabricated, and Phase 12
does not implement an authentication bypass or credential channel.

## 16. Route Absence

No new PREPARE mutation route was registered, no status route has mutation
side effects, and the isolated adapter is not referenced by API startup. The
legacy routes remain untouched. No UI control calls a new PREPARE mutation
endpoint.

## 17. Read-Only Planning Preservation

The phase adds no route or UI mutation. Existing read-only batch planning and
range-readiness behavior remain outside the disabled wiring module and continue
to support the schema-12 runtime. START_RENDER remains a separate action.

## 18. Tests

Focused Phase 12 validation passed: `16` tests. Coverage includes source and
destination guards, online backup, source invariants, exact migration order,
indexes/FKs/CHECK constraints, stage rollback, atomic full-file restore,
sidecar handling, repeated rollback, default-off flags, kill-switch precedence,
auth blocking, dependency non-construction, route absence, UI mutation absence,
and import isolation. The real external clone rehearsal also passed.

## 19. Canonical Safety

The canonical database remained schema 12 with the baseline hash, size, mtime,
counts, Chapter 369 state, and no persistent WAL/SHM sidecars after the
rehearsal. Runtime PREPARE flags remained disabled. Chapter 369 was not
mutated, and `experiment_b_transcript/` and `runs/` were preserved.

## 20. Phase 13 Prerequisites

The safe next boundary is clone-only disabled runtime integration plus an
explicit operator-authentication contract. It must run against a migrated
external clone, prove startup/restart isolation, and keep mutation disabled.

## 21. Open Risks

Operator authentication is still undefined for production. A clone rehearsal
does not prove canonical activation safety, enabled route behavior, PREPARE
transaction execution, worker behavior, or provider behavior. These remain
separate acceptance gates.

## 22. Authorization Gates

Phase 13 may begin only as:

`SYSTEM_ROADMAP / CLONE_ONLY_DISABLED_RUNTIME_INTEGRATION_AUTHORIZED /
OPERATOR_AUTHENTICATION_CONTRACT_IMPLEMENTATION_AUTHORIZED /
CANONICAL_ACTIVATION_NOT_AUTHORIZED / ENABLED_PREPARE_ROUTE_NOT_AUTHORIZED /
PRODUCTION_PREPARE_NOT_AUTHORIZED / START_RENDER_NOT_AUTHORIZED`

No canonical schema activation, production PREPARE, production Job creation,
UI PREPARE control, worker wake, START_RENDER, or Gemini/TTS/provider call is
authorized by this closeout.
