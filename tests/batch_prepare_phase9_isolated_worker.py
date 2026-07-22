from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["STORY_AUDIO_TESTING"] = "1"
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from story_audio.batch_prepare_isolated_transaction_service import BatchPrepareIsolatedTransactionService
from story_audio.batch_prepare_execution_attempt_store import BatchPrepareExecutionAttemptStore
from story_audio.batch_prepare_transaction_revalidator import (
    AuthoritativeChapterSnapshot,
    PrepareTransactionSnapshot,
)
from story_audio.db import Database
from tests.phase9_fixture import schema_15_runner


def _snapshot(payload: dict) -> PrepareTransactionSnapshot:
    return PrepareTransactionSnapshot(
        **{
            **payload,
            "chapters": tuple(AuthoritativeChapterSnapshot(**item) for item in payload["chapters"]),
        }
    )


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: worker DB_PATH ACTION")
    path = Path(sys.argv[1]).resolve()
    action = sys.argv[2]
    payload = json.load(sys.stdin)
    database = Database(path, migration_runner=schema_15_runner())
    service = BatchPrepareIsolatedTransactionService(database)
    if action == "acquire":
        lease = BatchPrepareExecutionAttemptStore(database).acquire(**payload)
        print(json.dumps({
            "owner_token": lease.owner_token,
            "generation": lease.record.attempt_generation,
            "transaction_reference": lease.record.transaction_reference,
        }, sort_keys=True))
        return 0
    snapshot = _snapshot(payload)
    if action == "prepare":
        result = service.prepare(snapshot)
    elif action == "recover":
        result = service.recover(snapshot)
    else:
        raise SystemExit("unsupported action")
    print(json.dumps(result.as_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
