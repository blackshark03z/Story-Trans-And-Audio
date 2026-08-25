# Evidence Index

- Task ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-F_DOCUMENTATION_AUTHORITY_V2
- Task revision: 1
- Success Criterion: Current authority surfaces state schema16, stopped runtime, Artifact93 stale, Artifact99 active approved, Artifact96 active pending, and no production action authorized; stale Artifact93 QA instructions are absent.
- Accepted outcome: Six authority documents now agree on the green 1,970-test/schema16/stopped-runtime baseline, current Artifact99 approved and Artifact96 pending bindings, stale historical Artifact93 status, and a no-production v1.25 compatibility decision boundary.
- Generated: 2026-08-25T11:11:14+00:00
- Risk tier: R2
- Verified snapshot SHA256: d25fd6109e85c8bd7b50f0256698fbdb74de673e6768e00496d81e73cf27cbcc
- Verified HEAD: a4e3490db9ed9d00fc0a4d08d4ec2f99d62cae09
- Final verdict: PASS
- Evidence schema: 4
- Evidence mode: FULL
- Manifest: manifest.json

## Checks

| ID | Kind | Command | Exit | Result | Inspection | Stdout SHA256 | Stderr SHA256 | Started | Completed |
|---|---|---|---:|---|---|---|---|---|---|
| EV-001 | focused,negative,integration,acceptance_contract | `git diff --check` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `ca02f66f4dba74312e1136575f259dc13a8fe21ef95b937c7a45f4aa1b7f1204` | 2026-08-25T11:11:13+00:00 | 2026-08-25T11:11:13+00:00 |

## Output Assertions

- NONE

## Runtime Artifacts

- NONE

## Side Effects and Cleanup

- Cleanup/rollback verification: Documentation-only diff; no runtime, database, artifact, provider, or production process was touched.
- Known limits: Historical chronology retains old point-in-time schema and artifact statements below the explicitly authoritative current-state summaries; stale-current-instruction absence was separately inspected with ripgrep.
