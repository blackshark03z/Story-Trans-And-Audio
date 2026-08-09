# Package Manifest — Senior AI Build OS v1.16.0

## Core contracts

- `.ai/PROJECT.md` — product contract + project-specific risk surfaces
- `.ai/GOAL.md` — human-readable active Goal
- `.ai/GOAL_STATE.json` — machine-readable Goal/DAG state
- `.ai/ACTIVE_TASK.md` — single-writer execution contract
- `.ai/STATE.md`
- `.ai/CONTEXT_CAPSULE.md` — compact worker packet
- `.ai/DECISIONS.md`, `.ai/QUALITY_GATES.md`, `.ai/COST_LEDGER.csv`

## Goal orchestration records

- `.ai/goals/<goal>/plan.json` — current Goal plan/DAG snapshot
- `.ai/goals/<goal>/decisions.jsonl` — assumptions, auto-decisions, owner decisions, risk escalations and policy exceptions
- `.ai/goals/<goal>/owner_digest.json` — generated owner attention digest at Goal completion
- `.ai/goals/<goal>/result.json` — immutable final Goal acceptance result
- `scripts/goal_support.py` — Goal state, dependency waves, frozen acceptance contracts, auto-Scout insertion, Scout/Worker routing and task-result aggregation
- `scripts/delegation_support.py` — conservative subagent ROI heuristics, write-scope overlap/parallel selection and machine-readable delegation planning

## Task execution and immutable records

- `.ai/runtime/task_baseline.json` — generated task-start dirty fingerprints
- `.ai/runtime/*.json` — generated mirrors including Goal state
- `.ai/evidence/<task>/rNNN/` — immutable COMPACT/FULL evidence bundles with verified application fingerprints and Goal linkage
- `.ai/history/<task>/rNNN.json` — accepted-task history with Goal linkage
- `.ai/transactions/` — lifecycle transaction journal
- `.ai/field/README.md` — field-learning runtime contract; generated `.ai/field/events.jsonl` is Git-ignored, while the optional redacted global mirror lives outside repo

## Commit-aware CI

- `init` auto-installs `.github/workflows/ai-build-os.yml` in Git repos unless `--no-ci`.
- `validate_ai_os.py --ci` binds committed application paths to verified evidence file fingerprints from the same change set.
- Goal orchestration is additive; application-integrity trust boundary remains task evidence + CI. R2/R3 Goal contracts bind predeclared acceptance/probe hashes into task evidence.

## Runtime/validation

- `scripts/ai_os.py`, `scripts/cli_support.py`, `scripts/goal_support.py`, `scripts/delegation_support.py`
- `scripts/risk_support.py`, `scripts/runtime_support.py`, `scripts/evidence_support.py`, `scripts/state_hazard_support.py`
- `scripts/state_runtime.py`, `scripts/validate_ai_os.py`, `scripts/refresh_context_capsule.py`
- `scripts/project_ci.py`, `scripts/append_cost_ledger.py`, `scripts/self_test.py`
- `scripts/assurance_support.py`, `scripts/guardian.py` — achieved assurance and external signed reviewer protocol
- `scripts/field_support.py`, `scripts/decision_support.py`, `scripts/ai.py` — field learning, owner digest and compact agent facade
- `scripts/self_test.py` — default bounded fast/current regression pyramid
- `scripts/self_test_v116.py` — namespace/stale-lock/redaction/state-hazard/reuse/debug-stop-loss regressions
- `scripts/self_test_v115.py` — Guardian/assurance/field-learning/decision/risk-uncertainty compatibility regressions
- `scripts/self_test_v114.py` — architecture / quality-capability / structured-dependency / anti-monster regressions
- `scripts/self_test_v113.py` — fail-closed CI / lane / telemetry / codebase-health compatibility regressions
- `scripts/self_test_v112.py`, `scripts/self_test_v112_trust.py` — Goal/Scout/budget/dedup + external-trust compatibility regressions
- `scripts/self_test_full.py` — historical broad release/nightly regression

## Templates and guides

- LEAN / STANDARD / DEEP task templates
- Goal Orchestrator / Scout / Goal Acceptance prompts
- GitHub Actions commit-provenance + product CI template
- Root quickstarts and docs 01–21
- Upgrade guides through v1.16

## Policy / lane / health kernels

- `config/gates.json` — single machine-readable R0–R3 gate policy; `.ai/QUALITY_GATES.md` is generated from it.
- `config/codebase_health.json` — codebase-health hard rules, anti-monster ratchets and architecture decision policy.
- `config/quality_policy.json` — required/recommended Product CI capabilities and explicit capability waivers.
- `config/assurance.json` — review trust requirements, assurance environment hooks and field-learning privacy defaults.
- `config/risk_semantics.json` — conservative unknown-side-effect semantics.
- State/temporal hazard policy is deliberately compact in `scripts/state_hazard_support.py`; S0/S1 adds no required proof and S2/S3 proof is dependency-fingerprint reusable.
- `config/kernel_contract.json` — stable-core vs tunable-policy release discipline.
- `scripts/project_support.py` / `project_ci.py` — canonical baseline + fail-closed Product CI.
- `scripts/lane_support.py` — FAST/STANDARD/GOAL routing.
- `scripts/telemetry_support.py` — provider-neutral usage ingestion and conservative delegation feedback.
- `scripts/health_support.py` — bloat/architecture ratchet + hotspot metrics.
- `scripts/reporting_support.py` — cost/quality/health reporting split from lifecycle mutation.
