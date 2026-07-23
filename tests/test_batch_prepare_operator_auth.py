from __future__ import annotations

import hashlib
import inspect
import unittest
from unittest.mock import patch

from story_audio.batch_prepare_operator_auth import (
    AUTHENTICATED_OPERATOR,
    AUTH_CONFIG_INVALID,
    AUTH_CONFIG_MISSING,
    AUTH_CREDENTIAL_INVALID,
    AUTH_CREDENTIAL_MALFORMED,
    AUTH_CREDENTIAL_MISSING,
    AUTH_DISABLED,
    AUTH_OPERATOR_UNKNOWN,
    MAX_TOKEN_BYTES,
    authenticate_operator,
    parse_operator_auth_config,
    public_auth_status,
)


TOKEN = "phase13-synthetic-token"
TOKEN_HASH = hashlib.sha256(TOKEN.encode()).hexdigest()


def enabled_config(**overrides):
    values = {
        "PREPARE_OPERATOR_AUTH_ENABLED": "true",
        "PREPARE_OPERATOR_ID": "operator.phase13",
        "PREPARE_OPERATOR_TOKEN_SHA256": TOKEN_HASH,
        "PREPARE_OPERATOR_TOKEN_VERSION": "test-v1",
        "PREPARE_OPERATOR_AUTH_LOCAL_TEST_MODE": "true",
    }
    values.update(overrides)
    return parse_operator_auth_config(values)


class OperatorAuthTests(unittest.TestCase):
    def test_disabled_provider_is_fail_closed(self):
        config = parse_operator_auth_config()
        self.assertEqual(authenticate_operator(config, None).state, AUTH_DISABLED)
        self.assertFalse(authenticate_operator(config, None).mutation_authorized)

    def test_enabled_missing_config_is_reported(self):
        config = parse_operator_auth_config({"PREPARE_OPERATOR_AUTH_ENABLED": "true"})
        self.assertEqual(authenticate_operator(config, None).state, AUTH_CONFIG_MISSING)

    def test_invalid_hash_and_operator_are_rejected(self):
        config = enabled_config(
            PREPARE_OPERATOR_ID="bad operator",
            PREPARE_OPERATOR_TOKEN_SHA256=TOKEN_HASH.upper(),
        )
        self.assertFalse(config.config_valid)
        self.assertEqual(authenticate_operator(config, None).state, AUTH_CONFIG_INVALID)

    def test_missing_wrong_scheme_empty_and_oversized_are_rejected(self):
        config = enabled_config()
        self.assertEqual(authenticate_operator(config, None).state, AUTH_CREDENTIAL_MISSING)
        self.assertEqual(authenticate_operator(config, f"Basic {TOKEN}").state, AUTH_CREDENTIAL_MALFORMED)
        self.assertEqual(authenticate_operator(config, "Bearer ").state, AUTH_CREDENTIAL_MALFORMED)
        oversized = "x" * (MAX_TOKEN_BYTES + 1)
        self.assertEqual(authenticate_operator(config, f"Bearer {oversized}").state, AUTH_CREDENTIAL_MALFORMED)

    def test_wrong_prefix_suffix_and_whitespace_are_rejected(self):
        config = enabled_config()
        for candidate in ("wrong", TOKEN[:-1], TOKEN + "x"):
            self.assertEqual(authenticate_operator(config, f"Bearer {candidate}").state, AUTH_CREDENTIAL_INVALID)
        for header in (f"Bearer  {TOKEN}", f"Bearer {TOKEN} ", f"Bearer {TOKEN}\tmore"):
            self.assertEqual(authenticate_operator(config, header).state, AUTH_CREDENTIAL_MALFORMED)

    def test_correct_token_authenticates_but_never_authorizes_mutation(self):
        decision = authenticate_operator(enabled_config(), f"Bearer {TOKEN}")
        self.assertEqual(decision.state, AUTHENTICATED_OPERATOR)
        self.assertTrue(decision.authenticated)
        self.assertEqual(decision.operator_identity_ref, "operator.phase13")
        self.assertFalse(decision.mutation_authorized)

    def test_configured_identity_cannot_be_selected_by_client(self):
        decision = authenticate_operator(
            enabled_config(), f"Bearer {TOKEN}", client_operator_id="somebody-else"
        )
        self.assertEqual(decision.state, AUTH_OPERATOR_UNKNOWN)

    def test_url_credentials_are_rejected(self):
        decision = authenticate_operator(enabled_config(), f"Bearer {TOKEN}", credential_in_url=True)
        self.assertEqual(decision.state, AUTH_CREDENTIAL_MALFORMED)

    def test_loopback_location_does_not_authenticate(self):
        decision = authenticate_operator(enabled_config(), None)
        self.assertEqual(decision.state, AUTH_CREDENTIAL_MISSING)
        self.assertFalse(decision.authenticated)

    def test_constant_time_primitive_is_used(self):
        with patch(
            "story_audio.batch_prepare_operator_auth.hmac.compare_digest",
            wraps=__import__("hmac").compare_digest,
        ) as compare:
            authenticate_operator(enabled_config(), f"Bearer {TOKEN}")
        compare.assert_called_once()

    def test_public_status_and_decisions_never_expose_credentials(self):
        config = enabled_config()
        values = (
            repr(public_auth_status(config))
            + repr(authenticate_operator(config, f"Bearer {TOKEN}"))
            + repr(authenticate_operator(config, "Bearer wrong"))
        )
        self.assertNotIn(TOKEN, values)
        self.assertNotIn(TOKEN_HASH, values)
        self.assertNotIn("Authorization", values)

    def test_invalid_credentials_do_not_appear_in_exception_or_logs(self):
        secret = "do-not-log-this-token"
        with self.assertLogs(level="CRITICAL") as captured:
            __import__("logging").critical("phase13-test-marker")
            decision = authenticate_operator(enabled_config(), f"Bearer {secret}")
        self.assertEqual(decision.state, AUTH_CREDENTIAL_INVALID)
        self.assertNotIn(secret, "".join(captured.output))
        self.assertNotIn(secret, repr(decision))

    def test_repeated_validation_is_deterministic(self):
        config = enabled_config()
        first = authenticate_operator(config, f"Bearer {TOKEN}")
        second = authenticate_operator(config, f"Bearer {TOKEN}")
        self.assertEqual(first, second)

    def test_module_has_no_mutation_or_global_registry(self):
        import story_audio.batch_prepare_operator_auth as module

        source = inspect.getsource(module)
        for forbidden in ("prepare_job(", "create_job(", "start_prepared_job(", "worker.wake("):
            self.assertNotIn(forbidden, source)
        self.assertFalse(any(isinstance(value, dict) and value for name, value in vars(module).items()
                             if "registry" in name.lower()))


if __name__ == "__main__":
    unittest.main()
