from __future__ import annotations

import json
import subprocess
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from tests.test_production_scope_browser import ROOT, ScopeFixtureHandler


VOICE_ITEMS = [
    {"assignment_key": "narrator", "display_name": "Narrator Default", "source_kind": "preset", "active": True, "usable": True, "selectable": True},
    {"assignment_key": "male", "display_name": "Male Default", "source_kind": "preset", "active": True, "usable": True, "selectable": True},
    {"assignment_key": "female", "display_name": "Female Range", "source_kind": "preset", "active": True, "usable": True, "selectable": True},
    {"assignment_key": "character-alt", "display_name": "Character Alt", "source_kind": "preset", "active": True, "usable": True, "selectable": True},
    {"assignment_key": "unknown-alt", "display_name": "Unknown Alt", "source_kind": "preset", "active": True, "usable": True, "selectable": True},
    {"assignment_key": "legacy", "display_name": "Legacy Unavailable", "source_kind": "preset", "active": False, "usable": False, "selectable": False},
]


def _voice(voice_id: str | None) -> dict | None:
    if not voice_id:
        return None
    item = next((row for row in VOICE_ITEMS if row["assignment_key"] == voice_id), None)
    return {
        "id": voice_id,
        "display_name": item["display_name"] if item else voice_id,
        "available": bool(item and item.get("selectable")),
        "source_kind": item.get("source_kind") if item else "preset",
        "preview_url": f"/preview/{voice_id}.mp3",
    }


