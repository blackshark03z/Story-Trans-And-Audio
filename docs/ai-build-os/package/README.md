# Senior AI Build OS — Reusable v1.16

Repository-based operating system cho vibe coding/AI-assisted delivery, tối ưu **accepted Goal / cycle time / human attention / total cost** thay vì số lượt agent hay độ dày ceremony.

### v1.16 lightweight state/debug + production hardening

- **State Hazard S0–S4:** default `auto`; stateless work remains zero-ceremony, while only competing/multi-mechanism state gets transition/temporal gates.
- **Tiny pre-code state contract:** S2+ declares authority + one representative transition + one overwrite/reconciliation invariant.
- **Prove once, reuse until affected source changes:** state proofs are cached by contract + exact command + dependency fingerprint and linked back to immutable evidence.
- **Fast debug memory:** bounded failure signatures identify the violated state/event/invariant without global tracing.
- **Evidence stop-loss:** after two verifier-infrastructure failures of the same method, change the acceptance method instead of spending Worker cycles fixing the test tool.
- **Production hardening:** identifier/path confinement, stale lifecycle-lock recovery, stronger durable-evidence secret redaction, clearer A2–A4 attestation-basis warning.

See `docs/21_STATE_HAZARD_AND_FAST_DEBUG.md`.

### v1.15 trust + field learning

- **Assurance A0–A4:** the OS now reports what is actually enforced. A1 is repo-local; A2 requires an external Guardian key plus trusted-runtime attestation that signer authority is outside Worker control; A3/A4 require trusted runtime attestations for protected merge / isolation.
- **Signed Guardian review:** R2 when review is triggered and all R3 default to a separate external reviewer attestation signed with an Ed25519 private key kept outside Worker authority. CI/validator verifies the bundled signature using an external public key.
- **Compact agent facade:** ordinary Workers can use `scripts/ai.py start|finish|status|next`; the broad kernel CLI remains an internal/admin surface.
- **Field Learning Loop:** normalized friction/failure events, governance-overhead ratios and evidence-backed upgrade candidates; optional privacy-redacted cross-project learning is off by default.
- **Owner decision digest:** assumptions and reversible auto-decisions are recorded without interrupting the owner; low-confidence/high-impact items are surfaced at Goal completion.
- **Risk uncertainty:** unknown mutation-like semantics become a first-class uncertainty signal and default to R2 rather than silently falling through to low risk.
- **Stable core / tunable policy:** `config/kernel_contract.json` formalizes release discipline so field evidence tunes policy before stable-core churn.

See `docs/20_TRUSTED_GUARDIAN_AND_FIELD_LEARNING.md`.

### v1.14 hardening

- Executable projects must make an explicit architecture-boundary decision before protected CI.
- Product CI now reasons in quality capabilities (`test`, `lint`, `typecheck`, `build`) instead of treating any single command as equivalent to a complete quality contract.
- New runtime dependencies require structured capability / alternatives / removal-cost evidence.
- Configurable hard ratchets reject new monster source files and excessive growth in already-large or hotspot files while grandfathering legacy debt.
- Default Build OS regression stays tiered; historical broad suites remain release/trust jobs.

See `docs/19_V114_QUALITY_AND_ANTI_ENTROPY.md`.

## v1.13 — Ship Factory + Codebase Integrity

v1.13 keeps the v1.12 trust kernel and moves the optimization boundary outward:

- **Fail-closed Product CI:** canonical install/quality commands from Project Contract; executable repos cannot go green just because test tooling is absent.
- **Gate-policy SSOT:** `config/gates.json` drives runtime + validator; `.ai/QUALITY_GATES.md` is generated and drift is rejected.
- **FAST / STANDARD / GOAL routing:** Product Goal shaping is always useful, but DAG/subagent ceremony is paid only when dependency/uncertainty/parallel/multiple acceptance surfaces justify it.
- **Codebase Health Ratchet:** legacy debt is grandfathered, new bloat/architecture violations fail, runtime dependency growth needs justification, and hotspot reports prioritize frequently painful code instead of cosmetic cleanup.
- **Runtime telemetry:** outer Codex/Kiro/Claude wrappers can ingest model/token/cost/wall data; Scout routing only learns after enough observations.
- **Regression pyramid + modular seams:** default core feedback is bounded; historical full E2E stays available for release/nightly.

