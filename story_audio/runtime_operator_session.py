"""In-memory browser session bridge for the supervised production launcher.

The launcher owns the operator secret.  The web client must never receive that
secret or its hash, but it still needs a deterministic way to call the existing
PREPARE authentication boundary after a supervised restart.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Mapping

from starlette.requests import Request
from starlette.responses import Response

from .batch_prepare_operator_auth import OperatorAuthConfig, auth_configuration_state
from .batch_prepare_runtime_integration import PRODUCTION, RuntimeIntegrationDescriptor


BOOTSTRAP_ENV = "STORY_AUDIO_OPERATOR_TOKEN_BOOTSTRAP"
COOKIE_NAME = "story_audio_operator_session"


@dataclass
class RuntimeOperatorSession:
    """Holds one verified launcher credential without exposing it to JavaScript."""

    verified: bool
    blocker_code: str | None = None
    _token: str | None = None
    _cookie_value: str | None = None

    @classmethod
    def from_environment(
        cls,
        descriptor: RuntimeIntegrationDescriptor,
        config: OperatorAuthConfig,
        environment: Mapping[str, str] | None = None,
    ) -> "RuntimeOperatorSession":
        source = os.environ if environment is None else environment
        token = source.pop(BOOTSTRAP_ENV, None) if hasattr(source, "pop") else None
        if descriptor.runtime_mode != PRODUCTION:
            return cls(False, "RUNTIME_NOT_PRODUCTION")
        if source.get("STORY_AUDIO_SUPERVISED") != "1":
            return cls(False, "SUPERVISED_LAUNCHER_REQUIRED")
        if auth_configuration_state(config) != "AUTH_CONFIGURED":
            return cls(False, "AUTH_CONFIGURATION_INVALID")
        if not isinstance(token, str) or not token:
            return cls(False, "AUTH_BOOTSTRAP_MISSING")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(token_hash, config.token_sha256 or ""):
            return cls(False, "AUTH_BOOTSTRAP_MISMATCH")
        return cls(True, None, token, secrets.token_urlsafe(32))

    @property
    def configured(self) -> bool:
        return self._token is not None or self.verified

    def authorization_header(self, request: Request) -> str | None:
        """Prefer explicit compatibility credentials; otherwise use the HttpOnly session."""

        explicit = request.headers.get("authorization")
        if explicit:
            return explicit
        if not self.verified or not self._token or not self._cookie_value:
            return None
        presented = request.cookies.get(COOKIE_NAME, "")
        if not hmac.compare_digest(presented, self._cookie_value):
            return None
        return f"Bearer {self._token}"

    def apply_cookie(self, response: Response) -> None:
        if not self.verified or not self._cookie_value:
            return
        response.set_cookie(
            COOKIE_NAME,
            self._cookie_value,
            httponly=True,
            samesite="strict",
            secure=False,  # Canonical UI is bound to localhost HTTP.
            path="/",
        )


def mutation_service_construction_allowed(
    descriptor: RuntimeIntegrationDescriptor,
    session: RuntimeOperatorSession,
) -> bool:
    """Keep production PREPARE dormant until launcher authentication is verified."""

    return bool(
        descriptor.prepare_mutation_enabled
        and (descriptor.runtime_mode != PRODUCTION or session.verified)
    )


__all__ = [
    "BOOTSTRAP_ENV",
    "COOKIE_NAME",
    "RuntimeOperatorSession",
    "mutation_service_construction_allowed",
]
