# DAILY-PROD-5B Phase 14 Clone PREPARE API Acceptance

Updated: 2026-07-23

## Status

Phase 14 is accepted as `CLONE_ONLY_AUTHENTICATED_PREPARE_API`.

This acceptance does not authorize canonical migration, production
credentials, production PREPARE, production Job creation, a UI control, worker
wake, provider/Gemini/TTS calls, or `START_RENDER`.

## API

The clone test runtime exposes:

- `POST /api/production/batch-prepare`
- `GET /api/production/batch-prepare/{client_request_id}`

POST accepts only a bounded JSON object containing `client_request_id`,
`book_id`, `from_chapter`, `to_chapter`, literal `target_phase=PREPARE`, the
current plan fingerprint, and literal `confirmation=true`.

URL/query credentials, body credentials, client-selected operator or execution
ownership, generation, chapter authority, Job authority, status, render/start
fields, unknown fields, malformed JSON, and bodies over 16 KiB are rejected.

GET can replay a terminal result or recover an already committed transaction
from durable evidence. It does not acquire a new owner for a PLANNED request,
reset FAILED, choose another Job, rerun the Job transaction, or start render.

## Authentication And Gates

Bearer authentication uses the existing configured single-operator provider.
Loopback is not authentication.

Mutation service construction requires all of the following:

- runtime mode `CLONE_DISABLED`;
- the exact inspected DB path is outside the repository and canonical data root;
- schema exactly 15 and `quick_check=ok`;
- feature, mutation, canonical-schema-readiness, and operator-window flags open;
- valid configured operator authentication in explicit local-test mode;
- kill switch inactive;
- strict `PREPARE_CLONE_MUTATION_TEST_AUTHORIZED=true`;
- the existing temporary-clone marker required by the isolated adapter.

Unknown or malformed configuration fails closed. The validated descriptor is
bound to the same DB path used by the writable clone service, preventing a
safe-descriptor/unsafe-settings mismatch.

Default runtime constructs no batch PREPARE mutation service. The route returns
unavailable while the service is absent. The kill switch overrides valid
authentication and every other enable flag.

## Transaction And Idempotency

The API reuses the accepted isolated orchestrator and same-transaction adapter.
A valid request creates exactly one durable request, one prepared Job, the
exact JobChapter set, one request-to-Job linkage, and one COMMITTED execution
attempt before recording APPLIED.

The same request ID and payload replay the same Job. A changed payload conflicts.
Concurrent duplicates create one Job. Overlapping requests produce one winner;
non-overlapping requests may each succeed.

Authoritative eligibility, active Text Revision, approved Casting Plan, voice
pins, owner generation, and lease are revalidated by the existing adapter.
Stale or mismatched state cannot create a partial Job.

APPLIED persistence loss and response loss recover committed evidence without a
second Job. Ambiguous commit remains terminal review-required and is never
automatically rerun.

## Execution Boundary

PREPARE creates no Segment or Artifact, produces no audio, does not wake the
worker, and does not start render. Clone runtime lifespan does not start the
production worker.

Public API payloads remove token/auth material, credential hashes, fingerprints,
digests, internal request identity, owner/generation data, DB paths, SQL,
tracebacks, full text, and full Casting Plan content. A safe top-level `job_id`
is returned for operator replay verification.

## External Clone Acceptance

Evidence root:
`D:\Youtube_AI_HANDOFFS\Story Audio\phase14_clone_api\run_20260723_120013695480`

The acceptance runtime used a fresh read-only backup of canonical schema 12,
then applied only the dormant 13 -> 14 -> 15 chain on the external clone. Two
synthetic approved chapters were added to that clone.

Observed result:

- clone schema 15; `quick_check=ok`;
- request 1: APPLIED;
- Job 23: prepared;
- two exact JobChapters: pending, pinned to their Text Revisions and Casting Plans;
- one linkage with `worker_woken=0` and `render_started=0`;
- one execution attempt: COMMITTED;
- restart POST and GET returned the same Job 23;
- valid-auth kill-switch request returned 503 and changed no row counts;
- Segments remained 688 and Artifacts remained 84;
- public response/log redaction passed.

## Canonical Safety

Before and after acceptance:

- schema remained 12;
- SHA-256 remained
  `dba41f6eb3eaba5de4a4d9964f41ee93bb730ac8c2d6fd47df202479ad203b23`;
- size remained 4009984 bytes;
- Jobs 21, JobChapters 21, Segments 688, Artifacts 84, Casting Plans 23,
  and Speaker Assignment Drafts 15 were unchanged;
- Chapter 369 remained active Text Revision 738, audio `not_created`, no active
  artifact, and Casting Plan 24 revision 1 draft/unapproved.

No canonical dormant migration or production mutation occurred.

## Validation

- focused runtime/API suite: 33 tests passed;
- affected Phase 10-14 suite: 49 tests passed;
- concurrency/restart suite: 28 tests passed twice;
- full offline suite: 1624 tests passed with 1 established skip;
- external clone API/restart/kill-switch acceptance: passed.

Python syntax, UI JavaScript syntax, Doctor, diff hygiene, and final canonical
checks are part of the commit closeout.

## Remaining Boundary

Production secret provisioning, rotation/revocation, browser origin/CSRF policy,
durable operator audit, incident response, canonical schema migration,
maintenance/backup/rollback operations, production enablement, and rollout
monitoring remain incomplete and unauthorized.

Recommended next authorization, not granted by Phase 14:

`DAILY-PROD-5B Phase 15 - Production PREPARE Activation Readiness And Security Design Review`

That task must be design/read-only only. It must stop before canonical migration,
production credentials, production PREPARE, Job creation, UI mutation, worker
wake, provider/Gemini/TTS calls, or `START_RENDER`.