See `docs/17_CODEBASE_HEALTH_RATCHET.md` and `docs/18_LANES_CI_AND_RUNTIME_TELEMETRY.md`.

## v1.12 — Goal Trust + Efficient Handoff

v1.12 hardens the orchestration glue without making R0/R1 heavier:

- **Goal Acceptance Contract is frozen before the first Worker starts.** Each declared Goal criterion must be bound with `goal bind-acceptance` to either a command/probe or an explicit inspection requirement. `goal done` no longer accepts arbitrary last-minute judge commands.
- Goal acceptance probe hashes are frozen; changing the judge after implementation is blocked. Identical Goal-level commands are deduplicated on the same application snapshot.
- **Scout → Worker handoff is now canonical.** Scout result carries root cause, affected files, invariants, risk signals, entry point, confidence and optional recommended scope; the Worker Packet receives the compressed handoff directly.
- HIGH-confidence Scout scope may narrow a broad Worker scope only when the Scout explicitly returns `--recommended-scope`; otherwise original scope stays intact and normal `amend` remains available.
- Scout budget now covers observed input tokens and wall time in addition to summary output; provider-cost cap is optional because pricing varies. Unmeasured usage is never treated as zero.
- Goal `max_revisions_per_task` and `scope_growth_limit_percent` are enforced. Excess growth/revision requires stop-loss acknowledgement or `SPLIT_OR_REPLAN`.
- Verification commands are deduplicated by **exact command + application snapshot + execution mode**. One execution may satisfy focused/negative/integration/frozen-acceptance gates; changed snapshots force a fresh run.
- Unknown write scope is conservatively treated as overlapping for parallel planning. Sensitive shared contract surfaces are also kept sequential.
- Historical v1.12 trust naming distinguished repo-declared review from external attestation. v1.15 raises the default: triggered R2 and all R3 require `SIGNED_GUARDIAN` evidence; unsigned external JSON is no longer sufficient under the default policy.

### Goal acceptance example

```bash
python scripts/ai_os.py goal begin \
  --goal "User can import a CSV and see validated rows" \
  --accept "valid fixture imports successfully" \
  --accept "invalid rows are surfaced" \
  --risk-ceiling R2

# Orchestrator binds the judge before the first Worker starts.
python scripts/ai_os.py goal bind-acceptance \
  --criterion 1 \
  --command "python -m pytest -q tests/e2e/test_import_valid.py" \
  --probe-file tests/e2e/test_import_valid.py
python scripts/ai_os.py goal bind-acceptance \
  --criterion 2 \
  --command "python -m pytest -q tests/e2e/test_import_invalid.py" \
  --probe-file tests/e2e/test_import_invalid.py

# Goal done runs only the frozen contract; no new --acceptance-command is accepted.
python scripts/ai_os.py goal done --output-inspected-by agent:orchestrator
```

## v1.11 — Cost-Aware Automatic Delegation

v1.11 keeps v1.10 quality gates unchanged and optimizes **where subagents are worth their bootstrap cost**:

- `goal add-task --delegation-policy auto` is the default. Small explicit R0/R1 work (1–2 files) stays on one Worker.
- Discovery-heavy work with high-confidence uncertainty + broad scope automatically gets a read-only `__SCOUT` dependency. No owner forwarding is required.
- Auto Scouts are capped per Goal (`--max-auto-scouts`, default 2) and must return a compact summary (`--scout-summary-token-budget`, default ~350 tokens).
- `goal next --json` now emits a machine-readable `delegation` plan with model class, hard/advisory action, reasons, parallel-safe groups and held-overlapping writers.
- Parallel writers are selected only when declared write scopes are clearly disjoint. The default writer budget stays 1; if two independent nodes exist, v1.11 surfaces a `PARALLEL_OPPORTUNITY` for environments that can provide isolated worktrees. This targets wall-clock, not token reduction.
- When R2-elevated or R3 needs fresh review, `done` writes `.ai/runtime/delegation_request.json` with `SPAWN_REVIEWER`, so an outer orchestrator can spawn the reviewer automatically instead of making the owner relay the request.
- Optional Scout/Reviewer usage (`input/output tokens`, provider cost, wall minutes) can be recorded at `goal node-done`; Goal results/report expose read-only delegation cost separately.
- No extra specialist personas are introduced. Canonical roles remain Scout / Worker / Reviewer.

