# v1.16

- Added lightweight State Hazard S0–S4 classification. S0/S1 add no required proof; S2+ freezes a tiny authority/transition/invariant contract; S3+ adds temporal/background-writer verification.
- Added cross-task state proof reuse keyed by contract + exact proof command + declared dependency fingerprint, linked to immutable accepted evidence.
- Added bounded `debug state-failure` signatures for faster root-cause localization without global tracing.
- Added two-strike `debug evidence-infra-failure` stop-loss; `next` tells Workers to change acceptance method instead of repeatedly repairing the same verifier.
- Fixed task/Goal/node identifier path traversal with namespace validation/confinement across evidence/history/goal records.
- Added dead-PID lifecycle-lock recovery while retaining fail-closed behavior for live/fresh locks.
- Expanded durable evidence secret redaction for auth headers/cookies/JWT/private keys/common tokens/credential URLs.
- Assurance output now states `attestation_basis` so A2–A4 trusted-runtime environment claims are not mistaken for independent repo-kernel proof.
- Added focused v1.16 regression coverage; historical v1.12–v1.15 matrices remain compatibility/trust suites.

# v1.15

- Added explicit A0–A4 assurance reporting; A1 is documented as repo-local governance, and A2 requires explicit trusted-runtime attestation of external Guardian authority rather than merely finding a public key.
- Added external Ed25519 Guardian keys and separate reviewer-process attestation; triggered R2 and all R3 default to `SIGNED_GUARDIAN`.
- CI/validator now cryptographically verifies triggered R2 and R3 Guardian attestations using a public key supplied from outside the repository; schema v3 signatures bind the review-report hash as well as task/snapshot/session identity.
- Added compact `scripts/ai.py start|finish|status|next` facade for coding agents.
- Added first-class semantic risk uncertainty with configurable fail-closed R2 escalation.
- Added Goal assumption/auto-decision ledger and owner digest.
- Added local and optional privacy-redacted cross-project Field Learning Loop, pain ranking, governance-overhead ratios, empirical p50/p75/p95 budgets and evidence-backed upgrade candidates.
- Added stable-core / tunable-policy release contract; field telemetry can recommend but never self-edit policy/kernel.

# v1.14

- Added explicit architecture decision gate for executable projects.
- Added machine-readable quality capability policy with required/recommended capabilities and substantive waivers.
- Added dedicated lint/typecheck Project Contract commands.
- Replaced free-form runtime dependency approval with structured capability / alternatives / removal-cost evidence.
- Added configurable anti-monster-file and hotspot growth hard ratchets scoped to the active task baseline.
- Added focused v1.14 regression matrix and kept historical broad matrices outside ordinary product-task paths.

# v1.13.0

- Fail-closed Product CI with canonical install/quality commands and pnpm/yarn/uv/poetry setup paths.
- Machine-readable gate-policy SSOT (`config/gates.json`) generates `.ai/QUALITY_GATES.md`; validator rejects drift.
- FAST/STANDARD/GOAL lane router separates Product Goal shaping from Goal DAG ceremony.
- Provider-neutral runtime telemetry ingestion plus conservative historical Scout feedback.
- Codebase Health Ratchet: legacy-debt baseline, new bloat/architecture hard gates, task-local dependency justification, LOC/file/tree/Git-size ratchets and hotspot report; filesystem scans prune heavy ignored directories.
- Initial kernel modularization: CLI schema plus project, policy, lane, telemetry, health and reporting support modules moved out of `ai_os.py`; lifecycle entrypoint reduced to ~1.5k lines without a rewrite.
- Regression pyramid: default fast/current suite, focused trust suites, historical full suite isolated for release/nightly.

# Changelog

## 1.12.0

- Freeze Goal Acceptance Contract before first Writer; `goal done` cannot introduce a new judge command.
- Bind each Goal criterion to a command/probe or declared inspection requirement; freeze probe hashes.
- Inject structured Scout handoff into Worker Packet; HIGH-confidence explicit recommended scope may narrow broad scope.
- Enforce Scout input/wall budget when telemetry exists; keep unmeasured usage distinct from zero.
- Enforce Goal revision and scope-growth budgets.
- Deduplicate exact verification executions on the same application snapshot and record `checks[].satisfies`.
- Fail closed on unknown parallel write scope and sensitive contract coupling.
- Rename repo-authored review trust to `DECLARED_REPO_REVIEW`; add optional outer-runtime attestation hook.

## 1.11.0

