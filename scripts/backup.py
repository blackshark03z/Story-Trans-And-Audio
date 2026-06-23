from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from story_audio.backup import BackupError, create_backup  # noqa: E402
from story_audio.config import settings  # noqa: E402


def main() -> int:
    default = ROOT / "backups" / f"story-audio-{datetime.now():%Y%m%d-%H%M%S}"
    parser = argparse.ArgumentParser(description="Create a verified Story Audio backup")
    parser.add_argument("destination", nargs="?", type=Path, default=default)
    parser.add_argument(
        "--exclude-work",
        action="store_true",
        help="Do not include resumable segment WAV files.",
    )
    parser.add_argument(
        "--allow-active",
        action="store_true",
        help="Allow backup while a job is active (less consistent).",
    )
    args = parser.parse_args()
    try:
        manifest = create_backup(
            settings,
            args.destination,
            include_work=not args.exclude_work,
            allow_active=args.allow_active,
        )
    except BackupError as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {key: value for key, value in manifest.items() if key != "files"},
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"Backup created: {args.destination.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