Cost rule: **delegate only when context avoided + parallel time saved + fresh-context assurance exceeds bootstrap + duplicate context + merge cost**.

### Automatic Scout example

```bash
python scripts/ai_os.py goal add-task \
  --node BUG \
  --outcome "Diagnose unknown intermittent session failure" \
  --risk R1 \
  --delivery-delta EXECUTABLE_CAPABILITY \
  --modify "src/**" \
  --accept "regression is fixed"

# v1.11 automatically inserts BUG__SCOUT when the benefit threshold is high.
python scripts/ai_os.py goal next --json
```

## v1.10 — Risk-Proportional Acceptance

v1.10 giữ Goal Orchestration của v1.9 nhưng tách rõ **Spec Author → Builder → Judge** ở đúng nơi có ROI cao:

- R0/R1 vẫn lean và self-verified; không thêm reviewer/gate đồng loạt.
- Goal-linked R2/R3 Worker phải có `--acceptance-command` khai **trước** `goal start`. Contract được đóng băng và tự chạy trong `done`.
- `--probe-file` là optional acceptance/test probe: SHA256 được khóa trước Worker start; Worker sửa probe sẽ bị chặn.
- `--expected-output` trong Goal node trở thành marker của frozen acceptance contract, không phải marker Worker nghĩ ra sau khi code.
- R2 review là **trigger-based** (`auto`): first-pass fail, >8 file, risk escalation, hoặc project/auth/security/financial boundary. `--review-policy required|none` chỉ được quyết định trước Worker start.
- R3 vẫn bắt independent review + rollback/full critical gates như trước.
- Goal acceptance ghi số attempt, Goal first-pass, Goal cycle time, aggregated AI/provider cost, human review/wait và token totals.
- `report` phân đoạn quality theo **risk** và **actual changed surface**, rồi hiển thị cost/accepted Goal để dữ liệu thực quyết định nơi cần nâng/hạ rigor.
- Goal acceptance có heuristic cảnh báo tiêu chí quá mơ hồ; không áp fixed spec-time ceremony.

### R2 Goal node example

```bash
python scripts/ai_os.py goal add-task \
  --node W1 \
  --outcome "Duplicate signup is rejected without creating another user" \
  --risk R2 \
  --delivery-delta EXECUTABLE_CAPABILITY \
  --modify "src/api/**" \
  --accept "duplicate email returns 409 and user count is unchanged" \
  --acceptance-command "python -m pytest -q tests/acceptance/test_duplicate_signup.py" \
  --probe-file tests/acceptance/test_duplicate_signup.py

python scripts/ai_os.py goal start --node W1
# Worker implements; normal done automatically runs the frozen acceptance command.
```

Task-first `begin → done` remains fully supported for tiny/standalone work, but the strongest builder/judge separation is intentionally a Goal-mode feature.

## v1.9 — Goal Mode

v1.10 giữ nguyên Task Execution Kernel của v1.8 nhưng thêm **Goal Orchestration Layer** để owner không còn phải copy task/report giữa Lead và Worker.

```text
Owner Goal → Orchestrator → dependency DAG → Scout/Worker/Reviewer → Goal Acceptance → Owner
```

- `goal begin`: tạo outcome/acceptance/risk ceiling/budget cấp Goal.
- `goal add-task`: orchestrator tạo DAG nhỏ, chỉ gồm work nằm trên đường tới Goal acceptance.
- `goal next --json`: trả wave READY; ưu tiên shipping path và cho biết khi parallel writers cần isolated worktrees.
- `goal start --node`: materialize node thành task v1.8 bình thường; không lặp lại toàn bộ CLI flags.
- Worker `done` tự sync evidence/result về Goal node; **không cần owner chuyển tiếp report**.
- Scout read-only có `goal node-done` để trả summary nhỏ mà không phải mở task/evidence nặng.
- `goal done`: chạy goal-level behavior acceptance và ghi `.ai/goals/<id>/result.json`.
- Risk ceiling được enforce lúc start và acceptance-time actual-risk reconciliation.

