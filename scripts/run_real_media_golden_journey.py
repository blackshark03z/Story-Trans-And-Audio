from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import sys
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATA = REPO_ROOT / "data"
RUNTIME_ROOT = Path(r"C:\StoryAudio_RealMediaJourney")
TEMP_ROOT = Path(r"C:\StoryAudio_Temp")
PRODUCTION_ENV = REPO_ROOT / "secrets" / "production-runtime.env"
HARD_FREE_BYTES = 8 * 1024**3
PREFERRED_FREE_BYTES = 10 * 1024**3


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _reserve_port() -> int:
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = int(sock.getsockname()[1])
        if port != 8772:
            return port


def _select_port(requested: int) -> int:
    if requested == 8772:
        raise ValueError("Port 8772 is reserved for the canonical runtime.")
    port = requested or _reserve_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"Runtime port {port} is unavailable.") from exc
    return port


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_production_runtime_env() -> dict[str, str]:
    if not PRODUCTION_ENV.is_file():
        raise FileNotFoundError(f"Missing production runtime env file: {PRODUCTION_ENV}")
    values: dict[str, str] = {}
    raw_token: str | None = None
    for line_number, line in enumerate(
        PRODUCTION_ENV.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        if "=" not in trimmed:
            raise ValueError(f"Invalid runtime env entry on line {line_number}.")
        name, value = trimmed.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            raise ValueError("Runtime env key cannot be empty.")
        if name == "PREPARE_OPERATOR_TOKEN":
            raw_token = value
            continue
        values[name] = value
    if raw_token is None:
        raise ValueError("PREPARE_OPERATOR_TOKEN is required in production-runtime.env")
    values["PREPARE_OPERATOR_TOKEN_SHA256"] = _sha256_text(raw_token)
    return values


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _assert_isolated_paths(run_root: Path, temp_root: Path) -> None:
    repo_root = REPO_ROOT.resolve(strict=False)
    source_data = SOURCE_DATA.resolve(strict=False)
    for label, path in (("run root", run_root), ("temp root", temp_root)):
        resolved = path.resolve(strict=False)
        if _is_relative_to(resolved, repo_root) or _is_relative_to(resolved, source_data):
            raise RuntimeError(f"Isolated {label} cannot be inside the canonical repository.")


def _storage_evidence(run_root: Path) -> dict[str, int | bool | str]:
    source_free_bytes = int(shutil.disk_usage(SOURCE_DATA.anchor).free)
    output_free_bytes = int(shutil.disk_usage(run_root.anchor).free)
    if source_free_bytes < HARD_FREE_BYTES:
        raise RuntimeError(
            f"Source storage hard gate failed: {source_free_bytes} bytes free; "
            f"{HARD_FREE_BYTES} required."
        )
    if output_free_bytes < HARD_FREE_BYTES:
        raise RuntimeError(
            f"Output storage hard gate failed: {output_free_bytes} bytes free; "
            f"{HARD_FREE_BYTES} required."
        )
    return {
        "source_drive": SOURCE_DATA.anchor,
        "source_drive_free_bytes": source_free_bytes,
        "output_drive": run_root.anchor,
        "output_drive_free_bytes": output_free_bytes,
        "hard_gate_bytes": HARD_FREE_BYTES,
        "preferred_gate_bytes": PREFERRED_FREE_BYTES,
        "source_preferred_gate_met": source_free_bytes >= PREFERRED_FREE_BYTES,
        "output_preferred_gate_met": output_free_bytes >= PREFERRED_FREE_BYTES,
    }


def _backup_database(source_db: Path, clone_db: Path) -> None:
    source_uri = source_db.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source:
        with closing(sqlite3.connect(clone_db)) as clone:
            source.backup(clone)
            quick_check = clone.execute("PRAGMA quick_check").fetchone()
            foreign_keys = clone.execute("PRAGMA foreign_key_check").fetchall()
            if quick_check != ("ok",):
                raise RuntimeError(f"Isolated database quick_check failed: {quick_check!r}")
            if foreign_keys:
                raise RuntimeError(
                    f"Isolated database has {len(foreign_keys)} foreign-key violation(s)."
                )


def _prepare_isolated_clone(run_root: Path) -> Path:
    if not SOURCE_DATA.is_dir():
        raise FileNotFoundError(f"Missing source data directory: {SOURCE_DATA}")
    source_db = SOURCE_DATA / "app.db"
    source_blobs = SOURCE_DATA / "blobs"
    if not source_db.is_file():
        raise FileNotFoundError(f"Missing source database: {source_db}")
    if not source_blobs.is_dir():
        raise FileNotFoundError(f"Missing source blob root: {source_blobs}")

    data_root = run_root / "data"
    if data_root.exists():
        shutil.rmtree(data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    _backup_database(source_db, data_root / "app.db")
    shutil.copytree(source_blobs, data_root / "blobs")
    for relative in ("output", "work", "cache", "cache/previews", "cache/gemini_repairs", "exports/youtube_auto", "runtime"):
        (data_root / relative).mkdir(parents=True, exist_ok=True)
    return data_root


def _validate_existing_clone(run_root: Path) -> Path:
    data_root = run_root / "data"
    clone_db = data_root / "app.db"
    clone_blobs = data_root / "blobs"
    if not clone_db.is_file() or not clone_blobs.is_dir():
        raise FileNotFoundError(
            "Existing isolated clone requires data/app.db and data/blobs."
        )
    clone_uri = clone_db.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(clone_uri, uri=True)) as connection:
        quick_check = connection.execute("PRAGMA quick_check").fetchone()
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    if quick_check != ("ok",):
        raise RuntimeError(f"Existing isolated database quick_check failed: {quick_check!r}")
    if foreign_keys:
        raise RuntimeError(
            f"Existing isolated database has {len(foreign_keys)} foreign-key violation(s)."
        )
    for relative in (
        "output",
        "work",
        "cache",
        "cache/previews",
        "cache/gemini_repairs",
        "exports/youtube_auto",
        "runtime",
    ):
        (data_root / relative).mkdir(parents=True, exist_ok=True)
    return data_root


def _configure_environment(run_root: Path, data_root: Path, temp_root: Path) -> None:
    env = _load_production_runtime_env()
    env.update(
        {
            "STORY_AUDIO_DATA_DIR": str(data_root),
            "STORY_AUDIO_ALLOW_LIVE_DB": "1",
            "STORY_AUDIO_SUPERVISED": "1",
            "STORY_AUDIO_RESTART_SIGNAL": str(data_root / "runtime" / "restart.request"),
            "TEMP": str(temp_root),
            "TMP": str(temp_root),
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    temp_root.mkdir(parents=True, exist_ok=True)
    (data_root / "runtime").mkdir(parents=True, exist_ok=True)
    os.environ.pop("PREPARE_OPERATOR_TOKEN", None)
    for key, value in env.items():
        os.environ[key] = value


def _patch_runtime_paths(run_root: Path, data_root: Path) -> None:
    import story_audio.config as config

    clone_db = (data_root / "app.db").resolve(strict=False)
    config.canonical_production_db_path = lambda: clone_db  # type: ignore[assignment]
    isolated_settings = replace(config.settings, log_dir=run_root / "logs")
    expected_paths = {
        "data_dir": data_root,
        "db_path": clone_db,
        "blobs_dir": data_root / "blobs",
        "output_dir": data_root / "output",
        "work_dir": data_root / "work",
    }
    mismatches = {
        name: str(getattr(isolated_settings, name))
        for name, expected in expected_paths.items()
        if getattr(isolated_settings, name).resolve(strict=False)
        != expected.resolve(strict=False)
    }
    if mismatches:
        raise RuntimeError(
            "Runtime settings were imported before isolation was configured: "
            + ", ".join(sorted(mismatches))
        )
    config.settings = isolated_settings
    isolated_settings.ensure_dirs()


def main() -> int:
    parser = argparse.ArgumentParser(description="Start an isolated real-media Story Audio runtime.")
    parser.add_argument("--run-root", type=Path, help="Explicit isolated journey root.")
    parser.add_argument(
        "--temp-root",
        type=Path,
        help="Explicit isolated temp root; defaults to C:\\StoryAudio_Temp\\<timestamp>.",
    )
    parser.add_argument("--port", type=int, default=0, help="Runtime port. Use 0 for a free port.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window.")
    parser.add_argument(
        "--resume-existing",
        action="store_true",
        help="Resume a validated existing isolated clone without copying canonical data again.",
    )
    args = parser.parse_args()

    if args.resume_existing and args.run_root is None:
        parser.error("--resume-existing requires --run-root")
    run_root = (args.run_root or (RUNTIME_ROOT / _timestamp())).resolve()
    temp_root = (args.temp_root or (TEMP_ROOT / _timestamp())).resolve()
    _assert_isolated_paths(run_root, temp_root)
    storage = _storage_evidence(run_root)
    port = _select_port(args.port)
    run_root.mkdir(parents=True, exist_ok=True)
    data_root = (
        _validate_existing_clone(run_root)
        if args.resume_existing
        else _prepare_isolated_clone(run_root)
    )
    _configure_environment(run_root, data_root, temp_root)
    _patch_runtime_paths(run_root, data_root)

    import story_audio.api as api_module

    api_module.settings.ensure_dirs()

    runtime_manifest = {
        "run_root": str(run_root),
        "data_root": str(data_root),
        "temp_root": str(temp_root),
        "port": port,
        "base_url": f"http://{args.host}:{port}",
        "db_path": str(data_root / "app.db"),
        "db_sha256": hashlib.sha256((data_root / "app.db").read_bytes()).hexdigest(),
        "runtime_pid": os.getpid(),
        "resumed_existing_clone": bool(args.resume_existing),
        **storage,
    }
    manifest_path = run_root / "runtime-manifest.json"
    manifest_path.write_text(
        json.dumps(runtime_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(runtime_manifest, ensure_ascii=False))

    import uvicorn

    uvicorn.run(api_module.app, host=args.host, port=port, reload=False, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
