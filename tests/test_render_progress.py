from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from story_audio.render_progress import STALL_AFTER_SECONDS, build_render_progress


UTC = timezone.utc


class RenderProgressTests(unittest.TestCase):
    def test_synthesis_progress_uses_persisted_segment_timestamps_for_eta(self) -> None:
        started = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
        progress = build_render_progress(
            {
                "status": "synthesizing",
                "current_stage": "tts",
                "total_segments": 49,
                "completed_segments": 10,
                "failed_segments": 0,
                "running_segments": 1,
                "started_at": started.isoformat(),
                "first_segment_completed_at": (started + timedelta(seconds=12)).isoformat(),
                "last_segment_completed_at": (started + timedelta(seconds=120)).isoformat(),
            },
            now=started + timedelta(seconds=125),
        )

        self.assertEqual(progress["phase"], "synthesizing")
        self.assertEqual(progress["unit_pending"], 38)
        self.assertEqual(progress["percent_complete"], 20)
        self.assertEqual(progress["elapsed_seconds"], 125)
        self.assertEqual(progress["estimated_remaining_seconds"], 468)
        self.assertFalse(progress["stalled"])

    def test_stall_requires_no_durable_progress_beyond_safe_interval(self) -> None:
        completed = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
        progress = build_render_progress(
            {
                "status": "synthesizing",
                "total_segments": 49,
                "completed_segments": 1,
                "last_segment_completed_at": completed.isoformat(),
            },
            now=completed + timedelta(seconds=STALL_AFTER_SECONDS),
        )

        self.assertTrue(progress["stalled"])
        self.assertEqual(progress["stalled_for_seconds"], STALL_AFTER_SECONDS)

    def test_assembly_reports_completed_units_without_fake_remaining_time(self) -> None:
        progress = build_render_progress(
            {
                "status": "assembling",
                "current_stage": "assemble",
                "total_segments": 49,
                "completed_segments": 49,
            },
            now=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(progress["phase"], "assembling")
        self.assertEqual(progress["percent_complete"], 100)
        self.assertIsNone(progress["estimated_remaining_seconds"])

    def test_prepared_job_uses_pinned_segment_plan_before_worker_creates_rows(self) -> None:
        progress = build_render_progress(
            {
                "status": "scheduled",
                "planned_segment_total": 49,
                "scheduled_at": "2026-08-09T12:00:00+00:00",
            },
            now=datetime(2026, 8, 9, 12, 0, 5, tzinfo=UTC),
        )

        self.assertEqual(progress["source"], "pinned_segment_plan")
        self.assertEqual(progress["unit_total"], 49)
        self.assertEqual(progress["unit_completed"], 0)
        self.assertEqual(progress["percent_complete"], 0)


if __name__ == "__main__":
    unittest.main()
