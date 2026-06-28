from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from story_audio.character_bible import (  # noqa: E402
    CharacterBibleError,
    apply_character_bible_import,
    parse_character_bible,
    plan_character_bible_import,
)
from story_audio.config import settings  # noqa: E402
from story_audio.db import Database  # noqa: E402

def main() -> int:
    parser = argparse.ArgumentParser(description="Import Character Bible JSON V1")
    parser.add_argument("--allow-live-db", action="store_true", help="Opt-in to use the canonical live DB")
    parser.add_argument("--book-id", type=int, required=True)
    parser.add_argument("--file", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--update-existing", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if getattr(args, "allow_live_db", False):
        import os
        os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = "1"
    
    
    try:
        raw = args.file.read_bytes()
        parsed = parse_character_bible(raw, source_label=args.file.name)
        requested_voices = {
            record.get("voice_override_id") for record in parsed.records
            if record.get("voice_override_id")
        }
        allowed_voices = None
        if requested_voices:
            from story_audio.tts import tts_service
            allowed_voices = {item["id"] for item in tts_service.voices()}
        database = Database(settings.db_path)
        database.initialize()
        plan = plan_character_bible_import(
            database, args.book_id, parsed,
            allowed_voice_ids=allowed_voices,
            update_existing=args.update_existing,
        )
        result = None
        if args.apply:
            result = apply_character_bible_import(database, plan)
        output = {"mode": "apply" if args.apply else "dry-run", "plan": plan, "result": result}
        if args.json:
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            summary = plan["summary"]
            print(f"Character Bible {output['mode']}: book={args.book_id} source={plan['source_label']}")
            print(" ".join(f"{key}={value}" for key, value in summary.items()))
            for item in plan["records"]:
                print(f"[{item['action']}] #{item['index'] + 1} {item.get('canonical_name') or 'invalid'}")
                for warning in item["warnings"]:
                    print(f"  warning: {warning}")
                for error in item["errors"]:
                    print(f"  error: {error}")
            if result:
                print(f"applied={result['applied']} changed_records={result['changed_records']}")
        return 2 if plan["summary"]["invalid_count"] or plan["summary"]["conflict_count"] else 0
    except (OSError, CharacterBibleError) as exc:
        print(f"Character Bible import failed: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
