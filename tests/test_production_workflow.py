from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from story_audio.audio_qa import QaArtifactIntegrityError
from story_audio.files import atomic_write_bytes, sha256_file
from story_audio.listening_checklist import ChecklistInputMismatchError
from story_audio.production_runner import BindingMismatchError, RuntimeMismatchError, WatchTimeoutError
from story_audio.production_workflow import WORKFLOW_SCHEMA, main, run_workflow


def _preflight_result(*, status: str = "preflight_pass", duplicate: dict | None = None) -> dict:
    return {
        "status": status,
        "runtime_identity": {
            "api_base": "http://127.0.0.1:8771",
            "data_root": "D:/isolated/data",
            "db_path": "D:/isolated/data/app.db",
            "schema_version": 9,
            "latest_schema_version": 9,
            "canonical_live_data_root": "D:/Youtube/Story Trans And Audio/data",
            "canonical_live_db_path": "D:/Youtube/Story Trans And Audio/data/app.db",
            "is_canonical_live_data_root": False,
            "is_canonical_live_db": False,
        },
        "book": {"id": 1},
        "chapter": {"id": 629, "book_id": 1, "number": 629, "title": "Chapter 629"},
        "text_revision": {"id": 400, "content_sha256": "rev-sha", "status": "approved"},
        "casting_plan": {"id": 2, "revision": 1, "sha256": "plan-sha", "character_bible_fingerprint": "cbf"},
        "book_voice_profile": {"id": 3, "config_version": 4, "current_profile": {}, "profile_drift": False},
        "derived_default_voice": {"voice_id": "ngoc_lan", "label": "Ngoc Lan"},
        "expected_utterance_count": 12,
        "speaker_voice_distribution": [],
        "duplicate_job": duplicate or {"duplicate": False, "matches": []},
        "request_preview": {"payload": {"output_format": "m4a", "repair_mode": "off"}, "payload_bytes_ascii": "{}", "contains_substitution_question_mark": False, "contains_replacement_char": False},
        "mutation_performed": False,
    }


def _runner_result(*, status: str = "completed", mutation_performed: bool = False, manifest_path: str = "D:/isolated/data/manifests/job_2_chapter_629.json", manifest_sha: str = "manifest-sha", reused_manifest: bool = False, job_id: int = 2, job_chapter_id: int = 920) -> dict:
    return {
        "status": status,
        "job": {
            "job_id": job_id,
            "job_status": "completed" if status == "completed" else status,
            "job_chapter_id": job_chapter_id,
            "job_chapter_status": "completed" if status == "completed" else status,
        },
        "manifest": {
            "path": manifest_path,
            "sha256": manifest_sha,
            "reused_existing": reused_manifest,
            "schema": "story-audio-production-manifest/v1",
        } if status == "completed" else None,
        "progress": None,
        "preflight": _preflight_result(),
        "resume_response": None,
        "mutation_performed": mutation_performed,
    }


def _qa_result(*, status: str = "success", reused_existing: bool = False) -> dict:
    return {
        "status": status,
        "exit_code": 0 if status == "success" else 4,
        "report_path": "D:/isolated/data/workflow/job_2_chapter_629/audio_qa.json",
        "report_sha256": "qa-sha",
        "reused_existing": reused_existing,
        "report": {"segment_results": [{"id": 1}], "voice_aggregates": [{"voice_id": "duc_tri"}]},
    }


def _checklist_result(*, reused_existing: bool = False) -> dict:
    return {
        "status": "success",
        "exit_code": 0,
        "package_path": "D:/isolated/data/workflow/job_2_chapter_629/checklist/index.html",
        "package_sha256": "checklist-sha",
        "package_size_bytes": 1234,
        "package_identity": "pkg-1",
        "reused_existing": reused_existing,
        "selected_segment_count": 5,
        "hard_clipping_count": 0,
        "integrity_failure_count": 0,
        "report": {},
    }


