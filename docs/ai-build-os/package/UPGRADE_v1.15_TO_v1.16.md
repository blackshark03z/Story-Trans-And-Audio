# Upgrade v1.15 → v1.16

v1.16 is a lightweight production hardening + state/temporal efficiency release.

## Security/reliability hardening

- Task/Goal/node identifiers are validated and confined to managed namespaces; path traversal is rejected.
- Lifecycle locks recover automatically when the recorded PID is dead; live/fresh locks still fail closed.
- Durable evidence redaction now covers bearer/basic auth, cookies, common key/value credentials, JWTs, private-key blocks, common cloud/GitHub/API token forms, and credential-bearing URLs.
- A2–A4 assurance output now explicitly states when its basis is a trusted-runtime environment claim rather than independent repo-kernel proof.

## State Hazard gate

Default is `--state-hazard auto`.

- S0: no extra work.
- S1: signal only.
- S2: authority + transition + invariant; require `--state-transition-command` at finish.
- S3+: additionally require `--state-temporal-command`.

The compact `scripts/ai.py` facade exposes these as optional flags. Existing stateless task commands do not need changes.

## Reusable proof

State proof caching is automatic. A prior PASS is reused only when the state contract, exact proof command, and declared dependency fingerprint are unchanged. Cache records live under `.ai/evidence/_state_cache/` and point back to immutable accepted evidence.

## Debug + stop-loss

- `debug state-failure` records a bounded transition failure signature.
- `debug evidence-infra-failure` records verifier/harness failure. Two consecutive failures of the same method make `next` recommend a method change.

See `docs/21_STATE_HAZARD_AND_FAST_DEBUG.md`.
