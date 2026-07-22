from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from story_audio.batch_plan import build_batch_plan
from story_audio.batch_prepare_execution_attempt_store import BatchPrepareExecutionAttemptStore
from story_audio.batch_prepare_isolated_adapter import (
    BatchPrepareCommittedEvidenceReader,
    BatchPrepareIsolatedAdapter,
    DatabaseAuthoritativeSnapshotProvider,
)
from story_audio.batch_prepare_isolated_transaction_service import BatchPrepareIsolatedTransactionService
from story_audio.batch_prepare_orchestrator import BatchPrepareOrchestrator
from story_audio.batch_prepare_store import BatchPrepareRequestStore
from story_audio.config import Settings
from story_audio.db import Database
from story_audio.storage import ContentStore
from tests.phase9_fixture import schema_15_runner


def _plan(db: Database, *, book_id: int, from_chapter: int, to_chapter: int) -> dict[str, Any]:
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT * FROM chapters WHERE book_id=? AND chapter_number BETWEEN ? AND ? ORDER BY chapter_number,id",
            (book_id, from_chapter, to_chapter),
        ).fetchall()
        chapters = []
        for chapter in rows:
            plan = connection.execute(
                "SELECT * FROM casting_plans WHERE chapter_id=? ORDER BY plan_revision DESC,id DESC LIMIT 1",
                (int(chapter["id"]),),
            ).fetchone()
            live = connection.execute(
                """SELECT j.id,j.status FROM jobs j JOIN job_chapters jc ON jc.job_id=j.id
                   WHERE jc.chapter_id=? AND j.status IN ('prepared','scheduled','queued','running','paused','interrupted')
                   ORDER BY j.id LIMIT 1""",
                (int(chapter["id"]),),
            ).fetchone()
            ready = plan is not None and plan["status"] == "approved" and plan["approved_at"] and live is None
            chapters.append(
                {
                    "chapter_id": int(chapter["id"]),
                    "chapter_number": int(chapter["chapter_number"]),
                    "chapter_title": str(chapter["title"]),
                    "state": "READY_TO_PREPARE" if ready else "PREPARED",
                    "next_action": "PREPARE" if ready else "START_RENDER",
                    "blockers": [],
                    "active_text_revision_id": chapter["active_text_revision_id"],
                    "latest_casting_plan_id": plan["id"] if plan else None,
                    "latest_casting_plan_revision": plan["plan_revision"] if plan else None,
                    "latest_casting_plan_status": plan["status"] if plan else None,
                    "active_artifact_id": chapter["active_audio_artifact_id"],
                    "active_output_job_id": live["id"] if live else None,
                    "active_output_job_chapter_id": None,
                    "live_job_id": live["id"] if live else None,
                    "live_job_status": live["status"] if live else None,
                    "human_qa_status": "pending",
                }
            )
    return build_batch_plan(
        {
            "scope": {
                "book_id": book_id,
                "book_title": "Phase 10",
                "from_chapter": from_chapter,
                "to_chapter": to_chapter,
                "chapter_count": len(chapters),
            },
            "chapters": chapters,
            "summary": {"total": len(chapters)},
            "exceptions": [],
        },
        target_phase="PREPARE",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode")
    parser.add_argument("db_path")
    parser.add_argument("request_json")
    args = parser.parse_args()
    os.environ["STORY_AUDIO_TESTING"] = "1"
    db_path = Path(args.db_path).resolve()
    temporary_root = db_path.parent
    config = Settings(
        root=temporary_root,
        data_dir=temporary_root,
        db_path=db_path,
        blobs_dir=temporary_root / "blobs",
        output_dir=temporary_root / "output",
        work_dir=temporary_root / "work",
        log_dir=temporary_root / "logs",
    )
    store = ContentStore(config)
    db = Database(db_path, migration_runner=schema_15_runner())
    request = json.loads(args.request_json)

    def provider(**kwargs):
        return _plan(
            db,
            book_id=int(kwargs["book_id"]),
            from_chapter=int(kwargs["from_chapter"]),
            to_chapter=int(kwargs["to_chapter"]),
        )

    def lifecycle(stage, _context):
        if args.mode == "exit-after-owner" and stage == "after_execution_ownership":
            os._exit(17)
        if args.mode == "exit-after-commit" and stage == "after_commit_before_applied":
            os._exit(19)

    def transaction_failure(stage, _context):
        if args.mode == "exit-after-job" and stage == "after_job_insert":
            os._exit(18)

    adapter = BatchPrepareIsolatedAdapter(
        db=db,
        attempt_store=BatchPrepareExecutionAttemptStore(db),
        transaction_service=BatchPrepareIsolatedTransactionService(db),
        snapshot_provider=DatabaseAuthoritativeSnapshotProvider(
            db,
            store,
            config,
            temporary_root=temporary_root,
        ),
        evidence_reader=BatchPrepareCommittedEvidenceReader(db, temporary_root=temporary_root),
        temporary_root=temporary_root,
        lease_seconds=1,
        lifecycle_hook=lifecycle,
        transaction_failure_injector=transaction_failure,
    )
    orchestrator = BatchPrepareOrchestrator(
        current_plan_provider=provider,
        request_store=BatchPrepareRequestStore(db),
        future_prepare_transaction=adapter,
    )
    result = orchestrator.prepare(request)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
