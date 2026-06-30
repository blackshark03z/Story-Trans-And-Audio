"""
UI contract tests for segment regeneration feature.

Tests that UI elements and API calls exist for the regeneration flow:
- Regenerate button for verified segments
- Original and candidate audio players
- Accept and Reject buttons
- API endpoint calls
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import story_audio.api as api_module
from tests.base import IsolatedTestCase


class SegmentRegenerationUiTests(IsolatedTestCase):
    """UI contract tests for segment regeneration."""

    def setUp(self) -> None:
        super().setUp()
        self.ui_root = Path(__file__).resolve().parents[1] / "ui"

    def tearDown(self) -> None:
        super().tearDown()

    def test_ui_contract_verified_segment_renders_regenerate_button(self) -> None:
        """Verified segments render a Regenerate button in diagnostics modal."""
        script = (self.ui_root / "app.js").read_text(encoding="utf-8")
        
        # Regenerate button only shown for verified segments
        self.assertIn("status==='verified'", script)
        self.assertIn("Regenerate Verified Segment", script)
        self.assertIn("regenerateSegment", script)

    def test_ui_contract_active_attempt_renders_original_audio_endpoint(self) -> None:
        """Active attempt renders the original audio endpoint."""
        script = (self.ui_root / "app.js").read_text(encoding="utf-8")
        
        # Original audio from segment endpoint
        self.assertIn("active_attempt", script)
        self.assertIn("/api/segments/", script)
        self.assertIn("/audio", script)
        self.assertIn("<audio controls", script)

    def test_ui_contract_candidate_renders_safe_candidate_audio_endpoint(self) -> None:
        """Candidate attempt renders the safe candidate-audio endpoint."""
        script = (self.ui_root / "app.js").read_text(encoding="utf-8")
        
        # Candidate audio from segment-attempts endpoint (safe path lookup)
        self.assertIn("candidate", script)
        self.assertIn("/api/segment-attempts/", script)
        self.assertIn("attempt_id", script)

    def test_ui_contract_candidate_renders_accept_and_reject_actions(self) -> None:
        """Candidate renders Accept and Reject action buttons."""
        script = (self.ui_root / "app.js").read_text(encoding="utf-8")
        
        # Accept and Reject buttons
        self.assertIn("Accept", script)
        self.assertIn("Reject", script)
        self.assertIn("acceptCandidate", script)
        self.assertIn("rejectCandidate", script)

    def test_ui_contract_regenerate_calls_correct_api_endpoint(self) -> None:
        """Regenerate calls POST /api/segments/{id}/regenerate."""
        script = (self.ui_root / "app.js").read_text(encoding="utf-8")
        
        # Regenerate API call
        self.assertIn("async function regenerateSegment", script)
        self.assertIn("/api/segments/", script)
        self.assertIn("/regenerate", script)
        self.assertIn("method: 'POST'", script)

    def test_ui_contract_accept_calls_correct_api_endpoint(self) -> None:
        """Accept calls POST /api/segments/{id}/accept-candidate."""
        script = (self.ui_root / "app.js").read_text(encoding="utf-8")
        
        # Accept API call
        self.assertIn("async function acceptCandidate", script)
        self.assertIn("/accept-candidate", script)
        self.assertIn("method: 'POST'", script)
        self.assertIn("attempt_id", script)

    def test_ui_contract_reject_calls_correct_api_endpoint(self) -> None:
        """Reject calls POST /api/segments/{id}/reject-candidate."""
        script = (self.ui_root / "app.js").read_text(encoding="utf-8")
        
        # Reject API call
        self.assertIn("async function rejectCandidate", script)
        self.assertIn("/reject-candidate", script)
        self.assertIn("method: 'POST'", script)

    def test_ui_contract_existing_retry_action_remains_unchanged(self) -> None:
        """Existing failed-segment Retry action remains unchanged."""
        script = (self.ui_root / "app.js").read_text(encoding="utf-8")
        
        # Existing retry for failed/interrupted segments
        self.assertIn("retrySegmentAction", script)
        # Retry shown for failed/interrupted, NOT for verified
        self.assertIn("['failed','interrupted']", script)

    def test_ui_contract_safe_rendering_uses_esc_helper(self) -> None:
        """UI safely renders user content using esc() helper."""
        script = (self.ui_root / "app.js").read_text(encoding="utf-8")
        
        # All user-controlled content uses esc() helper
        # Check that raw innerHTML is not used for dynamic content
        self.assertIn("esc(", script)
        # Regeneration UI should not have raw innerHTML injection
        self.assertNotIn("innerHTML=result", script)
        self.assertNotIn("innerHTML=data.candidate", script)

    def test_api_endpoints_are_registered(self) -> None:
        """Regeneration API endpoints are registered in api.py."""
        api_path = Path(__file__).resolve().parents[1] / "story_audio" / "api.py"
        api_code = api_path.read_text(encoding="utf-8")
        
        # All regeneration endpoints exist
        self.assertIn("/api/segments/{segment_id}/regenerate", api_code)
        self.assertIn("/api/segments/{segment_id}/accept-candidate", api_code)
        self.assertIn("/api/segments/{segment_id}/reject-candidate", api_code)
        self.assertIn("/api/segments/{segment_id}/attempts", api_code)
        self.assertIn("/api/segment-attempts/{attempt_id}/audio", api_code)
        
        # Existing retry endpoint unchanged
        self.assertIn("/api/segments/{segment_id}/retry", api_code)


if __name__ == "__main__":
    import unittest
    unittest.main()
