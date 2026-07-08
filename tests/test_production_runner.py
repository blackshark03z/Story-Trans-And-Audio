from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from story_audio.production_runner import (
    ApiFailureError,
    BindingMismatchError,
    DuplicateJobError,
    EXIT_API_FAILURE,
    EXIT_BINDING_MISMATCH,
    EXIT_DUPLICATE_JOB,
    EXIT_INTERNAL_ERROR,
    EXIT_INVALID_ARGUMENTS,
    EXIT_OPERATOR_INTERRUPT,
    EXIT_RUNTIME_MISMATCH,
    EXIT_SUBMIT_PERSISTENCE_MISMATCH,
    EXIT_WATCH_TIMEOUT,
    RuntimeMismatchError,
    SubmitPersistenceError,
    WatchTimeoutError,
    build_unicode_safe_json_bytes,
    canonicalize_data_root,
    run_cli,
    run_job_flow,
    run_preflight,
    run_submit,
)


class FakeClient:
    def __init__(self, responses: dict[tuple[str, str], object]):
        self.responses = responses
        self.api_base = "http://127.0.0.1:8768"
        self.get_calls: list[tuple[str, dict | None]] = []
        self.post_calls: list[tuple[str, bytes]] = []

    def get_json(self, path: str, params: dict | None = None):
        self.get_calls.append((path, params))
        key = ("GET", self._key(path, params))
        value = self.responses[key]
        if isinstance(value, Exception):
            raise value
        return value

    def post_json_bytes(self, path: str, payload_bytes: bytes):
        self.post_calls.append((path, payload_bytes))
        key = ("POST", path)
        value = self.responses[key]
        if isinstance(value, Exception):
            raise value
        return value

    def post_empty_json(self, path: str):
        return self.post_json_bytes(path, b"{}")

    @staticmethod
    def _key(path: str, params: dict | None) -> str:
        if not params:
            return path
        items = "&".join(f"{key}={params[key]}" for key in sorted(params))
        return f"{path}?{items}"


def make_base_responses(*, data_root: str = "D:/isolated/data", jobs: list[dict] | None = None, job_details: dict[int, dict] | None = None) -> dict[tuple[str, str], object]:
    chapter_list_item = {
        "id": 100,
        "chapter_number": 629,
        "title": "Chapter 629",
        "char_count": 14256,
        "audio_status": "completed",
        "active_audio_artifact_id": 6,
        "qa_count": 0,
    }
    chapter = {
        "id": 100,
        "book_id": 1,
        "chapter_number": 629,
        "title": "Chapter 629",
        "active_text_revision_id": 200,
    }
    revision = {
        "id": 200,
        "status": "approved",
        "content_sha256": "rev-hash-200",
    }
    plan = {
        "id": 55,
        "chapter_id": 100,
        "text_revision_id": 200,
        "plan_revision": 3,
        "status": "approved",
        "plan_sha256": "plan-sha-55",
        "plan": {
            "narrator_voice_id": "ngoc_lan",
            "book_voice_profile": {
                "id": 9,
                "config_version": 4,
                "narrator_voice_id": "ngoc_lan",
                "male_dialogue_voice_id": "duc_tri",
                "female_dialogue_voice_id": "my_duyen",
                "unknown_fallback": "narrator",
                "unknown_voice_id": None,
            },
            "utterances": [
                {"utterance_id": "u1", "role": "narrator", "resolved_voice_id": "ngoc_lan"},
                {"utterance_id": "u2", "role": "character", "character_id": 81, "resolved_voice_id": "duc_tri"},
                {"utterance_id": "u3", "role": "character", "character_id": 82, "resolved_voice_id": "my_duyen"},
            ],
        },
    }
    profile = {
        "configured": True,
        "profile": {
            "id": 9,
            "config_version": 4,
            "narrator_voice_id": "ngoc_lan",
            "male_dialogue_voice_id": "duc_tri",
            "female_dialogue_voice_id": "my_duyen",
            "unknown_fallback": "narrator",
            "unknown_voice_id": None,
        },
        "valid": True,
        "missing_preset_ids": [],
    }
    runtime = {
        "root": "D:/Youtube/Story Trans And Audio",
        "data_root": data_root,
        "db_path": str(Path(data_root) / "app.db"),
        "schema_version": 7,
        "latest_schema_version": 7,
        "canonical_live_data_root": "D:/Youtube/Story Trans And Audio/data",
        "canonical_live_db_path": "D:/Youtube/Story Trans And Audio/data/app.db",
        "is_canonical_live_data_root": False,
        "is_canonical_live_db": False,
    }
    chapter_detail = {"chapter": chapter, "revisions": [revision], "qa_issues": [], "audio_artifact": None}
    voices = {
        "items": [
            {"id": "ngoc_lan", "label": "Ngọc Lan"},
            {"id": "duc_tri", "label": "Đức Trí"},
            {"id": "my_duyen", "label": "Mỹ Duyên"},
        ],
        "status": "ready",
    }
    responses: dict[tuple[str, str], object] = {
        ("GET", "/api/runtime"): runtime,
        ("GET", "/api/books/1/chapters?limit=20&offset=0&query=629"): {"items": [chapter_list_item], "total": 1},
        ("GET", "/api/chapters/100"): chapter_detail,
        ("GET", "/api/casting/55"): plan,
        ("GET", "/api/books/1/voice-profile"): profile,
        ("GET", "/api/voices"): voices,
        ("GET", "/api/jobs"): jobs or [],
        ("POST", "/api/jobs"): {"job_id": 900, "selected_chapters": 1, "skipped_completed": 0},
    }
    for job_id, detail in (job_details or {}).items():
        responses[("GET", f"/api/jobs/{job_id}")] = detail
    return responses


