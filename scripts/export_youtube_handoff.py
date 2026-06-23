from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from story_audio.config import settings  # noqa: E402
from story_audio.db import Database  # noqa: E402
from story_audio.storage import ContentStore  # noqa: E402
from story_audio.youtube_handoff import HandoffError, export_chapter_handoff  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export one completed Story Audio chapter for YouTube Auto.")
    parser.add_argument("--chapter-id", type=int, required=True)
    parser.add_argument("--job-id", type=int)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        result = export_chapter_handoff(
            Database(settings.db_path), ContentStore(settings), settings,
            chapter_id=args.chapter_id, job_id=args.job_id,
            export_root=args.output_root, overwrite=args.overwrite,
        )
    except (HandoffError, OSError, ValueError) as exc:
        print(f"Failure: {exc}")
        return 1
    print("Success")
    print(f"Bundle: {result['path']}")
    print(f"Export ID: {result['manifest']['export_id']}")
    print(f"Reused: {result['reused']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
