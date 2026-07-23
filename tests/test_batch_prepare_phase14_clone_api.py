from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi.testclient import TestClient

from story_audio.batch_prepare_clone_api import (
    BatchPrepareCloneApiService,
    _http_status,
    build_clone_prepare_api_service,
)
from story_audio.batch_prepare_runtime_integration import (
    build_runtime_integration,
    parse_runtime_integration_config,
)
from tests.batch_prepare_phase10_fixture import Phase10FixtureMixin


TOKEN = "phase14-synthetic-token"


class FailAppliedOnceStore:
    def __init__(self, inner):
        self.inner = inner
        self.failed = False

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def record_applied_result(self, *args, **kwargs):
        if not self.failed:
            self.failed = True
            raise RuntimeError("simulated APPLIED persistence loss")
        return self.inner.record_applied_result(*args, **kwargs)


class Phase14CloneApiTests(Phase10FixtureMixin):
    def setUp(self) -> None:
        super().setUp()
        values = {
            "PREPARE_RUNTIME_MODE": "CLONE_DISABLED",
            "PREPARE_FEATURE_AVAILABLE": "true",
            "PREPARE_MUTATION_ENABLED": "true",
            "PREPARE_OPERATOR_WINDOW_OPEN": "true",
            "PREPARE_CANONICAL_SCHEMA_READY": "true",
            "PREPARE_KILL_SWITCH_ACTIVE": "false",
            "PREPARE_CLONE_MUTATION_TEST_AUTHORIZED": "true",
            "PREPARE_OPERATOR_AUTH_ENABLED": "true",
            "PREPARE_OPERATOR_ID": "operator.phase14-test",
            "PREPARE_OPERATOR_TOKEN_SHA256": hashlib.sha256(TOKEN.encode()).hexdigest(),
            "PREPARE_OPERATOR_TOKEN_VERSION": "phase14-v1",
            "PREPARE_OPERATOR_AUTH_LOCAL_TEST_MODE": "true",
        }
        self.runtime_config = parse_runtime_integration_config(values)
        self.descriptor = build_runtime_integration(
            self.runtime_config,
            db_path=self.db_path,
            repository_root=self.config.root / "repository-sentinel",
            canonical_db_path=self.config.root / "canonical" / "app.db",
        )
        self.assertTrue(self.descriptor.clone_mutation_test_enabled)
        self.service = build_clone_prepare_api_service(
            settings=self.config,
            config=self.runtime_config,
            descriptor=self.descriptor,
        )
        self.assertIsNotNone(self.service)
        self.authorization = f"Bearer {TOKEN}"

    def api_request(self, plan=None, *, client_request_id="phase14-request-001"):
        plan = plan or self.plan()
        scope = plan["scope"]
        return {
            "client_request_id": client_request_id,
            "book_id": scope["book_id"],
            "from_chapter": scope["from_chapter"],
            "to_chapter": scope["to_chapter"],
            "target_phase": "PREPARE",
            "plan_fingerprint": plan["plan_fingerprint"],
            "confirmation": True,
        }

    def _prepare(self, request):
        return self.service.prepare(request, authorization_header=self.authorization)

    def test_valid_request_creates_exact_atomic_prepared_state(self):
        result = self._prepare(self.api_request())
        self.assertEqual(result.http_status, 200)
        self.assertEqual(result.payload["request_state"], "APPLIED")
        self.assertEqual(
            self.counts(),
            {
                "batch_prepare_requests": 1,
                "batch_prepare_execution_attempts": 1,
                "batch_prepare_job_links": 1,
                "jobs": 1,
                "job_chapters": 2,
                "segments": 0,
                "artifacts": 0,
            },
        )
        rendered = json.dumps(result.payload, sort_keys=True)
        for forbidden in (
            "token",
            "hash",
            "fingerprint",
            "digest",
            "identity",
            "db_path",
            "traceback",
            "full_text",
            "casting_plan",
        ):
            self.assertNotIn(forbidden, rendered.lower())

    def test_http_status_mapping_fails_closed_for_unknown_core_state(self):
        self.assertEqual(_http_status({"status": "APPLIED_REPLAYED"}), 200)
        self.assertEqual(_http_status({"status": "PLANNED_REPLAYED"}), 202)
        self.assertEqual(_http_status({"status": "REJECTED_REPLAYED"}), 409)
        self.assertEqual(_http_status({"status": "FAILED_REPLAYED"}), 409)
        self.assertEqual(_http_status({"status": "UNEXPECTED_CORE_STATE"}), 500)

    def test_same_request_replays_same_job_and_status_get_is_nonexecuting(self):
        request = self.api_request()
        first = self._prepare(request)
        before = self.counts()
        replay = self._prepare(request)
        status = self.service.status(
            request["client_request_id"],
            authorization_header=self.authorization,
        )
        self.assertEqual(replay.http_status, 200)
        self.assertEqual(status.http_status, 200)
        self.assertEqual(first.payload["job_id"], replay.payload["job_id"])
        self.assertEqual(first.payload["job_id"], status.payload["job_id"])
        self.assertEqual(self.counts(), before)

    def test_same_request_id_different_payload_conflicts_without_second_job(self):
        first_plan = self.plan(from_chapter=10, to_chapter=11)
        self._prepare(self.api_request(first_plan, client_request_id="phase14-conflict"))
        second_plan = self.plan(from_chapter=12, to_chapter=13)
        conflict = self._prepare(self.api_request(second_plan, client_request_id="phase14-conflict"))
        self.assertEqual(conflict.http_status, 409)
        self.assertEqual(self.counts()["jobs"], 1)
        self.assertEqual(self.counts()["batch_prepare_requests"], 1)

    def test_auth_failures_and_loopback_authority_create_no_rows(self):
        request = self.api_request()
        for header in (None, "Basic wrong", "Bearer wrong", "Bearer "):
            with self.assertRaisesRegex(Exception, "authentication failed"):
                self.service.prepare(request, authorization_header=header)
        self.assertEqual(self.counts()["batch_prepare_requests"], 0)
        self.assertEqual(self.counts()["jobs"], 0)

    def test_kill_switch_and_missing_test_authorization_prevent_service_construction(self):
        base = {
            "PREPARE_RUNTIME_MODE": "CLONE_DISABLED",
            "PREPARE_FEATURE_AVAILABLE": "true",
            "PREPARE_MUTATION_ENABLED": "true",
            "PREPARE_OPERATOR_WINDOW_OPEN": "true",
            "PREPARE_CANONICAL_SCHEMA_READY": "true",
            "PREPARE_OPERATOR_AUTH_ENABLED": "true",
            "PREPARE_OPERATOR_ID": "operator.phase14-test",
            "PREPARE_OPERATOR_TOKEN_SHA256": hashlib.sha256(TOKEN.encode()).hexdigest(),
        }
        for override in (
            {"PREPARE_KILL_SWITCH_ACTIVE": "true", "PREPARE_CLONE_MUTATION_TEST_AUTHORIZED": "true"},
            {"PREPARE_KILL_SWITCH_ACTIVE": "false"},
        ):
            config = parse_runtime_integration_config({**base, **override})
            descriptor = build_runtime_integration(
                config,
                db_path=self.db_path,
                repository_root=self.config.root / "repository-sentinel",
                canonical_db_path=self.config.root / "canonical" / "app.db",
            )
            self.assertFalse(descriptor.clone_mutation_test_enabled)
            self.assertIsNone(
                build_clone_prepare_api_service(
                    settings=self.config,
                    config=config,
                    descriptor=descriptor,
                )
            )
        self.assertEqual(self.counts()["jobs"], 0)

    def test_service_rejects_descriptor_database_path_mismatch(self):
        mismatched = replace(
            self.descriptor,
            inspected_db_path=self.temp_root / "different.db",
        )
        self.assertIsNone(
            build_clone_prepare_api_service(
                settings=self.config,
                config=self.runtime_config,
                descriptor=mismatched,
            )
        )
        self.assertEqual(self.counts()["jobs"], 0)

    def test_stale_plan_creates_no_request_or_job(self):
        stale = self.api_request()
        stale["plan_fingerprint"] = "0" * 64
        result = self._prepare(stale)
        self.assertEqual(result.http_status, 409)
        self.assertEqual(self.counts()["batch_prepare_requests"], 0)
        self.assertEqual(self.counts()["jobs"], 0)

    def test_status_recovers_committed_job_after_applied_persistence_failure(self):
        request = self.api_request(client_request_id="phase14-recovery-request")
        failing_store = FailAppliedOnceStore(self.store)
        failing_orchestrator, _adapter = self.orchestrator(request_store=failing_store)
        failing_service = BatchPrepareCloneApiService(
            config=self.runtime_config,
            descriptor=self.descriptor,
            orchestrator=failing_orchestrator,
            request_store=failing_store,
        )
        failed = failing_service.prepare(request, authorization_header=self.authorization)
        self.assertEqual(failed.http_status, 409)
        self.assertEqual(self.counts()["jobs"], 1)

        recovery_orchestrator, _adapter = self.orchestrator()
        recovery_service = BatchPrepareCloneApiService(
            config=self.runtime_config,
            descriptor=self.descriptor,
            orchestrator=recovery_orchestrator,
            request_store=self.store,
        )
        recovered = recovery_service.status(
            request["client_request_id"],
            authorization_header=self.authorization,
        )
        self.assertEqual(recovered.http_status, 200)
        self.assertEqual(recovered.payload["request_state"], "APPLIED")
        self.assertEqual(recovered.payload["job_id"], 1)
        self.assertEqual(self.counts()["jobs"], 1)
        self.assertEqual(self.counts()["batch_prepare_execution_attempts"], 1)

    def test_concurrent_duplicate_creates_one_job(self):
        request = self.api_request(client_request_id="phase14-concurrent")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _value: self._prepare(request), range(2)))
        self.assertTrue(all(result.http_status in {200, 202} for result in results))
        self.assertEqual(self.counts()["jobs"], 1)
        self.assertEqual(self.counts()["batch_prepare_requests"], 1)
        self.assertEqual(self.counts()["batch_prepare_execution_attempts"], 1)

    def test_overlapping_distinct_requests_have_one_winner(self):
        plan_a = self.plan(from_chapter=10, to_chapter=11)
        plan_b = self.plan(from_chapter=11, to_chapter=12)
        requests = (
            self.api_request(plan_a, client_request_id="phase14-overlap-a"),
            self.api_request(plan_b, client_request_id="phase14-overlap-b"),
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self._prepare, requests))
        self.assertEqual(sum(result.http_status == 200 for result in results), 1)
        self.assertEqual(self.counts()["jobs"], 1)

    def test_non_overlapping_requests_each_succeed(self):
        first = self._prepare(
            self.api_request(self.plan(from_chapter=10, to_chapter=11), client_request_id="phase14-nonoverlap-a")
        )
        second = self._prepare(
            self.api_request(self.plan(from_chapter=12, to_chapter=13), client_request_id="phase14-nonoverlap-b")
        )
        self.assertEqual((first.http_status, second.http_status), (200, 200))
        self.assertEqual(self.counts()["jobs"], 2)
        self.assertEqual(self.counts()["job_chapters"], 4)

    def test_http_route_auth_validation_replay_and_status(self):
        import story_audio.api as api

        request = self.api_request(client_request_id="phase14-http-request")
        with (
            patch.object(api, "batch_prepare_api_service", self.service),
            patch.object(api, "prepare_runtime_config", self.runtime_config),
            patch.object(api, "prepare_runtime_integration", self.descriptor),
        ):
            client = TestClient(api.app)
            denied = client.post("/api/production/batch-prepare", json=request)
            self.assertEqual(denied.status_code, 401)
            headers = {"Authorization": self.authorization}
            accepted = client.post("/api/production/batch-prepare", json=request, headers=headers)
            self.assertEqual(accepted.status_code, 200)
            replay = client.post("/api/production/batch-prepare", json=request, headers=headers)
            self.assertEqual(replay.status_code, 200)
            status = client.get(
                f"/api/production/batch-prepare/{request['client_request_id']}",
                headers=headers,
            )
            self.assertEqual(status.status_code, 200)
            self.assertEqual(accepted.json()["job_id"], replay.json()["job_id"])
            self.assertEqual(accepted.json()["job_id"], status.json()["job_id"])

    def test_http_rejects_url_body_authority_and_oversized_body(self):
        import story_audio.api as api

        request = self.api_request(client_request_id="phase14-http-invalid")
        headers = {"Authorization": self.authorization}
        with (
            patch.object(api, "batch_prepare_api_service", self.service),
            patch.object(api, "prepare_runtime_integration", self.descriptor),
        ):
            client = TestClient(api.app)
            self.assertEqual(
                client.post("/api/production/batch-prepare?token=bad", json=request, headers=headers).status_code,
                400,
            )
            for field, value in (
                ("owner_token", "forbidden"),
                ("generation", 7),
                ("included_chapters", [1]),
                ("job_id", 1),
                ("start_render", True),
                ("authorization", TOKEN),
            ):
                response = client.post(
                    "/api/production/batch-prepare",
                    json={**request, field: value},
                    headers=headers,
                )
                self.assertEqual(response.status_code, 400)
            oversized = b'{"padding":"' + (b"x" * (17 * 1024)) + b'"}'
            response = client.post(
                "/api/production/batch-prepare",
                content=oversized,
                headers={**headers, "Content-Type": "application/json"},
            )
            self.assertEqual(response.status_code, 413)
            malformed = client.post(
                "/api/production/batch-prepare",
                content=b'{"client_request_id":',
                headers={**headers, "Content-Type": "application/json"},
            )
            self.assertEqual(malformed.status_code, 400)
        self.assertEqual(self.counts()["jobs"], 0)


if __name__ == "__main__":
    unittest.main()
