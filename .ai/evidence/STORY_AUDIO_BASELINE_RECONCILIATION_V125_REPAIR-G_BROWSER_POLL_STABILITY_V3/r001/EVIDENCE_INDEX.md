# Evidence Index

- Task ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-G_BROWSER_POLL_STABILITY_V3
- Task revision: 1
- Success Criterion: Five consecutive isolated real-browser assignment journeys pass and preserve the exact polling stability assertions; then the independent full offline review may rerun.
- Accepted outcome: Assignment browser polling evidence now waits for the real UI to quiesce, preserves active DOM identity/focus/draft/scroll invariants through repeated loadJobs polling, and atomically exercises injected repair controls without route-refresh races.
- Generated: 2026-08-25T10:15:00+00:00
- Risk tier: R1
- Verified snapshot SHA256: 5af5167acf43426b96e245fd1c9a5fdddbe220ec5d0f2ef229132f0322ad479e
- Verified HEAD: 801ac72664eb4a8274914b87ab562bd8e9d03968
- Final verdict: PASS
- Evidence schema: 4
- Evidence mode: COMPACT
- Manifest: manifest.json

## Checks

| ID | Kind | Command | Exit | Result | Inspection | Stdout SHA256 | Stderr SHA256 | Started | Completed |
|---|---|---|---:|---|---|---|---|---|---|
| EV-001 | focused,state_transition,state_temporal,acceptance_contract | `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest tests.test_assignment_workflow_browser` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `5d2b815830155a10aa3fec98cc7e37b59e207e0b60eb4a36bf0bc0977ca0597b` | 2026-08-25T10:14:53+00:00 | 2026-08-25T10:14:59+00:00 |

## Output Assertions

- PASS: `OK`

## Runtime Artifacts

- NONE

## Side Effects and Cleanup

- Cleanup/rollback verification: Each browser run removes only its fresh exact timestamped test root and Chromium profile after process shutdown.
- Known limits: Full-suite and CI gates remain assigned to independent E review; five consecutive focused passes were also observed before lifecycle capture.
