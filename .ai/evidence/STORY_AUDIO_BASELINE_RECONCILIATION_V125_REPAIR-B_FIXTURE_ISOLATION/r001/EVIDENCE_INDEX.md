# Evidence Index

- Task ID: STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR-B_FIXTURE_ISOLATION
- Task revision: 1
- Success Criterion: All assignment, batch-plan, Human Approval, Production Runner, phase13 and phase14 focused tests pass using isolated schema-16/temp dependencies with no provider or canonical mutation.
- Accepted outcome: All inventory-proven fixture and dependency-binding failures pass against isolated schema-16 and provider-disabled runtime state.
- Generated: 2026-08-25T09:27:57+00:00
- Risk tier: R2
- Verified snapshot SHA256: 6f1a4e9b7d73c654b9f4f33271a57b4abb382b7eff378b36e9ae6d555ae662d6
- Verified HEAD: 4ebc6f498d4e35de8b7d24e30362490e8f777feb
- Final verdict: PASS
- Evidence schema: 4
- Evidence mode: FULL
- Manifest: manifest.json

## Checks

| ID | Kind | Command | Exit | Result | Inspection | Stdout SHA256 | Stderr SHA256 | Started | Completed |
|---|---|---|---:|---|---|---|---|---|---|
| EV-001 | focused,acceptance_contract | `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest tests.test_assignment_workflow_browser tests.test_batch_plan_api tests.test_human_approval_api tests.test_production_runner_api tests.test_batch_prepare_phase13_clone_runtime tests.test_batch_prepare_phase14_restart -v` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `b4128e59d99effbbc291e801db1b83f863d1c77fd28f26ecb5603319210e7245` | 2026-08-25T09:27:06+00:00 | 2026-08-25T09:27:40+00:00 |
| EV-002 | negative | `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest tests.test_batch_plan_api.BatchPlanApiTests.test_request_is_read_only_and_does_not_call_worker_or_tts tests.test_batch_prepare_phase13_clone_runtime.Phase13CloneRuntimeTests.test_inspect_has_get_readiness_and_disabled_batch_mutation_route -v` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `7f66d55ae3dc51123f3579137dbd89a3dd327efe206e8000c83b70b6be8d2e03` | 2026-08-25T09:27:40+00:00 | 2026-08-25T09:27:44+00:00 |
| EV-003 | integration | `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe -m unittest tests.test_assignment_workflow_browser tests.test_human_approval_api tests.test_production_runner_api -v` | 0 | PASS | AGENT_INSPECTED | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `4c81f8fcbfebd168349eeba3ad978f9b377199a5d29dadecf123a47bb1c0a01c` | 2026-08-25T09:27:45+00:00 | 2026-08-25T09:27:56+00:00 |

## Output Assertions

- PASS: `OK`

## Runtime Artifacts

- NONE

## Side Effects and Cleanup

- Cleanup/rollback verification: no residual process; rollback remains available
- Known limits: Timestamped noncanonical assignment-test directories may remain after historical interrupted runs; current run cleaned its own directory.
