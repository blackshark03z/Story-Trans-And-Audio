from __future__ import annotations

import json
import subprocess
import threading
import time
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]


class ScopeFixtureHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        return

    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _chapters(self, book_id: int, query: str) -> list[dict]:
        if book_id == 2:
            return [
                {
                    "id": 2001,
                    "chapter_number": 1,
                    "title": "Pilot Chapter",
                    "char_count": 120,
                    "audio_status": "not_created",
                }
            ]
        rows = [
            {
                "id": 1000 + number,
                "chapter_number": number,
                "title": f"Chapter {number}",
                "char_count": 100 + number,
                "audio_status": "completed" if number in {372, 373} else "not_created",
            }
            for number in range(350, 395)
        ]
        if query:
            rows = [
                row
                for row in rows
                if query.lower() in f"{row['chapter_number']} {row['title']}".lower()
            ]
        return rows

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/":
            return self._serve_file(ROOT / "ui" / "index.html", "text/html; charset=utf-8")
        if parsed.path.startswith("/assets/"):
            return self._serve_file(ROOT / "ui" / parsed.path.removeprefix("/assets/"))
        if parsed.path == "/api/config":
            return self._json(
                {
                    "gemini_configured": False,
                    "tts_status": "fixture",
                    "available_epubs": [],
                }
            )
        if parsed.path == "/api/runtime":
            return self._json(
                {
                    "data_root": "fixture",
                    "db_path": "fixture/app.db",
                    "schema_version": 15,
                    "latest_schema_version": 15,
                    "is_canonical_live_data_root": False,
                    "is_canonical_live_db": False,
                    "worker_available": False,
                    "supervised_restart_available": False,
                }
            )
        if parsed.path == "/api/production/prepare-readiness":
            return self._json(
                {
                    "runtime_mode": "ISOLATED",
                    "schema_version": 15,
                    "required_schema_version": 15,
                    "status": "DISABLED",
                    "kill_switch_active": True,
                    "authentication_state": "AUTH_NOT_CONFIGURED",
                    "feature_available": False,
                    "mutation_enabled": False,
                    "mutation_authorized": False,
                    "operator_window_open": False,
                    "start_render_available": False,
                }
            )
        if parsed.path == "/api/books":
            return self._json(
                [
                    {
                        "id": 1,
                        "title": "Fixture Book",
                        "author": "Fixture Author",
                        "chapter_count": 394,
                        "audio_chapters": 2,
                    },
                    {
                        "id": 2,
                        "title": "Other Book",
                        "author": "Other Author",
                        "chapter_count": 1,
                        "audio_chapters": 0,
                    },
                ]
            )
        if parsed.path == "/api/jobs":
            return self._json([])
        if parsed.path == "/api/audio-library":
            return self._json({"items": []})
        if parsed.path.startswith("/api/books/") and parsed.path.endswith("/chapters"):
            book_id = int(parsed.path.split("/")[3])
            search = query.get("query", [""])[0]
            if search == "__fail__":
                return self._json({"detail": "fixture chapter failure"}, 500)
            if search == "__slow__":
                time.sleep(0.3)
            rows = self._chapters(book_id, search)
            offset = int(query.get("offset", ["0"])[0])
            limit = int(query.get("limit", ["40"])[0])
            return self._json({"total": len(rows), "items": rows[offset : offset + limit]})
        if parsed.path == "/api/production/range-readiness":
            book_id = int(query["book_id"][0])
            start = int(query["from_chapter"][0])
            end = int(query["to_chapter"][0])
            rows = [
                row
                for row in self._chapters(book_id, "")
                if start <= row["chapter_number"] <= end
            ]
            if len(rows) != end - start + 1:
                return self._json({"detail": "Selected range is missing chapters."}, 404)
            chapters = [
                {
                    "chapter_id": row["id"],
                    "chapter_number": row["chapter_number"],
                    "chapter_title": row["title"],
                    "state": "COMPLETE",
                    "next_action": "VIEW_OUTPUTS_OR_SELECT_NEXT_SCOPE",
                    "requires_operator_action": False,
                    "human_qa_status": "accepted",
                    "blockers": [],
                    "voice_issues": [],
                }
                for row in rows
            ]
            return self._json(
                {
                    "scope": {
                        "book_id": book_id,
                        "book_title": "Fixture Book" if book_id == 1 else "Other Book",
                        "from_chapter": start,
                        "to_chapter": end,
                        "chapter_count": len(chapters),
                    },
                    "summary": {
                        "total": len(chapters),
                        "complete": len(chapters),
                        "ready_to_prepare": 0,
                        "needs_attention": 0,
                        "rendering_or_paused": 0,
                        "prepared": 0,
                        "rendered_not_qa": 0,
                        "state_counts": {"COMPLETE": len(chapters)},
                    },
                    "chapters": chapters,
                    "exceptions": [],
                }
            )
        if parsed.path == "/api/production/task-projection":
            book_id = int(query["book_id"][0])
            start = int(query["from_chapter"][0])
            end = int(query["to_chapter"][0])
            if book_id == 91:
                queue = [
                    {
                        "chapter_id": 9101,
                        "chapter_number": 401,
                        "title": "Chương kiểm thử",
                        "status": "current",
                        "state": "SPEAKER_EXCEPTIONS",
                        "user_stage": 2,
                        "task_type": "RESOLVE_SPEAKER",
                        "task_key": "chapter:9101:RESOLVE_SPEAKER",
                    }
                ]
                return self._json(
                    {
                        "range_identity": "book:91:401-401",
                        "task_scope": "chapter",
                        "task_type": "RESOLVE_SPEAKER",
                        "task_key": "chapter:9101:RESOLVE_SPEAKER",
                        "user_stage": 2,
                        "title": "Xác nhận người nói",
                        "summary": "Chương 401 còn một dòng chưa xác nhận.",
                        "task_title": "Xác nhận người nói",
                        "task_summary": "Chương 401 còn một dòng chưa xác nhận.",
                        "affected_chapter": {
                            "id": 9101,
                            "number": 401,
                            "title": "Chương kiểm thử",
                        },
                        "chapter_queue": queue,
                        "queue": queue,
                        "primary_action": {
                            "key": "RESOLVE_SPEAKER",
                            "label": "Xác nhận và tiếp tục",
                            "target": "speakers",
                        },
                        "secondary_actions": [],
                        "secondary_links": [],
                        "blocker": None,
                        "range_readiness": {
                            "scope": {
                                "book_id": 91,
                                "from_chapter": 401,
                                "to_chapter": 401,
                            },
                            "summary": {},
                        },
                        "next_task_hint": "Duyệt Speaker Draft.",
                        "next_task_after_success": "Duyệt Speaker Draft.",
                        "technical_details": [],
                        "phases": [],
                        "conceptual_state": "SPEAKER_EXCEPTIONS",
                        "current_stage_key": "speakers",
                    }
                )
            rows = [
                row
                for row in self._chapters(book_id, "")
                if start <= row["chapter_number"] <= end
            ]
            queue = [
                {
                    "chapter_id": row["id"],
                    "chapter_number": row["chapter_number"],
                    "title": row["title"],
                    "status": "complete",
                    "state": "COMPLETE",
                    "user_stage": 5,
                    "task_type": None,
                    "task_key": f"chapter:{row['id']}:READY",
                }
                for row in rows
            ]
            return self._json(
                {
                    "range_identity": f"book:{book_id}:{start}-{end}",
                    "task_scope": "range",
                    "task_type": "COMPLETE",
                    "task_key": f"range:{book_id}:{start}-{end}:COMPLETE",
                    "user_stage": 5,
                    "title": "Phạm vi đã hoàn tất",
                    "summary": "Tất cả chương trong phạm vi đã hoàn tất.",
                    "task_title": "Phạm vi đã hoàn tất",
                    "task_summary": "Tất cả chương trong phạm vi đã hoàn tất.",
                    "affected_chapter": None,
                    "chapter_queue": queue,
                    "queue": queue,
                    "primary_action": None,
                    "secondary_actions": [],
                    "secondary_links": [],
                    "blocker": None,
                    "range_readiness": {"scope": {"book_id": book_id, "from_chapter": start, "to_chapter": end}, "summary": {}},
                    "next_task_hint": "Chọn phạm vi tiếp theo.",
                    "next_task_after_success": "Chọn phạm vi tiếp theo.",
                    "technical_details": [],
                    "phases": [],
                    "conceptual_state": "COMPLETE",
                    "current_stage_key": "qa",
                }
            )
        return self._json({"detail": f"Unhandled fixture route: {parsed.path}"}, 404)

    def _serve_file(self, path: Path, content_type: str | None = None) -> None:
        if not path.is_file():
            return self._json({"detail": "Not found"}, 404)
        body = path.read_bytes()
        if content_type is None:
            content_type = {
                ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".html": "text/html; charset=utf-8",
            }.get(path.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ProductionScopeBrowserTests(unittest.TestCase):
    def test_real_browser_completes_scope_interaction(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ScopeFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [
                    "node",
                    "scripts/browser_scope_smoke.mjs",
                    f"http://127.0.0.1:{server.server_port}",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=45,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["ok"])
        self.assertEqual(evidence["bookCount"], 2)
        self.assertEqual(evidence["firstPage"], "1-6 / 45")
        self.assertEqual(evidence["confirmedCount"], 2)
        self.assertTrue(evidence["oneChapterReady"])
        self.assertTrue(evidence["rowSelectionWorks"])
        self.assertTrue(evidence["keyboardWorkflow"])
        self.assertEqual(evidence["quickRanges"], ["372-372", "372-376", "372-381"])
        self.assertTrue(evidence["apiErrorVisible"])
        self.assertTrue(evidence["technicalErrorAvailable"])
        self.assertTrue(evidence["staleResponseIgnored"])
        self.assertTrue(evidence["recoveredErrorHidden"])
        self.assertTrue(evidence["skipCompletedRestored"])
        self.assertTrue(evidence["primaryLabelsAreHuman"])
        self.assertTrue(evidence["layout1366"]["ctaVisible"])
        self.assertFalse(evidence["layout1366"]["horizontal"])
        self.assertEqual(evidence["layout1366"]["nestedScrolling"], [])
        self.assertTrue(evidence["layout1920"]["ctaVisible"])
        self.assertFalse(evidence["layout1920"]["horizontal"])
        self.assertTrue(evidence["browserOpenLayout"]["ctaVisible"])
        self.assertFalse(evidence["browserOpenLayout"]["horizontal"])
        self.assertEqual(evidence["interactionCounts"], {"oneChapter": 3, "range": 3})
        self.assertEqual(evidence["final"]["state"], "NO_SCOPE")
        self.assertEqual(evidence["final"]["primaryAction"], "Chọn chương")
        self.assertEqual(evidence["final"]["route"], "#/production")


if __name__ == "__main__":
    unittest.main()
