from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from .config import canonical_production_db_path


EXIT_INVALID_ARGUMENTS = 2
EXIT_RUNTIME_MISMATCH = 3
EXIT_BINDING_MISMATCH = 4
EXIT_DUPLICATE_JOB = 5
EXIT_API_FAILURE = 6
EXIT_SUBMIT_PERSISTENCE_MISMATCH = 7
EXIT_INTERNAL_ERROR = 8

ACTIVE_DUPLICATE_STATUSES = {
    "scheduled",
    "queued",
    "running",
    "repairing",
    "synthesizing",
    "assembling",
    "paused",
    "interrupted",
}


class RunnerError(RuntimeError):
    exit_code = EXIT_BINDING_MISMATCH
    status = "error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


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


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


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


def _identity_strings(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, str):
        values.append(value)
    elif isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(key, str):
                values.append(key)
            values.extend(_identity_strings(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            values.extend(_identity_strings(nested))
    return values


def build_unicode_safe_json_bytes(
    payload: dict[str, Any],
    *,
    unicode_identity_fields: tuple[str, ...] = ("voice_name",),
) -> bytes:
    _check_strings_for_replacement(payload)
    payload_bytes = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
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


def canonicalize_data_root(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ArgumentError("--data-root must be an absolute path")
    resolved = path.resolve()
    if not resolved.exists():
        raise ArgumentError("--data-root must already exist")
    live_root = canonical_production_db_path().resolve().parent
    if resolved == live_root:
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


def fetch_runtime_identity(client: HttpJsonClient, expected_data_root: Path) -> RuntimeIdentity:
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
            details={
                "expected_data_root": str(expected_data_root),
                "api_data_root": identity.data_root,
            },
        )
    if identity.is_canonical_live_data_root or identity.is_canonical_live_db:
        raise RuntimeMismatchError("API server is pointing at canonical live storage")
    return identity


def _chapter_from_number(client: HttpJsonClient, book_id: int, chapter_number: int) -> dict[str, Any]:
    payload = client.get_json(
        f"/api/books/{book_id}/chapters",
        params={"offset": 0, "limit": 20, "query": str(chapter_number)},
    )
    items = [
        item for item in payload.get("items", [])
        if int(item["chapter_number"]) == chapter_number
    ]
    if len(items) != 1:
        raise BindingMismatchError("Could not resolve exactly one chapter from chapter number")
    chapter = items[0]
    _require_field(chapter, "id", "Chapter list item")
    _require_field(chapter, "chapter_number", "Chapter list item")
    return chapter


def _require_field(mapping: dict[str, Any], field: str, context: str) -> Any:
    if field not in mapping:
        raise BindingMismatchError(f"{context} is missing required field {field}")
    return mapping[field]


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
    result = [
        {"role": role, "voice_id": voice_id, "utterance_count": count}
        for (role, voice_id), count in sorted(counts.items())
    ]
    return result


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
        current_profile = {
            "id": int(profile["id"]),
            "config_version": int(profile["config_version"]),
        }
        if (
            int(plan_profile["id"]) != current_profile["id"]
            or int(plan_profile["config_version"]) != current_profile["config_version"]
        ):
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
    return {str(item["id"]): str(item.get("label") or item["id"]) for item in items}


def _verify_voice_availability(plan_detail: dict[str, Any], voice_catalog: dict[str, str]) -> None:
    plan = plan_detail["plan"]
    required = {str(plan["narrator_voice_id"])}
    required.update(str(item["resolved_voice_id"]) for item in plan["utterances"])
    missing = sorted(voice_id for voice_id in required if voice_id not in voice_catalog)
    if missing:
        raise BindingMismatchError(
            "Casting Plan contains unavailable preset voice(s)",
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
    if status in ACTIVE_DUPLICATE_STATUSES:
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
) -> dict[str, Any]:
    runtime = fetch_runtime_identity(client, data_root)
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
) -> dict[str, Any]:
    preflight = run_preflight(
        client,
        data_root=data_root,
        book_id=book_id,
        chapter_number=chapter_number,
        casting_plan_id=casting_plan_id,
        output_format=output_format,
    )
    duplicate = preflight["duplicate_job"]
    if duplicate["duplicate"]:
        raise DuplicateJobError(
            "Duplicate production job already exists",
            details=duplicate,
        )
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


def build_error_result(exc: RunnerError) -> dict[str, Any]:
    result = {
        "status": exc.status,
        "error": str(exc),
        "mutation_performed": False,
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

    parser = argparse.ArgumentParser(description="Preflight or submit one isolated production chapter job")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--book-id", required=True, type=int)
    parser.add_argument("--chapter-number", required=True, type=int)
    parser.add_argument("--casting-plan-id", required=True, type=int)
    parser.add_argument("--output-format", choices=("m4a", "mp3"), default="m4a")
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args(argv)

    try:
        data_root = canonicalize_data_root(args.data_root)
        api_base = normalize_api_base(args.api_base)
        client = HttpJsonClient(api_base)
        if args.submit:
            result = run_submit(
                client,
                data_root=data_root,
                book_id=args.book_id,
                chapter_number=args.chapter_number,
                casting_plan_id=args.casting_plan_id,
                output_format=args.output_format,
            )
        else:
            result = run_preflight(
                client,
                data_root=data_root,
                book_id=args.book_id,
                chapter_number=args.chapter_number,
                casting_plan_id=args.casting_plan_id,
                output_format=args.output_format,
            )
        print(_canonical_json(result))
        return 0
    except RunnerError as exc:
        print(_canonical_json(build_error_result(exc)))
        return exc.exit_code
    except Exception as exc:
        print(_canonical_json(build_internal_error_result(exc)))
        print(f"internal_error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR


def main() -> int:
    return run_cli(sys.argv[1:])
