from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from story_audio.config import settings  # noqa: E402
from story_audio.db import Database  # noqa: E402
from story_audio.speaker_assignment import generate_speaker_assignment_draft  # noqa: E402
from story_audio.storage import ContentStore  # noqa: E402

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an immutable Gemini speaker draft")
    parser.add_argument("--allow-live-db", action="store_true", help="Opt-in to use the canonical live DB")
    parser.add_argument("--chapter-id", type=int, required=True)
    parser.add_argument("--mode", choices=("unassigned-only", "reanalyze"), default="unassigned-only")
    parser.add_argument("--utterance-id", action="append", dest="utterance_ids")
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()

    if getattr(args, "allow_live_db", False):
        import os
        os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = "1"
    
    
    settings.ensure_dirs()
    database = Database(settings.db_path)
    database.initialize()
    result = generate_speaker_assignment_draft(
        database,
        ContentStore(settings),
        settings,
        chapter_id=args.chapter_id,
        mode=args.mode.replace("-", "_"),
        utterance_ids=args.utterance_ids,
        force_refresh=args.force_refresh,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
