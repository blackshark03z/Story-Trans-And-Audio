from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from story_audio.db import utcnow
from story_audio.files import sha256_file
from story_audio.video_export import (
    VideoExportError,
    create_video_export,
    inspect_video_export,
    load_video_export_file,
)
from tests.base import IsolatedTestCase
from tests.test_active_output import seed_active_output


def _write_test_m4a(path: Path, *, duration_seconds: float = 1.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration_seconds}",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


class VideoExportTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        seeded = seed_active_output(self.temp_root)
        self.db = seeded["db"]
        self.config = seeded["config"]
        self.chapter_id = seeded["chapter_one"]
        self.artifact_id = seeded["old_artifact_id"]
        self._make_active_artifact_accepted()

    def _make_active_artifact_accepted(self, *, duration_seconds: float = 1.0) -> None:
        row = self.db.fetch_one("SELECT path FROM artifacts WHERE id=?", (self.artifact_id,))
        artifact_path = Path(row["path"])
        _write_test_m4a(artifact_path, duration_seconds=duration_seconds)
        now = utcnow()
        approval = {
            "status": "approved",
            "artifact_id": self.artifact_id,
            "recorded_at": now,
            "notes": "accepted for export test",
        }
        with self.db.connect() as connection:
            connection.execute(
                """
                UPDATE artifacts
                SET sha256=?, size_bytes=?, duration_ms=?, verified_at=?
                WHERE id=?
                """,
                (
                    sha256_file(artifact_path),
                    artifact_path.stat().st_size,
                    int(round(duration_seconds * 1000)),
                    now,
                    self.artifact_id,
                ),
            )
            connection.execute(
                "UPDATE chapters SET human_approval_json=? WHERE id=?",
                (json.dumps(approval, sort_keys=True), self.chapter_id),
            )

    def test_create_video_export_creates_mp4_manifest_and_reuses_it(self) -> None:
        first = create_video_export(self.db, self.config, self.artifact_id)
        self.assertFalse(first["reused"])
        self.assertEqual(first["source_artifact_id"], self.artifact_id)
        self.assertRegex(first["export_id"], r"^artifact-\d+-[0-9a-f]{12}-[0-9a-f]{12}$")
        self.assertRegex(first["download_url"], r"^/api/video-exports/artifact-\d+-[0-9a-f]{12}-[0-9a-f]{12}/file$")
        self.assertEqual(first["video_codec"], "h264")
        self.assertEqual(first["audio_codec"], "aac")
        self.assertEqual((first["width"], first["height"]), (1280, 720))
        self.assertLessEqual(abs(int(first["duration_delta_ms"] or 0)), 1500)

        path, manifest = load_video_export_file(
            self.db,
            self.config,
            first["export_id"],
        )
        self.assertTrue(path.is_file())
        self.assertEqual(manifest["source_artifact_id"], self.artifact_id)
        self.assertEqual(manifest["sha256"], sha256_file(path))

        inspected = inspect_video_export(self.db, self.config, self.artifact_id)
        self.assertIsNotNone(inspected)
        self.assertTrue(inspected["reused"])
        self.assertEqual(inspected["sha256"], first["sha256"])

        second = create_video_export(self.db, self.config, self.artifact_id)
        self.assertTrue(second["reused"])
        self.assertEqual(second["export_id"], first["export_id"])
        self.assertEqual(second["sha256"], first["sha256"])

    def test_video_export_caps_static_video_to_verified_audio_duration(self) -> None:
        # libx264 still-image lookahead can exceed short audio by dozens of
        # one-fps frames unless the output duration is explicitly capped.
        self._make_active_artifact_accepted(duration_seconds=65.25)

        exported = create_video_export(self.db, self.config, self.artifact_id)

        self.assertLessEqual(abs(int(exported["duration_delta_ms"] or 0)), 1500)
        path, _manifest = load_video_export_file(
            self.db,
            self.config,
            exported["export_id"],
        )
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-show_entries",
                "stream=codec_type,duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        metadata = json.loads(probe.stdout)
        self.assertAlmostEqual(float(metadata["format"]["duration"]), 65.25, delta=1.5)
        audio_stream = next(
            stream for stream in metadata["streams"] if stream["codec_type"] == "audio"
        )
        self.assertAlmostEqual(float(audio_stream["duration"]), 65.25, delta=1.5)

    def test_video_export_requires_accepted_active_audio(self) -> None:
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE chapters SET human_approval_json=NULL WHERE id=?",
                (self.chapter_id,),
            )
        with self.assertRaises(VideoExportError) as raised:
            create_video_export(self.db, self.config, self.artifact_id)
        self.assertEqual(raised.exception.code, "HUMAN_QA_NOT_ACCEPTED")

    def test_video_export_rejects_non_active_artifact(self) -> None:
        new_id = int(
            self.db.fetch_one(
                "SELECT id FROM artifacts WHERE id<>? ORDER BY id DESC LIMIT 1",
                (self.artifact_id,),
            )["id"]
        )
        with self.assertRaises(VideoExportError) as raised:
            create_video_export(self.db, self.config, new_id)
        self.assertEqual(raised.exception.code, "ARTIFACT_NOT_ACTIVE")

    def test_video_export_api_creates_and_downloads_mp4(self) -> None:
        multipart_patcher = patch(
            "fastapi.dependencies.utils.ensure_multipart_is_installed",
            lambda: None,
        )
        multipart_patcher.start()
        import story_audio.api as api_module

        original_db = api_module.db
        original_settings = api_module.settings
        api_module.db = self.db
        api_module.settings = self.config
        try:
            client = TestClient(api_module.app)
            response = client.post(f"/api/artifacts/{self.artifact_id}/video-export")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertFalse(payload["reused"])
            self.assertRegex(payload["download_url"], r"^/api/video-exports/artifact-\d+-[0-9a-f]{12}-[0-9a-f]{12}/file$")

            download = client.get(payload["download_url"])
            self.assertEqual(download.status_code, 200)
            self.assertEqual(download.headers["content-type"], "video/mp4")
            self.assertGreater(len(download.content), 0)

            repeated = client.post(f"/api/artifacts/{self.artifact_id}/video-export")
            self.assertEqual(repeated.status_code, 200)
            self.assertTrue(repeated.json()["reused"])
        finally:
            api_module.db = original_db
            api_module.settings = original_settings
            multipart_patcher.stop()

    def test_video_download_rejects_export_after_active_artifact_changes(self) -> None:
        exported = create_video_export(self.db, self.config, self.artifact_id)
        replacement_id = int(
            self.db.fetch_one(
                "SELECT id FROM artifacts WHERE id<>? ORDER BY id DESC LIMIT 1",
                (self.artifact_id,),
            )["id"]
        )
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE chapters SET active_audio_artifact_id=? WHERE id=?",
                (replacement_id, self.chapter_id),
            )

        with self.assertRaises(VideoExportError) as raised:
            load_video_export_file(
                self.db,
                self.config,
                exported["export_id"],
            )

        self.assertEqual(raised.exception.code, "ARTIFACT_NOT_ACTIVE")

    def test_export_id_rejects_path_traversal(self) -> None:
        with self.assertRaises(VideoExportError) as raised:
            load_video_export_file(
                self.db,
                self.config,
                "../artifact-1-aaaaaaaaaaaa-bbbbbbbbbbbb",
            )
        self.assertEqual(raised.exception.code, "EXPORT_ID_INVALID")


if __name__ == "__main__":
    unittest.main()
