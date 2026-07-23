from __future__ import annotations

import argparse
import json
import os


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()

    import story_audio.api as api_module
    from story_audio.batch_prepare_runtime_integration import public_runtime_readiness

    if os.environ.get("STORY_AUDIO_TESTING") == "1":
        class _CatalogOnlyTts:
            def voices(self):
                return [
                    {"id": "custom:26", "label": "Fixture Narrator"},
                    {"id": "ngoc_lan", "label": "Fixture Preset"},
                ]

        api_module.tts_service = _CatalogOnlyTts()

    app = api_module.app
    prepare_runtime_integration = api_module.prepare_runtime_integration

    if args.inspect:
        routes = sorted((
            {"path": route.path, "methods": sorted(getattr(route, "methods", None) or ())}
            for route in app.routes
            if hasattr(route, "path")
        ), key=lambda item: item["path"])
        print(json.dumps({"readiness": public_runtime_readiness(prepare_runtime_integration), "routes": routes}))
        return
    if not args.port:
        raise SystemExit("--port is required unless --inspect is used")
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
