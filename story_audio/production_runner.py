from __future__ import annotations

import json
import sqlite3
import sys
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib import error, parse, request

from .config import canonical_production_db_path
from .files import atomic_write_bytes, sha256_file, sha256_text


EXIT_INVALID_ARGUMENTS = 2
EXIT_RUNTIME_MISMATCH = 3
EXIT_BINDING_MISMATCH = 4
EXIT_DUPLICATE_JOB = 5
EXIT_API_FAILURE = 6
EXIT_SUBMIT_PERSISTENCE_MISMATCH = 7
EXIT_INTERNAL_ERROR = 8
EXIT_WATCH_TIMEOUT = 9
EXIT_OPERATOR_INTERRUPT = 10
EXIT_TERMINAL_VALIDATION_FAILED = 11

JOB_ACTIVE_STATUSES = {
    "scheduled",
    "queued",
    "running",
    "repairing",
    "synthesizing",
    "assembling",
}
JOB_RESUMABLE_STATUSES = {"paused", "interrupted"}
JOB_TERMINAL_STATUSES = {"completed", "completed_with_errors", "failed", "cancelled"}
SEGMENT_ACTIVE_STATUSES = {"pending", "running"}
FINAL_ARTIFACT_TYPES = ("chapter_m4a", "chapter_mp3", "chapter_final_m4a", "chapter_final_mp3")


class RunnerError(RuntimeError):
    exit_code = EXIT_BINDING_MISMATCH
    status = "error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None, mutation_performed: bool = False):
        super().__init__(message)
        self.details = details or {}
        self.mutation_performed = mutation_performed


class ArgumentError(RunnerError):
    exit_code = EXIT_INVALID_ARGUMENTS
    status = "invalid_arguments"


class RuntimeMismatchError(RunnerError):
    exit_code = EXIT_RUNTIME_MISMATCH
    status = "runtime_mismatch"


class BindingMismatchError(RunnerError):
    exit_code = EXIT_BINDING_MISMATCH
    status = "binding_mismatch"


class DuplicateJobError(RunnerError):
    exit_code = EXIT_DUPLICATE_JOB
    status = "duplicate_job"


class ApiFailureError(RunnerError):
    exit_code = EXIT_API_FAILURE
    status = "api_failure"


class SubmitPersistenceError(RunnerError):
    exit_code = EXIT_SUBMIT_PERSISTENCE_MISMATCH
    status = "submit_persistence_mismatch"


class InternalRunnerError(RunnerError):
    exit_code = EXIT_INTERNAL_ERROR
    status = "internal_error"


class WatchTimeoutError(RunnerError):
    exit_code = EXIT_WATCH_TIMEOUT
    status = "watch_timeout"


class OperatorInterruptError(RunnerError):
    exit_code = EXIT_OPERATOR_INTERRUPT
    status = "operator_interrupt"


class TerminalValidationError(RunnerError):
    exit_code = EXIT_TERMINAL_VALIDATION_FAILED
    status = "terminal_validation_failed"


def _canonical_json(value: Any, *, ensure_ascii: bool = True) -> str:
    return json.dumps(value, ensure_ascii=ensure_ascii, sort_keys=True, separators=(",", ":"))


def _check_strings_for_replacement(value: Any) -> None:
    if isinstance(value, str):
        if "\ufffd" in value:
            raise BindingMismatchError("Request payload contains Unicode replacement character")
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            _check_strings_for_replacement(key)
            _check_strings_for_replacement(nested)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _check_strings_for_replacement(nested)


def build_unicode_safe_json_bytes(
    payload: dict[str, Any],
    *,
    unicode_identity_fields: tuple[str, ...] = ("voice_name",),
) -> bytes:
    _check_strings_for_replacement(payload)
    payload_bytes = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    parsed = json.loads(payload_bytes.decode("ascii"))
    if parsed != payload:
        raise BindingMismatchError("Serialized request payload does not round-trip exactly")
    for field in unicode_identity_fields:
        if field not in payload:
            continue
        source = payload[field]
        parsed_value = parsed.get(field)
        if not isinstance(source, str) or not isinstance(parsed_value, str):
            raise BindingMismatchError(f"Unicode identity field {field} must remain a string")
        if source != parsed_value:
            raise BindingMismatchError(f"Unicode identity field {field} changed during serialization")
        if "\ufffd" in source:
            raise BindingMismatchError(f"Unicode identity field {field} contains invalid replacement characters")
    return payload_bytes


def canonicalize_data_root(value: str, *, allow_canonical_production: bool = False) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ArgumentError("--data-root must be an absolute path")
    resolved = path.resolve()
    if not resolved.exists():
        raise ArgumentError("--data-root must already exist")
    live_root = canonical_production_db_path().resolve().parent
    if resolved == live_root and not allow_canonical_production:
        raise RuntimeMismatchError("Refusing canonical live data root")
    return resolved


def normalize_api_base(value: str) -> str:
    base = value.strip().rstrip("/")
    if not base:
        raise ArgumentError("--api-base is required")
    parsed_base = parse.urlparse(base)
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
        raise ArgumentError("--api-base must be an absolute http(s) base URL")
    return base


