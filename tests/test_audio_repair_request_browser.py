from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from tests.test_production_scope_browser import ROOT, ScopeFixtureHandler


class AudioRepairRequestFixtureHandler(ScopeFixtureHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/audio-library":
            return self._json(
                {
                    "items": [
                        {
                            "artifact_id": 5001,
                            "chapter_id": 102,
                            "book_id": 1,
                            "book_title": "Quang Âm Chi Ngoại",
                            "chapter_number": 2,
                            "chapter_title": "Chương 2",
                            "job_id": 77,
                            "sha256": "fixture-current-audio-sha",
                            "duration_ms": 369000,
                            "size_bytes": 8_000_000,
                            "human_qa_status": "pending",
                            "file_url": "/api/artifacts/5001/file",
                            "created_at": "2026-09-12T15:51:00+07:00",
                        }
                    ]
                }
            )
        if path == "/api/audio-library/5001/automated-qa":
            points = [
                (1, 94000, "loudness", "Âm lượng không đều", "Mức âm khác đáng kể so với các đoạn cùng giọng."),
                (2, 138000, "silence", "Khoảng nghỉ dài", "Khoảng nghỉ cuối segment dài 529 ms."),
                (3, 152000, "silence", "Khoảng nghỉ dài", "Khoảng nghỉ cuối segment dài 488 ms."),
                (4, 169000, "silence", "Mở đầu chậm", "Segment bắt đầu bằng 1257 ms im lặng."),
                (5, 198000, "pacing", "Nhịp đọc khác biệt", "Nhịp đoạn này khác đáng kể."),
                (6, 211000, "silence", "Khoảng lặng bất thường", "Có khoảng lặng bên trong dài 1735 ms."),
            ]
            return self._json(
                {
                    "state": "attention",
                    "artifact": {"id": 5001, "sha256": "fixture-current-audio-sha"},
                    "summary": {"segment_count": 53, "analyzed_segment_wavs": 53, "risk_count": 18},
                    "assessment": {"technical_score": 64, "coverage_percent": 100, "confidence": "high"},
                    "shortlist": [
                        {
                            "segment_id": segment_id,
                            "sequence": segment_id,
                            "timestamp_ms": timestamp_ms,
                            "risk_kind": risk_kind,
                            "label": label,
                            "reason": reason,
                            "segment_audio_sha256": f"{segment_id:064x}",
                            "repair": {
                                "supported": segment_id <= 4,
                                "kind": (
                                    "normalize_loudness"
                                    if segment_id == 1
                                    else "trim_leading_silence"
                                    if segment_id == 4
                                    else "trim_trailing_silence"
                                    if segment_id <= 4
                                    else None
                                ),
                            },
                        }
                        for segment_id, timestamp_ms, risk_kind, label, reason in points
                    ],
                    "human_qa": "required",
                    "mutation_performed": False,
                }
            )
        if path == "/api/audio-library/5001/machine-repair-candidate":
            return self._json({"candidate": None})
        return super().do_GET()


class AudioRepairRequestBrowserTests(unittest.TestCase):
    def test_one_aggregate_repair_path_replaces_per_finding_actions(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), AudioRepairRequestFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        screenshots_exist = False
        try:
            with tempfile.TemporaryDirectory() as evidence_dir:
                result = subprocess.run(
                    [
                        "node",
                        "scripts/browser_audio_repair_request_acceptance.mjs",
                        f"http://127.0.0.1:{server.server_port}",
                        evidence_dir,
                    ],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=60,
                )
                if result.returncode == 0:
                    rendered = json.loads(result.stdout)
                    screenshots_exist = all(
                        Path(rendered["screenshots"][name]).is_file()
                        for name in ("desktop", "narrow", "unifiedDesktop", "unifiedNarrow")
                    )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["ok"])
        self.assertEqual(evidence["desktop"]["choiceCount"], 4)
        self.assertEqual(evidence["desktop"]["selectedCount"], 4)
        self.assertEqual(evidence["desktop"]["perFindingCreateCount"], 0)
        self.assertEqual(evidence["afterDeselect"]["selectedCount"], 3)
        self.assertIn("3 điểm", evidence["afterDeselect"]["cta"])
        self.assertTrue(evidence["review"]["detailsOpen"])
        self.assertEqual(evidence["review"]["noteFindingCount"], 3)
        self.assertEqual(evidence["review"]["boundMarkerCount"], 3)
        self.assertEqual(evidence["review"]["automaticMarkerCount"], 3)
        self.assertTrue(evidence["review"]["allMarkersHaveSegmentSha"])
        self.assertTrue(evidence["review"]["manualRepeatedPreserved"])
        self.assertEqual(evidence["review"]["manualSpeedPreserved"], "1.5")
        self.assertFalse(evidence["desktop"]["horizontal"])
        self.assertFalse(evidence["narrow"]["horizontal"])
        self.assertEqual(evidence["review"]["mutations"], [])
        self.assertEqual(evidence["unifiedDesktop"]["route"], "production")
        self.assertEqual(evidence["unifiedDesktop"]["heading"], "Kiểm tra toàn bộ bản sửa")
        self.assertEqual(evidence["unifiedDesktop"]["primaryIds"], ["repairConfirmUnified"])
        self.assertEqual(evidence["unifiedDesktop"]["legacyControls"], 0)
        self.assertEqual(evidence["unifiedDesktop"]["markerCount"], 3)
        self.assertEqual(evidence["unifiedDesktop"]["stepCount"], 4)
        self.assertFalse(evidence["unifiedDesktop"]["horizontal"])
        self.assertFalse(evidence["unifiedNarrow"]["horizontal"])
        self.assertTrue(evidence["unifiedNarrow"]["primaryVisible"])
        self.assertEqual(
            evidence["unifiedCommit"]["calls"],
            ["CONFIRM_REPAIR_PLAN", "APPLY_REPAIR_PLAN", "CONFIRM_REPAIR_DRAFT"],
        )
        self.assertEqual(evidence["unifiedCommit"]["reviewedHeading"], "Đã xác nhận toàn bộ bản sửa")
        self.assertTrue(evidence["unifiedCommit"]["prepareVisible"])
        self.assertFalse(evidence["unifiedCommit"]["confirmVisible"])
        self.assertTrue(screenshots_exist)


if __name__ == "__main__":
    unittest.main()
