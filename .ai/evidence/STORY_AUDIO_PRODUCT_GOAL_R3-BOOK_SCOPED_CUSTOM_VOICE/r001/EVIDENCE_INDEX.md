# Evidence Index

- Task ID: STORY_AUDIO_PRODUCT_GOAL_R3-BOOK_SCOPED_CUSTOM_VOICE
- Task revision: 1
- Success Criterion: A normal user can add a sample-backed custom voice to one Book, it persists on reload, resolves in that Book runtime context, and cannot be seen or resolved by another Book.
- Accepted outcome: ADD CUSTOM VOICE TO SELECTED BOOK
- Generated: 2026-08-09T09:10:01+00:00
- Risk tier: R3
- Verified snapshot SHA256: 083073f70cb9ad6595429201f2cac84b74e8b185a9af1a4a05fa0b4d3331761c
- Verified HEAD: 0189b0ae34e1831929fa4b8b9746c199fdbc1896
- Final verdict: PASS
- Evidence schema: 4
- Evidence mode: FULL
- Manifest: manifest.json

## Checks

| ID | Kind | Command | Exit | Result | Inspection | Stdout SHA256 | Stderr SHA256 | Started | Completed |
|---|---|---|---:|---|---|---|---|---|---|
| EV-001 | focused | `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest tests.test_backup_restore tests.test_integrity tests.test_prepare_production_activation tests.test_batch_prepare_isolated_adapter` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `36947370388d5486444634c8699782665cad8f52818f0653394de584c68692a3` | 2026-08-09T09:07:55+00:00 | 2026-08-09T09:08:05+00:00 |
| EV-002 | negative | `node scripts/browser_book_custom_voice_acceptance.mjs --self-check-canonical-url` | 0 | PASS | AGENT_INSPECTED | `03e7701f786c2099ceb4f645b2e3671e090eec749180a495e26fb3004b70b942` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 2026-08-09T09:08:05+00:00 | 2026-08-09T09:08:05+00:00 |
| EV-003 | integration | `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest tests.test_book_scoped_custom_voices tests.test_range_input_api tests.test_range_readiness_api tests.test_voice_snapshot tests.test_casting` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `fb471c404401ffa924552809628222a695d8ff4322b72344a37da53cae0e7773` | 2026-08-09T09:08:06+00:00 | 2026-08-09T09:08:35+00:00 |
| EV-004 | state_transition | `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest tests.test_book_scoped_custom_voices.BookScopedCustomVoiceTests.test_worker_cache_is_keyed_by_book_and_keeps_legacy_available` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `6468378e6100359f274ecdcde4e999b96c35563fc13ff1ea9eb9dc2a2dcd15ec` | 2026-08-09T09:08:46+00:00 | 2026-08-09T09:08:47+00:00 |
| EV-005 | acceptance_contract | `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest tests.test_book_scoped_custom_voices tests.test_custom_voice_api tests.test_custom_voice tests.test_voice_catalog tests.test_assignment_workflow_browser` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `ce2e129ff651702981db12b560bddc236768929a890d15141fac9144703ee9f7` | 2026-08-09T09:08:57+00:00 | 2026-08-09T09:09:12+00:00 |
| EV-006 | rollback | `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest tests.test_backup_restore.BackupRestoreTests.test_schema16_backup_restore_and_integrity_preserve_voice_ownership` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `1ad13de8256d7626d2a1d58f6035f2fb139de650265ca384ab64ed92a4b63b64` | 2026-08-09T09:09:12+00:00 | 2026-08-09T09:09:13+00:00 |
| EV-007 | full_suite | `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest tests.test_book_scoped_custom_voices tests.test_custom_voice_api tests.test_custom_voice tests.test_voice_catalog tests.test_backup_restore tests.test_integrity tests.test_prepare_production_activation tests.test_batch_prepare_isolated_adapter tests.test_range_input_api tests.test_range_readiness_api tests.test_production_commands_api tests.test_production_preflight_api tests.test_speaker_review_api tests.test_voice_profile tests.test_voice_snapshot tests.test_casting tests.test_migrations` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `d96c6be1686f5a78c0556f2c9492eb32e7cb4858eec180939c1719b2bf8a44fe` | 2026-08-09T09:09:13+00:00 | 2026-08-09T09:10:01+00:00 |

## Output Assertions

- PASS: `OK`

## Runtime Artifacts

- NONE

## Side Effects and Cleanup

- Cleanup/rollback verification: Disposable browser runtimes were stopped and removed; no canonical certification voice was created.
- Known limits: Known clone-runtime, golden-journey and speaker-review failures remain documented baseline exceptions; assignment browser polling flake reran independently PASS and was Guardian-classified baseline.
