# Owner Quickstart — v1.16

## Preferred: Product Goal → automatic lane routing

1. Initialize once with `ai_os.py init ...`; Git repos get managed fail-closed CI and a Codebase Health baseline. Run `ai_os.py assurance` and treat A1 as repo-local governance, not a security boundary.
2. Clarify one Product Goal with observable acceptance.
3. Orchestrator runs `ai_os.py route ... --json`. FAST/STANDARD stay on one Worker; only GOAL pays DAG/subagent overhead.
4. In GOAL lane, Worker completion syncs evidence/result directly into Goal state. **Do not forward worker reports manually.**
5. Owner is interrupted only for product choice, authority/risk escalation, unresolved blocker or final Goal acceptance.

```bash
python scripts/ai_os.py route \
  --outcome "User can complete the primary workflow" \
  --accept "representative behavior is observable" \
  --modify "src/**" \
  --risk R2 --json
```

If router returns `GOAL`, use `prompts/08_GOAL_ORCHESTRATOR.md`.

## Tiny task mode

For a truly small isolated change, `begin → done` remains faster than creating a Goal.


## Goal Judge — automatic orchestration, not owner ceremony

Sau khi bạn chốt Goal/acceptance ở ChatGPT Web, Orchestrator phải bind từng criterion bằng `goal bind-acceptance` **trước Worker đầu tiên**. Bạn không cần tự viết command nếu coding agent/orchestrator có thể tạo probe phù hợp; mục đích là không cho cùng Builder đổi tiêu chuẩn PASS sau khi đã thấy code. `goal done` chỉ chạy contract đã freeze.

## Stateful feature/bug rule

Không yêu cầu owner thiết kế state machine. Worker/Orchestrator dùng `--state-hazard auto`; task stateless không chịu thêm gate. Khi OS phát hiện S2/S3, Worker chỉ cần authority + một transition + một invariant, rồi proof được reuse cho đến khi affected source thay đổi. Khi bug state xuất hiện, dùng bounded `debug state-failure` thay vì trace toàn app.

## Subagent rule — cost-aware in v1.16

Normally you do **not** decide whether to add a Scout/Reviewer. The orchestrator reads `goal next --json`; high-confidence Scout dependencies are auto-created and R2-elevated/R3 emits a machine-readable Reviewer request. Manual override remains available with `--delegation-policy main|scout`.


- Scout: read-only exploration/log/root-cause; cheap model where available.
- Worker: write task; one writer per worktree.
- Reviewer: fresh context only for elevated R2 triggers and all R3; normal R2 relies on frozen acceptance + focused/negative/integration checks.
- Parallel writers only when slices are independent **and** each has an isolated worktree. Parallelism optimizes wall-clock, not necessarily total tokens.

## Health

For executable projects, make the architecture decision once: configure `architecture_boundaries`, or record a temporary explicit reason with `health architecture-decision`.

```bash
python scripts/ai_os.py check --strict
python scripts/ai_os.py doctor
python scripts/ai_os.py goal status --json
python scripts/validate_ai_os.py --ci
python scripts/self_test.py
```

R3/production/destructive authority remains unchanged from v1.8.

Parallel writers are **opt-in** (`--max-parallel >1`); default is 1 because Goal state is repository-local. Use >1 only when the external coding environment manages isolated worktrees and state/merge reconciliation.

## ROI rule

Do not harden R0/R1 just because more gates exist. Use `report` after real delivery; raise rigor only where rework/escaped defects concentrate by risk/surface. North star: accepted Goal throughput per total cost and human attention.

## Guardian and field feedback

For R2-triggered/R3 review, keep Guardian keys outside the repo and let the Guardian launch/sign the fresh reviewer process. For day-to-day Workers, prefer the compact `scripts/ai.py` facade. Periodically inspect `field report` plus Goal `owner_digest.json`; this is how the OS learns where it is expensive, noisy, or under-protective without asking you on every reversible decision.
