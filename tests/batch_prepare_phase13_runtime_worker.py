from __future__ import annotations

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()

    from story_audio.api import app, prepare_runtime_integration
    from story_audio.batch_prepare_runtime_integration import public_runtime_readiness

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
