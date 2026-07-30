from __future__ import annotations

import importlib.util
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_real_media_golden_journey.py"
)


def _load_launcher():
    spec = importlib.util.spec_from_file_location("real_media_launcher_test", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load real-media launcher.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RealMediaGoldenJourneyLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.launcher = _load_launcher()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_online_backup_includes_committed_wal_rows(self) -> None:
        source = self.root / "source.db"
        clone = self.root / "clone.db"
        connection = sqlite3.connect(source)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO evidence(value) VALUES ('committed-in-wal')")
            connection.commit()
            self.launcher._backup_database(source, clone)
        finally:
            connection.close()

        with closing(sqlite3.connect(clone)) as cloned:
            rows = cloned.execute("SELECT id, value FROM evidence").fetchall()
            self.assertEqual(rows, [(1, "committed-in-wal")])
            self.assertEqual(cloned.execute("PRAGMA quick_check").fetchone(), ("ok",))

    def test_resume_validates_and_preserves_existing_clone(self) -> None:
        data_root = self.root / "data"
        blobs_root = data_root / "blobs"
        blobs_root.mkdir(parents=True)
        clone = data_root / "app.db"
        with closing(sqlite3.connect(clone)) as connection:
            connection.execute("CREATE TABLE evidence (value TEXT NOT NULL)")
            connection.execute("INSERT INTO evidence(value) VALUES ('preserve-me')")
            connection.commit()

        resolved = self.launcher._validate_existing_clone(self.root)

        self.assertEqual(resolved, data_root)
        with closing(sqlite3.connect(clone)) as connection:
            self.assertEqual(
                connection.execute("SELECT value FROM evidence").fetchone(),
                ("preserve-me",),
            )
        self.assertTrue((data_root / "runtime").is_dir())
        self.assertTrue((data_root / "cache" / "previews").is_dir())

    def test_resume_rejects_incomplete_existing_clone(self) -> None:
        (self.root / "data").mkdir()
        with self.assertRaisesRegex(FileNotFoundError, "data/app.db and data/blobs"):
            self.launcher._validate_existing_clone(self.root)

    def test_storage_gate_fails_below_eight_gibibytes(self) -> None:
        low_usage = shutil._ntuple_diskusage(
            total=64 * 1024**3,
            used=57 * 1024**3,
            free=7 * 1024**3,
        )
        safe_usage = shutil._ntuple_diskusage(
            total=64 * 1024**3,
            used=55 * 1024**3,
            free=9 * 1024**3,
        )
        with mock.patch.object(
            self.launcher.shutil,
            "disk_usage",
            side_effect=[safe_usage, low_usage],
        ):
            with self.assertRaisesRegex(RuntimeError, "Output storage hard gate failed"):
                self.launcher._storage_evidence(Path("C:/isolated"))

    def test_storage_gate_allows_minimum_and_reports_preferred_state(self) -> None:
        usage = shutil._ntuple_diskusage(
            total=64 * 1024**3,
            used=55 * 1024**3,
            free=9 * 1024**3,
        )
        with mock.patch.object(self.launcher.shutil, "disk_usage", return_value=usage):
            evidence = self.launcher._storage_evidence(Path("C:/isolated"))
        self.assertEqual(evidence["source_drive_free_bytes"], 9 * 1024**3)
        self.assertEqual(evidence["output_drive_free_bytes"], 9 * 1024**3)
        self.assertFalse(evidence["source_preferred_gate_met"])
        self.assertFalse(evidence["output_preferred_gate_met"])

    def test_canonical_port_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "reserved for the canonical runtime"):
            self.launcher._select_port(8772)

    def test_isolated_paths_cannot_be_inside_repository(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "canonical repository"):
            self.launcher._assert_isolated_paths(
                self.launcher.REPO_ROOT / "unsafe-run",
                self.root / "temp",
            )

    def test_runtime_env_hashes_token_without_returning_plaintext(self) -> None:
        env_file = self.root / "production-runtime.env"
        env_file.write_text(
            "PREPARE_OPERATOR_TOKEN=fixture-secret\n"
            "STORY_AUDIO_PRODUCTION_PREPARE_ENABLED=1\n",
            encoding="utf-8",
        )
        with mock.patch.object(self.launcher, "PRODUCTION_ENV", env_file):
            values = self.launcher._load_production_runtime_env()
        self.assertNotIn("PREPARE_OPERATOR_TOKEN", values)
        self.assertNotIn("fixture-secret", repr(values))
        self.assertEqual(
            values["PREPARE_OPERATOR_TOKEN_SHA256"],
            self.launcher._sha256_text("fixture-secret"),
        )

    def test_configure_environment_removes_inherited_plaintext_token(self) -> None:
        data_root = self.root / "data"
        temp_root = self.root / "temp"
        data_root.mkdir()
        env = {
            "PREPARE_OPERATOR_TOKEN_SHA256": self.launcher._sha256_text(
                "fixture-secret"
            )
        }
        with mock.patch.object(
            self.launcher,
            "_load_production_runtime_env",
            return_value=env,
        ):
            with mock.patch.dict(
                self.launcher.os.environ,
                {"PREPARE_OPERATOR_TOKEN": "must-not-survive"},
                clear=False,
            ):
                self.launcher._configure_environment(self.root, data_root, temp_root)
                self.assertNotIn(
                    "PREPARE_OPERATOR_TOKEN",
                    self.launcher.os.environ,
                )
