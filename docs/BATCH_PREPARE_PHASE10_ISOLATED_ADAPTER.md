# Batch PREPARE Phase 10 Isolated Adapter

Status: `PHASE_10_ACCEPTED_ISOLATED_ONLY`

Authorization labels:

- `ISOLATED_ONLY`
- `TEMPORARY_DATABASE_ONLY`
- `NO_RUNTIME_WIRING`
- `NO_CANONICAL_ACTIVATION`
- `NO_PRODUCTION_PREPARE`
- `NO_API_ROUTE`
- `NO_UI_CONTROL`
- `NO_WORKER_WAKE`
- `START_RENDER_NOT_AUTHORIZED`

## 1. Status And Authorization

Phase 10 assembles the Phase 5-9 contracts into an end-to-end PREPARE adapter on disposable schema-15 test databases. It proves durable request ownership, one atomic prepared Job transaction, post-commit evidence, APPLIED ordering, replay, concurrency, and restart recovery. It does not authorize or provide a production entry point.

## 2. Existing Prerequisites

| Area | Existing prerequisite | Phase 10 assembly | Acceptance evidence |
| --- | --- | --- | --- |
| Request | schema-13 store and Phase 5 orchestrator | replay-first lookup and guarded ownership | duplicate/replay/restart tests |
| Execution | schema-15 attempts | token, lease, generation, and fence handoff | owner/expiry/race tests |
| Authority | plan contract and transaction revalidator | intake, second plan, then in-transaction reload | stale revision/plan/pin tests |
| Mutation | transaction manager and prepared Job repository | one caller-owned transaction | rollback/failure matrix |
| Linkage | schema-14 request-to-Job link | same transaction as Job and attempt COMMITTED | evidence and uniqueness tests |
| Recovery | Phase 9 evidence reader | tokenless committed recovery and APPLIED persistence | response-loss/process-restart tests |

## 3. Adapter Assembly

`story_audio/batch_prepare_isolated_adapter.py` injects the current-plan provider through the orchestrator and directly receives the request store, execution-attempt store, isolated transaction service, authoritative snapshot provider, committed-evidence reader, clock, lifecycle hook, and temporary root. There is no singleton or import-time mutation.

Every DB-backed dependency must resolve to the same database under an explicit temporary root containing `.story-audio-phase10-temporary`. The content store must also remain under that root.

## 4. Exact Request Flow

1. Validate request shape, PREPARE target, explicit confirmation, scope, and fingerprint.
2. Resolve an existing client request before reading current plan when the store supports replay-first lookup.
3. Recompute and validate the current plan.
4. Create or replay the durable request.
5. Acquire `PLANNED -> APPLYING` ownership.
6. Build render-compatible immutable chapter pins and acquire execution token/generation/lease.
7. Recompute the plan and reject stale input before the transaction.
8. Start one bounded `BEGIN IMMEDIATE` transaction.
9. Revalidate request, owner, range, eligibility, Text Revisions, approved Casting Plans, hashes, voices, and pins.
10. Inspect exact linkage and overlapping live work.
11. Insert one prepared Job, N pending JobChapters, one linkage, and mark the attempt COMMITTED.
12. Commit once, reload durable evidence on a new connection, validate it, then persist APPLIED.
13. Reload and return the durable request result.

## 5. Historical Replay Precedence

APPLIED, REJECTED, and FAILED records replay their stored bounded result without current-plan recomputation, ownership acquisition, or another Job transaction. APPLYING first checks durable execution evidence. PLANNED alone may acquire new request ownership.

The optional replay-first store method preserves compatibility with the earlier store protocol: stores without it continue through create-or-replay.

## 6. Request Ownership

Request ownership is the durable guarded transition `PLANNED -> APPLYING`. Competing callers reload the winner. The short window between this transition and execution-attempt creation is treated only as in progress; it is never terminalized as failure.

## 7. Execution Fencing

The execution attempt stores only a SHA-256 token hash, a monotonic generation, bounded lease, immutable request/fingerprint/digest bindings, and transaction reference. The raw token is process-local and redacted from repr, results, logs, SQLite, tests, and handoff files.

Expired-owner classification obtains its own bounded write reservation, reloads the attempt, and either recovers COMMITTED evidence or atomically marks no-commit ownership EXPIRED. A committing owner therefore cannot be overwritten by an observer.

## 8. Plan Validation

The submitted fingerprint validates intake. A second current plan is required after ownership and before the transaction. A mismatch cancels the execution acquisition as rollback-confirmed and records a deterministic rejection without creating a Job.

## 9. Transaction Revalidation

Inside `BEGIN IMMEDIATE`, the service reloads the exact request and owner, chapter set, active Text Revision, latest approved Casting Plan, plan revision/hash, narrator voice, eligibility, active output state, and immutable casting/voice pins. Newer facts are never silently adopted.

## 10. Job, JobChapter, And Linkage Transaction

One transaction inserts exactly one `prepared` Job, one pending JobChapter per validated chapter, one request-to-Job linkage, and the COMMITTED attempt update. Job settings and each voice snapshot are render-compatible with the existing pipeline: TTS settings, Casting Plan identity/hash, utterance offsets/hashes, resolved voices, and chunker version are pinned.

No Segment, synthesis attempt, Artifact, audio row, wake action, or render action is created.

## 11. Durable Evidence

Success requires a fresh-connection reload proving one COMMITTED attempt, one exact linkage, one prepared Job, ordered unique JobChapters, exact request/fingerprint/digest/reference/counts, render-compatible settings and voice snapshots, `worker_woken=0`, and `render_started=0`.

