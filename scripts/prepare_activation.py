from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from story_audio.prepare_activation import (  # noqa: E402
    CloneEvidenceError,
    ClonePathRejected,
    PrepareActivationError,
    execute_migration,
    rollback_migration,
    run_preflight,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preflight or explicitly activate production PREPARE schema 15."
    )
    parser.add_argument("--backup", type=Path, required=True)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--execute-migration", action="store_true")
    action.add_argument("--rollback", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    try:
        if args.execute_migration:
            result = execute_migration(args.backup, confirmation=args.confirm)
        elif args.rollback:
            result = rollback_migration(args.backup, confirmation=args.confirm)
        else:
            result = run_preflight(args.backup, script_path=Path(__file__))
    except (PrepareActivationError, CloneEvidenceError, ClonePathRejected, OSError) as exc:
        print(f"PREPARE activation blocked: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
