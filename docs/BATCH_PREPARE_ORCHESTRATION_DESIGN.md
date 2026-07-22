# Batch PREPARE Orchestration Design

Status: `DESIGN_AND_ISOLATED_CONTRACT_ONLY`

Authorization:

- `ISOLATED_PREPARE_ORCHESTRATION_DESIGN_AUTHORIZED`
- `NO_API_ROUTE`
- `NO_REAL_JOB_CREATION`
- `NO_CANONICAL_SCHEMA_ACTIVATION`
- `PREPARE_EXECUTION_NOT_AUTHORIZED`
- `START_RENDER_NOT_AUTHORIZED`

## Existing Prerequisites

- Read-only batch plan: `story_audio/batch_plan.py`
- Pure PREPARE validation: `story_audio/batch_prepare_contract.py`
- Persistence contract: `story_audio/batch_prepare_persistence_contract.py`
- Durable request store: `story_audio/batch_prepare_store.py`
- Dormant schema 13: `story_audio/migrations/dormant/0013_batch_prepare_requests.sql`

## Goals

Phase 5 defines an isolated service-level orchestration contract for PREPARE request intake, durable replay, atomic ownership, second fingerprint validation, injected future transaction behavior, terminal result recording, timeout replay, and stale APPLYING reconciliation.

The orchestrator is intentionally not wired to HTTP, the worker, the runtime lifecycle, or production job creation.

## Non-Goals

- No API route.
- No canonical schema activation.
- No `prepare_job` or `create_job` invocation.
- No real Job or JobChapter creation.
- No UI.
- No provider, Gemini, TTS, segment, artifact, or audio work.
- No START_RENDER behavior.

## Dependency Interfaces

`CurrentPlanProvider` recomputes the current read-only PREPARE batch plan from authoritative runtime facts.

`PrepareRequestStore` provides durable `create_or_replay_request`, guarded state transition, terminal result recording, and historical replay.

`FuturePrepareTransaction` is an injected fake or future adapter boundary. In Phase 5 it must not write `jobs`, write `job_chapters`, wake the worker, start render, or call provider/TTS/Gemini.

## Request Intake

The request flow is:

1. Require request object.
2. Validate PREPARE-only contract, scope, fingerprint, and exact boolean confirmation through the pure Phase 1 contract.
3. Recompute current plan; client included/excluded rows are never authority.
4. Build durable request binding and canonical request identity.
5. Create or replay the durable request.

Malformed requests, unsupported phases, missing confirmation, invalid fingerprints, and stale-at-intake requests are rejected before durable persistence.

## Create-Or-Replay

If the store returns a terminal record, the orchestrator replays the durable historical result and does not call the future transaction.

If the store returns `APPLYING`, the orchestrator returns in-progress and does not call the future transaction.

If the store returns `PLANNED`, the orchestrator proceeds to the ownership path.

Same `client_request_id` with a different bound payload returns `REQUEST_ID_CONFLICT`.

## No-Eligible Requests

When the current plan is valid but contains no eligible chapters, the orchestrator records a deterministic `REJECTED` result directly from `PLANNED` without acquiring APPLYING ownership and without calling the future transaction.

## Ownership Acquisition

Executable requests acquire ownership only through the durable store compare-and-transition:

```text
PLANNED -> APPLYING
```

Exactly one caller can win. Losers reload/replay the durable state and do not call the future transaction.

## Second Fingerprint Validation

After ownership is acquired but before the future transaction boundary, the orchestrator recomputes the PREPARE plan again.

If the fingerprint, scope, phase, or eligibility changed, the request records deterministic `REJECTED` with `STALE_PLAN`. The orchestrator does not adopt the new fingerprint and does not call the future transaction.

## Future Transaction Boundary

Only after the second validation passes does the orchestrator call the injected future transaction.

The injected result may contain an opaque `simulated_job_reference` / `future_job_reference`, per-chapter result rows, and public audit fields. It must not contain absolute paths, secrets, raw SQL, tracebacks, full text, or blobs.

Phase 5 stores APPLIED with `job_id = null` because no real Job exists.

## Success Ordering

Success ordering is:

1. Future transaction returns simulated success.
2. Durable APPLIED result is recorded.
3. The service response is built from the durable record.

If APPLIED persistence fails, success is not returned. The durable request remains in its real state for later replay or operator review.

## Failure Ordering

Deterministic business conflict records `REJECTED`.

Retryable infrastructure failure records `FAILED` with `FAILED_RETRYABLE`.

Ambiguous failure records `FAILED` with `FAILED_REVIEW_REQUIRED`.

The orchestrator does not auto-retry a failed request. A fresh `client_request_id` is required after review.

## Timeout Replay

If a client times out after APPLIED persistence and submits the same request again, the durable APPLIED result is replayed. The future transaction call count remains one.

If a client retries while the request is APPLYING, the orchestrator returns in-progress and does not call the future transaction.

Replay never depends on process memory.

## Reconciliation Classification

Phase 5 includes a pure classifier for stale APPLYING rows. It only returns a decision contract:

- `STILL_IN_PROGRESS`
- `SAFE_TO_MARK_FAILED_RETRYABLE`
- `OPERATOR_REVIEW_REQUIRED`
- `APPLIED_RESULT_RECOVERY_REQUIRED`
- `REQUEST_RECORD_CORRUPT`

The classifier does not call the future transaction, transition state, create jobs, retry, or start render.

## Operator Actions

Responses use deterministic operator actions:

- `NONE`
- `REVIEW_REQUEST`
- `CREATE_NEW_REQUEST`
- `WAIT_AND_RETRY_STATUS`
- `REBUILD_PLAN`
- `INVESTIGATE_AMBIGUOUS_APPLYING`

## Response Contract

Every response includes:

- `status`
- `request_id`
- `client_request_id`
- `request_identity`
- `request_state`
- `scope`
- `plan_fingerprint`
- `replay`
- `ownership_acquired`
- `future_transaction_called`
- `result`
- `error_code`
- `operator_action`
- `mutation_authorized = false`
- `execution_endpoint_available = false`
- `real_job_execution = false`
- `prepare_starts_render = false`

Responses do not claim `job_created`.

## Audit Evidence

Result payloads may include bounded public `audit_fields`. They must not contain paths, secrets, full text, raw SQL, tracebacks, casting blobs, or voice snapshot blobs.

## Testing Strategy

Focused tests cover request validation, no-store malformed rejects, current-plan authority, no-eligible rejection, durable create/replay, APPLIED/REJECTED/FAILED replay, APPLYING retry behavior, payload conflicts, atomic ownership, second fingerprint rejection, simulated success, simulated failures, APPLIED persistence failure, concurrency, reconciliation classification, import side effects, and source-level execution-boundary guards.

Closeout should run the full offline suite separately before committing.

## Implementation Authorization Gates

Future work requires separate authorization for:

1. Canonical schema 13 activation.
2. HTTP route registration.
3. Real PREPARE execution.
4. Real Job/JobChapter creation.
5. START_RENDER integration.
6. UI controls.

## Open Risks

- Real Job transaction integration still needs a durable all-or-nothing adapter.
- API timeout behavior must preserve the same durable replay contract.
- Stale APPLYING reconciliation still needs a reviewed mutation workflow.
- Canonical schema activation remains separate and unauthorized.
