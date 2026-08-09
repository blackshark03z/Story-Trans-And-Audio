# Start Here — v1.16


## Default operating mode

Owner supplies a clear **Product Goal + falsifiable acceptance**, then the Orchestrator routes execution before materializing ceremony:

- `FAST` — tiny/clear R0–R1 change, usually 1–2 explicit files, one Worker.
- `STANDARD` — bounded single outcome (often 2–5 files/R1–R2), one Worker on the Task kernel.
- `GOAL` — dependency DAG, meaningful uncertainty, multiple acceptance surfaces or useful parallelism.

Use `python scripts/ai_os.py route ... --json`. Product Goal shaping does **not** imply Goal Mode. Canonical manager prompt: `prompts/08_GOAL_ORCHESTRATOR.md`.

## Authority

```text
runtime/data
> Git application snapshot + task-start baseline
> immutable evidence manifest
> PROJECT / ACTIVE_TASK / STATE
> chat history
```

Worker chỉ sửa application code khi task `ACTIVE`, lease `CLAIMED`, identity `VERIFIED`.

## New project

Chạy `init`, rồi `check --strict`. Init v1.16 chỉ tạo SC-001 thật sự và auto-detect technical baseline khi repo có marker phổ biến.

## Trust check

Run `python scripts/ai_os.py assurance`. A1 means useful repo-local governance but **not** protection from a Worker that can rewrite governance state. Configure an external Guardian key and externally attest signer authority for A2 before relying on R2-triggered/R3 reviewer independence.

For ordinary agent work prefer `python scripts/ai.py start|finish|status|next`; use the full kernel CLI only when the compact facade returns `ACTION_REQUIRED` or the workflow is exceptional.

## New task

`begin` mặc định:

- `--risk auto`;
- auto-claim writer lease;
- capture fingerprint của pre-existing dirty files;
- generate compact worker packet.

Dùng `--ready` nếu cần tách authorize và claim.

## Verification lanes

- **R0:** focused check + output/task-delta inspection phù hợp task.
- **R1:** như R0; thêm negative chỉ khi `--negative-required`/failure behavior thật.
- **R2:** focused + negative + affected integration/runtime.
- **R3:** R2 gates + rollback rehearsal + full suite/critical check + approval + independent snapshot-bound review.

Risk floor không thể hạ bằng cách khai `R0` thủ công. `done/close` còn reconcile lại actual task delta; nếu actual floor cao hơn, phải amend/escalate trước acceptance.

## State/temporal work without heavy ceremony

`--state-hazard auto` is default. S0/S1 adds no new verification gate. Only S2+ asks for a tiny authority/transition/invariant contract; S3+ adds a temporal/background-writer proof. Exact state proofs are reused automatically while the contract + declared dependency fingerprint stay unchanged. See `docs/21_STATE_HAZARD_AND_FAST_DEBUG.md`.

When verifier infrastructure itself fails twice, use `debug evidence-infra-failure`; `next` will require a change of acceptance method rather than another expensive retry of the same harness.

## Scope discovery

Nếu root cause cần thêm file, dùng `amend --add-modify/--add-create --reason ...`. Không widen scope im lặng và không restart task chỉ vì một adjacent file.

## Runnable

`runnable` là metric tùy chọn cho user-visible/executable tasks; không phải ceremony bắt buộc trước `done`.

## Done

`done` reconcile actual risk + Delivery Delta, chạy verification, kiểm **task delta** (không phải toàn dirty worktree), tạo evidence và release lease.

Sau close: `status`/`next`, định kỳ `report`, và `reconcile` khi có operational feedback.

## Shipping breaker

`status`/capsule/`next` luôn surface breaker. Khi ACTIVE, `begin` non-shipping bị chặn trừ explicit override có lý do; shipping delta giả với empty/docs/tests-only task delta bị reject lúc close.

## Learning from real work

Use `python scripts/ai_os.py field report` periodically. Optional cross-project learning is `field report --global` after explicitly enabling the privacy-redacted global store. Upgrade candidates are experiments, never automatic policy mutations.