### Goal-first quick example

```bash
python scripts/ai_os.py goal begin \
  --goal "User can import a CSV and see validated rows" \
  --accept "valid fixture imports" \
  --accept "invalid rows are surfaced" \
  --risk-ceiling R2

# Orchestrator/agent plans nodes, then loops:
python scripts/ai_os.py goal next --json
python scripts/ai_os.py goal start --node W1
# worker patches + normal `done`
python scripts/ai_os.py goal next --json

# Bind Goal acceptance before the first Worker start (see Goal Trust section).
python scripts/ai_os.py goal done --output-inspected-by agent:orchestrator
```

Task-first `begin → done` remains fully supported for tiny work.

## v1.8 execution kernel retained

- **Commit-aware CI provenance:** `init` tự cài `.github/workflows/ai-build-os.yml`; CI bind application delta trong commit/PR với SHA256 từng file đã được verify trong evidence mới của cùng change set. Commit sau `done` không còn bị false-fail vì STATE/HEAD local.
- **Cross-revision stop-loss:** sau 2 revision liên tiếp của cùng task có `first_pass_accepted=no`, revision kế tiếp bị chặn cho tới khi có `--stop-loss-ack` mô tả root-cause hypothesis đã đổi. Task bình thường không thêm ceremony.
- **Breaker abuse telemetry:** override được lưu vào immutable history và `report` thống kê tần suất/lý do; >20% recent accepted work sẽ cảnh báo.
- **Project-sensitive business terms:** `PROJECT.md` có `Sensitive business terms` để nâng actual risk lên R2 cho domain-specific logic mà generic path/regex không biết.
- **Optional semantic output assertion:** `done --expected-output "..."` buộc marker thật sự xuất hiện trong stdout/stderr đã lưu, tăng assurance mà không thêm lifecycle round-trip.
- **Risk không thể downgrade:** `--risk auto` là mặc định; side effect và declared surface tạo authorization-time risk floor. Overwrite/delete/in-place mutation tự lên R3.
- **Acceptance-time risk reconciliation:** `done/close` đọc task-delta + changed lines thực tế; nếu code cho thấy mutation/persistence/external/shared surface cao hơn risk đã authorize, task bị chặn để `amend` và chạy lại gate đúng tier.
- **Shipping breaker thật sự enforce:** breaker hiện trong `status`, `next`, worker packet và chặn `begin` non-shipping khi ACTIVE; override phải explicit + có lý do.
- **Delivery Delta reconciliation:** shipping delta bị reject khi task delta rỗng hoặc chỉ docs/tests, ngăn fake `EXECUTABLE_CAPABILITY` reset breaker.
- **Scope theo task delta:** dirty worktree có sẵn không chặn task. Chỉ thay đổi phát sinh sau baseline mới bị so với `Modify/Create`; nếu worker sửa tiếp file dirty cũ, file đó trở thành task delta và bị kiểm tra scope.
- **Fast Lane ít ceremony:** `begin` auto-claim mặc định; R0/R1 chỉ bắt buộc focused check. Negative-path chỉ bắt buộc khi task có failure behavior (`--negative-required`).
- **Lifecycle đầy đủ:** `claim`, `pause`, `resume`, `amend`, `abort`; không còn state “có trong docs nhưng không có command”.
- **Compact worker packet:** `CONTEXT_CAPSULE.md` là packet canonical cho worker; R0/R1 nhắm < ~400 token và không yêu cầu đọc lại toàn bộ `ACTIVE_TASK`.
- **Risk-proportional evidence:** R0/R1 dùng `COMPACT` bundle (log cap nhỏ hơn); R2/R3 dùng `FULL` bundle.
- **Product CI:** `scripts/project_ci.py` auto-detect các check chuẩn của Node/Python/Go/Rust; CI template chạy cả OS regression lẫn product checks.
- **Strict init sạch:** `init` tạo SC-001 duy nhất, điền baseline/default hợp lý và auto-detect technical baseline khi có thể.

