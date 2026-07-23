from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Sequence

from .batch_prepare_execution_attempt_store import BatchPrepareExecutionAttemptStore


ACTIVE_JOB_STATUSES = (
    "prepared",
    "scheduled",
    "queued",
    "running",
    "repairing",
    "synthesizing",
    "assembling",
    "paused",
    "interrupted",
)


class AuthoritativeInputRejected(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AuthoritativeChapterSnapshot:
    book_id: int
    chapter_id: int
    chapter_number: int
    text_revision_id: int
    casting_plan_id: int
    casting_plan_revision: int
    casting_plan_sha256: str
    narrator_voice_id: str
    deterministic_order: int
    eligibility_evidence: tuple[str, ...] = ("READY_TO_PREPARE",)
    casting_snapshot_json: str = "{}"
    voice_snapshot_json: str = "{}"


@dataclass(frozen=True)
class PrepareTransactionSnapshot:
    request_id: int
    request_identity: str
    book_id: int
    from_chapter: int
    to_chapter: int
    target_phase: str
    plan_fingerprint: str
    chapters: tuple[AuthoritativeChapterSnapshot, ...]
    chapter_snapshot_digest: str
    owner_generation: int
    owner_token: str
    transaction_reference: str
    explicit_no_render: bool = True


@dataclass(frozen=True)
class ValidatedPrepareSnapshot:
    request: PrepareTransactionSnapshot
    chapters: tuple[AuthoritativeChapterSnapshot, ...]
    validation_digest: str


def chapter_snapshot_digest(chapters: Sequence[AuthoritativeChapterSnapshot]) -> str:
    rows = [
        {
            "book_id": item.book_id,
            "chapter_id": item.chapter_id,
            "chapter_number": item.chapter_number,
            "text_revision_id": item.text_revision_id,
            "casting_plan_id": item.casting_plan_id,
            "casting_plan_revision": item.casting_plan_revision,
            "casting_plan_sha256": item.casting_plan_sha256,
            "narrator_voice_id": item.narrator_voice_id,
            "deterministic_order": item.deterministic_order,
            "eligibility_evidence": list(item.eligibility_evidence),
            "casting_snapshot_json": item.casting_snapshot_json,
            "voice_snapshot_json": item.voice_snapshot_json,
        }
        for item in chapters
    ]
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _reject(code: str, message: str) -> None:
    raise AuthoritativeInputRejected(code, message)


class BatchPrepareTransactionRevalidator:
    """Reload immutable PREPARE authority inside the caller's write transaction."""

    def __init__(self, attempt_store: BatchPrepareExecutionAttemptStore):
        self.attempt_store = attempt_store

    @staticmethod
    def _chapter_allows_prepare(
        connection: sqlite3.Connection,
        chapter: sqlite3.Row,
    ) -> bool:
        active_artifact_id = int(chapter["active_audio_artifact_id"] or 0)
        if not active_artifact_id:
            return str(chapter["audio_status"] or "") == "not_created"
        try:
            approval = json.loads(chapter["human_approval_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            return False
        if (
            not isinstance(approval, dict)
            or str(approval.get("status") or "").lower() != "needs_fixes"
            or int(approval.get("artifact_id") or 0) != active_artifact_id
        ):
            return False
        artifact = connection.execute(
            """SELECT id,text_revision_id,status,deleted_at
               FROM artifacts WHERE id=? AND chapter_id=?""",
            (active_artifact_id, int(chapter["id"])),
        ).fetchone()
        return bool(
            artifact
            and artifact["deleted_at"] is None
            and str(artifact["status"] or "") == "active"
            and int(artifact["text_revision_id"] or 0)
            != int(chapter["active_text_revision_id"] or 0)
        )

    def validate(
        self,
        connection: sqlite3.Connection,
        snapshot: PrepareTransactionSnapshot,
        *,
        now: str | None = None,
    ) -> ValidatedPrepareSnapshot:
        if not connection.in_transaction:
            _reject("TRANSACTION_NOT_ACTIVE", "authoritative validation requires an active caller transaction")
        if snapshot.target_phase != "PREPARE" or not snapshot.explicit_no_render:
            _reject("UNSUPPORTED_PHASE", "only no-render PREPARE is supported")
        request = connection.execute(
            "SELECT * FROM batch_prepare_requests WHERE id=?", (int(snapshot.request_id),)
        ).fetchone()
        if request is None:
            _reject("REQUEST_NOT_FOUND", "PREPARE request does not exist")
        expected = {
            "request_identity": snapshot.request_identity,
            "book_id": int(snapshot.book_id),
            "from_chapter": int(snapshot.from_chapter),
            "to_chapter": int(snapshot.to_chapter),
            "target_phase": snapshot.target_phase,
            "plan_fingerprint": snapshot.plan_fingerprint,
            "state": "APPLYING",
        }
        for field, value in expected.items():
            if request[field] != value:
                _reject("REQUEST_BINDING_CHANGED", f"request {field} no longer matches the owned snapshot")
        self.attempt_store.validate_owner_in_connection(
            connection,
            request_id=snapshot.request_id,
            request_identity=snapshot.request_identity,
            generation=snapshot.owner_generation,
            owner_token=snapshot.owner_token,
            plan_fingerprint=snapshot.plan_fingerprint,
            chapter_snapshot_digest=snapshot.chapter_snapshot_digest,
            transaction_reference=snapshot.transaction_reference,
            now=now,
        )
        if int(snapshot.from_chapter) > int(snapshot.to_chapter):
            _reject("INVALID_RANGE", "chapter range is invalid")
        if connection.execute("SELECT 1 FROM books WHERE id=?", (int(snapshot.book_id),)).fetchone() is None:
            _reject("BOOK_NOT_FOUND", "book no longer exists")
        chapters = tuple(snapshot.chapters)
        if not chapters:
            _reject("EMPTY_ELIGIBLE_SET", "at least one authoritative chapter is required")
        ids = [item.chapter_id for item in chapters]
        numbers = [item.chapter_number for item in chapters]
        orders = [item.deterministic_order for item in chapters]
        if len(ids) != len(set(ids)):
            _reject("DUPLICATE_CHAPTER", "authoritative snapshot contains duplicate chapters")
        if orders != list(range(1, len(chapters) + 1)) or numbers != sorted(numbers):
            _reject("NON_DETERMINISTIC_ORDER", "authoritative chapters are not in deterministic order")
        if chapter_snapshot_digest(chapters) != snapshot.chapter_snapshot_digest:
            _reject("SNAPSHOT_DIGEST_CHANGED", "chapter snapshot digest does not match")

        ready_ids: list[int] = []
        scope_rows = connection.execute(
            "SELECT * FROM chapters WHERE book_id=? AND chapter_number BETWEEN ? AND ? ORDER BY chapter_number,id",
            (int(snapshot.book_id), int(snapshot.from_chapter), int(snapshot.to_chapter)),
        ).fetchall()
        for chapter in scope_rows:
            latest_plan = connection.execute(
                "SELECT * FROM casting_plans WHERE chapter_id=? ORDER BY plan_revision DESC,id DESC LIMIT 1",
                (int(chapter["id"]),),
            ).fetchone()
            conflict = self.find_conflict(connection, (int(chapter["id"]),))
            if (
                self._chapter_allows_prepare(connection, chapter)
                and chapter["active_text_revision_id"] is not None
                and latest_plan is not None
                and latest_plan["status"] == "approved"
                and latest_plan["approved_at"] is not None
                and int(latest_plan["text_revision_id"]) == int(chapter["active_text_revision_id"])
                and conflict is None
            ):
                ready_ids.append(int(chapter["id"]))
        if ready_ids != ids:
            _reject("ELIGIBLE_SET_CHANGED", "authoritative eligible chapter set changed inside the transaction")

        for item in chapters:
            if item.book_id != snapshot.book_id or not snapshot.from_chapter <= item.chapter_number <= snapshot.to_chapter:
                _reject("CROSS_SCOPE_CHAPTER", "chapter is outside the owned book/range")
            row = connection.execute("SELECT * FROM chapters WHERE id=?", (int(item.chapter_id),)).fetchone()
            if row is None or int(row["book_id"]) != int(item.book_id) or int(row["chapter_number"]) != int(item.chapter_number):
                _reject("CHAPTER_CHANGED", "chapter identity or number changed")
            if int(row["active_text_revision_id"] or 0) != int(item.text_revision_id):
                _reject("STALE_TEXT_REVISION", "active Text Revision changed")
            text = connection.execute(
                "SELECT 1 FROM text_revisions WHERE id=? AND chapter_id=? AND status='approved'",
                (int(item.text_revision_id), int(item.chapter_id)),
            ).fetchone()
            if text is None:
                _reject("TEXT_REVISION_INVALID", "Text Revision pin is not authoritative")
            plan = connection.execute("SELECT * FROM casting_plans WHERE id=?", (int(item.casting_plan_id),)).fetchone()
            if plan is None:
                _reject("CASTING_PLAN_NOT_FOUND", "Casting Plan no longer exists")
            plan_checks = (
                int(plan["chapter_id"]) == int(item.chapter_id),
                int(plan["text_revision_id"]) == int(item.text_revision_id),
                int(plan["plan_revision"]) == int(item.casting_plan_revision),
                plan["status"] == "approved",
                plan["approved_at"] is not None,
                plan["plan_sha256"] == item.casting_plan_sha256,
                plan["narrator_voice_id"] == item.narrator_voice_id,
                bool(str(plan["content_path"] or "").strip()),
            )
            if not all(plan_checks):
                _reject("CASTING_AUTHORITY_CHANGED", "approved Casting Plan or voice authority changed")
            try:
                casting_snapshot = json.loads(item.casting_snapshot_json)
                voice_snapshot = json.loads(item.voice_snapshot_json)
            except (TypeError, json.JSONDecodeError) as exc:
                raise AuthoritativeInputRejected("INVALID_PINNED_JSON", "pinned casting/voice JSON is invalid") from exc
            if not isinstance(casting_snapshot, dict) or not isinstance(voice_snapshot, dict):
                _reject("INVALID_PINNED_JSON", "pinned casting/voice JSON must encode objects")

        evidence = {
            "request_identity": snapshot.request_identity,
            "plan_fingerprint": snapshot.plan_fingerprint,
            "chapter_snapshot_digest": snapshot.chapter_snapshot_digest,
            "chapter_ids": ids,
            "transaction_reference": snapshot.transaction_reference,
        }
        validation_digest = hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return ValidatedPrepareSnapshot(snapshot, chapters, validation_digest)

    @staticmethod
    def find_conflict(connection: sqlite3.Connection, chapter_ids: Sequence[int]) -> dict[str, Any] | None:
        if not chapter_ids:
            return None
        chapter_marks = ",".join("?" for _ in chapter_ids)
        status_marks = ",".join("?" for _ in ACTIVE_JOB_STATUSES)
        row = connection.execute(
            f"""SELECT j.id,j.status,jc.chapter_id
                FROM jobs j JOIN job_chapters jc ON jc.job_id=j.id
                WHERE jc.chapter_id IN ({chapter_marks}) AND j.status IN ({status_marks})
                ORDER BY j.id LIMIT 1""",
            (*[int(value) for value in chapter_ids], *ACTIVE_JOB_STATUSES),
        ).fetchone()
        return dict(row) if row else None


__all__ = [
    "ACTIVE_JOB_STATUSES",
    "AuthoritativeChapterSnapshot",
    "AuthoritativeInputRejected",
    "BatchPrepareTransactionRevalidator",
    "PrepareTransactionSnapshot",
    "ValidatedPrepareSnapshot",
    "chapter_snapshot_digest",
]
