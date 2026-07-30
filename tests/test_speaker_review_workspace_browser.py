from __future__ import annotations

import json
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

from tests.test_character_assignment_browser import CharacterAssignmentFixtureHandler
from tests.test_production_scope_browser import ROOT


class SpeakerReviewWorkspaceFixtureHandler(CharacterAssignmentFixtureHandler):
    unresolved_targets = {
        **CharacterAssignmentFixtureHandler.unresolved_targets,
        "unresolved-dialogue:1005:u0002-010203040506": {
            "chapter_id": 1005,
            "chapter_number": 5,
            "utterance_id": "u0002-010203040506",
            "sequence": 2,
            "text": "- Hold this line until the signal changes.",
        },
        "unresolved-dialogue:1006:u0002-111213141516": {
            "chapter_id": 1006,
            "chapter_number": 6,
            "utterance_id": "u0002-111213141516",
            "sequence": 2,
            "text": "- Advance when the second signal appears.",
        },
    }
    review_states: dict[str, str] = {}
    review_history: dict[str, list[dict]] = {}
    mutation_count = 0

    @classmethod
    def reset(cls) -> None:
        super().reset()
        cls.review_states = {
            key: "PENDING_REVIEW" for key in cls.unresolved_targets
        }
        cls.review_history = {key: [] for key in cls.unresolved_targets}
        cls.mutation_count = 0
        cls.suggestions = cls.queue()

    @classmethod
    def queue(cls) -> dict:
        keys = list(cls.unresolved_targets)
        suggestions = []
        for index, key in enumerate(keys):
            target = cls.unresolved_targets[key]
            resolution = (
                "EXISTING_CHARACTER"
                if index in {0, 3, 4}
                else "NEW_CHARACTER"
                if index == 1
                else "NEEDS_HUMAN_DECISION"
            )
            warnings = (
                ["Possible continuity conflict; inspect before approval."]
                if index == 3
                else []
            )
            state = cls.review_states.get(key, "PENDING_REVIEW")
            history = cls.review_history.get(key, [])
            latest = history[-1] if history else None
            suggestions.append(
                {
                    "unresolved_key": key,
                    "source_analysis_run_id": "fixture-review-run",
                    "suggestion_id": f"fixture-review-run:{key}",
                    "chapter_number": target["chapter_number"],
                    "target": {
                        **target,
                        "dialogue_text": target["text"],
                        "previous_context": [
                            {"text": "The formation trembled before the order."}
                        ],
                        "following_context": [
                            {"text": "The nearby cultivators obeyed immediately."}
                        ],
                    },
                    "proposed_resolution": resolution,
                    "existing_character_id": 25 if resolution == "EXISTING_CHARACTER" else None,
                    "proposed_character_name": "Outer Sentinel" if resolution == "NEW_CHARACTER" else None,
                    "proposed_aliases": ["sentinel"] if resolution == "NEW_CHARACTER" else [],
                    "confidence": "HIGH",
                    "confidence_score": 0.94,
                    "evidence_summary": f"Fixture evidence for card {index + 1}.",
                    "context_evidence": ["Named action and nearby command response."],
                    "alternative_candidates": [],
                    "continuity_notes": "Stable fixture continuity.",
                    "continuity_conflict": index == 3,
                    "proposed_voice_handling": "INHERIT_EXISTING_CONFIGURATION",
                    "suggested_voice_id": None,
                    "voice_rationale": "Use the existing voice when available.",
                    "warnings": warnings,
                    "matched_character": cls.characters.get(25) if resolution == "EXISTING_CHARACTER" else None,
                    "effective_inherited_voice": {
                        "id": "male",
                        "display_name": "Male Default",
                        "available": True,
                        "source_kind": "preset",
                    }
                    if resolution == "EXISTING_CHARACTER"
                    else None,
                    "effective_voice_source": "book default" if resolution == "EXISTING_CHARACTER" else "Chưa có giọng",
                    "suggested_voice": None,
                    "possible_duplicates": [],
                    "review_state": state,
                    "human_review": latest,
                    "review_history": history,
                    "reviewed_at": latest.get("recorded_at") if latest else None,
                    "review_audit_event_id": latest.get("audit_event_id") if latest else None,
                    "source_revision_current": True,
                    "downstream_immutable_exists": index == 0,
                    "downstream_stale": state in {"CORRECTED", "REPLACEMENT_DRAFT"} and index == 0,
                    "approval_exclusion_reasons": (
                        []
                        if resolution in {"EXISTING_CHARACTER", "NEW_CHARACTER"} and not warnings
                        else ["human_decision_required"]
                        if resolution == "NEEDS_HUMAN_DECISION"
                        else ["warning_requires_review", "continuity_conflict"]
                    ),
                    "approval_eligible": resolution in {"EXISTING_CHARACTER", "NEW_CHARACTER"} and not warnings and state == "PENDING_REVIEW",
                }
            )
        approved = sum(
            state in {"ACCEPTED", "EDITED_AND_ACCEPTED", "CORRECTED"}
            for state in cls.review_states.values()
        )
        return {
            "schema": "story-audio-gemini-speaker-review-queue/v1",
            "status": "ready_for_human_review",
            "analysis_run_id": "fixture-review-run",
            "input_fingerprint": "fixture-review-fingerprint",
            "text_revisions": [
                {"chapter_number": number, "text_revision_id": 7000 + number}
                for number in range(2, 6)
            ],
            "target_count": len(suggestions),
            "suggestions": suggestions,
            "summary": {
                "total": len(suggestions),
                "analyzed": len(suggestions),
                "pending_review": sum(
                    state == "PENDING_REVIEW"
                    for state in cls.review_states.values()
                ),
                "needs_human_decision": sum(
                    item["proposed_resolution"] == "NEEDS_HUMAN_DECISION"
                    or item["review_state"] == "MARKED_UNCERTAIN"
                    for item in suggestions
                ),
                "approved": approved,
                "corrected": sum(
                    state == "CORRECTED" for state in cls.review_states.values()
                ),
                "deferred": sum(
                    state == "DEFERRED" for state in cls.review_states.values()
                ),
                "error": 0,
            },
        }

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/api/production/speaker-review-suggestions":
            type(self).suggestions = type(self).queue()
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/production/commands":
            return super().do_POST()
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        command_type = str(body.get("command_type") or "")
        supported = {
            "ACCEPT_SPEAKER_SUGGESTION",
            "EDIT_AND_ACCEPT_SPEAKER_SUGGESTION",
            "CORRECT_APPROVED_SPEAKER_SUGGESTION",
            "CREATE_SPEAKER_REPLACEMENT_DECISION",
            "DEFER_SPEAKER_SUGGESTION",
            "MARK_SPEAKER_SUGGESTION_UNCERTAIN",
            "APPROVE_SPEAKER_REVIEW_BATCH",
            "GENERATE_SPEAKER_SUGGESTIONS",
        }
        if command_type not in supported:
            return super().do_POST()
        idempotency_key = str(body.get("idempotency_key") or "")
        if idempotency_key in self.command_responses:
            self.commands.append(body)
            return self._json(self.command_responses[idempotency_key])

        time.sleep(0.35)
        payload = body.get("payload") or {}
        changed: list[tuple[str, str]] = []
        if command_type == "APPROVE_SPEAKER_REVIEW_BATCH":
            submitted = payload.get("items") or [
                {
                    "analysis_run_id": payload.get("analysis_run_id"),
                    "unresolved_key": key,
                }
                for key in payload.get("unresolved_keys") or []
            ]
            for item in submitted:
                key = str(item.get("unresolved_key") or "")
                proposal = next(
                    row for row in type(self).queue()["suggestions"]
                    if row["unresolved_key"] == key
                )
                if proposal["approval_eligible"]:
                    changed.append((key, "ACCEPTED"))
        elif command_type != "GENERATE_SPEAKER_SUGGESTIONS":
            key = str(payload.get("unresolved_key") or "")
            decision = {
                "ACCEPT_SPEAKER_SUGGESTION": "ACCEPTED",
                "EDIT_AND_ACCEPT_SPEAKER_SUGGESTION": "EDITED_AND_ACCEPTED",
                "CORRECT_APPROVED_SPEAKER_SUGGESTION": "CORRECTED",
                "CREATE_SPEAKER_REPLACEMENT_DECISION": "REPLACEMENT_DRAFT",
                "DEFER_SPEAKER_SUGGESTION": "DEFERRED",
                "MARK_SPEAKER_SUGGESTION_UNCERTAIN": "MARKED_UNCERTAIN",
            }[command_type]
            changed.append((key, decision))

        for key, decision in changed:
            previous = next(
                row for row in type(self).queue()["suggestions"]
                if row["unresolved_key"] == key
            )
            source_snapshot = {
                field: value
                for field, value in previous.items()
                if field not in {"human_review", "review_history"}
            }
            type(self).review_states[key] = decision
            entry = {
                "analysis_run_id": "fixture-review-run",
                "unresolved_key": key,
                "decision": decision,
                "reviewer_payload": dict(payload.get("reviewer_payload") or {}),
                "source_suggestion": source_snapshot,
                "resulting_mapping": {
                    "applied": [
                        {
                            "chapter_number": previous["chapter_number"],
                            "plan_revision": len(type(self).review_history[key]) + 2,
                        }
                    ]
                },
                "idempotency_key": idempotency_key,
                "audit_event_id": 900 + type(self).mutation_count,
                "recorded_at": "2026-07-29T15:00:00+00:00",
            }
            type(self).review_history[key].append(entry)
        if command_type != "GENERATE_SPEAKER_SUGGESTIONS":
            type(self).mutation_count += 1
        type(self).suggestions = type(self).queue()
        scope = body.get("scope") or {}
        range_scope = scope.get("range") or {}
        start = int(range_scope.get("from_chapter") or 2)
        end = int(range_scope.get("to_chapter") or 5)
        applied = [
            {
                "type": "speaker_review_decision",
                "unresolved_key": key,
                "decision": decision,
            }
            for key, decision in changed
        ] or [{"type": "speaker_review_analysis"}]
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
            "operator_message": "Đã lưu và cập nhật Preflight.",
            "resulting_task_projection": self.projection(1, start, end),
            "resulting_preflight": None,
            "asynchronous_reference": None,
            "state_tokens": {"task_projection": "fixture", "preflight": None},
        }
        if command_type == "APPROVE_SPEAKER_REVIEW_BATCH":
            response["result_metadata"] = {
                "requested_count": len(submitted),
                "approved_count": len(changed),
                "excluded_count": int(payload.get("excluded_count") or 0),
                "failed_count": 0,
                "decision_ids": [
                    type(self).review_history[key][-1]["audit_event_id"]
                    for key, _decision in changed
                ],
                "queue_counts": type(self).queue()["summary"],
            }
        self.command_responses[idempotency_key] = response
        self.commands.append(body)
        return self._json(response)