## Luồng mặc định cho vibe coding

```text
init once
  ↓
begin   # risk auto + auto-claim
  ↓
inspect smallest relevant surface
  ↓
smallest patch
  ↓
cheapest relevant verification
  ↓
inspect output + task delta
  ↓
done
```

### Init

```bash
python scripts/ai_os.py init \
  --project-id receipt-ai \
  --owner "Minh" \
  --problem "Nhập hóa đơn thủ công tốn thời gian" \
  --target-user "Người quản lý chi tiêu" \
  --primary-action "Tải ảnh hóa đơn" \
  --observable-result "Hiển thị cửa hàng, ngày và tổng tiền" \
  --mvp-goal "Ảnh hóa đơn trở thành giao dịch có thể chỉnh sửa"
```

### Start task — không cần khai risk nếu muốn auto

```bash
python scripts/ai_os.py begin \
  --task-id TASK-001 \
  --outcome "Ảnh mẫu trả về ba trường đã trích xuất" \
  --success-criterion SC-001 \
  --accept "Ảnh fixture trả về merchant/date/total đúng" \
  --delivery-delta EXECUTABLE_CAPABILITY \
  --modify "src/**,tests/**" \
  --create "src/**,tests/**"
```

`begin` auto-claim. Dùng `--accept` lặp lại để đưa acceptance cụ thể thẳng vào worker packet; dùng `--ready` nếu muốn scheduler/lead tạo task trước rồi worker `claim` sau.

Nếu task R1 có failure behavior cần chứng minh, thêm `--negative-required`.

### Fast Lane done

```bash
python scripts/ai_os.py done \
  --outcome "Email hợp lệ được chấp nhận" \
  --focused-command "python -m pytest -q tests/test_email.py" \
  --output-inspected-by agent:worker \
  --first-pass-accepted yes
```

Task có `Negative path required: yes` phải thêm `--negative-command`. R2 luôn cần negative + affected integration. R3 thêm rollback rehearsal + full suite + independent snapshot-bound review và authorization.

## Khi scope khám phá rộng hơn

Không khai `src/**` từ đầu chỉ để tránh bị block. Amend đúng file vừa phát hiện:

```bash
python scripts/ai_os.py amend \
  --add-modify src/adapters/email.py \
  --reason "root cause crosses existing adapter boundary"
```

Baseline task không đổi. Nếu amendment làm side effect/risk tăng, gate tự escalate; không được downgrade risk hiện tại.

## Dirty worktree

Tại `begin`, v1.8 lưu `.ai/runtime/task_baseline.json` gồm fingerprint các file đã dirty. `check/done` dùng:

```text
TASK_DELTA = current worktree - task-start baseline
TASK_DELTA ⊆ authorized Modify/Create
```

Do đó thay đổi cũ không liên quan không làm task fail, nhưng worker cũng không thể “ẩn” thay đổi mới trong một file đã dirty trước task.

## Acceptance-time reconciliation

`begin` vẫn nhẹ và dựa trên intent đã khai. Trước acceptance, v1.8 kiểm lại sự thật:

```text
declared intent/risk
  ↓
implementation
  ↓
actual task-delta paths + bounded changed lines
  ↓
risk reconciliation + delivery-delta reconciliation
  ↓
required gates / accept
```

Nếu actual risk cao hơn task hiện tại, `done/close` fail closed và yêu cầu `amend --risk ...`. Project có thể thêm path riêng trong `PROJECT.md`:

```text
## Risk Surface Map
- R2 paths: src/security/**,src/persistence/**
- R3 paths: migrations/**,infra/production/**,billing/**
- Sensitive business terms: wallet_balance,refund_amount,inventory_quantity
```

Classifier chỉ dùng high-signal heuristic để tránh biến Fast Lane thành static-analysis framework.

## Shipping circuit breaker

Ngưỡng lấy từ `Maximum consecutive non-shipping tasks` trong Project Contract. Khi ACTIVE, `begin` chỉ nhận `USER_VISIBLE_BEHAVIOR` hoặc `EXECUTABLE_CAPABILITY`, trừ explicit exception:

