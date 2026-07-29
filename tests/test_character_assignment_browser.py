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
    {"assignment_key": "narrator", "display_name": "Narrator Voice", "source_kind": "preset", "active": True, "usable": True, "selectable": True},
    {"assignment_key": "male", "display_name": "Male Default", "source_kind": "preset", "active": True, "usable": True, "selectable": True},
    {"assignment_key": "female", "display_name": "Female Default", "source_kind": "preset", "active": True, "usable": True, "selectable": True},
    {"assignment_key": "commander", "display_name": "Commander Voice", "source_kind": "preset", "active": True, "usable": True, "selectable": True},
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


class CharacterAssignmentFixtureHandler(ScopeFixtureHandler):
    unresolved_targets = {
        "unresolved-dialogue:1002:u0002-deadbeef0000": {
            "chapter_id": 1002,
            "chapter_number": 2,
            "utterance_id": "u0002-deadbeef0000",
            "sequence": 2,
            "text": "- Hold the gate and verify every pass.",
        },
        "unresolved-dialogue:1003:u0002-feedface0000": {
            "chapter_id": 1003,
            "chapter_number": 3,
            "utterance_id": "u0002-feedface0000",
            "sequence": 2,
            "text": "- Break the red formation now.",
        },
    }
    characters: dict[int, dict] = {}
    mapped: dict[str, int] = {}
    overrides: dict[tuple[int, str], str] = {}
    command_responses: dict[str, dict] = {}
    commands: list[dict] = []
    next_character_id = 31

    @classmethod
    def reset(cls) -> None:
        cls.characters = {
            25: {
                "id": 25,
                "display_name": "Existing Commander",
                "canonical_name": "Existing Commander",
                "role": "minor",
                "gender": "male",
                "aliases": ["captain"],
                "active": True,
            }
        }
        cls.mapped = {}
        cls.overrides = {}
        cls.command_responses = {}
        cls.commands = []
        cls.next_character_id = 31

    @classmethod
    def _effective_voice(cls, speaker_key: str, chapter_number: int) -> str:
        if (chapter_number, speaker_key) in cls.overrides:
            return cls.overrides[(chapter_number, speaker_key)]
        if speaker_key == "narrator":
            return "narrator"
        return "male"

    @classmethod
    def _character_row(
        cls,
        *,
        character_id: int,
        chapters: list[int],
        line_count: int,
    ) -> dict:
        character = cls.characters[character_id]
        speaker_key = f"character:{character_id}"
        voices = {
            chapter: cls._effective_voice(speaker_key, chapter)
            for chapter in chapters
        }
        voice_ids = sorted(set(voices.values()))
        effective_id = voice_ids[0] if len(voice_ids) == 1 else voices[chapters[0]]
        has_override = any((chapter, speaker_key) in cls.overrides for chapter in chapters)
        return {
            "speaker_key": speaker_key,
            "character_id": character_id,
            "display_name": character["display_name"],
            "aliases": list(character.get("aliases") or []),
            "role": "character",
            "role_label": "character",
            "gender": character.get("gender") or "unknown",
            "chapter_numbers": chapters,
            "chapter_range_label": f"{chapters[0]}-{chapters[-1]}" if len(chapters) > 1 else str(chapters[0]),
            "line_count": line_count,
            "first_appearance": chapters[0],
            "current_book_default_voice": _voice("male"),
            "saved_voice": _voice("male"),
            "base_resolved_voice": _voice("male"),
            "range_override_voice": _voice(effective_id) if has_override else None,
            "chapter_override_voice": None,
            "conflict_voices": [],
            "chapter_voice_details": [
                {
                    "chapter_number": chapter,
                    "inherited_voice": _voice("male"),
                    "chapter_override_voice": _voice(cls.overrides.get((chapter, speaker_key))),
                    "effective_voice": _voice(voice_id),
                    "assignment_source": "range override" if (chapter, speaker_key) in cls.overrides else "book default",
                }
                for chapter, voice_id in voices.items()
            ],
            "effective_voice": _voice(effective_id),
            "effective_voice_display_name": _voice(effective_id)["display_name"],
            "voice_available": True,
            "assignment_source": "range override" if has_override else "book default",
            "status": "READY",
            "status_reason": "",
            "last_review": {"reviewed": True, "reviewed_at": "fixture"},
            "sample_lines": [],
            "target_utterances": [],
            "provenance": [],
            "actions": {
                "can_save_book_default": True,
                "can_create_range_or_chapter_override": True,
                "can_remove_override": has_override,
                "can_preview_effective_voice": True,
                "future_render_only": True,
            },
        }

    @classmethod
    def _unresolved_row(cls, speaker_key: str, target: dict) -> dict:
        payload = {
            "chapter_id": target["chapter_id"],
            "chapter_number": target["chapter_number"],
            "utterance_id": target["utterance_id"],
            "sequence": target["sequence"],
            "text": target["text"],
            "role": "narrator",
            "character_id": None,
        }
        return {
            "speaker_key": speaker_key,
            "character_id": None,
            "display_name": "Chua xac dinh nhan vat",
            "aliases": [],
            "role": "unresolved_dialogue",
            "role_label": "Chua xac dinh nhan vat / nguoi noi",
            "gender": "unknown",
            "chapter_numbers": [target["chapter_number"]],
            "chapter_range_label": str(target["chapter_number"]),
            "line_count": 1,
            "first_appearance": target["chapter_number"],
            "current_book_default_voice": None,
            "saved_voice": None,
            "base_resolved_voice": None,
            "range_override_voice": None,
            "chapter_override_voice": None,
            "conflict_voices": [],
            "chapter_voice_details": [],
            "effective_voice": None,
            "effective_voice_display_name": None,
            "voice_available": False,
            "assignment_source": "unresolved dialogue",
            "status": "UNRESOLVED_DIALOGUE",
            "status_reason": "Needs character decision",
            "last_review": {"reviewed": False, "reviewed_at": None},
            "sample_lines": [payload],
            "target_utterances": [payload],
            "provenance": [{"source": "fixture", "chapter_number": target["chapter_number"]}],
            "actions": {
                "can_save_book_default": False,
                "can_create_range_or_chapter_override": False,
                "can_remove_override": False,
                "can_preview_effective_voice": False,
                "can_map_to_character": True,
                "can_create_character": True,
                "future_render_only": True,
            },
        }

    @classmethod
    def _narrator_row(cls, chapters: list[int]) -> dict:
        return {
            "speaker_key": "narrator",
            "character_id": None,
            "display_name": "Narrator",
            "aliases": [],
            "role": "narrator",
            "role_label": "narrator",
            "gender": "unknown",
            "chapter_numbers": chapters,
            "chapter_range_label": f"{chapters[0]}-{chapters[-1]}",
            "line_count": len(chapters) * 4,
            "first_appearance": chapters[0],
            "current_book_default_voice": _voice("narrator"),
            "saved_voice": _voice("narrator"),
            "base_resolved_voice": _voice("narrator"),
            "range_override_voice": None,
            "chapter_override_voice": None,
            "conflict_voices": [],
            "chapter_voice_details": [],
            "effective_voice": _voice("narrator"),
            "effective_voice_display_name": "Narrator Voice",
            "voice_available": True,
            "assignment_source": "book default",
            "status": "READY",
            "status_reason": "",
            "last_review": {"reviewed": True, "reviewed_at": "fixture"},
            "sample_lines": [],
            "target_utterances": [],
            "provenance": [],
            "actions": {
                "can_save_book_default": True,
                "can_create_range_or_chapter_override": True,
                "can_remove_override": False,
                "can_preview_effective_voice": True,
                "future_render_only": True,
            },
        }

    @classmethod
    def registry(cls, book_id: int, start: int, end: int) -> dict:
        chapters = list(range(start, end + 1))
        rows = [cls._narrator_row(chapters)]
        character_lines: dict[int, list[int]] = {25: [2, 3, 4]}
        for speaker_key, target in cls.unresolved_targets.items():
            chapter_number = int(target["chapter_number"])
            if chapter_number < start or chapter_number > end:
                continue
            mapped_id = cls.mapped.get(speaker_key)
            if mapped_id:
                character_lines.setdefault(mapped_id, []).append(chapter_number)
            else:
                rows.append(cls._unresolved_row(speaker_key, target))
        for character_id, character_chapters in sorted(character_lines.items()):
            visible = [chapter for chapter in sorted(set(character_chapters)) if start <= chapter <= end]
            if visible:
                rows.append(
                    cls._character_row(
                        character_id=character_id,
                        chapters=visible,
                        line_count=len(visible) * 2,
                    )
                )
        status_counts: dict[str, int] = {}
        for row in rows:
            status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
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
                "model": "book_voice_profiles + characters/aliases + casting_plan_revisions",
                "book_profile_config_version": 1,
            },
            "voice_catalog": {"selectable_count": len(VOICE_ITEMS), "narrator_voice_id": "narrator"},
            "characters": sorted(cls.characters.values(), key=lambda item: item["id"]),
            "rows": rows,
            "summary": {
                "total_rows": len(rows),
                "blocking_rows": status_counts.get("UNRESOLVED_DIALOGUE", 0),
                "status_counts": status_counts,
                "ready": status_counts.get("READY", 0),
                "unresolved_dialogue": status_counts.get("UNRESOLVED_DIALOGUE", 0),
            },
            "content_evidence": {
                "checked_revisions": [
                    {"chapter_id": 1000 + chapter, "chapter_number": chapter, "text_revision_id": 700 + chapter}
                    for chapter in chapters
                ],
                "dialogue_detection": "fixture",
                "unresolved_dialogue_count": status_counts.get("UNRESOLVED_DIALOGUE", 0),
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
        }
        return {
            "range_identity": {"book_id": book_id, "from_chapter": start, "to_chapter": end},
            "task_scope": "range",
            "task_type": "COMPLETE",
            "task_key": task["task_key"],
            "user_stage": 6,
            "title": task["title"],
            "summary": task["summary"],
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
            return self._json(
                {
                    "schema": "story-audio-effective-voice-catalog/v1",
                    "items": VOICE_ITEMS,
                    "selectable_count": len(VOICE_ITEMS),
                }
            )
        if parsed.path == "/api/production/book-voice-registry":
            return self._json(
                self.registry(
                    int(query["book_id"][0]),
                    int(query["from_chapter"][0]),
                    int(query["to_chapter"][0]),
                )
            )
        if parsed.path == "/api/production/task-projection":
            return self._json(
                self.projection(
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
                    },
                    "data_readiness": {"ready": True, "ordered_blockers": []},
                    "effective_voice_map": [],
                    "execution_readiness": {},
                    "execution_preview": {"next_action": {"key": "NO_ACTION", "label": "No action"}},
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
        if command_type in {"PREPARE", "START_RENDER"}:
            return self._json({"detail": "render command forbidden in assignment fixture"}, 409)
        if idempotency_key in self.command_responses:
            self.commands.append(body)
            return self._json(self.command_responses[idempotency_key])

        time.sleep(0.1)
        applied = []
        if command_type == "CREATE_CHARACTER":
            name = str(payload.get("display_name") or "").strip()
            existing = next(
                (item for item in self.characters.values() if item["display_name"].lower() == name.lower()),
                None,
            )
            if existing:
                character_id = int(existing["id"])
                created = False
            else:
                character_id = type(self).next_character_id
                type(self).next_character_id += 1
                self.characters[character_id] = {
                    "id": character_id,
                    "display_name": name,
                    "canonical_name": name,
                    "role": str(payload.get("role") or "unknown"),
                    "gender": str(payload.get("gender") or "unknown"),
                    "aliases": [],
                    "active": True,
                }
                created = True
            for alias in payload.get("aliases") or []:
                alias_text = str(alias).strip()
                if alias_text and alias_text not in self.characters[character_id]["aliases"]:
                    self.characters[character_id]["aliases"].append(alias_text)
            applied.append(
                {
                    "type": "character",
                    "book_id": book_id,
                    "character_id": character_id,
                    "display_name": name,
                    "created": created,
                    "reused": not created,
                }
            )
        elif command_type in {"MAP_SPEAKER_TO_CHARACTER", "MAP_RANGE_SPEAKER_TO_CHARACTER"}:
            speaker_key = str(payload.get("speaker_key") or "")
            character_id = int(payload.get("character_id") or 0)
            if speaker_key not in self.unresolved_targets:
                return self._json({"detail": "Speaker target missing"}, 409)
            if character_id not in self.characters:
                return self._json({"detail": "Character missing"}, 404)
            self.mapped[speaker_key] = character_id
            for alias in payload.get("aliases") or []:
                alias_text = str(alias).strip()
                if alias_text and alias_text not in self.characters[character_id]["aliases"]:
                    self.characters[character_id]["aliases"].append(alias_text)
            target = self.unresolved_targets[speaker_key]
            applied.append(
                {
                    "chapter_id": target["chapter_id"],
                    "chapter_number": target["chapter_number"],
                    "speaker_key": speaker_key,
                    "character_id": character_id,
                    "operation": "map",
                }
            )
        elif command_type in {"SET_CHAPTER_VOICE_OVERRIDE", "SET_RANGE_VOICE_OVERRIDE"}:
            speaker_key = str(payload.get("speaker_key") or "")
            voice_id = str(payload.get("voice_id") or "")
            for chapter in range(start, end + 1):
                self.overrides[(chapter, speaker_key)] = voice_id
                applied.append({"chapter_number": chapter, "speaker_key": speaker_key, "voice_id": voice_id})
        elif command_type in {"CLEAR_CHAPTER_VOICE_OVERRIDE", "CLEAR_RANGE_VOICE_OVERRIDE"}:
            speaker_key = str(payload.get("speaker_key") or "")
            for chapter in range(start, end + 1):
                self.overrides.pop((chapter, speaker_key), None)
                applied.append({"chapter_number": chapter, "speaker_key": speaker_key, "operation": "clear"})
        else:
            return self._json({"detail": f"Unsupported command {command_type}"}, 400)

        response = {
            "schema": "story-audio-production-command/v1",
            "command_id": f"fixture-{idempotency_key}",
            "command_type": command_type,
            "idempotency_key": idempotency_key,
            "scope": scope,
            "outcome": "APPLIED",
            "submitted_count": max(1, len(applied)),
            "applied_count": len(applied),
            "failed_count": 0,
            "applied_items": applied,
            "failed_items": [],
            "operator_message": "Character assignment command saved.",
            "resulting_task_projection": self.projection(book_id, start, end),
            "resulting_preflight": None,
            "asynchronous_reference": None,
            "state_tokens": {"task_projection": "fixture", "preflight": None},
        }
        self.command_responses[idempotency_key] = response
        self.commands.append(body)
        return self._json(response)


class CharacterAssignmentBrowserTests(unittest.TestCase):
    def test_assignment_character_mapping_journey_in_real_browser(self) -> None:
        CharacterAssignmentFixtureHandler.reset()
        server = ThreadingHTTPServer(("127.0.0.1", 0), CharacterAssignmentFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [
                    "node",
                    "scripts/browser_character_assignment_smoke.mjs",
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
        self.assertTrue(evidence["exactUrlHasRealRows"])
        self.assertTrue(evidence["sampleVisible"])
        self.assertTrue(evidence["newCharacterMapped"])
        self.assertTrue(evidence["existingCharacterMapped"])
        self.assertTrue(evidence["voiceAssigned"])
        self.assertEqual(evidence["renderCommands"], [])
        command_types = [item["type"] for item in evidence["commands"]]
        self.assertIn("CREATE_CHARACTER", command_types)
        self.assertIn("MAP_SPEAKER_TO_CHARACTER", command_types)
        self.assertIn("SET_RANGE_VOICE_OVERRIDE", command_types)
        self.assertEqual(
            sum(1 for item in CharacterAssignmentFixtureHandler.characters.values() if item["display_name"] == "Gate Captain"),
            1,
        )
        self.assertIn("red command voice", CharacterAssignmentFixtureHandler.characters[25]["aliases"])


if __name__ == "__main__":
    unittest.main()