def normalize_manifest_path(value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        raise ArgumentError("--manifest-out must be an absolute path")
    return path.resolve()


def normalize_poll_interval(value: float) -> float:
    if value <= 0:
        raise ArgumentError("--poll-interval must be greater than 0")
    return max(0.2, float(value))


def normalize_timeout_seconds(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= 0:
        raise ArgumentError("--timeout-seconds must be greater than 0")
    return float(value)


@dataclass(frozen=True)
class RuntimeIdentity:
    api_base: str
    root: str
    data_root: str
    db_path: str
    schema_version: int
    latest_schema_version: int
    canonical_live_data_root: str
    canonical_live_db_path: str
    is_canonical_live_data_root: bool
    is_canonical_live_db: bool


class HttpJsonClient:
    def __init__(self, api_base: str, timeout_seconds: float = 30.0):
        self.api_base = api_base.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = self._url(path, params=params)
        req = request.Request(url, method="GET")
        return self._send(req)

    def post_json_bytes(self, path: str, payload_bytes: bytes) -> Any:
        url = self._url(path)
        req = request.Request(
            url,
            data=payload_bytes,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        return self._send(req)

    def post_empty_json(self, path: str) -> Any:
        return self.post_json_bytes(path, b"{}")

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        url = f"{self.api_base}{path}"
        if params:
            clean = {key: value for key, value in params.items() if value is not None}
            query = parse.urlencode(clean, doseq=True)
            if query:
                url = f"{url}?{query}"
        return url

    def _send(self, req: request.Request) -> Any:
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ApiFailureError(
                f"HTTP {exc.code} for {req.method} {req.full_url}",
                details={"status_code": exc.code, "body": detail},
            ) from exc
        except error.URLError as exc:
            raise ApiFailureError(f"Network failure for {req.method} {req.full_url}: {exc.reason}") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ApiFailureError(
                f"Invalid JSON response for {req.method} {req.full_url}",
                details={"body": raw},
            ) from exc


def fetch_runtime_identity(
    client: HttpJsonClient,
    expected_data_root: Path,
    *,
    allow_canonical_production: bool = False,
) -> RuntimeIdentity:
    payload = client.get_json("/api/runtime")
    identity = RuntimeIdentity(
        api_base=client.api_base,
        root=str(payload["root"]),
        data_root=str(payload["data_root"]),
        db_path=str(payload["db_path"]),
        schema_version=int(payload["schema_version"]),
        latest_schema_version=int(payload["latest_schema_version"]),
        canonical_live_data_root=str(payload["canonical_live_data_root"]),
        canonical_live_db_path=str(payload["canonical_live_db_path"]),
        is_canonical_live_data_root=bool(payload["is_canonical_live_data_root"]),
        is_canonical_live_db=bool(payload["is_canonical_live_db"]),
    )
    if Path(identity.data_root).resolve() != expected_data_root.resolve():
        raise RuntimeMismatchError(
            "API server is using a different data root",
            details={"expected_data_root": str(expected_data_root), "api_data_root": identity.data_root},
        )
    if (identity.is_canonical_live_data_root or identity.is_canonical_live_db) and not allow_canonical_production:
        raise RuntimeMismatchError("API server is pointing at canonical live storage")
    return identity


def _require_field(mapping: dict[str, Any], field: str, context: str) -> Any:
    if field not in mapping:
        raise BindingMismatchError(f"{context} is missing required field {field}")
    return mapping[field]


def _chapter_from_number(client: HttpJsonClient, book_id: int, chapter_number: int) -> dict[str, Any]:
    payload = client.get_json(
        f"/api/books/{book_id}/chapters",
        params={"offset": 0, "limit": 20, "query": str(chapter_number)},
    )
    items = [item for item in payload.get("items", []) if int(item["chapter_number"]) == chapter_number]
    if len(items) != 1:
        raise BindingMismatchError("Could not resolve exactly one chapter from chapter number")
    chapter = items[0]
    _require_field(chapter, "id", "Chapter list item")
    _require_field(chapter, "chapter_number", "Chapter list item")
    return chapter


def _active_revision(chapter_detail: dict[str, Any]) -> dict[str, Any]:
    chapter = chapter_detail["chapter"]
    active_revision_id = chapter.get("active_text_revision_id")
    approved = [item for item in chapter_detail["revisions"] if item.get("status") == "approved"]
    if not active_revision_id:
        raise BindingMismatchError("Chapter does not have an active Text Revision")
    matches = [item for item in approved if int(item["id"]) == int(active_revision_id)]
    if len(matches) != 1:
        raise BindingMismatchError("Active Text Revision is missing or not approved")
    revision = matches[0]
    if not revision.get("content_sha256"):
        raise BindingMismatchError("Active Text Revision is missing content hash")
    return revision


def _voice_distribution(plan: dict[str, Any]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str], int] = {}
    for utterance in plan["utterances"]:
        key = (str(utterance.get("role") or "unknown"), str(utterance["resolved_voice_id"]))
        counts[key] = counts.get(key, 0) + 1
    return [
        {"role": role, "voice_id": voice_id, "utterance_count": count}
        for (role, voice_id), count in sorted(counts.items())
    ]


def _derive_default_voice(plan_detail: dict[str, Any], profile_detail: dict[str, Any]) -> dict[str, Any]:
    plan = plan_detail["plan"]
    profile = profile_detail.get("profile")
    plan_profile = plan.get("book_voice_profile")
    if not isinstance(plan_profile, dict):
        raise BindingMismatchError("Casting Plan is missing pinned Book Voice Profile snapshot")
    required_fields = (
        "id",
        "config_version",
        "narrator_voice_id",
        "male_dialogue_voice_id",
        "female_dialogue_voice_id",
        "unknown_fallback",
    )
    for field in required_fields:
        if field not in plan_profile:
            raise BindingMismatchError(f"Casting Plan profile snapshot is missing {field}")
    current_profile = None
    drift = None
    if profile:
        current_profile = {"id": int(profile["id"]), "config_version": int(profile["config_version"])}
        if int(plan_profile["id"]) != current_profile["id"] or int(plan_profile["config_version"]) != current_profile["config_version"]:
            drift = {
                "current_profile_id": current_profile["id"],
                "current_profile_version": current_profile["config_version"],
                "warning": "Current Book Voice Profile has drifted; runner will use immutable approved plan snapshot.",
            }
    narrator_voice = str(plan.get("narrator_voice_id") or "").strip()
    if not narrator_voice:
        raise BindingMismatchError("Casting Plan narrator voice is missing")
    if narrator_voice != str(plan_profile["narrator_voice_id"]):
        raise BindingMismatchError("Casting Plan narrator voice does not match pinned Book Voice Profile snapshot")
    return {
        "voice_id": narrator_voice,
        "profile_id": int(plan_profile["id"]),
        "profile_version": int(plan_profile["config_version"]),
        "current_profile": current_profile,
        "profile_drift": drift,
    }


def _verify_plan(plan_detail: dict[str, Any], chapter_id: int, revision: dict[str, Any]) -> None:
    if int(plan_detail["chapter_id"]) != chapter_id:
        raise BindingMismatchError("Casting Plan belongs to a different chapter")
    if str(plan_detail["status"]) != "approved":
        raise BindingMismatchError("Casting Plan must be approved")
    if int(plan_detail["text_revision_id"]) != int(revision["id"]):
        raise BindingMismatchError("Casting Plan does not bind the active Text Revision")
    if not plan_detail.get("plan_sha256"):
        raise BindingMismatchError("Casting Plan SHA-256 is missing")
    plan = plan_detail["plan"]
    if not isinstance(plan.get("utterances"), list) or not plan["utterances"]:
        raise BindingMismatchError("Casting Plan utterances are missing")
    for utterance in plan["utterances"]:
        resolved_voice_id = str(utterance.get("resolved_voice_id") or "").strip()
        if not resolved_voice_id:
            raise BindingMismatchError("Casting Plan contains an utterance without resolved voice")


def _voice_catalog(client: HttpJsonClient) -> dict[str, str]:
    payload = client.get_json("/api/voices")
    items = payload.get("items", [])
    catalog = {str(item["id"]): str(item.get("label") or item["id"]) for item in items}

    custom_items = client.get_json("/api/custom-voices", params={"active_only": "true"})
    if not isinstance(custom_items, list):
        raise BindingMismatchError("Custom voice catalog response is invalid")
    for item in custom_items:
        voice_id = item.get("id")
        if voice_id is None:
            raise BindingMismatchError("Custom voice catalog entry is missing id")
        logical_ref = f"custom:{int(voice_id)}"
        revisions = client.get_json(f"/api/custom-voices/{int(voice_id)}/revisions")
        if not isinstance(revisions, list):
            raise BindingMismatchError("Custom voice revisions response is invalid")
        preferred_revision_id = item.get("preferred_synthesis_revision_id")
        has_usable_revision = bool(revisions)
        if preferred_revision_id is not None:
            has_usable_revision = any(int(revision["id"]) == int(preferred_revision_id) for revision in revisions)
            if not has_usable_revision and revisions:
                has_usable_revision = True
        if not has_usable_revision:
            continue
        catalog[logical_ref] = str(item.get("display_name") or logical_ref)
    return catalog


def _verify_voice_availability(plan_detail: dict[str, Any], voice_catalog: dict[str, str]) -> None:
    plan = plan_detail["plan"]
    required = {str(plan["narrator_voice_id"])}
    required.update(str(item["resolved_voice_id"]) for item in plan["utterances"])
    missing = sorted(voice_id for voice_id in required if voice_id not in voice_catalog)
    if missing:
        raise BindingMismatchError(
            "Casting Plan contains unavailable voice(s)",
            details={"missing_voice_ids": missing},
        )


def _job_snapshot_matches(
    *,
    book_id: int,
    job_detail: dict[str, Any],
    chapter: dict[str, Any],
    revision: dict[str, Any],
    plan_detail: dict[str, Any],
    output_format: str,
    repair_mode: str,
    default_voice_id: str,
    profile_id: int,
    profile_version: int,
) -> bool:
    job = job_detail["job"]
    chapters = job_detail["chapters"]
    chapter_number = int(chapter.get("chapter_number", chapter.get("number")))
    if int(job["book_id"]) != int(book_id):
        return False
    if int(job["from_chapter"]) != chapter_number or int(job["to_chapter"]) != chapter_number:
        return False
    if str(job["repair_mode"]) != repair_mode or str(job["output_format"]) != output_format:
        return False
    if str(job["voice_name"]) != default_voice_id:
        return False
    if int(job.get("casting_plan_id") or 0) != int(plan_detail["id"]):
        return False
    if len(chapters) != 1:
        return False
    chapter_row = chapters[0]
    if int(chapter_row["chapter_id"]) != int(chapter["id"]):
        return False
    if int(chapter_row.get("text_revision_id") or 0) != int(revision["id"]):
        return False
    if int(chapter_row.get("casting_plan_id") or 0) != int(plan_detail["id"]):
        return False
    if str(chapter_row.get("casting_plan_sha256") or "") != str(plan_detail["plan_sha256"]):
        return False
    snapshot_raw = chapter_row.get("voice_snapshot_json")
    if not snapshot_raw:
        return False
    snapshot = json.loads(snapshot_raw)
    if int(snapshot.get("text_revision_id") or 0) != int(revision["id"]):
        return False
    if int(snapshot.get("casting_plan_id") or 0) != int(plan_detail["id"]):
        return False
    if str(snapshot.get("casting_plan_sha256") or "") != str(plan_detail["plan_sha256"]):
        return False
    if str(snapshot.get("narrator_voice_id") or "") != default_voice_id:
        return False
    book_voice_profile = snapshot.get("book_voice_profile") or {}
    if int(book_voice_profile.get("id") or 0) != profile_id:
        return False
    if int(book_voice_profile.get("config_version") or 0) != profile_version:
        return False
    return True


def _duplicate_result_for_status(job_id: int, status: str) -> dict[str, Any]:
    if status in JOB_ACTIVE_STATUSES | JOB_RESUMABLE_STATUSES:
        return {
            "duplicate": True,
            "existing_job_id": job_id,
            "existing_job_status": status,
            "result": "existing_active_job",
            "recommended_action": "operator_resume_or_inspect_existing_job",
        }
    if status == "completed":
        return {
            "duplicate": True,
            "existing_job_id": job_id,
            "existing_job_status": status,
            "result": "already_completed",
            "recommended_action": "reuse_existing_completed_job",
        }
    if status in {"failed", "cancelled", "completed_with_errors"}:
        return {
            "duplicate": True,
            "existing_job_id": job_id,
            "existing_job_status": status,
            "result": "existing_terminal_job_requires_operator_decision",
            "recommended_action": "operator_decide_in_task_11b2",
        }
    return {
        "duplicate": True,
        "existing_job_id": job_id,
        "existing_job_status": status,
        "result": "existing_job_detected",
        "recommended_action": "operator_inspect_existing_job",
    }


def _find_duplicate_job(
    client: HttpJsonClient,
    *,
    book_id: int,
    chapter: dict[str, Any],
    revision: dict[str, Any],
    plan_detail: dict[str, Any],
    output_format: str,
    repair_mode: str,
    default_voice_id: str,
    profile_id: int,
    profile_version: int,
) -> dict[str, Any]:
    jobs = client.get_json("/api/jobs")
    matches: list[dict[str, Any]] = []
    chapter_number = int(_require_field(chapter, "chapter_number", "Chapter list item"))
    for job in jobs:
        candidate_plan_id = job.get("casting_plan_id")
        if candidate_plan_id is None or int(candidate_plan_id) != int(plan_detail["id"]):
            continue
        if int(job["book_id"]) != int(book_id):
            continue
        if int(job["from_chapter"]) != chapter_number or int(job["to_chapter"]) != chapter_number:
            continue
        if str(job["repair_mode"]) != repair_mode or str(job["output_format"]) != output_format:
            continue
        detail = client.get_json(f"/api/jobs/{int(job['id'])}")
        if _job_snapshot_matches(
            book_id=book_id,
            job_detail=detail,
            chapter=chapter,
            revision=revision,
            plan_detail=plan_detail,
            output_format=output_format,
            repair_mode=repair_mode,
            default_voice_id=default_voice_id,
            profile_id=profile_id,
            profile_version=profile_version,
        ):
            matches.append(detail)
    if not matches:
        return {"duplicate": False, "matches": []}
    if len(matches) > 1:
        raise DuplicateJobError(
            "Multiple jobs share the same production identity",
            details={"job_ids": [int(item["job"]["id"]) for item in matches]},
        )
    detail = matches[0]
    duplicate = _duplicate_result_for_status(int(detail["job"]["id"]), str(detail["job"]["status"]))
    duplicate["matches"] = [detail["job"]]
    return duplicate


def _build_submit_payload(
    *,
    book_id: int,
    chapter_number: int,
    casting_plan_id: int,
    output_format: str,
    default_voice_id: str,
) -> tuple[dict[str, Any], bytes]:
    payload = {
        "book_id": int(book_id),
        "from_chapter": int(chapter_number),
        "to_chapter": int(chapter_number),
        "voice_name": str(default_voice_id),
        "repair_mode": "off",
        "output_format": str(output_format),
        "skip_completed": False,
        "casting_plan_id": int(casting_plan_id),
    }
    payload_bytes = build_unicode_safe_json_bytes(payload, unicode_identity_fields=("voice_name",))
    return payload, payload_bytes


def run_preflight(
    client: HttpJsonClient,
    *,
    data_root: Path,
    book_id: int,
    chapter_number: int,
    casting_plan_id: int,
    output_format: str,
    allow_canonical_production: bool = False,
) -> dict[str, Any]:
    runtime = fetch_runtime_identity(
        client,
        data_root,
        allow_canonical_production=allow_canonical_production,
    )
    chapter = _chapter_from_number(client, book_id, chapter_number)
    chapter_detail = client.get_json(f"/api/chapters/{int(chapter['id'])}")
    revision = _active_revision(chapter_detail)
    plan_detail = client.get_json(f"/api/casting/{casting_plan_id}")
    _verify_plan(plan_detail, int(chapter["id"]), revision)
    profile_detail = client.get_json(f"/api/books/{book_id}/voice-profile")
    default_voice = _derive_default_voice(plan_detail, profile_detail)
    voice_catalog = _voice_catalog(client)
    _verify_voice_availability(plan_detail, voice_catalog)
    duplicate = _find_duplicate_job(
        client,
        book_id=book_id,
        chapter=chapter,
        revision=revision,
        plan_detail=plan_detail,
        output_format=output_format,
        repair_mode="off",
        default_voice_id=default_voice["voice_id"],
        profile_id=default_voice["profile_id"],
        profile_version=default_voice["profile_version"],
    )
    payload, payload_bytes = _build_submit_payload(
        book_id=book_id,
        chapter_number=chapter_number,
        casting_plan_id=casting_plan_id,
        output_format=output_format,
        default_voice_id=default_voice["voice_id"],
    )
    return {
        "status": "preflight_pass" if not duplicate["duplicate"] else duplicate["result"],
        "runtime_identity": {
            "api_base": runtime.api_base,
            "data_root": runtime.data_root,
            "db_path": runtime.db_path,
            "schema_version": runtime.schema_version,
            "latest_schema_version": runtime.latest_schema_version,
            "canonical_live_data_root": runtime.canonical_live_data_root,
            "canonical_live_db_path": runtime.canonical_live_db_path,
            "is_canonical_live_data_root": runtime.is_canonical_live_data_root,
            "is_canonical_live_db": runtime.is_canonical_live_db,
        },
        "book": {"id": int(book_id)},
        "chapter": {
            "id": int(_require_field(chapter, "id", "Chapter list item")),
            "book_id": int(book_id),
            "number": int(_require_field(chapter, "chapter_number", "Chapter list item")),
            "title": chapter.get("title"),
        },
        "text_revision": {
            "id": int(revision["id"]),
            "content_sha256": str(revision["content_sha256"]),
            "status": str(revision["status"]),
        },
        "casting_plan": {
            "id": int(plan_detail["id"]),
            "revision": int(plan_detail["plan_revision"]),
            "sha256": str(plan_detail["plan_sha256"]),
            "character_bible_fingerprint": plan_detail.get("character_bible_fingerprint"),
        },
        "book_voice_profile": {
            "id": int(default_voice["profile_id"]),
            "config_version": int(default_voice["profile_version"]),
            "current_profile": default_voice["current_profile"],
            "profile_drift": default_voice["profile_drift"],
        },
        "derived_default_voice": {
            "voice_id": default_voice["voice_id"],
            "label": voice_catalog.get(default_voice["voice_id"], default_voice["voice_id"]),
        },
        "expected_utterance_count": len(plan_detail["plan"]["utterances"]),
        "speaker_voice_distribution": _voice_distribution(plan_detail["plan"]),
        "duplicate_job": duplicate,
        "request_preview": {
            "payload": payload,
            "payload_bytes_ascii": payload_bytes.decode("ascii"),
            "contains_substitution_question_mark": "?" in payload["voice_name"],
            "contains_replacement_char": False,
        },
        "mutation_performed": False,
    }


def verify_created_job(
    client: HttpJsonClient,
    *,
    book_id: int,
    job_id: int,
    chapter: dict[str, Any],
    revision: dict[str, Any],
    plan_detail: dict[str, Any],
    output_format: str,
    default_voice_id: str,
    profile_id: int,
    profile_version: int,
) -> dict[str, Any]:
    detail = client.get_json(f"/api/jobs/{job_id}")
    if not _job_snapshot_matches(
        book_id=book_id,
        job_detail=detail,
        chapter=chapter,
        revision=revision,
        plan_detail=plan_detail,
        output_format=output_format,
        repair_mode="off",
        default_voice_id=default_voice_id,
        profile_id=profile_id,
        profile_version=profile_version,
    ):
        raise SubmitPersistenceError("Created job bindings do not match preflight identity")
    chapter_row = detail["chapters"][0]
    return {
        "job_id": int(detail["job"]["id"]),
        "initial_status": str(detail["job"]["status"]),
        "job_chapter_id": int(chapter_row["id"]),
    }


def run_submit(
    client: HttpJsonClient,
    *,
    data_root: Path,
    book_id: int,
    chapter_number: int,
    casting_plan_id: int,
    output_format: str,
    allow_canonical_production: bool = False,
) -> dict[str, Any]:
    preflight = run_preflight(
        client,
        data_root=data_root,
        book_id=book_id,
        chapter_number=chapter_number,
        casting_plan_id=casting_plan_id,
        output_format=output_format,
        allow_canonical_production=allow_canonical_production,
    )
    duplicate = preflight["duplicate_job"]
    if duplicate["duplicate"]:
        raise DuplicateJobError("Duplicate production job already exists", details=duplicate)
    payload = preflight["request_preview"]["payload"]
    payload_bytes = build_unicode_safe_json_bytes(payload, unicode_identity_fields=("voice_name",))
    response = client.post_json_bytes("/api/jobs", payload_bytes)
    job_id = int(response["job_id"])
    verification = verify_created_job(
        client,
        book_id=book_id,
        job_id=job_id,
        chapter=preflight["chapter"],
        revision=preflight["text_revision"],
        plan_detail={
            "id": preflight["casting_plan"]["id"],
            "plan_revision": preflight["casting_plan"]["revision"],
            "plan_sha256": preflight["casting_plan"]["sha256"],
        } | client.get_json(f"/api/casting/{int(preflight['casting_plan']['id'])}"),
        output_format=output_format,
        default_voice_id=preflight["derived_default_voice"]["voice_id"],
        profile_id=preflight["book_voice_profile"]["id"],
        profile_version=preflight["book_voice_profile"]["config_version"],
    )
    preflight["status"] = "submitted"
    preflight["job"] = verification
    preflight["mutation_performed"] = True
    return preflight


def _load_verified_identity(preflight: dict[str, Any]) -> dict[str, Any]:
    return {
        "book_id": int(preflight["book"]["id"]),
        "chapter": {
            "id": int(preflight["chapter"]["id"]),
            "chapter_number": int(preflight["chapter"]["number"]),
            "title": preflight["chapter"].get("title"),
        },
        "revision": {
            "id": int(preflight["text_revision"]["id"]),
        },
        "plan": {
            "id": int(preflight["casting_plan"]["id"]),
            "plan_sha256": str(preflight["casting_plan"]["sha256"]),
        },
        "output_format": str(preflight["request_preview"]["payload"]["output_format"]),
        "repair_mode": str(preflight["request_preview"]["payload"]["repair_mode"]),
        "default_voice_id": str(preflight["derived_default_voice"]["voice_id"]),
        "profile_id": int(preflight["book_voice_profile"]["id"]),
        "profile_version": int(preflight["book_voice_profile"]["config_version"]),
    }


def _fetch_and_verify_job_detail(client: HttpJsonClient, preflight: dict[str, Any], job_id: int) -> dict[str, Any]:
    detail = client.get_json(f"/api/jobs/{job_id}")
    identity = _load_verified_identity(preflight)
    if not _job_snapshot_matches(
        book_id=identity["book_id"],
        job_detail=detail,
        chapter=identity["chapter"],
        revision=identity["revision"],
        plan_detail=identity["plan"],
        output_format=identity["output_format"],
        repair_mode=identity["repair_mode"],
        default_voice_id=identity["default_voice_id"],
        profile_id=identity["profile_id"],
        profile_version=identity["profile_version"],
    ):
        raise BindingMismatchError(
            f"Job {job_id} does not match the verified production identity",
            details={"job_id": int(job_id)},
        )
    if len(detail["chapters"]) != 1:
        raise BindingMismatchError("Production runner requires exactly one job chapter")
    return detail


def _resolve_target_job_id(preflight: dict[str, Any], explicit_job_id: int | None, created_job_id: int | None) -> int:
    duplicate = preflight["duplicate_job"]
    if explicit_job_id is not None:
        return int(explicit_job_id)
    if created_job_id is not None:
        return int(created_job_id)
    if duplicate.get("duplicate") and duplicate.get("existing_job_id") is not None:
        return int(duplicate["existing_job_id"])
    raise BindingMismatchError("No canonical job is available for watch/resume; use --submit or --job-id")


def _monitor_job_progress(
    client: HttpJsonClient,
    *,
    job_id: int,
    poll_interval: float,
    timeout_seconds: float | None,
    emit_progress: Callable[[dict[str, Any]], None],
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    started = monotonic_fn()
    last_signature = None
    last_snapshot = None
    while True:
        detail = client.get_json(f"/api/jobs/{job_id}")
        chapter_row = detail["chapters"][0]
        diagnostics = client.get_json(f"/api/diagnostics/job-chapters/{int(chapter_row['id'])}")
        segments = diagnostics.get("segments", [])
        counts = {
            "verified": sum(1 for item in segments if item["status"] == "verified"),
            "failed": sum(1 for item in segments if item["status"] == "failed"),
            "running": sum(1 for item in segments if item["status"] == "running"),
            "pending": sum(1 for item in segments if item["status"] == "pending"),
        }
        current_segment = None
        running_segments = [item for item in segments if item["status"] == "running"]
        if len(running_segments) == 1:
            current_segment = {
                "segment_id": int(running_segments[0]["id"]),
                "sequence": int(running_segments[0]["segment_index"]),
            }
        elapsed = monotonic_fn() - started
        snapshot = {
            "job_id": int(job_id),
            "job_status": str(detail["job"]["status"]),
            "job_chapter_id": int(chapter_row["id"]),
            "job_chapter_status": str(chapter_row["status"]),
            "verified_segments": counts["verified"],
            "failed_segments": counts["failed"],
            "running_segments": counts["running"],
            "pending_segments": counts["pending"],
            "total_segments": len(segments),
            "current_segment": current_segment,
            "started_at": detail["job"].get("started_at"),
            "updated_at": detail["job"].get("updated_at"),
            "finished_at": detail["job"].get("finished_at"),
            "elapsed_seconds": round(elapsed, 3),
        }
        signature = _canonical_json(snapshot)
        if signature != last_signature:
            emit_progress(snapshot)
            last_signature = signature
        last_snapshot = snapshot
        if snapshot["job_status"] in JOB_TERMINAL_STATUSES:
            return snapshot
        if snapshot["job_status"] in JOB_RESUMABLE_STATUSES:
            return snapshot
        if timeout_seconds is not None and elapsed >= timeout_seconds:
            raise WatchTimeoutError(
                "Timed out while watching job progress",
                details={"job_id": int(job_id), "last_progress": snapshot},
            )
        sleep_fn(poll_interval)


def _open_readonly_db(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _path_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _relative_to_root(path: Path, root: Path) -> str:
    if not _path_within_root(path, root):
        raise TerminalValidationError(
            "Artifact path escapes isolated data root",
            details={"path": str(path), "data_root": str(root)},
        )
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def _artifact_mime(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".m4a":
        return "audio/mp4"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".json":
        return "application/json"
    return None


def _render_generation_from_path(path: Path) -> str:
    render_dir = path.resolve().parent.name
    if not render_dir.startswith("render_"):
        raise TerminalValidationError(
            "Could not determine render generation from artifact path",
            details={"path": str(path)},
        )
    return render_dir


def _select_render_artifacts(rows: list[sqlite3.Row], output_format: str) -> tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row, str]:
    final_candidates = [
        row
        for row in rows
        if row["artifact_type"] in {f"chapter_{output_format}", f"chapter_final_{output_format}"} and row["status"] == "active"
    ]
    if len(final_candidates) != 1:
        raise TerminalValidationError(
            "Expected exactly one active final artifact",
            details={"artifact_types": [dict(row) for row in final_candidates]},
        )
    final_artifact = final_candidates[0]
    final_path = Path(final_artifact["path"]).resolve()
    render_generation = _render_generation_from_path(final_path)
    same_render = [row for row in rows if Path(row["path"]).resolve().parent == final_path.parent]
    master_candidates = [row for row in same_render if row["artifact_type"] == "chapter_master_wav"]
    timeline_candidates = [row for row in same_render if row["artifact_type"] == "segment_timeline_json"]
    if len(master_candidates) != 1 or len(timeline_candidates) != 1:
        raise TerminalValidationError(
            "Current render generation is missing master or timeline artifacts",
            details={
                "render_generation": render_generation,
                "master_count": len(master_candidates),
                "timeline_count": len(timeline_candidates),
            },
        )
    return master_candidates[0], timeline_candidates[0], final_artifact, render_generation


def _validate_file_hash(path: Path, expected_sha: str | None, data_root: Path) -> tuple[str, int, float]:
    if not _path_within_root(path, data_root):
        raise TerminalValidationError(
            "Artifact path escapes isolated data root",
            details={"path": str(path), "data_root": str(data_root)},
        )
    if path.is_symlink():
        raise TerminalValidationError("Artifact path must not be a symlink", details={"path": str(path)})
    if not path.exists():
        raise TerminalValidationError("Artifact file is missing", details={"path": str(path)})
    if not path.is_file():
        raise TerminalValidationError("Artifact path is not a file", details={"path": str(path)})
    actual_sha = sha256_file(path)
    if expected_sha and actual_sha != expected_sha:
        raise TerminalValidationError(
            "Artifact hash mismatch",
            details={"path": str(path), "expected_sha256": expected_sha, "actual_sha256": actual_sha},
        )
    stat = path.stat()
    return actual_sha, int(stat.st_size), float(stat.st_mtime)


def _load_manifest_context(db_path: Path, job_id: int) -> dict[str, Any]:
    with closing(_open_readonly_db(db_path)) as connection:
        job = connection.execute(
            """
            SELECT j.*, b.title AS book_title
            FROM jobs j
            JOIN books b ON b.id = j.book_id
            WHERE j.id = ?
            """,
            (job_id,),
        ).fetchone()
        if job is None:
            raise TerminalValidationError("Job not found in local database", details={"job_id": int(job_id)})
        chapters = connection.execute(
            """
            SELECT jc.*, c.book_id, c.chapter_number, c.title AS chapter_title, c.active_audio_artifact_id
            FROM job_chapters jc
            JOIN chapters c ON c.id = jc.chapter_id
            WHERE jc.job_id = ?
            ORDER BY jc.sequence
            """,
            (job_id,),
        ).fetchall()
        if len(chapters) != 1:
            raise TerminalValidationError("Manifest requires exactly one job chapter", details={"job_id": int(job_id)})
        chapter = chapters[0]
        text_revision = None
        if chapter["text_revision_id"] is not None:
            text_revision = connection.execute(
                "SELECT * FROM text_revisions WHERE id = ?",
                (chapter["text_revision_id"],),
            ).fetchone()
        segments = connection.execute(
            """
            SELECT *
            FROM segments
            WHERE job_chapter_id = ?
            ORDER BY segment_index
            """,
            (chapter["id"],),
        ).fetchall()
        artifacts = connection.execute(
            """
            SELECT *
            FROM artifacts
            WHERE job_chapter_id = ? AND deleted_at IS NULL
            ORDER BY id
            """,
            (chapter["id"],),
        ).fetchall()
        candidate_attempts = int(connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM segment_attempts sa
            JOIN segments s ON s.id = sa.segment_id
            WHERE s.job_chapter_id = ? AND sa.status = 'candidate'
            """,
            (chapter["id"],),
        ).fetchone()["count"])
    return {
        "job": dict(job),
        "job_chapter": dict(chapter),
        "text_revision": dict(text_revision) if text_revision is not None else None,
        "segments": [dict(row) for row in segments],
        "artifacts": [dict(row) for row in artifacts],
        "candidate_attempts": candidate_attempts,
    }


def build_completed_manifest(
    *,
    data_root: Path,
    db_path: Path,
    preflight: dict[str, Any],
    job_id: int,
) -> dict[str, Any]:
    context = _load_manifest_context(db_path, job_id)
    job = context["job"]
    chapter = context["job_chapter"]
    segments = context["segments"]
    artifacts = context["artifacts"]
    text_revision = context["text_revision"]
    if str(job["status"]) != "completed":
        raise TerminalValidationError("Job is not completed", details={"job_id": int(job_id), "status": job["status"]})
    if str(chapter["status"]) != "completed":
        raise TerminalValidationError(
            "Job chapter is not completed",
            details={"job_id": int(job_id), "job_chapter_id": int(chapter["id"]), "status": chapter["status"]},
        )
    if context["candidate_attempts"] != 0:
        raise TerminalValidationError(
            "Open candidate attempts exist for completed chapter",
            details={"job_id": int(job_id), "candidate_attempts": context["candidate_attempts"]},
        )
    total_segments = len(segments)
    verified_segments = [segment for segment in segments if segment["status"] == "verified"]
    failed_segments = [segment for segment in segments if segment["status"] == "failed"]
    running_segments = [segment for segment in segments if segment["status"] == "running"]
    pending_segments = [segment for segment in segments if segment["status"] == "pending"]
    if total_segments == 0:
        raise TerminalValidationError("Completed job has no segments", details={"job_id": int(job_id)})
    if failed_segments or running_segments or pending_segments or len(verified_segments) != total_segments:
        raise TerminalValidationError(
            "Completed job has incomplete segment state",
            details={
                "job_id": int(job_id),
                "total_segments": total_segments,
                "verified_segments": len(verified_segments),
                "failed_segments": len(failed_segments),
                "running_segments": len(running_segments),
                "pending_segments": len(pending_segments),
            },
        )
    sequences = [int(segment["segment_index"]) for segment in segments]
    duplicate_sequences = sorted({sequence for sequence in sequences if sequences.count(sequence) > 1})
    missing_sequences = sorted(set(range(min(sequences), max(sequences) + 1)) - set(sequences))
    if duplicate_sequences or missing_sequences:
        raise TerminalValidationError(
            "Segment sequence continuity failed",
            details={"duplicate_sequences": duplicate_sequences, "missing_sequences": missing_sequences},
        )
    expected_casting_plan_id = int(preflight["casting_plan"]["id"])
    persisted_casting_plan_id = chapter.get("casting_plan_id")
    if persisted_casting_plan_id is not None and int(persisted_casting_plan_id) != expected_casting_plan_id:
        raise TerminalValidationError(
            "Job chapter casting plan binding drifted",
            details={
                "job_chapter_id": int(chapter["id"]),
                "expected_casting_plan_id": expected_casting_plan_id,
                "persisted_casting_plan_id": int(persisted_casting_plan_id),
            },
        )
    for segment in segments:
        segment_casting_plan_id = segment.get("casting_plan_id")
        if segment_casting_plan_id is not None and int(segment_casting_plan_id) != expected_casting_plan_id:
            raise TerminalValidationError(
                "Segment casting plan binding drifted",
                details={
                    "segment_id": int(segment["id"]),
                    "expected_casting_plan_id": expected_casting_plan_id,
                    "persisted_casting_plan_id": int(segment_casting_plan_id),
                },
            )
        if not segment.get("wav_path") or not segment.get("audio_sha256") or segment.get("duration_ms") is None:
            raise TerminalValidationError("Segment is missing persisted audio fields", details={"segment_id": int(segment["id"])})
    master_artifact, timeline_artifact, final_artifact, render_generation = _select_render_artifacts(artifacts, str(job["output_format"]))
    if int(chapter["active_audio_artifact_id"] or 0) != int(final_artifact["id"]):
        raise TerminalValidationError(
            "Chapter active artifact does not match current final artifact",
            details={"active_audio_artifact_id": chapter["active_audio_artifact_id"], "final_artifact_id": final_artifact["id"]},
        )
    master_path = Path(master_artifact["path"]).resolve()
    timeline_path = Path(timeline_artifact["path"]).resolve()
    final_path = Path(final_artifact["path"]).resolve()
    artifact_entries = []
    for row in (master_artifact, timeline_artifact, final_artifact):
        path = Path(row["path"]).resolve()
        actual_sha, size_bytes, mtime = _validate_file_hash(path, row["sha256"], data_root)
        artifact_entries.append(
            {
                "artifact_id": int(row["id"]),
                "artifact_type": str(row["artifact_type"]),
                "status": str(row["status"]),
                "path_relative_to_data_root": _relative_to_root(path, data_root),
                "absolute_local_path": str(path),
                "size_bytes": size_bytes,
                "stored_sha256": row["sha256"],
                "computed_sha256": actual_sha,
                "mtime_epoch_seconds": mtime,
                "mime_type": _artifact_mime(path),
                "duration_ms": row["duration_ms"],
            }
        )
    timeline_payload = json.loads(timeline_path.read_text(encoding="utf-8"))
    timeline_items = timeline_payload.get("items")
    if not isinstance(timeline_items, list):
        raise TerminalValidationError("Timeline JSON is missing items", details={"path": str(timeline_path)})
    if len(timeline_items) != total_segments:
        raise TerminalValidationError(
            "Timeline entry count does not match segment count",
            details={"timeline_entries": len(timeline_items), "segment_count": total_segments},
        )
    previous_end = -1
    for index, item in enumerate(timeline_items, start=1):
        start_ms = int(item["start_ms"])
        end_ms = int(item["end_ms"])
        if start_ms < previous_end or end_ms < start_ms:
            raise TerminalValidationError(
                "Timeline timestamps are not monotonic",
                details={"item_index": index, "start_ms": start_ms, "end_ms": end_ms, "previous_end_ms": previous_end},
            )
        previous_end = end_ms
    missing_files = []
    segment_hash_mismatches = []
    segment_duration_total = 0
    voice_distribution: dict[tuple[str, str], int] = {}
    for segment in segments:
        wav_path = Path(str(segment["wav_path"])).resolve()
        actual_sha, _size_bytes, _mtime = _validate_file_hash(wav_path, str(segment["audio_sha256"]), data_root)
        if actual_sha != str(segment["audio_sha256"]):
            segment_hash_mismatches.append(int(segment["segment_index"]))
        segment_duration_total += int(segment["duration_ms"] or 0)
        role_key = str(segment.get("speaker_role") or "unknown")
        voice_key = str(segment.get("resolved_voice_id") or "")
        voice_distribution[(role_key, voice_key)] = voice_distribution.get((role_key, voice_key), 0) + 1
        if not wav_path.exists():
            missing_files.append(str(wav_path))
    if missing_files or segment_hash_mismatches:
        raise TerminalValidationError(
            "Segment artifact validation failed",
            details={"missing_files": missing_files, "hash_mismatches": segment_hash_mismatches},
        )
    casting_snapshot = json.loads(job["casting_snapshot_json"]) if job.get("casting_snapshot_json") else {}
    book_voice_profile = casting_snapshot.get("book_voice_profile") or {}
    manifest = {
        "schema": "story-audio-production-manifest/v1",
        "identity": {
            "data_root": str(data_root.resolve()),
            "data_root_fingerprint": sha256_text(str(data_root.resolve()).replace("\\", "/")),
            "db_path": str(db_path.resolve()),
            "db_identity": {"schema_version": int(preflight["runtime_identity"]["schema_version"])},
            "book_id": int(job["book_id"]),
            "book_title": job.get("book_title"),
            "chapter_id": int(chapter["chapter_id"]),
            "chapter_number": int(chapter["chapter_number"]),
            "chapter_title": chapter.get("chapter_title"),
            "job_id": int(job["id"]),
            "job_chapter_id": int(chapter["id"]),
            "output_format": str(job["output_format"]),
            "repair_mode": str(job["repair_mode"]),
            "render_generation": render_generation,
        },
        "immutable_bindings": {
            "text_revision_id": int(preflight["text_revision"]["id"]),
            "text_revision_content_sha256": preflight["text_revision"]["content_sha256"],
            "casting_plan_id": int(preflight["casting_plan"]["id"]),
            "casting_plan_revision": int(preflight["casting_plan"]["revision"]),
            "casting_plan_sha256": preflight["casting_plan"]["sha256"],
            "character_bible_fingerprint": preflight["casting_plan"].get("character_bible_fingerprint"),
            "book_voice_profile_id": int(book_voice_profile.get("id") or preflight["book_voice_profile"]["id"]),
            "book_voice_profile_version": int(book_voice_profile.get("config_version") or preflight["book_voice_profile"]["config_version"]),
            "derived_default_voice": str(job["voice_name"]),
            "speaker_voice_distribution": [
                {"speaker_role": role, "voice_id": voice_id, "segment_count": count}
                for (role, voice_id), count in sorted(voice_distribution.items())
            ],
        },
        "terminal_state": {
            "job_status": str(job["status"]),
            "job_chapter_status": str(chapter["status"]),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "expected_segments": total_segments,
            "verified_segments": len(verified_segments),
            "failed_segments": len(failed_segments),
            "pending_segments": len(pending_segments),
            "running_segments": len(running_segments),
            "final_duration_ms": final_artifact["duration_ms"],
            "retry_recovery_metadata": {
                "job_error_message": job.get("error_message"),
                "job_chapter_error_message": chapter.get("error_message"),
            },
        },
        "artifacts": artifact_entries,
        "segment_integrity_summary": {
            "segment_count": total_segments,
            "sequence_min": min(sequences),
            "sequence_max": max(sequences),
            "missing_sequences": missing_sequences,
            "duplicate_sequences": duplicate_sequences,
            "missing_files": missing_files,
            "hash_mismatches": segment_hash_mismatches,
            "duration_total_ms": segment_duration_total,
            "timeline_entry_count": len(timeline_items),
        },
        "mutation_performed": False,
    }
    if text_revision:
        manifest["immutable_bindings"]["persisted_text_revision_id"] = int(text_revision["id"])
        manifest["immutable_bindings"]["persisted_text_revision_sha256"] = str(text_revision["content_sha256"])
    return manifest


def _default_manifest_path(data_root: Path, chapter_number: int, job_id: int) -> Path:
    return (data_root / "manifests" / f"job_{job_id}_chapter_{chapter_number}.json").resolve()


def write_manifest(
    manifest: dict[str, Any],
    *,
    data_root: Path,
    manifest_out: Path | None,
) -> dict[str, Any]:
    target = manifest_out or _default_manifest_path(
        data_root,
        int(manifest["identity"]["chapter_number"]),
        int(manifest["identity"]["job_id"]),
    )
    if manifest_out is None and not _path_within_root(target, data_root):
        raise TerminalValidationError(
            "Default manifest path escapes isolated data root",
            details={"path": str(target), "data_root": str(data_root)},
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    payload_bytes = (_canonical_json(manifest, ensure_ascii=False) + "\n").encode("utf-8")
    if target.exists():
        existing = target.read_bytes()
        if existing == payload_bytes:
            return {
                "path": str(target),
                "sha256": sha256_file(target),
                "reused_existing": True,
            }
        raise TerminalValidationError(
            "Manifest already exists with different content",
            details={"path": str(target)},
        )
    atomic_write_bytes(target, payload_bytes)
    reloaded = json.loads(target.read_text(encoding="utf-8"))
    if reloaded != manifest:
        raise TerminalValidationError(
            "Manifest reread does not match in-memory payload",
            details={"path": str(target)},
        )
    return {
        "path": str(target),
        "sha256": sha256_file(target),
        "reused_existing": False,
    }


def _emit_progress_to_stderr(event: dict[str, Any]) -> None:
    print(_canonical_json({"type": "progress", **event}), file=sys.stderr, flush=True)


def run_job_flow(
    client: HttpJsonClient,
    *,
    data_root: Path,
    book_id: int,
    chapter_number: int,
    casting_plan_id: int,
    output_format: str,
    submit: bool,
    watch: bool,
    resume: bool,
    job_id: int | None,
    manifest_out: Path | None,
    poll_interval: float,
    timeout_seconds: float | None,
    allow_canonical_production: bool = False,
    emit_progress: Callable[[dict[str, Any]], None] = _emit_progress_to_stderr,
) -> dict[str, Any]:
    preflight = run_preflight(
        client,
        data_root=data_root,
        book_id=book_id,
        chapter_number=chapter_number,
        casting_plan_id=casting_plan_id,
        output_format=output_format,
        allow_canonical_production=allow_canonical_production,
    )
    mutation_performed = False
    created_job_id = None
    resume_response = None
    if submit:
        submitted = run_submit(
            client,
            data_root=data_root,
            book_id=book_id,
            chapter_number=chapter_number,
            casting_plan_id=casting_plan_id,
            output_format=output_format,
            allow_canonical_production=allow_canonical_production,
        )
        preflight = submitted
        mutation_performed = True
        created_job_id = int(submitted["job"]["job_id"])
    target_job_id = None
    if watch or resume or job_id is not None:
        target_job_id = _resolve_target_job_id(preflight, job_id, created_job_id)
        detail = _fetch_and_verify_job_detail(client, preflight, target_job_id)
        if resume:
            current_status = str(detail["job"]["status"])
            if current_status not in JOB_RESUMABLE_STATUSES:
                raise BindingMismatchError(
                    "Job is not in a resumable state",
                    details={"job_id": int(target_job_id), "status": current_status},
                )
            resume_response = client.post_empty_json(f"/api/jobs/{target_job_id}/resume")
            mutation_performed = True
            detail = _fetch_and_verify_job_detail(client, preflight, target_job_id)
            if str(detail["job"]["status"]) not in JOB_ACTIVE_STATUSES:
                raise SubmitPersistenceError(
                    "Resume did not transition job into an active state",
                    details={
                        "job_id": int(target_job_id),
                        "status_after_resume": str(detail["job"]["status"]),
                        "resume_response": resume_response,
                    },
                    mutation_performed=True,
                )
        elif str(detail["job"]["status"]) in JOB_RESUMABLE_STATUSES and watch:
            result = {
                "status": "resume_required",
                "job": {
                    "job_id": int(target_job_id),
                    "job_status": str(detail["job"]["status"]),
                    "job_chapter_id": int(detail["chapters"][0]["id"]),
                    "job_chapter_status": str(detail["chapters"][0]["status"]),
                },
                "preflight": preflight,
                "mutation_performed": mutation_performed,
            }
            return result
    if watch and target_job_id is not None:
        final_progress = _monitor_job_progress(
            client,
            job_id=target_job_id,
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
            emit_progress=emit_progress,
        )
        result = {
            "status": final_progress["job_status"],
            "job": {
                "job_id": int(target_job_id),
                "job_status": final_progress["job_status"],
                "job_chapter_id": int(final_progress["job_chapter_id"]),
                "job_chapter_status": final_progress["job_chapter_status"],
            },
            "progress": final_progress,
            "preflight": preflight,
            "resume_response": resume_response,
            "mutation_performed": mutation_performed,
        }
        if final_progress["job_status"] == "completed":
            manifest = build_completed_manifest(
                data_root=data_root,
                db_path=Path(preflight["runtime_identity"]["db_path"]).resolve(),
                preflight=preflight,
                job_id=int(target_job_id),
            )
            manifest_file = write_manifest(manifest, data_root=data_root, manifest_out=manifest_out)
            result["terminal_validation"] = {"status": "passed"}
            result["manifest"] = manifest_file | {"schema": manifest["schema"]}
        return result
    if target_job_id is not None and manifest_out is not None:
        detail = _fetch_and_verify_job_detail(client, preflight, target_job_id)
        if str(detail["job"]["status"]) != "completed":
            raise TerminalValidationError(
                "Cannot write manifest for non-completed job without watch completion",
                details={"job_id": int(target_job_id), "status": str(detail["job"]["status"])},
                mutation_performed=mutation_performed,
            )
        manifest = build_completed_manifest(
            data_root=data_root,
            db_path=Path(preflight["runtime_identity"]["db_path"]).resolve(),
            preflight=preflight,
            job_id=int(target_job_id),
        )
        manifest_file = write_manifest(manifest, data_root=data_root, manifest_out=manifest_out)
        return {
            "status": "completed",
            "job": {
                "job_id": int(target_job_id),
                "job_status": "completed",
                "job_chapter_id": int(detail["chapters"][0]["id"]),
                "job_chapter_status": str(detail["chapters"][0]["status"]),
            },
            "preflight": preflight,
            "terminal_validation": {"status": "passed"},
            "manifest": manifest_file | {"schema": manifest["schema"]},
            "resume_response": resume_response,
            "mutation_performed": mutation_performed,
        }
    if target_job_id is not None and resume:
        detail = _fetch_and_verify_job_detail(client, preflight, target_job_id)
        return {
            "status": "resumed",
            "job": {
                "job_id": int(target_job_id),
                "job_status": str(detail["job"]["status"]),
                "job_chapter_id": int(detail["chapters"][0]["id"]),
                "job_chapter_status": str(detail["chapters"][0]["status"]),
            },
            "preflight": preflight,
            "resume_response": resume_response,
            "mutation_performed": mutation_performed,
        }
    preflight["mutation_performed"] = mutation_performed
    return preflight


def build_error_result(exc: RunnerError) -> dict[str, Any]:
    result = {
        "status": exc.status,
        "error": str(exc),
        "mutation_performed": bool(exc.mutation_performed),
    }
    if exc.details:
        result["details"] = exc.details
    return result


def build_internal_error_result(exc: Exception) -> dict[str, Any]:
    return {
        "status": InternalRunnerError.status,
        "error": f"{type(exc).__name__}: {exc}",
        "mutation_performed": False,
    }


def run_cli(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Preflight, watch, resume, or submit one isolated production chapter job")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--book-id", required=True, type=int)
    parser.add_argument("--chapter-number", required=True, type=int)
    parser.add_argument("--casting-plan-id", required=True, type=int)
    parser.add_argument("--output-format", choices=("m4a", "mp3"), default="m4a")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--job-id", type=int)
    parser.add_argument("--manifest-out")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=3600.0)
    args = parser.parse_args(argv)

    try:
        if args.submit and args.resume:
            raise ArgumentError("--submit and --resume cannot be used together")
        data_root = canonicalize_data_root(args.data_root)
        api_base = normalize_api_base(args.api_base)
        manifest_out = normalize_manifest_path(args.manifest_out)
        poll_interval = normalize_poll_interval(args.poll_interval)
        timeout_seconds = normalize_timeout_seconds(args.timeout_seconds)
        client = HttpJsonClient(api_base)
        result = run_job_flow(
            client,
            data_root=data_root,
            book_id=args.book_id,
            chapter_number=args.chapter_number,
            casting_plan_id=args.casting_plan_id,
            output_format=args.output_format,
            submit=bool(args.submit),
            watch=bool(args.watch),
            resume=bool(args.resume),
            job_id=args.job_id,
            manifest_out=manifest_out,
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
        )
        print(_canonical_json(result))
        return 0
    except KeyboardInterrupt as exc:
        payload = {
            "status": OperatorInterruptError.status,
            "error": "KeyboardInterrupt: operator interrupted watch without cancelling job",
            "mutation_performed": False,
        }
        print(_canonical_json(payload))
        print("operator_interrupt: watch stopped locally; job was not cancelled", file=sys.stderr)
        return EXIT_OPERATOR_INTERRUPT
    except RunnerError as exc:
        print(_canonical_json(build_error_result(exc)))
        return exc.exit_code
    except Exception as exc:
        print(_canonical_json(build_internal_error_result(exc)))
        print(f"internal_error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR


def main() -> int:
    return run_cli(sys.argv[1:])
