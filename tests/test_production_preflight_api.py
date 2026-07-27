from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from story_audio.production_preflight import PREFLIGHT_SCHEMA
from tests.base import IsolatedTestCase


class ProductionPreflightApiTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._multipart = patch(
            "fastapi.dependencies.utils.ensure_multipart_is_installed",
            lambda: None,
        )
        self._multipart.start()
        from story_audio.api import app

        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._multipart.stop()
        super().tearDown()

    def test_route_passes_typed_scope_to_read_only_service(self) -> None:
        captured = {}

        def fake_preflight(_db, **kwargs):
            captured.update(kwargs)
            return {
                "schema": PREFLIGHT_SCHEMA,
                "range": {},
                "data_readiness": {},
                "effective_voice_map": [],
                "execution_readiness": {},
                "execution_preview": {},
                "technical_details": {},
            }

        with (
            patch("story_audio.api.get_production_preflight", fake_preflight),
            patch("story_audio.api._load_voice_catalog", return_value=object()),
            patch("story_audio.api._build_custom_voice_context", return_value=None),
        ):
            response = self.client.get(
                "/api/production/preflight",
                params={
                    "book_id": 7,
                    "from_chapter": 372,
                    "to_chapter": 373,
                    "skip_completed": "false",
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["schema"], PREFLIGHT_SCHEMA)
        self.assertEqual(captured["book_id"], 7)
        self.assertEqual(captured["from_chapter"], 372)
        self.assertEqual(captured["to_chapter"], 373)
        self.assertFalse(captured["skip_completed"])

    def test_route_rejects_invalid_range_parameters_before_service(self) -> None:
        response = self.client.get(
            "/api/production/preflight",
            params={
                "book_id": 0,
                "from_chapter": -1,
                "to_chapter": 2,
            },
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    import unittest

    unittest.main()
