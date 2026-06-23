from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from story_audio.config import settings  # noqa: E402
from story_audio.integrity import check_data_integrity, has_errors  # noqa: E402


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
    parser.add_argument("--deep", action="store_true", help="Hash blobs/artifacts; slower.")
    args = parser.parse_args()
    errors = 0

    result("INFO", "root", str(ROOT))
    result(
        "OK" if settings.gemini_key() else "WARN",
        "gemini_key",
        "configured" if settings.gemini_key() else "missing",
    )
    for command in ("ffmpeg", "ffprobe"):
        available = command_available(command)
        result("OK" if available else "ERROR", command, "available" if available else "missing")
        errors += int(not available)

    usage = shutil.disk_usage(settings.root)
    free_gb = usage.free / (1024 ** 3)
    level = "OK" if free_gb >= settings.minimum_free_gb else "ERROR"
    result(level, "disk_free", f"{free_gb:.1f} GB")
    errors += int(level == "ERROR")

    findings = check_data_integrity(settings, deep=args.deep)
    for finding in findings:
        result(finding.level, finding.name, finding.detail)
    errors += int(has_errors(findings))

    result("OK" if errors == 0 else "ERROR", "summary", f"critical_errors={errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
