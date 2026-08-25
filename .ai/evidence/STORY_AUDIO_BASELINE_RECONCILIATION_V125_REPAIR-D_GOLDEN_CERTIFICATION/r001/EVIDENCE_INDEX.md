# Evidence Index

- Task ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-D_GOLDEN_CERTIFICATION
- Task revision: 1
- Success Criterion: Golden Journey passes entirely in an isolated non-8772 runtime with fake TTS/prepare boundaries, current schema semantics, no canonical artifact assumptions, and before/after non-mutation evidence.
- Accepted outcome: Golden Journey passes on isolated schema 16 through repair-plan confirmation, self-cleans its bounded run directory, and proves explicit protected-target before/after equality without replacement execution.
- Generated: 2026-08-25T09:49:07+00:00
- Risk tier: R3
- Verified snapshot SHA256: 7eaa71686efbb1889e9e92c72963c2512f9eae4d3ba3cd2b866e2068d1c664f7
- Verified HEAD: f2128d3523bdf9a7f8fc0e118e3ed1510ae2d6fa
- Final verdict: PASS
- Evidence schema: 4
- Evidence mode: FULL
- Manifest: manifest.json

## Checks

| ID | Kind | Command | Exit | Result | Inspection | Stdout SHA256 | Stderr SHA256 | Started | Completed |
|---|---|---|---:|---|---|---|---|---|---|
| EV-001 | focused,negative,acceptance_contract,rollback,full_suite | `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest tests.test_golden_journey_certification -v` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `5c1f156193dcc9e5eeb84e874fdbfbccf9959e5c08e41df33225cdb33886b34a` | 2026-08-25T09:48:10+00:00 | 2026-08-25T09:48:35+00:00 |
| EV-002 | integration | `node --check scripts\browser_golden_journey_certification.mjs` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 2026-08-25T09:48:36+00:00 | 2026-08-25T09:48:36+00:00 |
| EV-003 | state_transition | `"D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe" -X utf8 scripts\run_golden_journey_certification.py --timeout 180 --canonical-db "D:\Youtube\Story Trans And Audio\data\app.db"` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 2026-08-25T09:48:37+00:00 | 2026-08-25T09:49:05+00:00 |

## Output Assertions

- PASS: `OK`

## Runtime Artifacts

- NONE

## Side Effects and Cleanup

- Cleanup/rollback verification: Each fresh Golden run directory is validated as an immediate child of C:\StoryAudio_GoldenJourney_Test and removed after browser, server, and worker shutdown; cleanup is best-effort under external file locks.
- Known limits: The browser script retains unreachable replacement-path code under if(false); current certification stops before Apply and performs no replacement execution.