- Added conservative Automatic Delegation Planner above Goal DAG execution.
- High-confidence discovery-heavy Worker nodes auto-insert a capped cheap/read-only Scout dependency; small explicit R0/R1 nodes stay single-worker.
- `goal next --json` now emits machine-readable delegation recommendations, parallel-safe groups, overlap-held nodes, and advisory parallel opportunities.
- Elevated R2 / R3 missing review now writes `.ai/runtime/delegation_request.json` with a hard `SPAWN_REVIEWER` request for outer orchestrators.
- Scout summaries are token-budgeted (default ~350) and optional Scout/Reviewer token/cost/wall telemetry is stored in Goal results.
- Parallel writer selection is scope-aware and conservative; default max_parallel remains 1 so speed optimizations never silently increase merge risk/token duplication.
- Added delegation regression coverage and cost reporting without adding Fast Lane ceremony.

## 1.10.0

- Added frozen Goal acceptance contracts for Goal-linked R2/R3 Worker nodes.
- `goal add-task` now supports `--acceptance-command`, `--expected-output`, `--probe-file` and predeclared R2 `--review-policy`.
- `goal start` freezes the acceptance contract and SHA256 of optional probe files before the Worker writes code.
- `done` automatically executes frozen acceptance commands and rejects modified probe files/contract hashes.
- Added trigger-based R2 review: first-pass failure, large task delta, risk escalation, project-sensitive boundary or auth/security/financial path; R3 review remains mandatory.
- Added Goal acceptance-attempt tracking, Goal first-pass acceptance and aggregated Goal cycle/cost/human/token metrics.
- Expanded `report` with quality segmentation by risk and actual changed surface plus cost per accepted Goal.
- Added high-confidence warnings for obviously non-falsifiable Goal acceptance without introducing fixed spec ceremony.
- Updated worker packet/prompts for builder/judge separation while keeping R0/R1 lean.

## 1.9.0

- Added Goal Orchestration Layer above the v1.8 task execution kernel.
- Added `.ai/GOAL.md`, `.ai/GOAL_STATE.json` and per-goal plan/result/decision records.
- Added `goal begin/add-task/next/start/status/discover/scout-done/defer/block/resume/abort/done`.
- Goal-linked task completion automatically syncs outcome/evidence/risk back into the DAG; owner no longer forwards worker reports.
- Added Goal risk ceiling enforcement both before task start and against acceptance-time actual risk.
- Added lightweight read-only Scout path and explicit delegation guidance for Scout/Worker/Reviewer.
- Added dependency-aware ready waves with isolated-worktree warning for parallel writers.
- Product Goal completion requires accepted shipping work plus explicit goal-level acceptance commands.
- Evidence/history/runtime worker packets now carry Goal ID/node linkage.
- Added Goal orchestration regression coverage and canonical orchestrator/scout/acceptance prompts.

## 1.8.0

- Added commit-aware CI provenance mode (`validate_ai_os.py --ci`) that binds committed application paths to v1.8 evidence added in the same change set.
- Evidence schema v4 now stores `task_delta_file_hashes` for each verified application path, including deletions via `MISSING`.
- `init` auto-installs `.github/workflows/ai-build-os.yml` in Git repositories unless `--no-ci` is used.
- CI mode intentionally ignores local pre-commit HEAD/worktree continuity and instead verifies bundle/history integrity plus current per-file fingerprints.
- Added cross-revision stop-loss: two consecutive prior revisions with `first_pass_accepted=no` require `--stop-loss-ack` before starting the next revision.
- Persisted shipping-breaker override flag/reason into immutable history and surfaced usage in `report`, including >20% abuse warning.
- Added optional project-specific `Sensitive business terms` for acceptance-time R2 escalation without broad noisy global keywords.
- Added optional repeatable `done --expected-output` semantic assertions against stored verification stdout/stderr.
- Added regression coverage for commit-after-done CI pass, post-evidence source drift CI failure, stop-loss, sensitive business terms and breaker override telemetry.

## 1.7.0