def _final_workflow_result(*, status: str = "success") -> dict:
    return {
        "schema": WORKFLOW_SCHEMA,
        "implementation_version": "production-workflow/v1",
        "status": status,
        "through": "manifest",
        "mutation_performed": True,
        "identity": {"mode": "CANONICAL PRODUCTION MODE"},
        "stages": {"preflight": {"status": "preflight_pass"}},
        "outputs": {},
    }


def _write_manifest_fixture(
    root: Path,
    *,
    canonical: bool = False,
    job_id: int = 2,
    job_chapter_id: int = 920,
    chapter_id: int = 629,
    chapter_number: int = 629,
    text_revision_id: int = 400,
    casting_plan_id: int = 2,
    casting_plan_revision: int = 1,
    casting_plan_sha256: str = "plan-sha",
    artifact_id: int = 88,
) -> Path:
    data_root = root.resolve()
    output_dir = data_root / "output" / "book_1" / f"chapter_{chapter_number:04d}" / f"job_{job_id}" / "render_0001"
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / "chapter.m4a"
    atomic_write_bytes(final_path, b"fixture-m4a")
    final_sha = sha256_file(final_path)
    manifest_path = data_root / "workflow" / f"job_{job_id}_chapter_{chapter_number}" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    root_string = str(data_root if not canonical else (Path.cwd() / "data").resolve())
    db_string = str((data_root / "app.db").resolve() if not canonical else (Path.cwd() / "data" / "app.db").resolve())
    manifest = {
        "schema": "story-audio-production-manifest/v1",
        "identity": {
            "data_root": root_string,
            "db_path": db_string,
            "book_id": 1,
            "chapter_id": chapter_id,
            "chapter_number": chapter_number,
            "job_id": job_id,
            "job_chapter_id": job_chapter_id,
            "output_format": "m4a",
        },
        "immutable_bindings": {
            "text_revision_id": text_revision_id,
            "text_revision_content_sha256": "rev-sha",
            "casting_plan_id": casting_plan_id,
            "casting_plan_revision": casting_plan_revision,
            "casting_plan_sha256": casting_plan_sha256,
        },
        "terminal_state": {
            "job_status": "completed",
            "job_chapter_status": "completed",
        },
        "artifacts": [
            {
                "artifact_id": artifact_id,
                "artifact_type": "chapter_m4a",
                "status": "active",
                "absolute_local_path": str(final_path.resolve()),
                "computed_sha256": final_sha,
                "stored_sha256": final_sha,
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


class ProductionWorkflowTests(unittest.TestCase):
    def test_default_preflight_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result()) as preflight_mock:
                result = run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    stderr=io.StringIO(),
                )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["through"], "preflight")
        self.assertEqual(result["stages"]["preflight"]["status"], "preflight_pass")
        self.assertEqual(result["stages"]["runner"]["status"], "skipped")
        preflight_mock.assert_called_once()

    def test_completed_job_through_checklist_runs_downstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result(status="already_completed", duplicate={"duplicate": True, "existing_job_id": 2, "existing_job_status": "completed"})), \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="completed")), \
                 patch("story_audio.production_workflow._verify_downstream_manifest_identity", return_value={"final_artifact_id": 88, "final_artifact_path": "D:/isolated/data/output/chapter.m4a", "final_artifact_sha256": "final-sha"}), \
                 patch("story_audio.production_workflow.generate_audio_qa_report", return_value=_qa_result()) as qa_mock, \
                 patch("story_audio.production_workflow.build_listening_checklist", return_value=_checklist_result()) as checklist_mock:
                result = run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="checklist",
                    stderr=io.StringIO(),
                )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["outputs"]["manifest_path"], "D:/isolated/data/manifests/job_2_chapter_629.json")
        self.assertEqual(result["outputs"]["qa_report_path"], "D:/isolated/data/workflow/job_2_chapter_629/audio_qa.json")
        self.assertEqual(result["outputs"]["listening_checklist_path"], "D:/isolated/data/workflow/job_2_chapter_629/checklist/index.html")
        qa_mock.assert_called_once()
        checklist_mock.assert_called_once()
        self.assertFalse(qa_mock.call_args.kwargs["allow_canonical_production"])
        self.assertFalse(checklist_mock.call_args.kwargs["allow_canonical_production"])

    def test_existing_completed_job_no_new_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result(status="already_completed", duplicate={"duplicate": True, "existing_job_id": 2, "existing_job_status": "completed"})), \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="completed")) as runner_mock, \
                 patch("story_audio.production_workflow._verify_downstream_manifest_identity", return_value={"final_artifact_id": 88, "final_artifact_path": "D:/isolated/data/output/chapter.m4a", "final_artifact_sha256": "final-sha"}), \
                 patch("story_audio.production_workflow.generate_audio_qa_report", return_value=_qa_result()), \
                 patch("story_audio.production_workflow.build_listening_checklist", return_value=_checklist_result()):
                run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="checklist",
                    stderr=io.StringIO(),
                )
        self.assertFalse(runner_mock.call_args.kwargs["submit"])

    def test_submit_create_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result()), \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="completed", mutation_performed=True)) as runner_mock, \
                 patch("story_audio.production_workflow._verify_downstream_manifest_identity", return_value={"final_artifact_id": 88, "final_artifact_path": "D:/isolated/data/output/chapter.m4a", "final_artifact_sha256": "final-sha"}):
                result = run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="manifest",
                    submit=True,
                    stderr=io.StringIO(),
                )
        self.assertTrue(result["mutation_performed"])
        self.assertTrue(runner_mock.call_args.kwargs["submit"])

    def test_resume_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result(duplicate={"duplicate": True, "existing_job_id": 2, "existing_job_status": "paused"})), \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="completed", mutation_performed=True)) as runner_mock, \
                 patch("story_audio.production_workflow._verify_downstream_manifest_identity", return_value={"final_artifact_id": 88, "final_artifact_path": "D:/isolated/data/output/chapter.m4a", "final_artifact_sha256": "final-sha"}):
                result = run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="manifest",
                    resume=True,
                    stderr=io.StringIO(),
                )
        self.assertEqual(result["status"], "success")
        self.assertTrue(runner_mock.call_args.kwargs["resume"])

    def test_submit_resume_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(Exception, "cannot be used together"):
                run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="manifest",
                    submit=True,
                    resume=True,
                    stderr=io.StringIO(),
                )

    def test_canonical_mode_requires_explicit_submit(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(Exception, "requires explicit --submit or --job-id"):
                run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="manifest",
                    allow_canonical_production=True,
                    stderr=io.StringIO(),
                )

    def test_canonical_downstream_with_explicit_job_id_is_allowed_and_stays_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            manifest_path = _write_manifest_fixture(root, job_id=17, job_chapter_id=17, chapter_id=629, chapter_number=629, text_revision_id=400, casting_plan_id=2, casting_plan_sha256="plan-sha")
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result()), \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="completed", mutation_performed=False, manifest_path=str(manifest_path), job_id=17, job_chapter_id=17)) as runner_mock, \
                 patch("story_audio.production_workflow.generate_audio_qa_report", return_value=_qa_result()) as qa_mock, \
                 patch("story_audio.production_workflow.build_listening_checklist", return_value=_checklist_result()) as checklist_mock:
                result = run_workflow(
                    data_root=root,
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    job_id=17,
                    through="checklist",
                    allow_canonical_production=True,
                    stderr=io.StringIO(),
                )
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["mutation_performed"])
        self.assertFalse(runner_mock.call_args.kwargs["submit"])
        self.assertTrue(qa_mock.call_args.kwargs["allow_canonical_production"])
        self.assertTrue(checklist_mock.call_args.kwargs["allow_canonical_production"])

    def test_canonical_mode_marks_identity_and_delegates_explicit_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = _write_manifest_fixture(Path(tmp).resolve(), job_id=2, job_chapter_id=920)
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result()) as preflight_mock, \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="completed", mutation_performed=True, manifest_path=str(manifest_path))) as runner_mock:
                result = run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="manifest",
                    submit=True,
                    allow_canonical_production=True,
                    stderr=io.StringIO(),
                )
        self.assertEqual(result["identity"]["mode"], "CANONICAL PRODUCTION MODE")
        self.assertTrue(preflight_mock.call_args.kwargs["allow_canonical_production"])
        self.assertTrue(runner_mock.call_args.kwargs["allow_canonical_production"])

    def test_isolated_workflow_default_unchanged_without_canonical_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = _write_manifest_fixture(Path(tmp).resolve(), job_id=2, job_chapter_id=920)
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result()) as preflight_mock, \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="completed", mutation_performed=True, manifest_path=str(manifest_path))) as runner_mock:
                run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="manifest",
                    submit=True,
                    stderr=io.StringIO(),
                )
        self.assertFalse(preflight_mock.call_args.kwargs["allow_canonical_production"])
        self.assertFalse(runner_mock.call_args.kwargs["allow_canonical_production"])

    def test_downstream_manifest_identity_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            manifest_path = _write_manifest_fixture(root, job_id=999, job_chapter_id=17, chapter_id=629, chapter_number=629, text_revision_id=400, casting_plan_id=2)
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result()), \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="completed", mutation_performed=False, manifest_path=str(manifest_path), job_id=17)):
                with self.assertRaisesRegex(BindingMismatchError, "Manifest identity field job_id"):
                    run_workflow(
                        data_root=root,
                        api_base="http://127.0.0.1:8771",
                        book_id=1,
                        chapter_number=629,
                        casting_plan_id=2,
                        job_id=17,
                        through="qa",
                        allow_canonical_production=True,
                        stderr=io.StringIO(),
                    )

    def test_paused_job_no_auto_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result(duplicate={"duplicate": True, "existing_job_id": 2, "existing_job_status": "paused"})), \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="resume_required")):
                result = run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="checklist",
                    stderr=io.StringIO(),
                )
        self.assertEqual(result["status"], "resume_required")
        self.assertEqual(result["stages"]["qa"]["status"], "skipped")

    def test_active_job_watched(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result(status="existing_job_detected", duplicate={"duplicate": True, "existing_job_id": 2, "existing_job_status": "running"})), \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="completed")) as runner_mock, \
                 patch("story_audio.production_workflow._verify_downstream_manifest_identity", return_value={"final_artifact_id": 88, "final_artifact_path": "D:/isolated/data/output/chapter.m4a", "final_artifact_sha256": "final-sha"}):
                run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="manifest",
                    stderr=io.StringIO(),
                )
        self.assertTrue(runner_mock.call_args.kwargs["watch"])

    def test_failed_terminal_stops_before_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result(status="existing_terminal_job_requires_operator_decision", duplicate={"duplicate": True, "existing_job_id": 2, "existing_job_status": "failed"})), \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="failed", mutation_performed=False)):
                result = run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="manifest",
                    stderr=io.StringIO(),
                )
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["outputs"]["manifest_path"])

    def test_manifest_fail_stops_qa_checklist(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result()), \
                 patch("story_audio.production_workflow.run_job_flow", side_effect=BindingMismatchError("manifest mismatch")), \
                 self.assertRaises(BindingMismatchError):
                run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="checklist",
                    stderr=io.StringIO(),
                )

    def test_qa_fail_stops_checklist(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = _write_manifest_fixture(Path(tmp).resolve(), job_id=2, job_chapter_id=920)
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result()), \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="completed", manifest_path=str(manifest_path))), \
                 patch("story_audio.production_workflow.generate_audio_qa_report", return_value=_qa_result(status="artifact_integrity_failure")) as qa_mock, \
                 patch("story_audio.production_workflow.build_listening_checklist") as checklist_mock:
                result = run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="checklist",
                    stderr=io.StringIO(),
                )
        self.assertEqual(result["status"], "artifact_integrity_failure")
        qa_mock.assert_called_once()
        checklist_mock.assert_not_called()

    def test_stage_reuse_reflected_correctly(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result()), \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="completed", reused_manifest=True)), \
                 patch("story_audio.production_workflow._verify_downstream_manifest_identity", return_value={"final_artifact_id": 88, "final_artifact_path": "D:/isolated/data/output/chapter.m4a", "final_artifact_sha256": "final-sha"}), \
                 patch("story_audio.production_workflow.generate_audio_qa_report", return_value=_qa_result(reused_existing=True)), \
                 patch("story_audio.production_workflow.build_listening_checklist", return_value=_checklist_result(reused_existing=True)):
                result = run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="checklist",
                    stderr=io.StringIO(),
                )
        self.assertTrue(result["stages"]["manifest"]["reused_existing"])
        self.assertTrue(result["stages"]["qa"]["reused_existing"])
        self.assertTrue(result["stages"]["checklist"]["reused_existing"])

    def test_conflicting_output_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result()), \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="completed")), \
                 patch("story_audio.production_workflow._verify_downstream_manifest_identity", return_value={"final_artifact_id": 88, "final_artifact_path": "D:/isolated/data/output/chapter.m4a", "final_artifact_sha256": "final-sha"}), \
                 patch("story_audio.production_workflow.generate_audio_qa_report", side_effect=QaArtifactIntegrityError("conflict")):
                with self.assertRaises(QaArtifactIntegrityError):
                    run_workflow(
                        data_root=Path(tmp).resolve(),
                        api_base="http://127.0.0.1:8771",
                        book_id=1,
                        chapter_number=629,
                        casting_plan_id=2,
                        through="qa",
                        stderr=io.StringIO(),
                    )

    def test_explicit_job_id_wrong_binding_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result()), \
                 patch("story_audio.production_workflow.run_job_flow", side_effect=BindingMismatchError("wrong binding")):
                with self.assertRaises(BindingMismatchError):
                    run_workflow(
                        data_root=Path(tmp).resolve(),
                        api_base="http://127.0.0.1:8771",
                        book_id=1,
                        chapter_number=629,
                        casting_plan_id=2,
                        job_id=999,
                        through="manifest",
                        stderr=io.StringIO(),
                    )

    def test_runtime_root_mismatch_bubbles(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_workflow.run_preflight", side_effect=BindingMismatchError("runtime mismatch")):
                with self.assertRaises(BindingMismatchError):
                    run_workflow(
                        data_root=Path(tmp).resolve(),
                        api_base="http://127.0.0.1:8771",
                        book_id=1,
                        chapter_number=629,
                        casting_plan_id=2,
                        through="preflight",
                        stderr=io.StringIO(),
                    )

    def test_timeout_does_not_cancel_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result()), \
                 patch("story_audio.production_workflow.run_job_flow", side_effect=WatchTimeoutError("timeout")):
                code = main([
                    "--data-root", str(Path(tmp).resolve()),
                    "--api-base", "http://127.0.0.1:8771",
                    "--book-id", "1",
                    "--chapter-number", "629",
                    "--casting-plan-id", "2",
                    "--through", "manifest",
                ], stdout=stdout, stderr=io.StringIO())
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "watch_timeout")

    def test_main_rejects_canonical_root_by_default(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "data"
            live.mkdir()
            with patch("story_audio.production_runner.canonical_production_db_path", return_value=live / "app.db"):
                code = main([
                    "--data-root", str(live.resolve()),
                    "--api-base", "http://127.0.0.1:8771",
                    "--book-id", "1",
                    "--chapter-number", "629",
                    "--casting-plan-id", "2",
                ], stdout=stdout, stderr=stderr)
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "runtime_mismatch")

    def test_main_allows_canonical_root_only_with_explicit_flag(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "data"
            live.mkdir()
            with patch("story_audio.production_runner.canonical_production_db_path", return_value=live / "app.db"), \
                 patch("story_audio.production_workflow.run_workflow", return_value=_final_workflow_result()) as workflow_mock:
                code = main([
                    "--data-root", str(live.resolve()),
                    "--api-base", "http://127.0.0.1:8771",
                    "--book-id", "1",
                    "--chapter-number", "629",
                    "--casting-plan-id", "2",
                    "--submit",
                    "--through", "manifest",
                    "--allow-canonical-production",
                ], stdout=stdout, stderr=stderr)
        self.assertEqual(code, 0)
        self.assertTrue(workflow_mock.call_args.kwargs["allow_canonical_production"])

    def test_main_allows_canonical_downstream_with_explicit_job_id(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "data"
            live.mkdir()
            with patch("story_audio.production_runner.canonical_production_db_path", return_value=live / "app.db"), \
                 patch("story_audio.production_workflow.run_workflow", return_value=_final_workflow_result()) as workflow_mock:
                code = main([
                    "--data-root", str(live.resolve()),
                    "--api-base", "http://127.0.0.1:8771",
                    "--book-id", "1",
                    "--chapter-number", "629",
                    "--casting-plan-id", "2",
                    "--job-id", "17",
                    "--through", "checklist",
                    "--allow-canonical-production",
                ], stdout=stdout, stderr=stderr)
        self.assertEqual(code, 0)
        self.assertEqual(workflow_mock.call_args.kwargs["job_id"], 17)

    def test_main_requires_casting_plan_id_in_canonical_mode(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with self.assertRaises(SystemExit):
            main([
                "--data-root", "D:/tmp/data",
                "--api-base", "http://127.0.0.1:8771",
                "--book-id", "1",
                "--chapter-number", "629",
                "--submit",
                "--through", "manifest",
                "--allow-canonical-production",
            ], stdout=stdout, stderr=stderr)

    def test_structured_internal_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with patch("story_audio.production_workflow.run_preflight", side_effect=KeyError("boom")):
                code = main([
                    "--data-root", str(Path(tmp).resolve()),
                    "--api-base", "http://127.0.0.1:8771",
                    "--book-id", "1",
                    "--chapter-number", "629",
                    "--casting-plan-id", "2",
                ], stdout=stdout, stderr=io.StringIO())
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stdout.getvalue())["schema"], WORKFLOW_SCHEMA)

    def test_final_stdout_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result()):
                code = main([
                    "--data-root", str(Path(tmp).resolve()),
                    "--api-base", "http://127.0.0.1:8771",
                    "--book-id", "1",
                    "--chapter-number", "629",
                    "--casting-plan-id", "2",
                ], stdout=stdout, stderr=io.StringIO())
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["schema"], WORKFLOW_SCHEMA)
        self.assertIn("stages", payload)

    def test_no_regenerate_accept_reject_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result()), \
                 patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="completed")), \
                 patch("story_audio.production_workflow._verify_downstream_manifest_identity", return_value={"final_artifact_id": 88, "final_artifact_path": "D:/isolated/data/output/chapter.m4a", "final_artifact_sha256": "final-sha"}), \
                 patch("story_audio.production_workflow.generate_audio_qa_report", return_value=_qa_result()), \
                 patch("story_audio.production_workflow.build_listening_checklist", return_value=_checklist_result()):
                result = run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="checklist",
                    stderr=io.StringIO(),
                )
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("regenerate", encoded)
        self.assertNotIn("reject", encoded)
        self.assertNotIn("accept", encoded)

    def test_deterministic_second_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            patches = [
                patch("story_audio.production_workflow.run_preflight", return_value=_preflight_result(status="already_completed", duplicate={"duplicate": True, "existing_job_id": 2, "existing_job_status": "completed"})),
                patch("story_audio.production_workflow.run_job_flow", return_value=_runner_result(status="completed", reused_manifest=True)),
                patch("story_audio.production_workflow._verify_downstream_manifest_identity", return_value={"final_artifact_id": 88, "final_artifact_path": "D:/isolated/data/output/chapter.m4a", "final_artifact_sha256": "final-sha"}),
                patch("story_audio.production_workflow.generate_audio_qa_report", return_value=_qa_result(reused_existing=True)),
                patch("story_audio.production_workflow.build_listening_checklist", return_value=_checklist_result(reused_existing=True)),
            ]
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                first = run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="checklist",
                    stderr=io.StringIO(),
                )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                second = run_workflow(
                    data_root=Path(tmp).resolve(),
                    api_base="http://127.0.0.1:8771",
                    book_id=1,
                    chapter_number=629,
                    casting_plan_id=2,
                    through="checklist",
                    stderr=io.StringIO(),
                )
        self.assertEqual(first["outputs"], second["outputs"])


if __name__ == "__main__":
    unittest.main()
