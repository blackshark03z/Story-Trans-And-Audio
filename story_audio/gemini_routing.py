from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .config import Settings


_HTTP_STATUS = re.compile(r"Gemini HTTP\s+(\d{3})", re.IGNORECASE)
_KEY_RETRY_STATUS = {401, 403, 429}
_MODEL_FALLBACK_STATUS = {400, 403, 404, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class GeminiRouteResult:
    value: Any
    model: str
    attempt_count: int


def gemini_http_status(error: BaseException) -> int | None:
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status
    match = _HTTP_STATUS.search(str(error))
    return int(match.group(1)) if match else None


def call_gemini_with_fallback(
    config: Settings,
    provider: Callable[..., Any],
    *,
    request_data: dict[str, Any],
    models: Iterable[str] | None = None,
    provider_kwargs: dict[str, Any] | None = None,
) -> GeminiRouteResult:
    """Call Gemini without exposing keys and with bounded key/model failover.

    A 401 advances to the next configured key but does not waste calls on
    alternate models when every key is unauthenticated.  403/429 can be
    key- or model-specific, so all keys are tried before descending the model
    chain.  Model/service availability errors descend immediately.  Semantic
    validation errors and unknown failures remain fail-closed.
    """
    keys = config.gemini_keys()
    key_budget = max(1, len(keys))
    candidates = [str(item).strip() for item in (models or config.gemini_models()) if str(item).strip()]
    if not candidates:
        raise RuntimeError("Gemini model is not configured")
    extra = dict(provider_kwargs or {})
    last_error: BaseException | None = None
    attempt_count = 0
    for model in candidates:
        key_statuses: list[int | None] = []
        for _ in range(key_budget):
            api_key = config.gemini_key()
            if not api_key:
                if last_error is not None:
                    break
                raise RuntimeError("Gemini API key is not configured")
            attempt_count += 1
            try:
                return GeminiRouteResult(
                    value=provider(
                        api_key=api_key,
                        model=model,
                        request_data=request_data,
                        **extra,
                    ),
                    model=model,
                    attempt_count=attempt_count,
                )
            except Exception as exc:
                last_error = exc
                status = gemini_http_status(exc)
                key_statuses.append(status)
                if status in _KEY_RETRY_STATUS:
                    continue
                if status in _MODEL_FALLBACK_STATUS:
                    break
                raise
        if key_statuses and len(key_statuses) >= key_budget and all(status == 401 for status in key_statuses):
            assert last_error is not None
            raise last_error
    if last_error is not None:
        raise last_error
    raise RuntimeError("Gemini provider failed without a result")


__all__ = ["GeminiRouteResult", "call_gemini_with_fallback", "gemini_http_status"]
