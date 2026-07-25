from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from story_audio.storage_cleanup import (  # noqa: E402
    CONFIRMATION,
    StorageCleanupError,
    _write_report,
    build_report,
    execute_cleanup,
)


def _print_summary(report: dict[str, object]) -> None:
    storage = report["storage"]
    print(f"Mode: {report['mode']}")
    print(f"Repository bytes: {storage['repository_bytes']}")
    print(f"Output bytes: {storage['output_bytes']}")
    print(f"Reclaimable bytes: {storage['reclaimable_bytes']}")
    if report.get("reclaimed_bytes") is not None:
        print(f"Reclaimed bytes: {report['reclaimed_bytes']}")
    print(f"Candidates: {len(report['candidates'])}")
    print(f"Blockers: {len(report['blockers'])}")
    for blocker in report["blockers"]:
        print(f"BLOCKED: {blocker}")
    for item in report["candidates"]:
        print(
            f"{item['category']} | {item['bytes']} | {item['path']} | "
            f"{item['reason']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report and delete only proven orphaned Story Audio storage."
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--report", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--json-report", type=Path)
    args = parser.parse_args()

    try:
        if args.execute:
            report = execute_cleanup(
                ROOT,
                confirmation=args.confirm or "",
                json_report=args.json_report,
            )
        else:
            report = build_report(ROOT)
            report["mode"] = "dry-run" if args.dry_run else "report"
            if args.json_report:
                _write_report(args.json_report, report, ROOT)
        _print_summary(report)
        return 0
    except (OSError, sqlite3.Error, StorageCleanupError) as exc:
        print(f"Storage cleanup failed safely: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
