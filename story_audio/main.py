from __future__ import annotations

import argparse
import os
import webbrowser

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Story Audio MVP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    # Log data directory configuration at startup
    from .config import settings
    data_override = os.getenv("STORY_AUDIO_DATA_DIR", "").strip()
    if data_override:
        print(f"[CONFIG] Using isolated data directory: {settings.data_dir}")
        print(f"[CONFIG] Database path: {settings.db_path}")

    if not args.no_browser:
        webbrowser.open(f"http://{args.host}:{args.port}")
    uvicorn.run("story_audio.api:app", host=args.host, port=args.port, reload=False)



if __name__ == "__main__":
    main()
