from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from story_audio.backup import (  # noqa: E402
    BackupError,
    BackupVerificationError,
    restore_backup,
    verify_backup,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify or restore a Story Audio backup")
    parser.add_argument("backup", type=Path)
    parser.add_argument("destination", nargs="?", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Move an existing destination aside before restore.",
    )
    args = parser.parse_args()
    try:
        if args.verify_only:
            manifest = verify_backup(args.backup)
            print(
                json.dumps(
                    {key: value for key, value in manifest.items() if key != "files"},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            print("Backup verification: OK")
            return 0
        if args.destination is None:
            parser.error("destination is required unless --verify-only is used")
        report = restore_backup(
            args.backup,
            args.destination,
            overwrite=args.overwrite,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"Restore completed: {args.destination.resolve()}")
        return 0
    except (BackupError, BackupVerificationError) as exc:
        print(f"Restore failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
