# Active Goal

Goal ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125
Goal Status: BLOCKED
Goal Type: risk
Risk Ceiling: R3
Updated: 2026-08-25T08:15:10+00:00

## Outcome

Restore one trustworthy Story Audio execution baseline and safely adopt Build OS v1.25 Work Loop authority without laundering v1.16 history.

## Acceptance

- [ ] A durable grounding record proves the repository, Git, worktree, runtime, database/schema, active artifact/QA, CI, lifecycle, and writer/lease facts required by the mission without production mutation.
- [ ] The CI command contract is machine-readable, install and product-check resolution are regression-covered, and the locally equivalent GitHub workflow checks pass without weakening fail-closed behavior.
- [ ] Current-state documentation agrees with canonical database/runtime/Git truth, supersedes the obsolete Artifact 93/96 instruction precisely, and names the exact post-Goal product-development boundary.
- [ ] Build OS v1.25 RC4 is adopted through a single durable external package authority with legacy v1.16 evidence preserved as historical provenance and no historical state reinterpreted as v1.25-supervised.
- [ ] A bounded non-production first Work Loop proves Work Contract to Grounding Report to admission to proportional assurance, and final baseline checks leave canonical data, providers, secrets, protected artifacts, push, and merge untouched.

## Acceptance Quality

- Falsifiability heuristic: no high-confidence warnings

## Goal Acceptance Contract

- Status: FROZEN 7a5f04f5b197
- Criterion mappings: 5/5

## Non-Goals

- NONE

## Budget

- Maximum tasks: 5
- Maximum parallel writers: 1
- Maximum consecutive non-shipping tasks: 5
- Maximum revisions per task before stop-loss: 2
- Scope growth limit: 80%
- Scout input budget: 24000 tokens
- Scout wall budget: 5.0 minutes
- Scout provider-cost budget: 0.0 (0 = unbounded/unavailable)

## Task Graph

| Node | Status | Agent | Risk | Delivery Delta | Depends On | Outcome |
|---|---|---|---|---|---|---|
| A_GROUND_TRUTH_PREFLIGHT | DONE | SCOUT | R1 | NO_DELTA | - | Record authoritative repository, runtime, database, CI and lifecycle grounding plus the migration compatibility map inputs. |
| B_CI_RECONCILIATION | ACTIVE | WORKER | R2 | RISK_RETIREMENT | A_GROUND_TRUTH_PREFLIGHT | Repair the machine-readable Project Contract command encoding and prove CI command resolution and relevant checks. |
| C_DOCUMENTATION_AUTHORITY | PLANNED | WORKER | R1 | DOCUMENTATION_ONLY | A_GROUND_TRUTH_PREFLIGHT | Reconcile current Story Audio documentation with canonical schema 16 and Artifact 93/96/99 QA truth. |
| D_V125_ADOPTION | PLANNED | WORKER | R3 | EXECUTABLE_CAPABILITY | B_CI_RECONCILIATION,C_DOCUMENTATION_AUTHORITY | Adopt the promoted v1.25 RC4 Work Loop through one external package authority while quarantining v1.16 controls as immutable history. |
| E_BASELINE_VERIFICATION | PLANNED | WORKER | R3 | RISK_RETIREMENT | D_V125_ADOPTION | Prove the first bounded no-production Work Loop and verify the resulting Story Audio development baseline. |

## Human Interrupt Policy

Only interrupt the owner for a genuine product decision, risk above ceiling/authorization, destructive/production authority, unresolved blocker, or final Goal acceptance. Worker reports are machine-to-machine state, not owner handoffs.
