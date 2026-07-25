from __future__ import annotations

import io
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from story_audio.audio_archive import build_archive_plan, create_archive
from tests.base import IsolatedTestCase
from tests.test_active_output import seed_active_output


class AudioRangeArchiveTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        seeded = seed_active_output(self.temp_root)
        self.db = seeded["db"]
        self.config = seeded["config"]
        self.book_id = int(
            self.db.fetch_one(
                "SELECT book_id FROM chapters WHERE id=?",
                (seeded["chapter_one"],),
            )["book_id"]
        )
        self._multipart_patcher = patch(
            "fastapi.dependencies.utils.ensure_multipart_is_installed",
            lambda: None,
        )
        self._multipart_patcher.start()
        import story_audio.api as api_module

        self.api_module = api_module
        self.original_db = api_module.db
        self.original_settings = api_module.settings
        api_module.db = self.db
        api_module.settings = self.config
        self.client = TestClient(api_module.app)

    def tearDown(self) -> None:
        self.api_module.db = self.original_db
        self.api_module.settings = self.original_settings
        self._multipart_patcher.stop()
        super().tearDown()

    def test_readiness_blocks_missing_chapter_with_exact_issue(self) -> None:
        response = self.client.get(
            "/api/audio-library/range-archive-readiness",
            params={
                "book_id": self.book_id,
                "from_chapter": 10,
                "to_chapter": 11,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ready"])
        self.assertEqual(payload["chapter_count"], 1)
        self.assertEqual(
            [(item["chapter_number"], item["code"]) for item in payload["issues"]],
            [(11, "ACTIVE_ARTIFACT_MISSING")],
        )
        self.assertNotIn("entries", payload)
        self.assertNotIn(str(self.config.output_dir), str(payload))

    def test_download_has_stable_name_order_hash_and_removes_temporary_zip(self) -> None:
        response = self.client.get(
            "/api/audio-library/range-archive",
            params={
                "book_id": self.book_id,
                "from_chapter": 10,
                "to_chapter": 10,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        self.assertIn("chapters-0010-0010.zip", response.headers["content-disposition"])
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(archive.namelist(), ["chapter_0010.m4a"])
            self.assertEqual(archive.read("chapter_0010.m4a"), b"old")
        archive_root = self.config.work_dir / "archive_downloads"
        self.assertEqual(list(archive_root.glob("*.zip")), [])

        plan = build_archive_plan(
            self.db,
            output_root=self.config.output_dir,
            book_id=self.book_id,
            from_chapter=10,
            to_chapter=10,
        )
        first = create_archive(plan, self.temp_root / "first.zip")
        second = create_archive(plan, self.temp_root / "second.zip")
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(first["size_bytes"], second["size_bytes"])

    def test_hash_mismatch_blocks_archive_without_creating_temp_file(self) -> None:
        artifact = self.db.fetch_one(
            """
            SELECT a.path
            FROM chapters c JOIN artifacts a ON a.id=c.active_audio_artifact_id
            WHERE c.book_id=? AND c.chapter_number=10
            """,
            (self.book_id,),
        )
        Path(artifact["path"]).write_bytes(b"tampered")
        response = self.client.get(
            "/api/audio-library/range-archive",
            params={
                "book_id": self.book_id,
                "from_chapter": 10,
                "to_chapter": 10,
            },
        )
        self.assertEqual(response.status_code, 409)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "ARCHIVE_RANGE_INCOMPLETE")
        self.assertEqual(detail["issues"][0]["code"], "OUTPUT_SIZE_MISMATCH")
        self.assertEqual(
            list((self.config.work_dir / "archive_downloads").glob("*.zip")),
            [],
        )


if __name__ == "__main__":
    unittest.main()