class SpeakerReviewWorkspaceBrowserTests(unittest.TestCase):
    def test_review_workspace_real_browser_certification(self) -> None:
        import subprocess

        SpeakerReviewWorkspaceFixtureHandler.reset()
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), SpeakerReviewWorkspaceFixtureHandler
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [
                    "node",
                    "scripts/browser_speaker_review_workspace_smoke.mjs",
                    f"http://127.0.0.1:{server.server_port}",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["ok"])
        self.assertEqual(evidence["allCardCount"], 5)
        self.assertTrue(evidence["busyVisible"])
        self.assertTrue(evidence["characterFocus"])
        self.assertTrue(evidence["newCharacterFocus"])
        self.assertTrue(evidence["voiceFocus"])
        self.assertTrue(evidence["editedDecisionSaved"])
        self.assertTrue(evidence["reanalysisApplied"])
        self.assertTrue(evidence["deferApplied"])
        self.assertTrue(evidence["draftsPreserved"])
        self.assertTrue(evidence["approvedMoved"])
        self.assertTrue(evidence["correctionHistoryVisible"])
        self.assertTrue(evidence["batchExcludedUnsafe"])
        self.assertTrue(evidence["batchBusyVisible"])
        self.assertTrue(evidence["batchResultVisible"], evidence["batchResultText"])
        self.assertTrue(evidence["unknownResponseReconciled"])
        self.assertTrue(evidence["reloadPersisted"])
        self.assertFalse(evidence["horizontalOverflow1366"])
        self.assertFalse(evidence["horizontalOverflow1920"])
        self.assertEqual(
            [
                command["command_type"]
                for command in SpeakerReviewWorkspaceFixtureHandler.commands
                if command["command_type"] in {"PREPARE", "START_RENDER"}
            ],
            [],
        )
        self.assertEqual(
            SpeakerReviewWorkspaceFixtureHandler.mutation_count,
            evidence["durableMutationCount"],
        )
        self.assertEqual(
            sum(
                command["command_type"] == "APPROVE_SPEAKER_REVIEW_BATCH"
                for command in SpeakerReviewWorkspaceFixtureHandler.commands
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