class VoiceOverrideFixtureHandler(ScopeFixtureHandler):
    overrides: dict[tuple[int, str], str] = {}
    book_defaults: dict[str, str] = {}
    command_responses: dict[str, dict] = {}
    commands: list[dict] = []
    mutation_count = 0

    @classmethod
    def reset(cls) -> None:
        cls.overrides = {}
        cls.book_defaults = {}
        cls.command_responses = {}
        cls.commands = []
        cls.mutation_count = 0

    @classmethod
    def _base_voice(cls, speaker_key: str) -> str:
        if speaker_key in cls.book_defaults:
            return cls.book_defaults[speaker_key]
        if speaker_key == "narrator":
            return "narrator"
        if speaker_key == "unknown":
            return "narrator"
        return "male"

    @classmethod
    def _effective_voice(cls, chapter_number: int, speaker_key: str) -> str:
        return cls.overrides.get((chapter_number, speaker_key)) or cls._base_voice(speaker_key)

    @classmethod
    def _row(cls, speaker_key: str, display_name: str, role: str, chapter_numbers: list[int], line_count: int) -> dict:
        effective_by_chapter = {
            chapter: cls._effective_voice(chapter, speaker_key)
            for chapter in chapter_numbers
        }
        voices = sorted(set(effective_by_chapter.values()))
        effective_voice_id = voices[0] if len(voices) == 1 else effective_by_chapter[chapter_numbers[0]]
        has_override = any((chapter, speaker_key) in cls.overrides for chapter in chapter_numbers)
        base_voice_id = cls._base_voice(speaker_key)
        return {
            "speaker_key": speaker_key,
            "character_id": 25 if speaker_key == "character:25" else None,
            "display_name": display_name,
            "aliases": [],
            "role": role,
            "role_label": role,
            "gender": "unknown",
            "chapter_numbers": chapter_numbers,
            "chapter_range_label": f"{chapter_numbers[0]}-{chapter_numbers[-1]}" if len(chapter_numbers) > 1 else str(chapter_numbers[0]),
            "line_count": line_count,
            "first_appearance": chapter_numbers[0],
            "current_book_default_voice": _voice(base_voice_id),
            "saved_voice": _voice(cls.book_defaults.get(speaker_key)),
            "base_resolved_voice": _voice(base_voice_id),
            "range_override_voice": _voice(effective_voice_id) if has_override and len(chapter_numbers) > 1 else None,
            "chapter_override_voice": _voice(effective_voice_id) if has_override and len(chapter_numbers) == 1 else None,
            "conflict_voices": [{"voice": _voice(voice)} for voice in voices] if len(voices) > 1 else [],
            "chapter_voice_details": [
                {
                    "chapter_number": chapter,
                    "inherited_voice": _voice(base_voice_id),
                    "chapter_override_voice": _voice(cls.overrides.get((chapter, speaker_key))),
                    "effective_voice": _voice(voice_id),
                    "assignment_source": "chapter override" if (chapter, speaker_key) in cls.overrides else "book default",
                }
                for chapter, voice_id in effective_by_chapter.items()
            ],
            "effective_voice": _voice(effective_voice_id),
            "effective_voice_display_name": _voice(effective_voice_id)["display_name"],
            "voice_available": effective_voice_id != "legacy",
            "assignment_source": "range override" if has_override and len(chapter_numbers) > 1 else "chapter override" if has_override else "book default",
            "status": "READY",
            "status_reason": "",
            "last_review": {"reviewed": False, "reviewed_at": None},
            "actions": {
                "can_save_book_default": True,
                "can_create_range_or_chapter_override": True,
                "can_remove_override": has_override,
                "can_preview_effective_voice": True,
            },
        }

    @classmethod
    def registry(cls, book_id: int, start: int, end: int) -> dict:
        chapters = list(range(start, end + 1))
        character_chapters = [chapter for chapter in chapters if 2 <= chapter <= 4] or chapters[:1]
        rows = [
            cls._row("narrator", "Narrator", "narrator", chapters, len(chapters) * 5),
            cls._row("character:25", "Gate Commander", "character", character_chapters, len(character_chapters) * 2),
            cls._row("unknown", "Unknown speaker", "unknown", chapters[:1], 1),
        ]
        return {
            "schema": "story-audio-book-voice-registry/v1",
            "book": {"id": book_id, "title": "Fixture Book", "chapter_count": 394},
            "range": {
                "from_chapter": start,
                "to_chapter": end,
                "chapter_count": len(chapters),
                "chapter_ids": [1000 + chapter for chapter in chapters],
                "focused_chapter_id": None,
            },
            "persistence": {
                "migration_required": False,
                "uses_existing_model": True,
                "model": "book_voice_profiles + characters.voice_override_id + casting_plan_revisions",
                "book_profile_config_version": 1,
            },
            "voice_catalog": {"selectable_count": 5, "narrator_voice_id": "narrator"},
            "rows": rows,
            "summary": {
                "total_rows": len(rows),
                "blocking_rows": 0,
                "status_counts": {"READY": len(rows)},
                "ready": len(rows),
            },
        }

    @staticmethod
    def projection(book_id: int, start: int, end: int) -> dict:
        queue = [
            {
                "chapter_id": 1000 + chapter,
                "chapter_number": chapter,
                "title": f"Chapter {chapter}",
                "status": "complete",
                "state": "COMPLETE",
                "user_stage": 6,
                "task_type": None,
                "task_key": f"chapter:{1000 + chapter}:COMPLETE",
            }
            for chapter in range(start, end + 1)
        ]
        task = {
            "task_scope": "range",
            "task_type": "COMPLETE",
            "task_key": f"range:{book_id}:{start}-{end}:COMPLETE",
            "user_stage": 6,
            "title": "Complete",
            "summary": "Fixture range complete.",
            "affected_chapter": None,
            "primary_action": None,
            "blocker": None,
            "next_task_hint": "Select another range.",
            "technical_details": [],
            "current_stage_key": "done",
            "speaker": None,
            "casting": None,
            "range_prepare": None,
            "render": None,
            "qa": None,
            "repair": None,
        }
        return {
            "range_identity": {"book_id": book_id, "from_chapter": start, "to_chapter": end},
            "task_scope": "range",
            "task_type": "COMPLETE",
            "task_key": task["task_key"],
            "user_stage": 6,
            "title": "Complete",
            "summary": "Fixture range complete.",
            "affected_chapter": None,
            "chapter_queue": queue,
            "queue": queue,
            "primary_action": None,
            "secondary_actions": [],
            "secondary_links": [],
            "blocker": None,
            "range_readiness": {"scope": {"book_id": book_id, "from_chapter": start, "to_chapter": end}, "summary": {}},
            "next_task_hint": "Select another range.",
            "next_task_after_success": "Select another range.",
            "technical_details": [],
            "phases": [],
            "conceptual_state": "COMPLETE",
            "current_stage_key": "done",
            "canonical_task": task,
        }

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/voice-catalog":
            return self._json({"schema": "story-audio-effective-voice-catalog/v1", "items": VOICE_ITEMS, "selectable_count": 5})
        if parsed.path == "/api/production/book-voice-registry":
            return self._json(
                self.registry(
                    int(query["book_id"][0]),
                    int(query["from_chapter"][0]),
                    int(query["to_chapter"][0]),
                )
            )
        if parsed.path == "/api/production/preflight":
            return self._json(
                {
                    "schema": "story-audio-production-preflight/v1",
                    "range": {
                        "book_id": int(query["book_id"][0]),
                        "from_chapter": int(query["from_chapter"][0]),
                        "to_chapter": int(query["to_chapter"][0]),
                        "selected_chapter_count": int(query["to_chapter"][0]) - int(query["from_chapter"][0]) + 1,
                    },
                    "data_readiness": {"ready": True, "ordered_blockers": []},
                    "effective_voice_map": [],
                    "execution_readiness": {},
                    "execution_preview": {"next_action": {"key": "NO_ACTION", "label": "No action"}, "voice_count": 0, "chapter_count": 0, "estimated_segment_count": 0},
                    "technical_details": {},
                }
            )
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/production/commands":
            return self._json({"detail": f"Unhandled fixture route: {parsed.path}"}, 404)
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        command_type = str(body.get("command_type") or "")
        idempotency_key = str(body.get("idempotency_key") or "")
        scope = body.get("scope") or {}
        payload = body.get("payload") or {}
        range_scope = scope.get("range") or {}
        book_id = int(range_scope.get("book_id") or payload.get("book_id") or 1)
        start = int(range_scope.get("from_chapter") or 1)
        end = int(range_scope.get("to_chapter") or start)
        speaker_key = str(payload.get("speaker_key") or "")
        voice_id = payload.get("voice_id")
        if command_type in {"PREPARE", "START_RENDER"}:
            return self._json({"detail": "render command forbidden in voice override fixture"}, 409)
        if idempotency_key in self.command_responses:
            self.commands.append(body)
            return self._json(self.command_responses[idempotency_key])
        if voice_id == "legacy":
            return self._json({"detail": "Selected voice is not available"}, 422)

        time.sleep(0.15)
        applied = []
        if command_type == "SET_BOOK_VOICE_DEFAULT":
            self.book_defaults[speaker_key] = str(voice_id)
            type(self).mutation_count += 1
            applied.append({"speaker_key": speaker_key, "voice_id": voice_id, "scope": "book"})
        elif command_type in {"SET_CHAPTER_VOICE_OVERRIDE", "SET_RANGE_VOICE_OVERRIDE"}:
            for chapter in range(start, end + 1):
                self.overrides[(chapter, speaker_key)] = str(voice_id)
                applied.append({"chapter_number": chapter, "speaker_key": speaker_key, "voice_id": voice_id})
            type(self).mutation_count += len(applied)
        elif command_type in {"CLEAR_CHAPTER_VOICE_OVERRIDE", "CLEAR_RANGE_VOICE_OVERRIDE"}:
            for chapter in range(start, end + 1):
                self.overrides.pop((chapter, speaker_key), None)
                applied.append({"chapter_number": chapter, "speaker_key": speaker_key, "operation": "clear"})
            type(self).mutation_count += len(applied)
        else:
            return self._json({"detail": f"Unsupported command {command_type}"}, 400)

        response = {
            "schema": "story-audio-production-command/v1",
            "command_id": f"fixture-{idempotency_key}",
            "command_type": command_type,
            "idempotency_key": idempotency_key,
            "scope": scope,
            "outcome": "APPLIED",
            "submitted_count": len(applied),
            "applied_count": len(applied),
            "failed_count": 0,
            "applied_items": applied,
            "failed_items": [],
            "operator_message": "Voice change saved.",
            "resulting_task_projection": self.projection(book_id, start, end),
            "resulting_preflight": None,
            "asynchronous_reference": None,
            "state_tokens": {"task_projection": "fixture", "preflight": None},
        }
        self.command_responses[idempotency_key] = response
        self.commands.append(body)
        return self._json(response)


class VoiceOverrideBrowserTests(unittest.TestCase):
    def test_assignment_voice_override_journey_in_real_browser(self) -> None:
        VoiceOverrideFixtureHandler.reset()
        server = ThreadingHTTPServer(("127.0.0.1", 0), VoiceOverrideFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [
                    "node",
                    "scripts/browser_voice_override_smoke.mjs",
                    f"http://127.0.0.1:{server.server_port}",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["ok"])
        self.assertTrue(evidence["exactUrlNotReadOnly"])
        self.assertTrue(evidence["oneChapterNarrator"])
        self.assertTrue(evidence["rangeNarrator"])
        self.assertTrue(evidence["characterRange"])
        self.assertTrue(evidence["clearRestoresDefault"])
        self.assertTrue(evidence["mixedVisible"])
        self.assertTrue(evidence["unavailableBlocked"])
        self.assertEqual(evidence["renderCommands"], [])
        self.assertEqual(VoiceOverrideFixtureHandler.mutation_count, evidence["mutationCount"])


if __name__ == "__main__":
    unittest.main()
