from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from .audio_qa import AudioQaError, generate_audio_qa_report
from .listening_checklist import ChecklistOptions, ListeningChecklistError, build_listening_checklist
from .production_runner import (
    ApiFailureError,
    BindingMismatchError,
    HttpJsonClient,
    RunnerError,
    build_internal_error_result,
    canonicalize_data_root,
    normalize_api_base,
    normalize_manifest_path,
    normalize_poll_interval,
    normalize_timeout_seconds,
    run_job_flow,
    run_preflight,
)


WORKFLOW_SCHEMA = "story-audio-production-workflow/v1"
IMPLEMENTATION_VERSION = "production-workflow/v1"
THROUGH_CHOICES = ("preflight", "manifest", "qa", "checklist")
STOPPED_RUNNER_STATUSES = {"resume_required", "failed", "cancelled", "completed_with_errors"}


class WorkflowError(RuntimeError):
    exit_code = 2
    status = "invalid_arguments"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


def _canonical_json(value: Any, *, ensure_ascii: bool = False) -> str:
    return json.dumps(value, ensure_ascii=ensure_ascii, sort_keys=True, separators=(",", ":"))


def _emit_event(stream: Any, event: dict[str, Any]) -> None:
    print(_canonical_json(event, ensure_ascii=True), file=stream, flush=True)


def _stage_record(*, status: str = "pending") -> dict[str, Any]:
    return {
        "status": status,
        "reused_existing": None,
        "created": None,
        "output_path": None,
        "output_sha256": None,
        "elapsed_seconds": 0.0,
        "details": None,
    }


