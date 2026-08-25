# Evidence Index

- Task ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-C_RESPONSIVE_LAYOUT
- Task revision: 1
- Success Criterion: The primary production action and required preflight content are usable at 1366x768 with no horizontal or nested overflow, while 1920 layout remains valid.
- Accepted outcome: Responsive production workbench and preflight hierarchy pass at 1366x768 and 1920x1080 without horizontal or nested scrolling.
- Generated: 2026-08-25T09:21:23+00:00
- Risk tier: R2
- Verified snapshot SHA256: 68165e9069fdc7d3c7d9d006250ae35cf396b80002fec1c625bc25364ebe3325
- Verified HEAD: da88199671c4259cf6e3ea6d464a3a38a0ec292d
- Final verdict: PASS
- Evidence schema: 4
- Evidence mode: FULL
- Manifest: manifest.json

## Checks

| ID | Kind | Command | Exit | Result | Inspection | Stdout SHA256 | Stderr SHA256 | Started | Completed |
|---|---|---|---:|---|---|---|---|---|---|
| EV-001 | focused | `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest tests.test_production_preflight_browser -v` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `a4cb82f40fcc6462ce4d5a6b22ecd55c01c50d234232f6928d980258a17d42de` | 2026-08-25T09:20:19+00:00 | 2026-08-25T09:20:25+00:00 |
| EV-002 | negative | `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest tests.test_production_workflow_browser -v` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `081fe29da83db02c1c997b8458a857dc15e5b9803b54770d0cec78a4e8d7d4a8` | 2026-08-25T09:20:25+00:00 | 2026-08-25T09:20:51+00:00 |
| EV-003 | integration,acceptance_contract | `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest tests.test_production_preflight_browser tests.test_production_workflow_browser -v` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `d194a855e46f954dc5225ccc714cfab8516941c6476a75bbc851c76ff142f559` | 2026-08-25T09:20:51+00:00 | 2026-08-25T09:21:22+00:00 |

## Output Assertions

- PASS: `OK`

## Runtime Artifacts

- NONE

## Side Effects and Cleanup

- Cleanup/rollback verification: no residual process; rollback remains available
- Known limits: Compact-height rules also reduce global top-bar and main spacing on other desktop views at heights <=800px; low risk, not separately sampled.
