from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from story_audio.config import settings  # noqa: E402
from story_audio.db import Database  # noqa: E402
from story_audio.files import sha256_file  # noqa: E402


def result(level: str, name: str, detail: str) -> None:
    print(f"[{level}] {name}: {detail}")


def command_available(name: str) -> bool:
    try:
        completed = subprocess.run(
            [name, "-version"], capture_output=True, text=True, timeout=10
        )
        return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Story Audio diagnostics")
    parser.add_argument("--deep", action="store_true", help="Hash active artifacts; slower.")
    args = parser.parse_args()
    errors = 0

    result("INFO", "root", str(ROOT))
    result("OK" if settings.gemini_key() else "WARN", "gemini_key", "configured" if settings.gemini_key() else "missing")
    for command in ("ffmpeg", "ffprobe"):
        available = command_available(command)
        result("OK" if available else "ERROR", command, "available" if available else "missing")
        errors += int(not available)

    usage = shutil.disk_usage(settings.root)
    free_gb = usage.free / (1024 ** 3)
    level = "OK" if free_gb >= settings.minimum_free_gb else "ERROR"
    result(level, "disk_free", f"{free_gb:.1f} GB")
    errors += int(level == "ERROR")

    if not settings.db_path.exists():
        result("ERROR", "database", f"missing: {settings.db_path}")
        return 1

    db = Database(settings.db_path)
    quick = db.fetch_one("PRAGMA quick_check")
    quick_value = next(iter(dict(quick).values())) if quick else "no result"
    level = "OK" if quick_value == "ok" else "ERROR"
    result(level, "sqlite_quick_check", str(quick_value))
    errors += int(level == "ERROR")

    counts = {}
    for table in ("books", "chapters", "text_revisions", "jobs", "segments", "artifacts"):
        counts[table] = int(db.fetch_one(f"SELECT COUNT(*) AS count FROM {table}")["count"])
    result("INFO", "counts", " ".join(f"{key}={value}" for key, value in counts.items()))

    missing_blobs = 0
    for row in db.fetch_all("SELECT id,content_path FROM text_revisions"):
        if not (settings.blobs_dir / row["content_path"]).exists():
            missing_blobs += 1
            if missing_blobs <= 5:
                result("ERROR", "missing_text_blob", f"revision={row['id']} path={row['content_path']}")
    result("OK" if missing_blobs == 0 else "ERROR", "text_blobs", f"missing={missing_blobs}")
    errors += int(missing_blobs > 0)

    missing_artifacts = 0
    bad_hashes = 0
    active_rows = db.fetch_all("SELECT id,path,sha256 FROM artifacts WHERE status='active' AND deleted_at IS NULL")
    for row in active_rows:
        path = Path(row["path"])
        if not path.exists():
            missing_artifacts += 1
            result("ERROR", "missing_active_artifact", f"artifact={row['id']} path={path}")
        elif args.deep and sha256_file(path) != row["sha256"]:
            bad_hashes += 1
            result("ERROR", "artifact_hash", f"artifact={row['id']} mismatch")
    result(
        "OK" if missing_artifacts == 0 and bad_hashes == 0 else "ERROR",
        "active_artifacts",
        f"checked={len(active_rows)} missing={missing_artifacts} bad_hash={bad_hashes}",
    )
    errors += int(missing_artifacts > 0 or bad_hashes > 0)

    stale_running = db.fetch_one(
        "SELECT COUNT(*) AS count FROM jobs WHERE status IN ('running','repairing','synthesizing','assembling')"
    )["count"]
    result("INFO", "active_jobs", str(stale_running))

    result("OK" if errors == 0 else "ERROR", "summary", f"critical_errors={errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
