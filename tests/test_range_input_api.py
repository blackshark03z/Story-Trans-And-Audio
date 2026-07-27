from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from story_audio.speaker_assignment import generate_speaker_assignment_draft
from story_audio.voice_eligibility import EffectiveVoiceCatalog
from tests.base import IsolatedTestCase
from tests.test_speaker_assignment import fake_response, seed


class RangeInputApiTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(dir=self.temp_root)
        (
            self.config,
            self.db,
            self.store,
            self.book_id,
            self.chapter_id,
            _revision_id,
            self.character_id,
        ) = seed(Path(self.temp.name))
        self.catalog = EffectiveVoiceCatalog.from_ids("narrator", "male", "female")
        self._multipart = patch(
            "fastapi.dependencies.utils.ensure_multipart_is_installed",
            lambda: None,
        )
        self._multipart.start()
        import story_audio.api as api_module

        self.api_module = api_module
        self.originals = {
            "db": api_module.db,
            "store": api_module.store,
            "settings": api_module.settings,
            "catalog": api_module._load_voice_catalog,
            "preset": api_module._preset_voice_ids,
            "custom": api_module._build_custom_voice_context,
        }
        api_module.db = self.db
        api_module.store = self.store
        api_module.settings = self.config
        api_module._load_voice_catalog = lambda: self.catalog
        api_module._preset_voice_ids = lambda: set(self.catalog.preset_ids)
        api_module._build_custom_voice_context = lambda: None
        self.client = TestClient(api_module.app)

    def tearDown(self) -> None:
        self.api_module.db = self.originals["db"]
        self.api_module.store = self.originals["store"]
        self.api_module.settings = self.originals["settings"]
        self.api_module._load_voice_catalog = self.originals["catalog"]
        self.api_module._preset_voice_ids = self.originals["preset"]
        self.api_module._build_custom_voice_context = self.originals["custom"]
        self._multipart.stop()
        self.temp.cleanup()
        super().tearDown()

    def scope(self) -> dict:
        return {
            "book_id": self.book_id,
            "from_chapter": 1,
            "to_chapter": 1,
            "skip_completed": True,
        }

    def test_api_executes_range_input_lifecycle_without_job_or_audio(self) -> None:
        initial = self.client.get(
            "/api/production/range-inputs",
            params={
                "book_id": self.book_id,
                "from_chapter": 1,
                "to_chapter": 1,
            },
        )
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(
            initial.json()["summary"]["proposal_required_chapters"], 1
        )

        def generated(*args, **kwargs):
            return generate_speaker_assignment_draft(
                *args,
                **kwargs,
                provider=lambda **provider_kwargs: fake_response(
                    provider_kwargs["request_data"], self.character_id
                ),
            )

        with (
            patch.object(type(self.config), "gemini_key", return_value="fake-key"),
            patch("story_audio.range_input.generate_speaker_assignment_draft", generated),
        ):
            proposal = self.client.post(
                "/api/production/range-inputs/prepare",
                json=self.scope(),
            )
        self.assertEqual(proposal.status_code, 200)
        ready = proposal.json()["snapshot"]["ready_speaker_drafts"][0]

        approved_speaker = self.client.post(
            "/api/production/range-inputs/speaker-approvals",
            json={
                **self.scope(),
                "chapters": [{
                    "chapter_id": ready["chapter_id"],
                    "draft_id": ready["draft_id"],
                }],
            },
        )
        self.assertEqual(approved_speaker.status_code, 200)
        self.assertEqual(approved_speaker.json()["status"], "complete")
        replayed_speaker = self.client.post(
            "/api/production/range-inputs/speaker-approvals",
            json={
                **self.scope(),
                "chapters": [{
                    "chapter_id": ready["chapter_id"],
                    "draft_id": ready["draft_id"],
                }],
            },
        )
        self.assertEqual(replayed_speaker.status_code, 200)
        self.assertEqual(replayed_speaker.json()["status"], "complete")
        self.assertTrue(replayed_speaker.json()["results"][0]["reused"])

        casting_draft = self.client.post(
            "/api/production/range-inputs/prepare",
            json=self.scope(),
        )
        self.assertEqual(casting_draft.status_code, 200)
        plan = casting_draft.json()["snapshot"]["casting_approvals"][0]

        approved_casting = self.client.post(
            "/api/production/range-inputs/casting-approvals",
            json={
                **self.scope(),
                "chapters": [{
                    "chapter_id": plan["chapter_id"],
                    "plan_id": plan["plan_id"],
                }],
            },
        )
        self.assertEqual(approved_casting.status_code, 200)
        self.assertEqual(approved_casting.json()["status"], "complete")
        replayed_casting = self.client.post(
            "/api/production/range-inputs/casting-approvals",
            json={
                **self.scope(),
                "chapters": [{
                    "chapter_id": plan["chapter_id"],
                    "plan_id": plan["plan_id"],
                }],
            },
        )
        self.assertEqual(replayed_casting.status_code, 200)
        self.assertEqual(replayed_casting.json()["status"], "complete")
        self.assertTrue(replayed_casting.json()["results"][0]["reused"])
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS n FROM jobs")["n"]), 0
        )
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS n FROM segments")["n"]), 0
        )
        self.assertEqual(
            int(self.db.fetch_one("SELECT COUNT(*) AS n FROM artifacts")["n"]), 0
        )

    def test_batch_routes_reject_stale_or_out_of_scope_identity(self) -> None:
        response = self.client.post(
            "/api/production/range-inputs/speaker-approvals",
            json={
                **self.scope(),
                "chapters": [{
                    "chapter_id": self.chapter_id,
                    "draft_id": 999999,
                }],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "failed")
        self.assertIn("outside", response.json()["failures"][0]["error"])
        self.assertEqual(
            int(
                self.db.fetch_one(
                    "SELECT COUNT(*) AS n FROM speaker_assignment_reviews"
                )["n"]
            ),
            0,
        )
