from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from story_audio.batch_prepare_store import BatchPrepareRequestStore
from story_audio.db import Database
from tests.test_batch_prepare_migration import schema_13_runner


def _database(path: str) -> Database:
    return Database(Path(path).resolve(), migration_runner=schema_13_runner())


def _record_payload(record) -> dict[str, Any]:
    payload = record.as_dict()
    return payload


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        raise SystemExit("usage: batch_prepare_isolated_worker.py <db_path> <action> [json_payload]")
    db_path = argv[1]
    action = argv[2]
    payload = json.loads(argv[3]) if len(argv) > 3 else {}
    db = _database(db_path)
    store = BatchPrepareRequestStore(db)

    if action == "schema":
        result = {
            "schema": db.schema_version(),
            "batch_prepare_requests": db.fetch_one(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_prepare_requests'"
            )
            is not None,
        }
    elif action == "create":
        result = {"record": _record_payload(store.create_or_replay_request(payload))}
    elif action == "get":
        record = store.get_request(int(payload["id"]))
        result = {"record": _record_payload(record) if record else None}
    elif action == "replay":
        result = {"replay": store.build_historical_replay(int(payload["id"]))}
    else:
        raise SystemExit(f"unknown action: {action}")

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