def _finish_stage(
    stage: dict[str, Any],
    *,
    status: str,
    started: float,
    reused_existing: bool | None = None,
    created: bool | None = None,
    output_path: str | None = None,
    output_sha256: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    stage["status"] = status
    stage["reused_existing"] = reused_existing
    stage["created"] = created
    stage["output_path"] = output_path
    stage["output_sha256"] = output_sha256
    stage["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    stage["details"] = details


def _normalize_output_path(value: str | None, *, label: str) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        raise WorkflowError(f"{label} must be an absolute path")
    return path.resolve()


def _base_identity(
    *,
    data_root: Path,
    api_base: str,
    book_id: int,
    chapter_number: int,
    casting_plan_id: int,
    job_id: int | None,
) -> dict[str, Any]:
    return {
        "api_base": api_base,
        "data_root": str(data_root),
        "book_id": int(book_id),
        "chapter_number": int(chapter_number),
        "casting_plan_id": int(casting_plan_id),
        "job_id": int(job_id) if job_id is not None else None,
    }


def _workflow_default_qa_path(*, data_root: Path, job_id: int, chapter_number: int) -> Path:
    return (
        data_root
        / "workflow"
        / f"job_{int(job_id)}_chapter_{int(chapter_number)}"
        / "audio_qa.json"
    ).resolve()


def _workflow_default_checklist_path(*, data_root: Path, job_id: int, chapter_number: int) -> Path:
    return (
        data_root
        / "workflow"
        / f"job_{int(job_id)}_chapter_{int(chapter_number)}"
        / "checklist"
        / "index.html"
    ).resolve()


def _final_payload(
    *,
    status: str,
    mutation_performed: bool,
    through: str,
    identity: dict[str, Any],
    stages: dict[str, dict[str, Any]],
    outputs: dict[str, Any],
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": WORKFLOW_SCHEMA,
        "implementation_version": IMPLEMENTATION_VERSION,
        "status": status,
        "through": through,
        "mutation_performed": mutation_performed,
        "identity": identity,
        "stages": stages,
        "outputs": outputs,
    }
    if error is not None:
        payload["error"] = error
    return payload


def run_workflow(
    *,
    data_root: Path,
    api_base: str,
    book_id: int,
    chapter_number: int,
    casting_plan_id: int,
    job_id: int | None = None,
    submit: bool = False,
    resume: bool = False,
    through: str = "preflight",
    poll_interval: float = 2.0,
    timeout_seconds: float | None = 3600.0,
    manifest_out: Path | None = None,
    qa_out: Path | None = None,
    checklist_out: Path | None = None,
    ffmpeg_path: str = "ffmpeg",
    ffprobe_path: str = "ffprobe",
    checklist_title: str | None = None,
    max_risk_items: int = 20,
    stderr: Any = None,
) -> dict[str, Any]:
    stderr = stderr or sys.stderr
    if submit and resume:
        raise WorkflowError("--submit and --resume cannot be used together")
    if through not in THROUGH_CHOICES:
        raise WorkflowError("--through is invalid", details={"allowed": list(THROUGH_CHOICES)})
    if through == "preflight" and (submit or resume):
        raise WorkflowError("--submit/--resume require --through manifest, qa, or checklist")

    client = HttpJsonClient(api_base)
    stages = {
        "preflight": _stage_record(),
        "runner": _stage_record(status="skipped"),
        "manifest": _stage_record(status="skipped"),
        "qa": _stage_record(status="skipped"),
        "checklist": _stage_record(status="skipped"),
    }
    outputs = {
        "manifest_path": None,
        "manifest_sha256": None,
        "qa_report_path": None,
        "qa_report_sha256": None,
        "listening_checklist_path": None,
        "listening_checklist_sha256": None,
    }
    identity = _base_identity(
        data_root=data_root,
        api_base=api_base,
        book_id=book_id,
        chapter_number=chapter_number,
        casting_plan_id=casting_plan_id,
        job_id=job_id,
    )
    mutation_performed = False

    preflight_started = time.perf_counter()
    _emit_event(stderr, {"type": "stage_start", "stage": "preflight"})
    preflight = run_preflight(
        client,
        data_root=data_root,
        book_id=book_id,
        chapter_number=chapter_number,
        casting_plan_id=casting_plan_id,
        output_format="m4a",
    )
    _finish_stage(
        stages["preflight"],
        status=preflight["status"],
        started=preflight_started,
        details={
            "chapter_id": preflight["chapter"]["id"],
            "text_revision_id": preflight["text_revision"]["id"],
            "casting_plan_revision": preflight["casting_plan"]["revision"],
            "duplicate_job": preflight["duplicate_job"],
        },
    )
    _emit_event(stderr, {"type": "stage_complete", "stage": "preflight", "status": preflight["status"]})
    identity.update(
        {
            "chapter_id": int(preflight["chapter"]["id"]),
            "text_revision_id": int(preflight["text_revision"]["id"]),
            "text_revision_content_sha256": str(preflight["text_revision"]["content_sha256"]),
            "casting_plan_revision": int(preflight["casting_plan"]["revision"]),
            "casting_plan_sha256": str(preflight["casting_plan"]["sha256"]),
        }
    )
    if through == "preflight":
        return _final_payload(
            status="success",
            mutation_performed=False,
            through=through,
            identity=identity,
            stages=stages,
            outputs=outputs,
        )

    runner_started = time.perf_counter()
    stages["runner"] = _stage_record()
    stages["manifest"] = _stage_record()
    _emit_event(stderr, {"type": "stage_start", "stage": "runner"})
    runner_result = run_job_flow(
        client,
        data_root=data_root,
        book_id=book_id,
        chapter_number=chapter_number,
        casting_plan_id=casting_plan_id,
        output_format="m4a",
        submit=submit,
        watch=True,
        resume=resume,
        job_id=job_id,
        manifest_out=manifest_out,
        poll_interval=poll_interval,
        timeout_seconds=timeout_seconds,
        emit_progress=lambda event: _emit_event(stderr, {"type": "progress", "stage": "runner", **event}),
    )
    mutation_performed = bool(runner_result.get("mutation_performed"))
    if runner_result.get("job"):
        identity["job_id"] = int(runner_result["job"]["job_id"])
        identity["job_chapter_id"] = int(runner_result["job"]["job_chapter_id"])
        identity["job_status"] = str(runner_result["job"]["job_status"])
        identity["job_chapter_status"] = str(runner_result["job"]["job_chapter_status"])
    _finish_stage(
        stages["runner"],
        status=runner_result["status"],
        started=runner_started,
        created=True if submit and mutation_performed else False if submit else None,
        details={"job": runner_result.get("job"), "progress": runner_result.get("progress")},
    )
    _emit_event(stderr, {"type": "stage_complete", "stage": "runner", "status": runner_result["status"]})

    manifest_info = runner_result.get("manifest")
    if manifest_info:
        _finish_stage(
            stages["manifest"],
            status="success",
            started=runner_started,
            reused_existing=bool(manifest_info.get("reused_existing")),
            created=not bool(manifest_info.get("reused_existing")),
            output_path=str(manifest_info["path"]),
            output_sha256=str(manifest_info["sha256"]),
            details={"schema": manifest_info.get("schema")},
        )
        outputs["manifest_path"] = str(manifest_info["path"])
        outputs["manifest_sha256"] = str(manifest_info["sha256"])

    if runner_result["status"] in STOPPED_RUNNER_STATUSES:
        return _final_payload(
            status=runner_result["status"],
            mutation_performed=mutation_performed,
            through=through,
            identity=identity,
            stages=stages,
            outputs=outputs,
            error={
                "stage": "runner",
                "message": runner_result["status"],
                "details": runner_result,
            },
        )
    if outputs["manifest_path"] is None:
        return _final_payload(
            status="terminal_validation_failed",
            mutation_performed=mutation_performed,
            through=through,
            identity=identity,
            stages=stages,
            outputs=outputs,
            error={
                "stage": "manifest",
                "message": "Workflow did not produce a manifest",
                "details": {"runner_status": runner_result["status"]},
            },
        )
    if through == "manifest":
        return _final_payload(
            status="success",
            mutation_performed=mutation_performed,
            through=through,
            identity=identity,
            stages=stages,
            outputs=outputs,
        )

    qa_started = time.perf_counter()
    stages["qa"] = _stage_record()
    _emit_event(stderr, {"type": "stage_start", "stage": "qa"})
    qa_target = qa_out if qa_out is not None else _workflow_default_qa_path(
        data_root=data_root,
        job_id=int(identity["job_id"]),
        chapter_number=int(identity["chapter_number"]),
    )
    qa_result = generate_audio_qa_report(
        Path(outputs["manifest_path"]),
        output_path=qa_target,
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_path,
    )
    _finish_stage(
        stages["qa"],
        status=qa_result["status"],
        started=qa_started,
        reused_existing=bool(qa_result["reused_existing"]),
        created=not bool(qa_result["reused_existing"]),
        output_path=str(qa_result["report_path"]),
        output_sha256=str(qa_result["report_sha256"]),
        details={
            "exit_code": int(qa_result["exit_code"]),
            "segment_count": len(qa_result["report"]["segment_results"]),
        },
    )
    _emit_event(stderr, {"type": "stage_complete", "stage": "qa", "status": qa_result["status"]})
    outputs["qa_report_path"] = str(qa_result["report_path"])
    outputs["qa_report_sha256"] = str(qa_result["report_sha256"])
    if qa_result["status"] != "success":
        return _final_payload(
            status=qa_result["status"],
            mutation_performed=mutation_performed,
            through=through,
            identity=identity,
            stages=stages,
            outputs=outputs,
            error={
                "stage": "qa",
                "message": qa_result["status"],
                "details": {"exit_code": qa_result["exit_code"]},
            },
        )
    if through == "qa":
        return _final_payload(
            status="success",
            mutation_performed=mutation_performed,
            through=through,
            identity=identity,
            stages=stages,
            outputs=outputs,
        )

    checklist_started = time.perf_counter()
    stages["checklist"] = _stage_record()
    _emit_event(stderr, {"type": "stage_start", "stage": "checklist"})
    checklist_target = checklist_out if checklist_out is not None else _workflow_default_checklist_path(
        data_root=data_root,
        job_id=int(identity["job_id"]),
        chapter_number=int(identity["chapter_number"]),
    )
    checklist_result = build_listening_checklist(
        Path(outputs["manifest_path"]),
        Path(outputs["qa_report_path"]),
        output_path=checklist_target,
        options=ChecklistOptions(max_risk_items=max_risk_items, title=checklist_title),
    )
    _finish_stage(
        stages["checklist"],
        status=checklist_result["status"],
        started=checklist_started,
        reused_existing=bool(checklist_result["reused_existing"]),
        created=not bool(checklist_result["reused_existing"]),
        output_path=str(checklist_result["package_path"]),
        output_sha256=str(checklist_result["package_sha256"]),
        details={
            "selected_segment_count": int(checklist_result["selected_segment_count"]),
            "package_identity": checklist_result["package_identity"],
        },
    )
    _emit_event(stderr, {"type": "stage_complete", "stage": "checklist", "status": checklist_result["status"]})
    outputs["listening_checklist_path"] = str(checklist_result["package_path"])
    outputs["listening_checklist_sha256"] = str(checklist_result["package_sha256"])
    return _final_payload(
        status="success",
        mutation_performed=mutation_performed,
        through=through,
        identity=identity,
        stages=stages,
        outputs=outputs,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the isolated production workflow through manifest, QA, and listening checklist")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--book-id", required=True, type=int)
    parser.add_argument("--chapter-number", required=True, type=int)
    parser.add_argument("--casting-plan-id", required=True, type=int)
    parser.add_argument("--job-id", type=int)
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--through", choices=THROUGH_CHOICES, default="preflight")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=3600.0)
    parser.add_argument("--manifest-out")
    parser.add_argument("--qa-out")
    parser.add_argument("--checklist-out")
    parser.add_argument("--ffmpeg-path", default="ffmpeg")
    parser.add_argument("--ffprobe-path", default="ffprobe")
    parser.add_argument("--checklist-title")
    parser.add_argument("--max-risk-items", type=int, default=20)
    return parser


def main(argv: list[str] | None = None, *, stdout: Any = None, stderr: Any = None) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    try:
        args = build_arg_parser().parse_args(argv)
        data_root = canonicalize_data_root(args.data_root)
        api_base = normalize_api_base(args.api_base)
        manifest_out = normalize_manifest_path(args.manifest_out)
        qa_out = _normalize_output_path(args.qa_out, label="--qa-out")
        checklist_out = _normalize_output_path(args.checklist_out, label="--checklist-out")
        poll_interval = normalize_poll_interval(args.poll_interval)
        timeout_seconds = normalize_timeout_seconds(args.timeout_seconds)
        result = run_workflow(
            data_root=data_root,
            api_base=api_base,
            book_id=int(args.book_id),
            chapter_number=int(args.chapter_number),
            casting_plan_id=int(args.casting_plan_id),
            job_id=args.job_id,
            submit=bool(args.submit),
            resume=bool(args.resume),
            through=str(args.through),
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
            manifest_out=manifest_out,
            qa_out=qa_out,
            checklist_out=checklist_out,
            ffmpeg_path=str(args.ffmpeg_path),
            ffprobe_path=str(args.ffprobe_path),
            checklist_title=args.checklist_title,
            max_risk_items=int(args.max_risk_items),
            stderr=stderr,
        )
        print(_canonical_json(result, ensure_ascii=True), file=stdout)
        return 0 if result["status"] == "success" else 1
    except WorkflowError as exc:
        payload = _final_payload(
            status=exc.status,
            mutation_performed=False,
            through="preflight",
            identity={},
            stages={},
            outputs={},
            error={"stage": "arguments", "message": str(exc), "details": exc.details},
        )
        print(_canonical_json(payload, ensure_ascii=True), file=stdout)
        return exc.exit_code
    except RunnerError as exc:
        payload = _final_payload(
            status=exc.status,
            mutation_performed=bool(getattr(exc, "mutation_performed", False)),
            through="preflight",
            identity={},
            stages={},
            outputs={},
            error={"stage": "runner", "message": str(exc), "details": getattr(exc, "details", {})},
        )
        print(_canonical_json(payload, ensure_ascii=True), file=stdout)
        return int(exc.exit_code)
    except (AudioQaError, ListeningChecklistError) as exc:
        payload = _final_payload(
            status=exc.status,
            mutation_performed=False,
            through="preflight",
            identity={},
            stages={},
            outputs={},
            error={"stage": "downstream", "message": str(exc), "details": getattr(exc, "details", {})},
        )
        print(_canonical_json(payload, ensure_ascii=True), file=stdout)
        return int(exc.exit_code)
    except SystemExit:
        raise
    except Exception as exc:
        payload = build_internal_error_result(exc)
        wrapped = _final_payload(
            status=payload["status"],
            mutation_performed=False,
            through="preflight",
            identity={},
            stages={},
            outputs={},
            error={"stage": "internal", "message": payload["error"], "details": None},
        )
        print(_canonical_json(wrapped, ensure_ascii=True), file=stdout)
        print(f"internal_error: {type(exc).__name__}: {exc}", file=stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