- Added acceptance-time actual-risk reconciliation from real task-delta paths and bounded changed lines.
- Added high-signal detection for persistent/destructive mutations, persistence access, shared/API/security/background surfaces and side-effecting network calls.
- Added optional project-specific `Risk Surface Map` (`R2 paths` / `R3 paths`) for repository naming conventions that generic heuristics cannot know.
- Made Shipping Circuit Breaker visible in `status`, `next`, machine runtime state and worker packet.
- Enforced active Shipping Circuit Breaker at `begin`; non-shipping exceptions require explicit override plus audit reason.
- Replaced hard-coded breaker threshold with the Project Contract `Maximum consecutive non-shipping tasks`.
- Added Delivery Delta reconciliation: empty or docs/tests-only task delta cannot close as `USER_VISIBLE_BEHAVIOR` or `EXECUTABLE_CAPABILITY`.
- Prevented stale low-risk evidence from being reused after risk/profile amendment.
- Added immutable history fields for acceptance-time actual risk floor/reasons.
- Expanded regression tests for actual-diff risk escalation, fake shipping and breaker enforcement.

## 1.6.0

- Added non-downgradable automatic risk floors from side effects and sensitive/shared change surfaces.
- Replaced whole-dirty-worktree scope checks with task-start baseline fingerprints and task-delta enforcement.
- Added complete lifecycle commands: `claim`, `pause`, `resume`, `amend`, `abort`; `begin` now auto-claims by default with `--ready` opt-out.
- Added scope amendment without task restart; risk can only remain or escalate.
- Rebuilt CONTEXT_CAPSULE as a compact worker packet; LEAN target is under ~400 coordination tokens.
- Made R1 negative-path verification trigger-based instead of universal; R2/R3 remain strict.
- Require explicit output inspection for R1+ verification.
- Added COMPACT evidence mode for R0/R1 and FULL mode for R2/R3; manifests record task delta.
- R3 completion now requires an explicit rollback rehearsal/proof command in evidence.
- Added `project_ci.py` and CI template support for product checks across common Node/Python/Go/Rust repos.
- `init` now emits one real SC-001, auto-detects technical baseline and passes strict validation without template placeholder noise.
- Expanded regression tests for risk-underclassification, pre-existing dirty worktrees, scope amendment, lifecycle recovery and abort laundering prevention.

## 1.5.0

- Immutable evidence bundles by task revision with machine-readable manifests.
- Git application snapshot binding: HEAD, tracked diff, untracked manifest and changed files.
- Recomputed log/artifact/review hashes and bundle-level integrity manifest.
- Explicit output inspection states; stored, redacted and bounded stdout/stderr.
- `done` and `close` require ACTIVE/CLAIMED/VERIFIED writer state.
- First-runnable timing is only recorded from explicit evidence.
- Structured independent R3 review bound to task revision and snapshot.
- Git scope enforcement, auto task revision and capped STATE history.
- Transaction journal, machine-readable runtime mirrors and immutable history records.
- New `init`, `doctor`, `status`, `next`, `history`, `report` and `reconcile` commands.
- Cost-quality learning loop with post-close rework/defect reconciliation.
- Default command execution uses argv rather than shell.
- Added CI and multi-agent operating guidance.

## 1.3.0

- Sửa Git fingerprint bằng cách loại trừ `.ai/**` khỏi application worktree state.
- Thêm Fast Lane `begin → done` với automated checks, structured evidence và artifact hashes.
- Thêm evidence enforcement theo risk tier; R3 completion cần review report độc lập.
- Thêm repository lifecycle lock, atomic checkpoint và atomic ledger writes.
- Rút gọn LEAN task; chuyển policy cố định về AGENTS.
- Đổi `GPT-5.6 Profile` thành model-neutral `Execution Profile`.
- Metric chưa đo trong cost ledger được để trống thay vì mặc định 0.
- Validator không còn scan toàn bộ host application source.
- Self-test chạy lifecycle trong Git repo thật và kiểm tra tampered evidence.

## 1.2.0

- Thêm Fast Lane cho R0/R1 và Startup Brief theo risk.
- Thêm `scripts/ai_os.py` với `start`, `runnable`, `check`, `close`.
- Validator kiểm tra fingerprint chéo, Git thật, risk/profile, lease/completion, R3, mutation authorization, evidence path và ledger uniqueness.
- Sửa capsule refresher để tách đúng nested Allowed/Prohibited và chỉ lấy decision của task hiện tại.
- Mở rộng cost ledger với cycle time, first runnable, first-pass acceptance, coordination/implementation tokens, human wait, escaped defect và rollback.
- Thêm deterministic self-test cho các regression quan trọng.

## 1.1.0

- Repository-based continuity, single-writer lease, context capsule, risk gates, shipping circuit breaker, economic stop-loss và basic ledger.

Version chính thức luôn đọc từ `VERSION`.