def make_job_detail(*, job_id: int = 700, status: str = "scheduled", chapter_status: str | None = None, text_revision_id: int = 200, casting_plan_id: int = 55, casting_plan_sha256: str = "plan-sha-55", voice_name: str = "ngoc_lan", profile_id: int = 9, profile_version: int = 4) -> dict:
    snapshot = {
        "casting_plan_id": casting_plan_id,
        "casting_plan_sha256": casting_plan_sha256,
        "text_revision_id": text_revision_id,
        "narrator_voice_id": voice_name,
        "book_voice_profile": {
            "id": profile_id,
            "config_version": profile_version,
        },
    }
    return {
        "job": {
            "id": job_id,
            "book_id": 1,
            "from_chapter": 629,
            "to_chapter": 629,
            "repair_mode": "off",
            "output_format": "m4a",
            "voice_name": voice_name,
            "status": status,
            "casting_plan_id": casting_plan_id,
        },
        "chapters": [
            {
                "id": 1700 + job_id,
                "chapter_id": 100,
                "status": chapter_status or status,
                "text_revision_id": text_revision_id,
                "casting_plan_id": casting_plan_id,
                "casting_plan_sha256": casting_plan_sha256,
                "voice_snapshot_json": json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
            }
        ],
    }


def make_job_chapter_diagnostics(*, job_chapter_id: int, segment_statuses: list[str]) -> dict:
    segments = []
    for index, status in enumerate(segment_statuses, start=1):
        segments.append(
            {
                "id": 5000 + index,
                "segment_index": index,
                "status": status,
                "attempt_count": 0,
                "error_message": None,
                "duration_ms": 1000,
                "text_sha256": f"text-{index}",
                "audio_sha256": f"audio-{index}",
                "created_at": "2026-07-05T00:00:00Z",
                "verified_at": "2026-07-05T00:00:00Z" if status == "verified" else None,
                "text_preview": f"segment {index}",
                "filename": f"{index:06d}.wav",
                "file_exists": True,
                "actual_size_bytes": 123,
                "hash_matches": True,
            }
        )
    return {
        "chapter": {
            "job_chapter_id": job_chapter_id,
            "job_id": 700,
            "chapter_id": 100,
            "sequence": 1,
            "status": "running",
            "error_message": None,
            "started_at": "2026-07-05T00:00:00Z",
            "finished_at": None,
            "text_revision_id": 200,
            "chapter_number": 629,
            "title": "Chapter 629",
            "job_status": "running",
            "book_title": "Test Book",
        },
        "text_revision": {"id": 200, "content_sha256": "rev-hash-200"},
        "repair_blocks": [],
        "segments": segments,
        "artifacts": [],
    }


