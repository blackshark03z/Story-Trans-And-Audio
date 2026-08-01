from __future__ import annotations

import hashlib
import tempfile
import unittest
from http.cookies import SimpleCookie
from pathlib import Path

from starlette.requests import Request
from starlette.responses import Response

from story_audio.batch_prepare_runtime_integration import (
    PRODUCTION,
    build_runtime_integration,
    parse_runtime_integration_config,
)
from story_audio.batch_prepare_schema import prepare_migration_runner
from story_audio.db import Database
from story_audio.production_runtime_readiness import production_runtime_readiness
from story_audio.runtime_operator_session import (
    COOKIE_NAME,
    RuntimeOperatorSession,
    mutation_service_construction_allowed,
)


TOKEN = "milestone-one-synthetic-token"


def production_values(**overrides: str) -> dict[str, str]:
    values = {
        "PREPARE_RUNTIME_MODE": PRODUCTION,
        "PREPARE_FEATURE_AVAILABLE": "true",
        "PREPARE_MUTATION_ENABLED": "true",
        "PREPARE_OPERATOR_WINDOW_OPEN": "true",
        "PREPARE_CANONICAL_SCHEMA_READY": "true",
        "PREPARE_KILL_SWITCH_ACTIVE": "false",
        "PREPARE_OPERATOR_AUTH_ENABLED": "true",
        "PREPARE_OPERATOR_ID": "operator.fixture",
        "PREPARE_OPERATOR_TOKEN_SHA256": hashlib.sha256(TOKEN.encode()).hexdigest(),
        "PREPARE_OPERATOR_TOKEN_VERSION": "fixture-v1",
        "PREPARE_OPERATOR_AUTH_LOCAL_TEST_MODE": "false",
        "PREPARE_RENDER_ENABLED": "true",
    }
    values.update(overrides)
    return values


class RuntimeOperatorSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "app.db"
        Database(self.db_path, migration_runner=prepare_migration_runner()).initialize()
        self.output = self.root / "output"
        self.output.mkdir()
        self.config = parse_runtime_integration_config(production_values())
        self.descriptor = build_runtime_integration(
            self.config,
            db_path=self.db_path,
            repository_root=self.root / "repo",
            canonical_db_path=self.db_path,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _session(self, **extra: str) -> RuntimeOperatorSession:
        environment = {
            "STORY_AUDIO_SUPERVISED": "1",
            "STORY_AUDIO_OPERATOR_TOKEN_BOOTSTRAP": TOKEN,
            **extra,
        }
        session = RuntimeOperatorSession.from_environment(
            self.descriptor, self.config.auth, environment
        )
        self.assertNotIn("STORY_AUDIO_OPERATOR_TOKEN_BOOTSTRAP", environment)
        return session

    def test_verified_session_uses_httponly_cookie_without_exposing_token(self) -> None:
        session = self._session()
        response = Response()
        session.apply_cookie(response)
        cookie = SimpleCookie(response.headers["set-cookie"])[COOKIE_NAME].value
        request = Request(
            {
                "type": "http",
                "headers": [(b"cookie", f"{COOKIE_NAME}={cookie}".encode())],
            }
        )
        self.assertEqual(session.authorization_header(request), f"Bearer {TOKEN}")
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertNotIn(TOKEN, response.headers["set-cookie"])

    def test_explicit_bearer_header_remains_available_for_isolated_api_compatibility(self) -> None:
        session = self._session()
        request = Request(
            {"type": "http", "headers": [(b"authorization", b"Bearer fixture-direct")]}
        )
        self.assertEqual(session.authorization_header(request), "Bearer fixture-direct")

    def test_missing_bootstrap_fails_closed_and_readiness_is_redacted(self) -> None:
        environment = {"STORY_AUDIO_SUPERVISED": "1"}
        session = RuntimeOperatorSession.from_environment(
            self.descriptor, self.config.auth, environment
        )
        readiness = production_runtime_readiness(
            self.descriptor,
            session=session,
            output_root=self.output,
            provider_configured=True,
            mutation_service_constructed=True,
        )
        self.assertFalse(readiness["operator_authentication_verified"])
        self.assertFalse(readiness["prepare_allowed"])
        self.assertIn("AUTH_BOOTSTRAP_MISSING", readiness["blocker_codes"])
        self.assertNotIn(TOKEN, repr(readiness))
        self.assertNotIn("token_sha256", repr(readiness).lower())

    def test_production_service_is_not_constructed_without_verified_launcher_session(self) -> None:
        session = RuntimeOperatorSession(False, "AUTH_BOOTSTRAP_MISSING")
        self.assertFalse(mutation_service_construction_allowed(self.descriptor, session))

    def test_verified_readiness_requires_no_provider_for_prepare_but_blocks_render(self) -> None:
        session = self._session()
        readiness = production_runtime_readiness(
            self.descriptor,
            session=session,
            output_root=self.output,
            provider_configured=False,
            mutation_service_constructed=True,
        )
        self.assertTrue(readiness["prepare_allowed"])
        self.assertFalse(readiness["start_render_allowed"])
        self.assertTrue(readiness["mutation_service_constructed"])
        self.assertFalse(readiness["start_render_available"])
        self.assertIn("PROVIDER_NOT_READY", readiness["start_render_blocker_codes"])


if __name__ == "__main__":
    unittest.main()
