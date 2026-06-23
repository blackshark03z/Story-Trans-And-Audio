from __future__ import annotations

import difflib
import re
from typing import Any

from .db import Database
from .files import sha256_text
from .storage import ContentStore
from .text import lexical_tokens, validate_lexical_identity


DIFF_ALGORITHM_VERSION = "story-block-token-v1"
MAX_DIFF_CHARACTERS = 500_000
LARGE_DIFF_WARNING_CHARACTERS = 50_000
TOKEN_RE = re.compile(r"\s+|[^\W_]+(?:['’][^\W_]+)?|[^\w\s]", re.UNICODE)


class TextDiffError(ValueError):
    pass


def _blocks(text: str) -> list[str]:
    if not text:
        return []
    values = [match.group(0) for match in re.finditer(r".*?(?:\n\s*\n+|\Z)", text, re.DOTALL)]
    return [value for value in values if value]


def _block_key(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def _is_whitespace(values: list[str]) -> bool:
    return bool(values) and all(value.isspace() for value in values)


def _token_operations(left: str, right: str) -> list[dict[str, Any]]:
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    matcher = difflib.SequenceMatcher(
        None,
        left_tokens,
        right_tokens,
        autojunk=max(len(left_tokens), len(right_tokens)) > 2_000,
    )
    operations: list[dict[str, Any]] = []
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        left_values, right_values = left_tokens[a1:a2], right_tokens[b1:b2]
        operations.append(
            {
                "status": tag,
                "left": "".join(left_values),
                "right": "".join(right_values),
                "whitespace_only": _is_whitespace(left_values + right_values),
            }
        )
    return operations


def _sequence_change_count(left: list[str], right: list[str]) -> tuple[int, int]:
    added = removed = 0
    for tag, a1, a2, b1, b2 in difflib.SequenceMatcher(
        None, left, right, autojunk=max(len(left), len(right)) > 2_000
    ).get_opcodes():
        if tag in {"delete", "replace"}:
            removed += a2 - a1
        if tag in {"insert", "replace"}:
            added += b2 - b1
    return added, removed


def _punctuation_tokens(text: str) -> list[str]:
    return [token for token in _tokens(text) if not token.isspace() and not lexical_tokens(token)]


def diff_texts(left: str, right: str) -> dict[str, Any]:
    if len(left) + len(right) > MAX_DIFF_CHARACTERS:
        raise TextDiffError(
            f"Combined revision text exceeds diff limit of {MAX_DIFF_CHARACTERS:,} characters"
        )
    left_blocks, right_blocks = _blocks(left), _blocks(right)
    matcher = difflib.SequenceMatcher(
        None,
        [_block_key(value) for value in left_blocks],
        [_block_key(value) for value in right_blocks],
        autojunk=False,
    )
    blocks: list[dict[str, Any]] = []
    changed = 0
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        left_value = "".join(left_blocks[a1:a2])
        right_value = "".join(right_blocks[b1:b2])
        if tag != "equal":
            changed += max(a2 - a1, b2 - b1, 1)
        blocks.append(
            {
                "status": tag,
                "left": left_value,
                "right": right_value,
                "operations": _token_operations(left_value, right_value),
                "collapsed_by_default": tag == "equal" and len(left_value) > 240,
            }
        )

    lexical_left, lexical_right = lexical_tokens(left), lexical_tokens(right)
    tokens_added, tokens_removed = _sequence_change_count(lexical_left, lexical_right)
    punctuation_added, punctuation_removed = _sequence_change_count(
        _punctuation_tokens(left), _punctuation_tokens(right)
    )
    lexical_ok, lexical_reason = validate_lexical_identity(left, right)
    denominator = max(len(lexical_left), len(lexical_right), 1)
    change_ratio = round((tokens_added + tokens_removed) / denominator, 6)
    warnings: list[str] = []
    if len(left) + len(right) > LARGE_DIFF_WARNING_CHARACTERS:
        warnings.append("Large diff payload; unchanged sections are collapsed by default.")
    if not lexical_ok:
        warnings.append("Lexical tokens differ; review before using this revision downstream.")
    return {
        "algorithm_version": DIFF_ALGORITHM_VERSION,
        "summary": {
            "blocks_changed": changed,
            "tokens_added": tokens_added,
            "tokens_removed": tokens_removed,
            "punctuation_changes": punctuation_added + punctuation_removed,
            "punctuation_added": punctuation_added,
            "punctuation_removed": punctuation_removed,
            "characters_a": len(left),
            "characters_b": len(right),
            "change_ratio": change_ratio,
            "lexical_integrity": lexical_ok,
            "lexical_reason": lexical_reason,
        },
        "warnings": warnings,
        "blocks": blocks,
    }


def revision_metadata(row: Any, chapter: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "chapter_id": int(row["chapter_id"]),
        "parent_revision_id": row["parent_revision_id"],
        "kind": row["kind"],
        "content_hash": row["content_sha256"],
        "short_hash": str(row["content_sha256"])[:12],
        "char_count": int(row["char_count"]),
        "processor_version": row["processor_version"],
        "status": row["status"],
        "created_at": row["created_at"],
        "is_raw_selected": int(chapter["raw_text_revision_id"] or 0) == int(row["id"]),
        "is_active": int(chapter["active_text_revision_id"] or 0) == int(row["id"]),
    }


def list_revision_metadata(db: Database, chapter_id: int) -> list[dict[str, Any]]:
    chapter = db.fetch_one("SELECT * FROM chapters WHERE id=?", (chapter_id,))
    if not chapter:
        raise TextDiffError("Chapter not found")
    return [
        revision_metadata(row, chapter)
        for row in db.fetch_all(
            "SELECT * FROM text_revisions WHERE chapter_id=? ORDER BY id", (chapter_id,)
        )
    ]


def build_revision_diff(
    db: Database,
    store: ContentStore,
    chapter_id: int,
    revision_a_id: int,
    revision_b_id: int,
) -> dict[str, Any]:
    chapter = db.fetch_one("SELECT * FROM chapters WHERE id=?", (chapter_id,))
    if not chapter:
        raise TextDiffError("Chapter not found")
    rows = db.fetch_all(
        "SELECT * FROM text_revisions WHERE id IN (?,?) ORDER BY id",
        (revision_a_id, revision_b_id),
    )
    by_id = {int(row["id"]): row for row in rows}
    if revision_a_id not in by_id or revision_b_id not in by_id:
        raise TextDiffError("Revision not found")
    left_row, right_row = by_id[revision_a_id], by_id[revision_b_id]
    if int(left_row["chapter_id"]) != chapter_id or int(right_row["chapter_id"]) != chapter_id:
        raise TextDiffError("Both revisions must belong to the same requested chapter")
    try:
        left = store.read_text(left_row["content_path"])
        right = store.read_text(right_row["content_path"])
    except (OSError, UnicodeError, ValueError) as exc:
        raise TextDiffError(f"Revision text blob is missing or unreadable: {exc}") from exc
    if sha256_text(left) != left_row["content_sha256"]:
        raise TextDiffError(f"Revision {revision_a_id} blob hash mismatch")
    if sha256_text(right) != right_row["content_sha256"]:
        raise TextDiffError(f"Revision {revision_b_id} blob hash mismatch")
    result = diff_texts(left, right)
    return {
        "chapter_id": chapter_id,
        "revision_a": revision_metadata(left_row, chapter),
        "revision_b": revision_metadata(right_row, chapter),
        **result,
    }
