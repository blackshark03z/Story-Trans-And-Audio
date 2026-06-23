from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from story_audio.config import settings  # noqa: E402
from story_audio.gemini_cache import GeminiRepairCache  # noqa: E402
from story_audio.storage import ContentStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview or apply cleanup of disposable Gemini repair cache manifests."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete selected cache manifests. Without this flag the command is read-only.",
    )
    args = parser.parse_args()
    settings.ensure_dirs()
    report = GeminiRepairCache(ContentStore(settings), settings).cleanup(dry_run=not args.apply)
    report["dry_run"] = not args.apply
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
