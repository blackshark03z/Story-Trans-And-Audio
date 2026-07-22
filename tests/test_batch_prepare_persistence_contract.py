from __future__ import annotations

import json
import unittest
from pathlib import Path

from story_audio.batch_prepare_persistence_contract import (
    AUTHORIZATION_STATUS,
    DUPLICATE_APPLIED,
    DUPLICATE_APPLYING,
    DUPLICATE_FAILED,
    DUPLICATE_FAILED_RETRYABLE,
    DUPLICATE_FAILED_REVIEW_REQUIRED,
    DUPLICATE_PLANNED,
    DUPLICATE_REJECTED,
    PROPOSED_REQUEST_TABLE,
    PROPOSED_SCHEMA_VERSION,
    REQUEST_ID_CONFLICT,
    STATE_APPLIED,
    STATE_APPLYING,
    STATE_FAILED,
    STATE_PLANNED,
    STATE_REJECTED,
    PreparePersistenceContractError,
    allowed_transition,
    build_replay_contract,
    build_request_binding,
    build_request_identity,
    build_result_payload,
    classify_duplicate_request,
    get_persistence_design_contract,
    normalize_client_request_id,
)


FINGERPRINT = "a" * 64


def _request(**overrides):
    request = {
        "client_request_id": "prepare-001",
        "book_id": 1,
        "from_chapter": 10,
        "to_chapter": 12,
        "target_phase": "PREPARE",
        "plan_fingerprint": FINGERPRINT,
        "explicit_confirmation": True,
    }
    request.update(overrides)
    return request