A provisional Job ID or a returned transaction value is not commit evidence.

## 12. APPLIED Ordering

The orchestrator validates committed evidence before writing APPLIED. If APPLIED persistence fails after commit, the request may remain APPLYING, but the same Job is recovered from durable evidence on retry. No failure response invites a second execution. Concurrent terminal writers reload and replay the durable winner.

## 13. Duplicate Behavior

- Same client request ID and payload: replay or report in progress; never create a second Job.
- Same client request ID with different payload: `REQUEST_ID_CONFLICT` before plan recomputation when replay-first lookup is available.
- Historical FAILED: replay-only; a retry requires a fresh client request ID after review.
- Committed evidence with missing APPLIED: recover the same Job and persist APPLIED when evidence is exact.

## 14. Overlap Behavior

SQLite `BEGIN IMMEDIATE` serializes writers. Overlapping requests reload eligibility after the winner commits; one request becomes APPLIED and the loser is deterministically REJECTED with `PREPARE_CONFLICT`. Non-overlapping requests may both commit sequentially. Database-wide serialization is claimed; range-level parallel writes are not.

## 15. Failure Injection

Tests inject failures after request validation, conflict inspection, Job insert, partial JobChapter insert, linkage insert, attempt update, before commit, during commit classification, after commit, evidence reload, and APPLIED persistence. Every proven pre-commit failure leaves zero Job, JobChapter, and linkage rows and records rollback evidence.

Transaction-begin failure validates owner evidence and proves absence before recording rollback. Bounded writer contention returns nonterminal APPLYING without a long terminal-write wait or raw SQLite detail.

## 16. Ambiguous Commit

A commit exception never reruns the transaction body. Exact committed evidence recovers the same Job. Unproven or contradictory outcomes become review-required with a durable recovery classification. Ambiguous historical requests remain replay-only.

## 17. Response-Loss Recovery

Exceptions after the real commit and before response/APPLIED are recovered from attempt, linkage, Job, and JobChapter evidence. Recovery does not require the raw owner token and does not recompute current plan facts.

## 18. Process Restart

Subprocess tests terminate after owner acquisition, after a provisional Job insert, and after commit. Reopen tests prove rollback of an interrupted transaction, tokenless recovery of a committed transaction, and exact APPLIED replay without a replacement Job.

## 19. Result Payload

The versioned APPLIED payload stores request identity, scope, fingerprint, chapter digest, Job reference, chapter count, compact `[chapter_id, job_chapter_id]` references, prepared status, commit timestamp, generation, linkage verification, recovery source, operator action, and no-render flags.

Per-chapter references are compact, the scope is bounded to 256 chapters, and a 100-chapter regression remains below the 16 KiB request-store limit. Full text, Casting Plan bodies, database paths, and owner material are excluded.

## 20. Security And Redaction

Internal exception text is not persisted at service boundaries. Public failure messages use fixed taxonomy text. Durable fields pass an explicit allowlist. Secret/token/path/SQL/traceback markers are replaced by a fixed fallback, and raw owner tokens are never serialized.

## 21. Canonical Isolation

The adapter requires an explicit marker-backed temporary root, same-path DB dependencies, and blob storage below that root. Canonical `data/app.db` is rejected before a writable connection. Dormant schemas 13-15 are explicitly composed only by disposable tests; `LATEST_SCHEMA_VERSION` remains 12.

## 22. Acceptance Tests

- Focused batch PREPARE and prepared-job suite: `404` tests PASS.
- Phase 10/orchestrator core: `59` tests PASS.
- Concurrency suite: `9` tests PASS, repeated ten times without a timing failure.
- Full offline suite: `1524` tests PASS, `1` skipped.
- Syntax and `node --check ui/app.js`: PASS.

Acceptance covers render-compatible pins without segment writes, replay-first behavior, legacy store compatibility, terminal races, expired-owner commit races, bounded busy, overlap rejection, compact payloads, redaction, process death, rollback, and ambiguous recovery.

## 23. Runtime-Wiring Prerequisites

Before any runtime implementation, Phase 11 must review dependency construction, feature-flag default-off behavior, canonical schema 12-to-15 activation, backup/hash/rollback, maintenance mode, API confirmation and status contracts, audit/redaction, recovery, kill switch, and Chapter 369 protection.

## 24. Remaining Risks

- The proof uses disposable SQLite databases, not the production launcher lifecycle.
- Writer serialization is database-wide and may need operational timing limits before rollout.
- Canonical migration, backup, rollback, maintenance, and feature-flag procedures are not yet accepted.
- No production API/status route or operator UI has been reviewed.
- START_RENDER remains a separate lifecycle and authorization boundary.

## 25. Authorization Gates

| Capability | State |
| --- | --- |
| Isolated temporary adapter tests | `AUTHORIZED_AND_ACCEPTED` |
| Runtime wiring design | `NEXT_REVIEW_BOUNDARY` |
| Runtime implementation | `NOT_AUTHORIZED` |
| Canonical schema activation | `NOT_AUTHORIZED` |
| Production PREPARE | `NOT_AUTHORIZED` |
| API mutation route | `NOT_AUTHORIZED` |
| UI control | `NOT_AUTHORIZED` |
| Worker wake | `NOT_AUTHORIZED` |
| START_RENDER | `NOT_AUTHORIZED` |
| Provider, Gemini, or TTS | `NOT_AUTHORIZED` |