```bash
python scripts/ai_os.py begin ... \
  --delivery-delta NO_DELTA \
  --breaker-override \
  --breaker-override-reason "urgent production defect containment"
```

Shipping declaration vẫn bị reconcile lúc close: delta rỗng hoặc docs/tests-only không được tính là shipping.

## Lifecycle

| Lệnh | Công dụng |
|---|---|
| `init` | Khởi tạo product contract + technical baseline |
| `begin` / `start` | Tạo task, auto risk-floor, auto-claim mặc định |
| `claim` | `READY → ACTIVE` |
| `pause` | Tạm dừng và release writer lease |
| `resume` | Claim lại task paused, giữ nguyên baseline |
| `amend` | Mở rộng scope/side-effect có lý do, không restart task |
| `abort` | Hủy task chỉ khi task delta đã sạch; tránh “launder” code dở sang baseline kế tiếp |
| `runnable` | Ghi first-runnable khi metric này thật sự hữu ích |
| `done` | Reconcile actual risk/delivery delta, chạy gate, tạo evidence, close |
| `check` | Kiểm tra risk floor, task delta, evidence, Git/history |
| `doctor` | Kiểm tra môi trường/transaction |
| `status` | Hiển thị risk, task delta, pre-existing dirty, shipping breaker và next action |
| `next` | Một hành động tiếp theo |
| `history` / `report` / `reconcile` | Learning loop sau delivery |

## Evidence

```text
.ai/evidence/TASK-001/r001/
├── manifest.json          # machine authority
├── bundle.sha256.json
├── EVIDENCE_INDEX.md
├── WORKER_REPORT.md
├── logs/
├── artifacts/
└── review/
```

- R0/R1: `evidence_mode=COMPACT`, stdout/stderr mỗi stream cap 32 KiB.
- R2/R3: `evidence_mode=FULL`, log cap 256 KiB.
- Manifest lưu verified application snapshot, `task_delta_files` và `task_delta_file_hashes` (fingerprint SHA256/MISSING cho từng path).
- `--expected-output` là optional semantic assertion trên log đã lưu; không được gọi là bằng chứng reviewer đã đọc output.
- Accepted bundle/revision không bị overwrite.

## Commit-aware CI + Product CI

`init` mặc định tự tạo `.github/workflows/ai-build-os.yml` trong Git repo (dùng `init --no-ci` để opt out). Workflow chạy provenance + product checks trên mọi PR/push; `self_test.py` chỉ chạy khi `scripts/*.py` hoặc templates của Build OS đổi để không cộng latency cố định vào task app bình thường:

```bash
python scripts/validate_ai_os.py --ci
python scripts/project_ci.py --ci
# python scripts/self_test.py  # conditional khi Build OS core đổi
```

`--ci` không so `STATE.HEAD == current HEAD` như local check. Thay vào đó nó lấy commit delta từ GitHub base/push base, tìm evidence manifest mới trong cùng change set, verify bundle/history, rồi yêu cầu fingerprint hiện tại của từng application path phải khớp `task_delta_file_hashes` đã verify. Code sửa sau evidence nhưng trước commit sẽ fail provenance gate.

CI này là **repository integrity boundary**, không phải chữ ký mật mã: actor có toàn quyền sửa repo vẫn có thể giả mạo toàn bộ evidence/history nếu không có external trusted signer. Với GitHub protected branch + required checks, nó đủ để ép workflow ở merge boundary mà không thêm bước cho worker. Project đặc thù vẫn nên bổ sung browser/E2E/release CI riêng.

## Kiểm định package

```bash
python -m py_compile scripts/*.py
python scripts/validate_ai_os.py --template
python scripts/self_test.py
python scripts/ai_os.py doctor
```

Xem thêm `docs/12_AUTOMATION_AND_FAST_LANE.md`, `docs/13_EVIDENCE_INTEGRITY.md`, `docs/15_CI_AND_MULTI_AGENT.md`, `UPGRADE_v1.5_TO_v1.6.md` và `UPGRADE_v1.6_TO_v1.7.md` và `UPGRADE_v1.7_TO_v1.8.md`.