class BatchPreparePersistenceContractTests(unittest.TestCase):
    def test_client_request_id_required_and_safe(self) -> None:
        for value in [None, "", "   ", "bad/id", "bad id", "x" * 201]:
            with self.subTest(value=value):
                with self.assertRaises(PreparePersistenceContractError):
                    normalize_client_request_id(value)
        self.assertEqual(normalize_client_request_id("  Request-01.OK:retry  "), "Request-01.OK:retry")

    def test_canonical_request_identity_is_deterministic(self) -> None:
        first = build_request_binding(_request())
        second = build_request_binding(dict(_request()))
        self.assertEqual(first.request_identity, second.request_identity)
        direct = build_request_identity(
            client_request_id="prepare-001",
            book_id=1,
            from_chapter=10,
            to_chapter=12,
            target_phase="prepare",
            plan_fingerprint=FINGERPRINT,
        )
        self.assertEqual(first.request_identity, direct)

    def test_canonical_serialization_is_independent_of_dict_order(self) -> None:
        first = build_request_binding(_request())
        reversed_items = dict(reversed(list(_request().items())))
        second = build_request_binding(reversed_items)
        self.assertEqual(first.request_identity, second.request_identity)

    def test_different_payload_changes_identity(self) -> None:
        baseline = build_request_binding(_request())
        changed_scope = build_request_binding(_request(to_chapter=13))
        changed_phase = None
        with self.assertRaises(PreparePersistenceContractError):
            changed_phase = build_request_binding(_request(target_phase="START_RENDER"))
        changed_fingerprint = build_request_binding(_request(plan_fingerprint="b" * 64))
        self.assertNotEqual(baseline.request_identity, changed_scope.request_identity)
        self.assertIsNone(changed_phase)
        self.assertNotEqual(baseline.request_identity, changed_fingerprint.request_identity)

    def test_same_request_id_same_payload_is_same_request(self) -> None:
        first = build_request_binding(_request())
        second = build_request_binding(_request())
        self.assertEqual(first.client_request_id, second.client_request_id)
        self.assertEqual(first.request_identity, second.request_identity)
        self.assertEqual(
            classify_duplicate_request(
                existing_state=STATE_APPLIED,
                same_client_request_id=True,
                same_request_identity=True,
            ),
            DUPLICATE_APPLIED,
        )

    def test_same_request_id_different_payload_is_conflict(self) -> None:
        self.assertEqual(
            classify_duplicate_request(
                existing_state=STATE_PLANNED,
                same_client_request_id=True,
                same_request_identity=False,
            ),
            REQUEST_ID_CONFLICT,
        )

    def test_prepare_only_and_confirmation_required(self) -> None:
        with self.assertRaises(PreparePersistenceContractError):
            build_request_binding(_request(target_phase="QA_CLOSEOUT"))
        with self.assertRaises(PreparePersistenceContractError):
            build_request_binding(_request(explicit_confirmation="true"))

    def test_state_transitions_are_explicit(self) -> None:
        self.assertTrue(allowed_transition(STATE_PLANNED, STATE_APPLYING))
        self.assertTrue(allowed_transition(STATE_PLANNED, STATE_REJECTED))
        self.assertTrue(allowed_transition(STATE_APPLYING, STATE_APPLIED))
        self.assertTrue(allowed_transition(STATE_APPLYING, STATE_FAILED))
        self.assertFalse(allowed_transition(STATE_APPLIED, STATE_APPLYING))
        self.assertFalse(allowed_transition(STATE_FAILED, STATE_APPLYING))
        self.assertFalse(allowed_transition(STATE_REJECTED, STATE_APPLYING))

    def test_duplicate_state_behavior(self) -> None:
        expected = {
            STATE_PLANNED: DUPLICATE_PLANNED,
            STATE_APPLYING: DUPLICATE_APPLYING,
            STATE_APPLIED: DUPLICATE_APPLIED,
            STATE_REJECTED: DUPLICATE_REJECTED,
            STATE_FAILED: DUPLICATE_FAILED,
        }
        for state, decision in expected.items():
            with self.subTest(state=state):
                self.assertEqual(
                    classify_duplicate_request(
                        existing_state=state,
                        same_client_request_id=True,
                        same_request_identity=True,
                    ),
                    decision,
                )

    def test_duplicate_failed_retryable_and_review_required_are_explicit(self) -> None:
        self.assertEqual(
            classify_duplicate_request(
                existing_state=STATE_FAILED,
                same_client_request_id=True,
                same_request_identity=True,
                existing_error_code="FAILED_RETRYABLE",
            ),
            DUPLICATE_FAILED_RETRYABLE,
        )
        self.assertEqual(
            classify_duplicate_request(
                existing_state=STATE_FAILED,
                same_client_request_id=True,
                same_request_identity=True,
                existing_error_code="FAILED_REVIEW_REQUIRED",
            ),
            DUPLICATE_FAILED_REVIEW_REQUIRED,
        )

    def test_timeout_replay_never_creates_new_mutation_intent(self) -> None:
        contract = get_persistence_design_contract()
        replay = contract["timeout_replay"]
        self.assertIn("in-progress", replay[STATE_APPLYING])
        self.assertIn("replay", replay[STATE_APPLIED])
        self.assertEqual(replay["different_payload"], REQUEST_ID_CONFLICT)
        self.assertFalse(contract["authorization"]["mutation_authorized"])

    def test_replay_payload_is_historical_and_safe(self) -> None:
        binding = build_request_binding(_request())
        payload = build_result_payload(
            binding,
            state=STATE_APPLIED,
            job_id=44,
            chapter_results=[
                {
                    "chapter_id": 1001,
                    "chapter_number": 10,
                    "plan_eligibility": "ELIGIBLE",
                    "result_status": "PREPARED",
                    "job_chapter_id": 55,
                    "reason_codes": ["PREPARED"],
                    "created_or_reused": "created",
                    "path": "D:/should/not/leak",
                    "full_text": "should not leak",
                }
            ],
        )
        encoded = json.dumps(payload, sort_keys=True)
        self.assertEqual(payload["result_schema_version"], 1)
        self.assertNotIn("should/not/leak", encoded)
        self.assertNotIn("should not leak", encoded)
        replay = build_replay_contract(existing_state=STATE_APPLIED, stored_result_payload=payload)
        self.assertTrue(replay["historical_result_replayed"])
        self.assertEqual(replay["stored_result_payload"]["job_id"], 44)

    def test_unsafe_replay_payload_is_rejected(self) -> None:
        with self.assertRaises(PreparePersistenceContractError):
            build_replay_contract(
                existing_state=STATE_APPLIED,
                stored_result_payload={"traceback": "Traceback (most recent call last)"},
            )

    def test_one_request_one_job_and_prepare_never_starts_render(self) -> None:
        contract = get_persistence_design_contract()
        self.assertTrue(contract["batch_shape"]["one_request_one_job"])
        self.assertFalse(contract["batch_shape"]["one_job_per_chapter"])
        self.assertFalse(contract["authorization"]["prepare_starts_render"])

    def test_atomicity_contract_is_all_or_nothing_with_applying_recovery(self) -> None:
        contract = get_persistence_design_contract()
        atomicity = contract["atomicity"]
        self.assertEqual(atomicity["recommended_option"], "A_REQUEST_APPLYING_COMMITTED_BEFORE_JOB_TRANSACTION")
        self.assertEqual(atomicity["job_creation_policy"], "all_or_nothing_job_and_job_chapters")
        self.assertIn("WHERE state='PLANNED'", atomicity["compare_and_transition"])
        self.assertIn("FAILED_RETRYABLE", atomicity["abandoned_applying_recovery"])
        self.assertIn("FAILED_REVIEW_REQUIRED", atomicity["abandoned_applying_recovery"])
        self.assertIn("reconciliation", atomicity["abandoned_applying_recovery"])

    def test_request_uniqueness_race_guard_metadata(self) -> None:
        guard = get_persistence_design_contract()["concurrency_uniqueness"]
        self.assertTrue(guard["unique_client_request_id"])
        self.assertTrue(guard["unique_request_identity"])
        self.assertTrue(guard["guarded_state_transition_required"])
        self.assertTrue(guard["no_check_then_insert_only"])

    def test_fingerprint_race_guard_requires_protected_revalidation(self) -> None:
        guard = get_persistence_design_contract()["fingerprint_race_guard"]
        self.assertTrue(guard["validate_at_request"])
        self.assertTrue(guard["validate_before_applying"])
        self.assertTrue(guard["validate_inside_or_equivalent_to_protected_execution_boundary"])
        self.assertFalse(guard["use_current_plan_to_rewrite_applied_result"])

    def test_per_chapter_result_schema_is_bounded(self) -> None:
        schema = get_persistence_design_contract()["per_chapter_result"]
        self.assertEqual(
            schema["fields"],
            [
                "chapter_id",
                "chapter_number",
                "plan_eligibility",
                "result_status",
                "job_chapter_id",
                "reason_codes",
                "created_or_reused",
            ],
        )
        self.assertFalse(schema["excluded_chapters_have_job_chapter"])
        self.assertFalse(schema["atomic_batch_mixed_success"])

    def test_proposed_migration_metadata_only(self) -> None:
        migration = get_persistence_design_contract()["proposed_migration"]
        self.assertEqual(migration["current_schema_version"], 12)
        self.assertEqual(migration["future_schema_version"], PROPOSED_SCHEMA_VERSION)
        self.assertEqual(migration["table"], PROPOSED_REQUEST_TABLE)
        self.assertTrue(migration["implemented"])
        self.assertEqual(migration["activation"], "DORMANT_EXPLICIT_TARGET_ONLY")
        self.assertFalse(migration["default_auto_discovered"])
        self.assertIn("UNIQUE(client_request_id)", migration["unique_constraints"])
        self.assertIn("from_chapter <= to_chapter", migration["check_constraints"])
        columns = dict(migration["columns"])
        self.assertIn("result_schema_version", columns)
        self.assertIn("applying_started_at", columns)
        self.assertIn("completed_at", columns)

    def test_proposed_schema_has_no_implementation_file(self) -> None:
        self.assertFalse(Path("story_audio/schema.py").exists())
        self.assertFalse(Path("story_audio/migrations/0013_batch_prepare_requests.sql").exists())
        self.assertTrue(Path("story_audio/migrations/dormant/0013_batch_prepare_requests.sql").exists())

    def test_retention_contract_does_not_cleanup_before_replay_window(self) -> None:
        retention = get_persistence_design_contract()["retention"]
        self.assertFalse(retention["hard_delete_initially_allowed"])
        self.assertIn("retain", retention[STATE_APPLIED])
        self.assertEqual(retention["cleanup_implementation"], "separate future task")

    def test_failure_taxonomy_is_public_and_deterministic(self) -> None:
        taxonomy = get_persistence_design_contract()["failure_taxonomy"]
        self.assertIn("REQUEST_ID_CONFLICT", taxonomy)
        self.assertIn("FAILED_REVIEW_REQUIRED", taxonomy)
        encoded = json.dumps(taxonomy)
        self.assertNotIn("Traceback", encoded)
        self.assertNotIn("Exception", encoded)

    def test_authorization_stays_false(self) -> None:
        contract = get_persistence_design_contract()
        self.assertEqual(contract["authorization"]["status"], AUTHORIZATION_STATUS)
        self.assertFalse(contract["authorization"]["mutation_authorized"])
        self.assertFalse(contract["authorization"]["execution_endpoint_available"])
        self.assertFalse(contract["authorization"]["prepare_starts_render"])

    def test_invalid_inputs_fail_closed(self) -> None:
        invalid_requests = [
            _request(book_id=True),
            _request(book_id=0),
            _request(from_chapter=12, to_chapter=10),
            _request(plan_fingerprint="A" * 64),
            _request(client_request_id=123),
        ]
        for request in invalid_requests:
            with self.subTest(request=request):
                with self.assertRaises(PreparePersistenceContractError):
                    build_request_binding(request)

    def test_unknown_state_fails_closed(self) -> None:
        with self.assertRaises(PreparePersistenceContractError):
            classify_duplicate_request(
                existing_state="MAYBE",
                same_client_request_id=True,
                same_request_identity=True,
            )
        with self.assertRaises(PreparePersistenceContractError):
            build_replay_contract(existing_state="MAYBE", stored_result_payload={})

    def test_canonical_identity_has_no_timestamp_or_randomness(self) -> None:
        identities = {build_request_binding(_request()).request_identity for _ in range(5)}
        self.assertEqual(len(identities), 1)
        identity = get_persistence_design_contract()["request_identity"]["canonical_request_identity"]
        self.assertFalse(identity["includes_timestamp"])
        self.assertFalse(identity["includes_random_uuid"])

    def test_safe_public_failure_codes_do_not_leak_sql_or_exception_details(self) -> None:
        taxonomy = " ".join(get_persistence_design_contract()["failure_taxonomy"])
        self.assertNotIn("sqlite", taxonomy.lower())
        self.assertNotIn("traceback", taxonomy.lower())
        self.assertNotIn("exception", taxonomy.lower())

    def test_pure_module_import_has_no_side_effect_state_registry(self) -> None:
        source = Path("story_audio/batch_prepare_persistence_contract.py").read_text(encoding="utf-8")
        forbidden = ["REQUEST_REGISTRY", "global_registry", "threading.Lock", "time.time(", "datetime.now("]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_result_replay_payload_rejects_paths_secrets_full_text_and_traceback(self) -> None:
        unsafe_payloads = [
            {"path": "D:/output/chapter.m4a"},
            {"secret": "token"},
            {"full_text": "chapter text"},
            {"casting_plan_blob": {"utterances": []}},
            {"voice_snapshot_json": "{}"},
            {"traceback": "boom"},
        ]
        for payload in unsafe_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(PreparePersistenceContractError):
                    build_replay_contract(existing_state=STATE_APPLIED, stored_result_payload=payload)

    def test_no_chapter_369_hard_code(self) -> None:
        source = Path("story_audio/batch_prepare_persistence_contract.py").read_text(encoding="utf-8")
        self.assertNotIn("369", source)

    def test_no_route_database_migration_or_execution_imports(self) -> None:
        source = Path("story_audio/batch_prepare_persistence_contract.py").read_text(encoding="utf-8")
        forbidden = [
            "from .db",
            "import sqlite",
            "prepare_job",
            "start_prepared_job",
            "PipelineWorker",
            "APIRouter",
            "@app.",
            "tts_service",
            "Gemini",
            "MigrationRunner",
        ]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_no_migration_files_changed_by_design_module(self) -> None:
        migration_files = sorted(path.name for path in Path("story_audio/migrations").glob("*.sql"))
        self.assertEqual(migration_files[-1], "0012_speaker_draft_reviews.sql")

    def test_missing_request_id_is_rejected(self) -> None:
        with self.assertRaises(PreparePersistenceContractError):
            build_request_binding(_request(client_request_id=None))

    def test_unicode_request_id_is_rejected(self) -> None:
        with self.assertRaises(PreparePersistenceContractError):
            normalize_client_request_id("yeu-cau-đặc-biệt")

    def test_request_id_case_is_preserved(self) -> None:
        lower = build_request_binding(_request(client_request_id="prepare-case"))
        upper = build_request_binding(_request(client_request_id="Prepare-Case"))
        self.assertNotEqual(lower.client_request_id, upper.client_request_id)
        self.assertNotEqual(lower.request_identity, upper.request_identity)

    def test_request_id_is_not_silently_truncated(self) -> None:
        valid = "x" * 200
        self.assertEqual(normalize_client_request_id(valid), valid)
        with self.assertRaises(PreparePersistenceContractError):
            normalize_client_request_id("x" * 201)

    def test_canonical_identity_includes_request_schema_version(self) -> None:
        contract = get_persistence_design_contract()
        algorithm = contract["request_identity"]["canonical_request_identity"]["algorithm"]
        self.assertIn("request_schema", algorithm)
        first = build_request_binding(_request(client_request_id="schema-version-1"))
        second = build_request_binding(_request(client_request_id="schema-version-2"))
        self.assertNotEqual(first.request_identity, second.request_identity)

    def test_plan_fingerprint_is_not_treated_as_request_id(self) -> None:
        contract = get_persistence_design_contract()
        identity = contract["request_identity"]["canonical_request_identity"]
        self.assertTrue(identity["distinct_from_plan_fingerprint"])
        first = build_request_binding(_request(client_request_id="request-a"))
        second = build_request_binding(_request(client_request_id="request-b"))
        self.assertEqual(first.plan_fingerprint, second.plan_fingerprint)
        self.assertNotEqual(first.request_identity, second.request_identity)

    def test_database_primary_key_is_not_canonical_identity(self) -> None:
        contract = get_persistence_design_contract()
        migration = contract["proposed_migration"]
        self.assertEqual(migration["columns"][0], ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"))
        self.assertIn(("request_identity", "TEXT NOT NULL"), migration["columns"])

    def test_latest_request_wins_is_forbidden(self) -> None:
        contract = get_persistence_design_contract()
        self.assertFalse(contract["payload_binding"]["latest_request_wins"])
        self.assertEqual(contract["payload_binding"]["same_client_request_id_different_payload"], REQUEST_ID_CONFLICT)

    def test_state_meanings_are_documented(self) -> None:
        source = Path("docs/BATCH_PREPARE_IDEMPOTENCY_DESIGN.md").read_text(encoding="utf-8")
        for phrase in [
            "request record",
            "protected execution boundary",
            "Job and all intended JobChapter rows",
            "deterministic rejection",
            "mutation fails",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, source)

    def test_terminal_and_retryable_states_are_explicit(self) -> None:
        state_machine = get_persistence_design_contract()["state_machine"]
        self.assertEqual(set(state_machine["terminal_states"]), {STATE_APPLIED, STATE_REJECTED, STATE_FAILED})
        self.assertEqual(set(state_machine["retryable_states"]), {STATE_PLANNED, STATE_APPLYING})

    def test_duplicate_failed_same_request_id_remains_replay_only(self) -> None:
        policy = get_persistence_design_contract()["state_machine"]["failed_retry_policy"]
        self.assertIn("fresh client_request_id", policy)
        self.assertIn("replay-only", policy)

    def test_timeout_replay_is_durable_record_based(self) -> None:
        replay = get_persistence_design_contract()["timeout_replay"]
        self.assertEqual(replay["same_client_request_id"], "lookup durable request record")
        self.assertNotIn("process-local", json.dumps(replay).lower())

    def test_rejected_and_failed_results_are_replayable(self) -> None:
        binding = build_request_binding(_request())
        for state, error_code in [(STATE_REJECTED, "STALE_PLAN"), (STATE_FAILED, "FAILED_REVIEW_REQUIRED")]:
            with self.subTest(state=state):
                payload = build_result_payload(binding, state=state, job_id=None, chapter_results=[], error_code=error_code)
                replay = build_replay_contract(
                    existing_state=state,
                    stored_result_payload=payload,
                    error_code=error_code,
                )
                self.assertTrue(replay["historical_result_replayed"])
                self.assertEqual(replay["stored_result_payload"]["error_code"], error_code)

    def test_start_render_remains_separate_authorization_gate(self) -> None:
        gates = get_persistence_design_contract()["authorization_gates"]
        self.assertIn("START_RENDER remains a separate action", gates)

    def test_option_a_documents_no_second_job_on_ambiguous_recovery(self) -> None:
        recovery = get_persistence_design_contract()["atomicity"]["abandoned_applying_recovery"]
        self.assertIn("Never auto-create a second Job", recovery)
        self.assertIn("ambiguous", recovery)

    def test_stale_plan_rejection_happens_before_job_insert(self) -> None:
        source = Path("docs/BATCH_PREPARE_IDEMPOTENCY_DESIGN.md").read_text(encoding="utf-8")
        self.assertIn("STALE_PLAN", source)
        self.assertIn("must not create a Job", source)

    def test_request_level_failed_does_not_claim_partial_prepared_rows(self) -> None:
        source = Path("docs/BATCH_PREPARE_IDEMPOTENCY_DESIGN.md").read_text(encoding="utf-8")
        self.assertIn("If mutation fails, transition to `FAILED`", source)
        self.assertIn("leave stale `APPLYING` for reconciliation", source)

    def test_proposed_schema_has_state_and_target_checks(self) -> None:
        checks = get_persistence_design_contract()["proposed_migration"]["check_constraints"]
        self.assertIn("target_phase IN ('PREPARE')", checks)
        self.assertIn("state IN ('PLANNED','APPLYING','APPLIED','REJECTED','FAILED')", checks)


if __name__ == "__main__":
    unittest.main()
