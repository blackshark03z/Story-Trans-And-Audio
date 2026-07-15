from __future__ import annotations

from typing import Any

from .db import Database, utcnow
from .files import sha256_text
from .storage import ContentStore
from .text import lexical_sha256


TARGETED_CORRECTION_KIND = "repaired"
TARGETED_CORRECTION_PROCESSOR_VERSION = "targeted-correction-v1"


class TextCorrectionError(ValueError):
    pass


class TextCorrectionNotFound(TextCorrectionError):
    pass


class TextCorrectionConflict(TextCorrectionError):
    pass


def _validate_base_text_revision(base_revision: Any, chapter: Any, *, chapter_id: int, base_revision_id: int) -> None:
    if not chapter:
        raise TextCorrectionNotFound("Chapter not found")
    if not base_revision:
        raise TextCorrectionNotFound("Base TextRevision not found for this chapter")
    if str(base_revision["status"]) != "approved":
        raise TextCorrectionConflict("Base TextRevision is not approved")
    if int(chapter["active_text_revision_id"] or 0) != base_revision_id:
        raise TextCorrectionConflict("Base TextRevision is no longer the active canonical revision")
    if int(base_revision["chapter_id"]) != chapter_id:
        raise TextCorrectionNotFound("Base TextRevision not found for this chapter")


def _insert_corrected_revision(
    connection: Any,
    *,
    chapter_id: int,
    base_revision_id: int,
    corrected_text: str,
    store: ContentStore,
) -> tuple[int, str, str, int]:
    content_path, content_sha256 = store.put_text(corrected_text)
    now = utcnow()
    cursor = connection.execute(
        """INSERT INTO text_revisions(
            chapter_id,parent_revision_id,kind,content_path,content_sha256,lexical_sha256,
            char_count,processor_version,status,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            chapter_id,
            base_revision_id,
            TARGETED_CORRECTION_KIND,
            content_path,
            content_sha256,
            lexical_sha256(corrected_text),
            len(corrected_text),
            TARGETED_CORRECTION_PROCESSOR_VERSION,
            "approved",
            now,
        ),
    )
    return int(cursor.lastrowid), str(content_path), content_sha256, len(corrected_text)


def _activate_corrected_revision(connection: Any, *, chapter_id: int, revision_id: int) -> None:
    connection.execute(
        "UPDATE chapters SET active_text_revision_id=?,updated_at=? WHERE id=?",
        (revision_id, utcnow(), chapter_id),
    )


def apply_targeted_text_correction(
    db: Database,
    store: ContentStore,
    *,
    chapter_id: int,
    base_revision_id: int,
    expected_text: str,
    replacement_text: str,
    reason: str,
) -> dict[str, Any]:
    if expected_text == "":
        raise TextCorrectionError("expected_text is required")
    if expected_text == replacement_text:
        raise TextCorrectionError("expected_text and replacement_text must differ")
    reason = reason.strip()
    if not reason:
        raise TextCorrectionError("reason is required")

    with db.transaction() as connection:
        chapter = connection.execute("SELECT * FROM chapters WHERE id=?", (chapter_id,)).fetchone()
        base_revision = connection.execute(
            "SELECT * FROM text_revisions WHERE id=? AND chapter_id=?",
            (base_revision_id, chapter_id),
        ).fetchone()
        _validate_base_text_revision(
            base_revision,
            chapter,
            chapter_id=chapter_id,
            base_revision_id=base_revision_id,
        )

        try:
            base_text = store.read_text(str(base_revision["content_path"]))
        except (OSError, UnicodeError, ValueError) as exc:
            raise TextCorrectionConflict(f"Base TextRevision blob is unreadable: {exc}") from exc
        if sha256_text(base_text) != str(base_revision["content_sha256"]):
            raise TextCorrectionConflict("Base TextRevision blob hash mismatch")

        occurrence_count = base_text.count(expected_text)
        if occurrence_count == 0:
            raise TextCorrectionError("expected_text does not occur in the base revision")
        if occurrence_count > 1:
            raise TextCorrectionError("expected_text must occur exactly once in the base revision")

        corrected_text = base_text.replace(expected_text, replacement_text, 1)
        if corrected_text == base_text:
            raise TextCorrectionError("Correction did not change the chapter text")
        if not corrected_text.strip():
            raise TextCorrectionError("Correction produced empty chapter content")

        new_revision_id, content_path, content_sha256, char_count = _insert_corrected_revision(
            connection,
            chapter_id=chapter_id,
            base_revision_id=base_revision_id,
            corrected_text=corrected_text,
            store=store,
        )
        _activate_corrected_revision(connection, chapter_id=chapter_id, revision_id=new_revision_id)

    lexical_hash = lexical_sha256(corrected_text)
    db.audit(
        "text_revision_targeted_corrected",
        chapter_id=chapter_id,
        details={
            "base_revision_id": base_revision_id,
            "new_revision_id": new_revision_id,
            "reason": reason,
            "processor_version": TARGETED_CORRECTION_PROCESSOR_VERSION,
            "replacement_occurrence_count": 1,
            "expected_text_sha256": sha256_text(expected_text),
            "replacement_text_sha256": sha256_text(replacement_text),
        },
    )
    return {
        "chapter_id": chapter_id,
        "old_active_revision_id": base_revision_id,
        "new_active_revision_id": new_revision_id,
        "base_revision_id": base_revision_id,
        "revision_id": new_revision_id,
        "parent_revision_id": base_revision_id,
        "kind": TARGETED_CORRECTION_KIND,
        "status": "approved",
        "processor_version": TARGETED_CORRECTION_PROCESSOR_VERSION,
        "content_path": content_path,
        "content_sha256": content_sha256,
        "lexical_sha256": lexical_hash,
        "char_count": char_count,
        "replacement_occurrence_count": 1,
        "is_active": True,
    }
