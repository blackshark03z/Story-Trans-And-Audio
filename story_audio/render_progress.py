from __future__ import annotations

from datetime import datetime, timezone
from math import floor
from typing import Any, Mapping


# A completed Chapter 1 segment took up to 38 seconds in the production trace.
# Sixty seconds avoids a false warning while still surfacing a genuinely stuck run.
STALL_AFTER_SECONDS = 60


def _as_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _phase(job: Mapping[str, Any]) -> str:
    status = str(job.get("status") or "").lower()
    stage = str(job.get("current_stage") or "").lower()
    if status in {"scheduled", "queued"}:
        return "waiting"
    if status in {"paused", "interrupted"}:
        return status
    if status in {"failed", "completed_with_errors"}:
        return "recovery"
    if status == "completed":
        return "complete"
    if status == "assembling" or stage == "assemble":
        return "assembling"
    if status in {"synthesizing", "repairing"} or stage in {"tts", "gemini"}:
        return "synthesizing"
    return "preparing"


def build_render_progress(
    job: Mapping[str, Any],
    *,
    now: datetime | None = None,
    stall_after_seconds: int = STALL_AFTER_SECONDS,
) -> dict[str, Any]:
    """Derive display-only render progress from persisted Job and Segment data."""

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)

    actual_total = max(0, int(job.get("total_segments") or 0))
    planned_total = max(0, int(job.get("planned_segment_total") or 0))
    total = actual_total or planned_total
    completed = max(0, int(job.get("completed_segments") or 0))
    failed = max(0, int(job.get("failed_segments") or 0))
    running = max(0, int(job.get("running_segments") or 0))
    pending = max(0, total - completed - failed - running)
    phase = _phase(job)
    percent = floor((completed * 100) / total) if total else 0
    if phase == "complete":
        percent = 100

    started_at = _as_datetime(job.get("started_at"))
    scheduled_at = _as_datetime(job.get("scheduled_at"))
    updated_at = _as_datetime(job.get("updated_at"))
    first_completed_at = _as_datetime(job.get("first_segment_completed_at"))
    last_completed_at = _as_datetime(job.get("last_segment_completed_at"))
    activity_at = last_completed_at or started_at or scheduled_at or updated_at
    elapsed_anchor = started_at or scheduled_at
    elapsed_seconds = (
        max(0, floor((current - elapsed_anchor).total_seconds()))
        if elapsed_anchor and phase not in {"complete", "recovery"}
        else None
    )

    eta_seconds: int | None = None
    if (
        phase == "synthesizing"
        and total > completed
        and completed >= 3
        and started_at
        and last_completed_at
        and last_completed_at >= started_at
    ):
        average_seconds = (last_completed_at - started_at).total_seconds() / completed
        eta_seconds = max(1, floor(average_seconds * (total - completed)))

    active = phase in {"waiting", "preparing", "synthesizing", "assembling"}
    stalled_for_seconds = (
        max(0, floor((current - activity_at).total_seconds()))
        if active and activity_at
        else 0
    )
    return {
        "source": "persisted_job_and_segment_state" if actual_total else "pinned_segment_plan",
        "phase": phase,
        "unit_total": total,
        "unit_completed": completed,
        "unit_failed": failed,
        "unit_running": running,
        "unit_pending": pending,
        "percent_complete": percent,
        "started_at": started_at.isoformat() if started_at else None,
        "first_unit_completed_at": first_completed_at.isoformat() if first_completed_at else None,
        "last_progress_at": last_completed_at.isoformat() if last_completed_at else None,
        "elapsed_seconds": elapsed_seconds,
        "estimated_remaining_seconds": eta_seconds,
        "stall_after_seconds": stall_after_seconds,
        "stalled": bool(active and activity_at and stalled_for_seconds >= stall_after_seconds),
        "stalled_for_seconds": stalled_for_seconds,
    }