class ProductionRunnerTests(unittest.TestCase):
    def test_absolute_isolated_data_root_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = canonicalize_data_root(tmp)
            self.assertTrue(path.is_absolute())
            self.assertEqual(path, Path(tmp).resolve())

    def test_relative_data_root_rejected(self):
        with self.assertRaisesRegex(Exception, "absolute path"):
            canonicalize_data_root("relative\\data")

    def test_canonical_live_root_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "data"
            live.mkdir()
            with patch("story_audio.production_runner.canonical_production_db_path", return_value=live / "app.db"):
                with self.assertRaises(RuntimeMismatchError):
                    canonicalize_data_root(str(live))

    def test_canonical_live_root_allowed_only_with_explicit_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "data"
            live.mkdir()
            with patch("story_audio.production_runner.canonical_production_db_path", return_value=live / "app.db"):
                resolved = canonicalize_data_root(str(live), allow_canonical_production=True)
        self.assertEqual(resolved, live.resolve())

    def test_api_runtime_canonical_allowed_only_with_explicit_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp).resolve()
            responses = make_base_responses(data_root=str(data_root))
            responses[("GET", "/api/runtime")]["canonical_live_data_root"] = str(data_root)
            responses[("GET", "/api/runtime")]["canonical_live_db_path"] = str(data_root / "app.db")
            responses[("GET", "/api/runtime")]["is_canonical_live_data_root"] = True
            responses[("GET", "/api/runtime")]["is_canonical_live_db"] = True
            client = FakeClient(responses)
            with self.assertRaises(RuntimeMismatchError):
                run_preflight(client, data_root=data_root, book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
            result = run_preflight(
                client,
                data_root=data_root,
                book_id=1,
                chapter_number=629,
                casting_plan_id=55,
                output_format="m4a",
                allow_canonical_production=True,
            )
        self.assertTrue(result["runtime_identity"]["is_canonical_live_data_root"])

    def test_api_runtime_root_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            responses = make_base_responses(data_root=str(Path(tmp).resolve()))
            responses[("GET", "/api/runtime")]["data_root"] = "D:/other/data"
            client = FakeClient(responses)
            with self.assertRaises(RuntimeMismatchError):
                run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")

    def test_wrong_chapter_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            responses = make_base_responses(data_root=str(Path(tmp).resolve()))
            responses[("GET", "/api/books/1/chapters?limit=20&offset=0&query=629")] = {"items": [], "total": 0}
            client = FakeClient(responses)
            with self.assertRaises(BindingMismatchError):
                run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")

    def test_stale_mismatched_text_revision_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            responses = make_base_responses(data_root=str(Path(tmp).resolve()))
            responses[("GET", "/api/casting/55")]["text_revision_id"] = 201
            client = FakeClient(responses)
            with self.assertRaises(BindingMismatchError):
                run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")

    def test_wrong_unapproved_casting_plan_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            responses = make_base_responses(data_root=str(Path(tmp).resolve()))
            responses[("GET", "/api/casting/55")]["status"] = "draft"
            client = FakeClient(responses)
            with self.assertRaises(BindingMismatchError):
                run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")

    def test_unresolved_missing_voice_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            responses = make_base_responses(data_root=str(Path(tmp).resolve()))
            responses[("GET", "/api/voices")] = {"items": [{"id": "ngoc_lan", "label": "Ngọc Lan"}], "status": "ready"}
            client = FakeClient(responses)
            with self.assertRaises(BindingMismatchError):
                run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")

    def test_default_voice_derived_correctly_from_profile_and_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient(make_base_responses(data_root=str(Path(tmp).resolve())))
            result = run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
            self.assertEqual(result["derived_default_voice"]["voice_id"], "ngoc_lan")
            self.assertEqual(result["book_voice_profile"]["id"], 9)
            self.assertEqual(result["book_voice_profile"]["config_version"], 4)

    def test_approved_plan_remains_valid_when_current_profile_has_newer_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            responses = make_base_responses(data_root=str(Path(tmp).resolve()))
            responses[("GET", "/api/books/1/voice-profile")]["profile"]["config_version"] = 5
            client = FakeClient(responses)
            result = run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
            self.assertEqual(result["book_voice_profile"]["id"], 9)
            self.assertEqual(result["book_voice_profile"]["config_version"], 4)
            self.assertEqual(result["book_voice_profile"]["current_profile"]["config_version"], 5)
            self.assertIsNotNone(result["book_voice_profile"]["profile_drift"])

    def test_unicode_voice_request_serializes_to_escaped_ascii_bytes(self):
        payload = {"voice_name": "Ngọc Lan", "repair_mode": "off"}
        payload_bytes = build_unicode_safe_json_bytes(payload)
        self.assertEqual(payload_bytes.decode("ascii"), '{"voice_name":"Ng\\u1ecdc Lan","repair_mode":"off"}')

    def test_payload_contains_no_substitution_question_mark(self):
        payload = {"voice_name": "Đức Trí", "repair_mode": "off"}
        payload_bytes = build_unicode_safe_json_bytes(payload)
        self.assertNotIn(b"?", payload_bytes)
        self.assertNotIn("\ufffd", payload_bytes.decode("ascii"))

    def test_legal_question_mark_is_not_rejected_when_schema_allows_it(self):
        payload = {"voice_name": "Voice?", "repair_mode": "off"}
        payload_bytes = build_unicode_safe_json_bytes(payload)
        self.assertIn(b"?", payload_bytes)
        self.assertEqual(json.loads(payload_bytes.decode("ascii"))["voice_name"], "Voice?")

    def test_preflight_mode_performs_no_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient(make_base_responses(data_root=str(Path(tmp).resolve())))
            result = run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
            self.assertFalse(result["mutation_performed"])
            self.assertEqual(client.post_calls, [])

    def test_identical_active_job_blocks_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = [{"id": 700, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55}]
            client = FakeClient(make_base_responses(data_root=str(Path(tmp).resolve()), jobs=jobs, job_details={700: make_job_detail(job_id=700, status="running")}))
            result = run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
            self.assertTrue(result["duplicate_job"]["duplicate"])
            self.assertEqual(result["duplicate_job"]["existing_job_status"], "running")

    def test_duplicate_statuses_use_exact_supported_enums(self):
        with tempfile.TemporaryDirectory() as tmp:
            for status in ("scheduled", "queued", "running", "repairing", "synthesizing", "assembling", "paused", "interrupted"):
                jobs = [{"id": 710, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55}]
                client = FakeClient(make_base_responses(data_root=str(Path(tmp).resolve()), jobs=jobs, job_details={710: make_job_detail(job_id=710, status=status)}))
                result = run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
                self.assertTrue(result["duplicate_job"]["duplicate"])
                self.assertEqual(result["duplicate_job"]["existing_job_status"], status)
            for status in ("completed", "completed_with_errors", "failed", "cancelled"):
                jobs = [{"id": 711, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55}]
                client = FakeClient(make_base_responses(data_root=str(Path(tmp).resolve()), jobs=jobs, job_details={711: make_job_detail(job_id=711, status=status)}))
                result = run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
                self.assertTrue(result["duplicate_job"]["duplicate"])
                self.assertEqual(result["duplicate_job"]["existing_job_status"], status)

    def test_identical_completed_job_reports_already_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = [{"id": 701, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55}]
            client = FakeClient(make_base_responses(data_root=str(Path(tmp).resolve()), jobs=jobs, job_details={701: make_job_detail(job_id=701, status="completed")}))
            result = run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
            self.assertEqual(result["status"], "already_completed")
            self.assertEqual(result["chapter"]["book_id"], 1)
            self.assertEqual(result["derived_default_voice"]["label"], "Ngọc Lan")
            self.assertFalse(result["mutation_performed"])
            self.assertEqual(client.post_calls, [])

    def test_exact_chapter_list_shape_without_book_id_uses_explicit_book_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = [{"id": 770, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55}]
            client = FakeClient(make_base_responses(data_root=str(Path(tmp).resolve()), jobs=jobs, job_details={770: make_job_detail(job_id=770, status="completed")}))
            result = run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
            self.assertEqual(result["status"], "already_completed")
            self.assertEqual(result["duplicate_job"]["existing_job_id"], 770)
            self.assertEqual(result["chapter"]["book_id"], 1)

    def test_missing_truly_required_chapter_field_raises_binding_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            responses = make_base_responses(data_root=str(Path(tmp).resolve()))
            responses[("GET", "/api/books/1/chapters?limit=20&offset=0&query=629")] = {
                "items": [{"chapter_number": 629, "title": "Chapter 629"}],
                "total": 1,
            }
            client = FakeClient(responses)
            with self.assertRaisesRegex(BindingMismatchError, "missing required field id"):
                run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")

    def test_multiple_identical_jobs_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = [
                {"id": 720, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55},
                {"id": 721, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55},
            ]
            client = FakeClient(make_base_responses(
                data_root=str(Path(tmp).resolve()),
                jobs=jobs,
                job_details={
                    720: make_job_detail(job_id=720, status="completed"),
                    721: make_job_detail(job_id=721, status="failed"),
                },
            ))
            with self.assertRaises(DuplicateJobError):
                run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")

    def test_failed_cancelled_identical_job_does_not_auto_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = [{"id": 702, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55}]
            client = FakeClient(make_base_responses(data_root=str(Path(tmp).resolve()), jobs=jobs, job_details={702: make_job_detail(job_id=702, status="failed")}))
            result = run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
            self.assertEqual(result["duplicate_job"]["result"], "existing_terminal_job_requires_operator_decision")

    def test_different_casting_plan_or_text_revision_not_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = [{"id": 703, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55}]
            client = FakeClient(make_base_responses(data_root=str(Path(tmp).resolve()), jobs=jobs, job_details={703: make_job_detail(job_id=703, status="completed", text_revision_id=201)}))
            result = run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
            self.assertFalse(result["duplicate_job"]["duplicate"])

    def test_different_book_same_chapter_number_not_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = [{"id": 704, "book_id": 2, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55}]
            client = FakeClient(make_base_responses(data_root=str(Path(tmp).resolve()), jobs=jobs, job_details={704: make_job_detail(job_id=704, status="completed")}))
            result = run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
            self.assertFalse(result["duplicate_job"]["duplicate"])

    def test_different_output_format_not_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = [{"id": 705, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "mp3", "casting_plan_id": 55}]
            detail = make_job_detail(job_id=705, status="completed")
            detail["job"]["output_format"] = "mp3"
            client = FakeClient(make_base_responses(data_root=str(Path(tmp).resolve()), jobs=jobs, job_details={705: detail}))
            result = run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
            self.assertFalse(result["duplicate_job"]["duplicate"])

    def test_submit_calls_create_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient(make_base_responses(data_root=str(Path(tmp).resolve()), job_details={900: make_job_detail(job_id=900, status="scheduled")}))
            result = run_submit(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
            self.assertTrue(result["mutation_performed"])
            self.assertEqual(len(client.post_calls), 1)
            self.assertEqual(client.post_calls[0][0], "/api/jobs")

    def test_non_2xx_submit_is_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            responses = make_base_responses(data_root=str(Path(tmp).resolve()))
            responses[("POST", "/api/jobs")] = ApiFailureError("submit failed", details={"status_code": 503})
            client = FakeClient(responses)
            with self.assertRaises(ApiFailureError):
                run_submit(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
            self.assertEqual(len(client.post_calls), 1)

    def test_persisted_binding_mismatch_after_create_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient(make_base_responses(data_root=str(Path(tmp).resolve()), job_details={900: make_job_detail(job_id=900, status="scheduled", voice_name="wrong_voice")}))
            with self.assertRaisesRegex(Exception, "bindings do not match"):
                run_submit(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")

    def test_protected_paths_are_never_referenced_or_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient(make_base_responses(data_root=str(Path(tmp).resolve())))
            result = run_preflight(client, data_root=Path(tmp).resolve(), book_id=1, chapter_number=629, casting_plan_id=55, output_format="m4a")
            encoded = json.dumps(result, ensure_ascii=False)
            self.assertNotIn("experiment_b_transcript", encoded)
            self.assertNotIn("runs/", encoded)
            for path, _params in client.get_calls:
                self.assertNotIn("experiment_b_transcript", path)
                self.assertNotIn("runs/", path)

    def test_cli_default_is_preflight_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_result = {"status": "preflight_pass", "mutation_performed": False}
            stdout = io.StringIO()
            with patch("story_audio.production_runner.run_preflight", return_value=fake_result) as preflight_mock, \
                 patch("story_audio.production_runner.run_submit") as submit_mock, \
                 patch("sys.stdout", stdout):
                code = run_cli([
                    "--data-root", str(Path(tmp).resolve()),
                    "--api-base", "http://127.0.0.1:8768",
                    "--book-id", "1",
                    "--chapter-number", "629",
                    "--casting-plan-id", "55",
                ])
            self.assertEqual(code, 0)
            preflight_mock.assert_called_once()
            submit_mock.assert_not_called()

    def test_cli_exit_codes_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_args = [
                "--data-root", str(Path(tmp).resolve()),
                "--api-base", "http://127.0.0.1:8768",
                "--book-id", "1",
                "--chapter-number", "629",
                "--casting-plan-id", "55",
            ]
            with patch("story_audio.production_runner.run_preflight", side_effect=RuntimeMismatchError("bad runtime")):
                self.assertEqual(run_cli(base_args), EXIT_RUNTIME_MISMATCH)
            with patch("story_audio.production_runner.run_preflight", side_effect=BindingMismatchError("bad binding")):
                self.assertEqual(run_cli(base_args), EXIT_BINDING_MISMATCH)
            with patch("story_audio.production_runner.run_preflight", side_effect=DuplicateJobError("duplicate")):
                self.assertEqual(run_cli(base_args), EXIT_DUPLICATE_JOB)
            with patch("story_audio.production_runner.run_preflight", side_effect=ApiFailureError("api")):
                self.assertEqual(run_cli(base_args), EXIT_API_FAILURE)
            with patch("story_audio.production_runner.run_job_flow", side_effect=SubmitPersistenceError("submit mismatch")):
                self.assertEqual(run_cli(base_args + ["--submit"]), EXIT_SUBMIT_PERSISTENCE_MISMATCH)

    def test_cli_known_errors_still_return_machine_readable_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with patch("story_audio.production_runner.run_preflight", side_effect=BindingMismatchError("bad binding")), \
                 patch("sys.stdout", stdout):
                code = run_cli([
                    "--data-root", str(Path(tmp).resolve()),
                    "--api-base", "http://127.0.0.1:8768",
                    "--book-id", "1",
                    "--chapter-number", "629",
                    "--casting-plan-id", "55",
                ])
            self.assertEqual(code, EXIT_BINDING_MISMATCH)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "binding_mismatch")
            self.assertFalse(payload["mutation_performed"])
            self.assertEqual(payload["error"], "bad binding")

    def test_cli_unexpected_exception_returns_internal_error_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch("story_audio.production_runner.run_preflight", side_effect=KeyError("book_id")), \
                 patch("sys.stdout", stdout), \
                 patch("sys.stderr", stderr):
                code = run_cli([
                    "--data-root", str(Path(tmp).resolve()),
                    "--api-base", "http://127.0.0.1:8768",
                    "--book-id", "1",
                    "--chapter-number", "629",
                    "--casting-plan-id", "55",
                ])
            self.assertEqual(code, EXIT_INTERNAL_ERROR)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "internal_error")
            self.assertFalse(payload["mutation_performed"])
            self.assertIn("KeyError", payload["error"])
            self.assertIn("internal_error: KeyError", stderr.getvalue())

    def test_cli_invalid_arguments_exit_code(self):
        code = run_cli([
            "--data-root", "relative",
            "--api-base", "http://127.0.0.1:8768",
            "--book-id", "1",
            "--chapter-number", "629",
            "--casting-plan-id", "55",
        ])
        self.assertEqual(code, EXIT_INVALID_ARGUMENTS)

    def test_watch_timeout_does_not_cancel_or_mutate(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_root = str(Path(tmp).resolve())
            responses = make_base_responses(
                data_root=data_root,
                jobs=[{"id": 700, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55}],
                job_details={700: make_job_detail(job_id=700, status="running", chapter_status="running")},
            )
            responses[("GET", "/api/diagnostics/job-chapters/2400")] = make_job_chapter_diagnostics(
                job_chapter_id=2400,
                segment_statuses=["verified", "running", "pending"],
            )
            client = FakeClient(responses)
            with self.assertRaisesRegex(Exception, "Timed out while watching job progress"):
                run_job_flow(
                    client,
                    data_root=Path(tmp).resolve(),
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=55,
                    output_format="m4a",
                    submit=False,
                    watch=True,
                    resume=False,
                    job_id=None,
                    manifest_out=None,
                    poll_interval=0.2,
                    timeout_seconds=0.001,
                    emit_progress=lambda _event: None,
                )
            self.assertEqual(client.post_calls, [])

    def test_paused_job_watch_does_not_auto_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_root = str(Path(tmp).resolve())
            responses = make_base_responses(
                data_root=data_root,
                jobs=[{"id": 700, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55}],
                job_details={700: make_job_detail(job_id=700, status="paused", chapter_status="interrupted")},
            )
            client = FakeClient(responses)
            result = run_job_flow(
                client,
                data_root=Path(tmp).resolve(),
                book_id=1,
                chapter_number=629,
                casting_plan_id=55,
                output_format="m4a",
                submit=False,
                watch=True,
                resume=False,
                job_id=None,
                manifest_out=None,
                poll_interval=0.2,
                timeout_seconds=1.0,
                emit_progress=lambda _event: None,
            )
            self.assertEqual(result["status"], "resume_required")
            self.assertFalse(result["mutation_performed"])
            self.assertEqual(client.post_calls, [])

    def test_paused_job_resume_calls_endpoint_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_root = str(Path(tmp).resolve())
            responses = make_base_responses(
                data_root=data_root,
                jobs=[{"id": 700, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55}],
                job_details={700: make_job_detail(job_id=700, status="paused", chapter_status="interrupted")},
            )
            responses[("POST", "/api/jobs/700/resume")] = {"ok": True, "action": "resume"}
            class ResumeClient(FakeClient):
                def get_json(self, path: str, params: dict | None = None):
                    if path == "/api/jobs/700" and self.post_calls:
                        self.get_calls.append((path, params))
                        return make_job_detail(job_id=700, status="queued", chapter_status="pending")
                    return super().get_json(path, params)

            client = ResumeClient(responses)
            result = run_job_flow(
                client,
                data_root=Path(tmp).resolve(),
                book_id=1,
                chapter_number=629,
                casting_plan_id=55,
                output_format="m4a",
                submit=False,
                watch=False,
                resume=True,
                job_id=None,
                manifest_out=None,
                poll_interval=0.2,
                timeout_seconds=1.0,
                emit_progress=lambda _event: None,
            )
            self.assertEqual(result["status"], "resumed")
            self.assertTrue(result["mutation_performed"])
            self.assertEqual(len(client.post_calls), 1)
            self.assertEqual(client.post_calls[0][0], "/api/jobs/700/resume")

    def test_resume_non_2xx_is_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_root = str(Path(tmp).resolve())
            responses = make_base_responses(
                data_root=data_root,
                jobs=[{"id": 700, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55}],
                job_details={700: make_job_detail(job_id=700, status="paused", chapter_status="interrupted")},
            )
            responses[("POST", "/api/jobs/700/resume")] = ApiFailureError("resume failed", details={"status_code": 409})
            client = FakeClient(responses)
            with self.assertRaises(ApiFailureError):
                run_job_flow(
                    client,
                    data_root=Path(tmp).resolve(),
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=55,
                    output_format="m4a",
                    submit=False,
                    watch=False,
                    resume=True,
                    job_id=None,
                    manifest_out=None,
                    poll_interval=0.2,
                    timeout_seconds=1.0,
                    emit_progress=lambda _event: None,
                )
            self.assertEqual(len(client.post_calls), 1)

    def test_running_job_resume_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_root = str(Path(tmp).resolve())
            responses = make_base_responses(
                data_root=data_root,
                jobs=[{"id": 700, "book_id": 1, "from_chapter": 629, "to_chapter": 629, "repair_mode": "off", "output_format": "m4a", "casting_plan_id": 55}],
                job_details={700: make_job_detail(job_id=700, status="running", chapter_status="running")},
            )
            client = FakeClient(responses)
            with self.assertRaisesRegex(BindingMismatchError, "not in a resumable state"):
                run_job_flow(
                    client,
                    data_root=Path(tmp).resolve(),
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=55,
                    output_format="m4a",
                    submit=False,
                    watch=False,
                    resume=True,
                    job_id=None,
                    manifest_out=None,
                    poll_interval=0.2,
                    timeout_seconds=1.0,
                    emit_progress=lambda _event: None,
                )

    def test_explicit_job_id_with_wrong_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            responses = make_base_responses(
                data_root=str(Path(tmp).resolve()),
                jobs=[],
                job_details={888: make_job_detail(job_id=888, status="completed", text_revision_id=999)},
            )
            client = FakeClient(responses)
            with self.assertRaisesRegex(BindingMismatchError, "does not match the verified production identity"):
                run_job_flow(
                    client,
                    data_root=Path(tmp).resolve(),
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=55,
                    output_format="m4a",
                    submit=False,
                    watch=False,
                    resume=False,
                    job_id=888,
                    manifest_out=None,
                    poll_interval=0.2,
                    timeout_seconds=1.0,
                    emit_progress=lambda _event: None,
                )

    def test_cli_watch_timeout_has_distinct_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_runner.run_job_flow", side_effect=WatchTimeoutError("timeout")):
                code = run_cli([
                    "--data-root", str(Path(tmp).resolve()),
                    "--api-base", "http://127.0.0.1:8768",
                    "--book-id", "1",
                    "--chapter-number", "629",
                    "--casting-plan-id", "55",
                    "--watch",
                ])
            self.assertEqual(code, EXIT_WATCH_TIMEOUT)

    def test_cli_keyboard_interrupt_does_not_cancel_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch("story_audio.production_runner.run_job_flow", side_effect=KeyboardInterrupt()), \
                 patch("sys.stdout", stdout), \
                 patch("sys.stderr", stderr):
                code = run_cli([
                    "--data-root", str(Path(tmp).resolve()),
                    "--api-base", "http://127.0.0.1:8768",
                    "--book-id", "1",
                    "--chapter-number", "629",
                    "--casting-plan-id", "55",
                    "--watch",
                ])
            self.assertEqual(code, EXIT_OPERATOR_INTERRUPT)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "operator_interrupt")


if __name__ == "__main__":
    unittest.main()
