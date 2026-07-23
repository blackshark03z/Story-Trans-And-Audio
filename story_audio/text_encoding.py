from __future__ import annotations

from pathlib import Path
from typing import Any

from .files import sha256_text
from .storage import ContentStore


TEXT_ENCODING_INVALID = "TEXT_ENCODING_INVALID"
TEXT_REVISION_INTEGRITY_INVALID = "TEXT_REVISION_INTEGRITY_INVALID"


class CanonicalTextValidationError(ValueError):
    """Fail-closed validation error for canonical text and revision blobs."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _legacy_byte(char: str) -> int | None:
    codepoint = ord(char)
    if codepoint <= 0xFF:
        return codepoint
    try:
        encoded = char.encode("cp1252")
    except UnicodeEncodeError:
        return None
    return encoded[0] if len(encoded) == 1 else None


def _contains_legacy_decoded_utf8(text: str) -> bool:
    """Detect legacy-code-page characters that reconstruct valid UTF-8."""
    for start, char in enumerate(text):
        lead = _legacy_byte(char)
        if lead is None:
            continue
        if 0xC2 <= lead <= 0xDF:
            width = 2
        elif 0xE0 <= lead <= 0xEF:
            width = 3
        elif 0xF0 <= lead <= 0xF4:
            width = 4
        else:
            continue
        if start + width > len(text):
            continue
        values = [_legacy_byte(item) for item in text[start : start + width]]
        if any(value is None for value in values):
            continue
        raw = bytes(value for value in values if value is not None)
        if all(0x80 <= value <= 0xBF for value in raw[1:]):
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            return True
    return False


def validate_canonical_text(text: str, *, field: str = "text") -> None:
    """Require valid UTF-8 text without controls or strong mojibake evidence."""
    if not isinstance(text, str):
        raise CanonicalTextValidationError(
            TEXT_ENCODING_INVALID,
            f"{field} must be Unicode text",
        )
    try:
        encoded = text.encode("utf-8")
        if encoded.decode("utf-8") != text:
            raise UnicodeError("UTF-8 round trip changed text")
    except UnicodeError as exc:
        raise CanonicalTextValidationError(
            TEXT_ENCODING_INVALID,
            f"{field} is not valid round-trip UTF-8",
        ) from exc

    disallowed_controls = [
        char
        for char in text
        if (ord(char) < 0x20 and char not in "\t\n\r")
        or 0x7F <= ord(char) <= 0x9F
    ]
    if disallowed_controls:
        raise CanonicalTextValidationError(
            TEXT_ENCODING_INVALID,
            f"{field} contains disallowed C0/C1 control characters",
        )
    if _contains_legacy_decoded_utf8(text):
        raise CanonicalTextValidationError(
            TEXT_ENCODING_INVALID,
            f"{field} contains probable UTF-8 mojibake",
        )


def _validate_revision_text(
    text: str,
    revision: Any,
    *,
    field: str,
) -> str:
    try:
        expected_sha = str(revision["content_sha256"])
        expected_chars = int(revision["char_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CanonicalTextValidationError(
            TEXT_REVISION_INTEGRITY_INVALID,
            f"{field} immutable record is incomplete",
        ) from exc
    if sha256_text(text) != expected_sha:
        raise CanonicalTextValidationError(
            TEXT_REVISION_INTEGRITY_INVALID,
            f"{field} blob hash does not match its immutable record",
        )
    if len(text) != expected_chars:
        raise CanonicalTextValidationError(
            TEXT_REVISION_INTEGRITY_INVALID,
            f"{field} character count does not match its immutable record",
        )
    validate_canonical_text(text, field=field)
    return text


def load_validated_text_revision(
    store: ContentStore,
    revision: Any,
    *,
    field: str = "Text Revision",
) -> str:
    """Read and validate an immutable Text Revision record and its blob."""
    try:
        text = store.read_text(str(revision["content_path"]))
    except (KeyError, OSError, TypeError, UnicodeError, ValueError) as exc:
        raise CanonicalTextValidationError(
            TEXT_REVISION_INTEGRITY_INVALID,
            f"{field} blob cannot be read safely",
        ) from exc
    return _validate_revision_text(text, revision, field=field)


def load_validated_text_revision_from_root(
    blobs_root: Path,
    revision: Any,
    *,
    field: str = "Text Revision",
) -> str:
    """Read a revision from an explicit blob root without constructing a store."""
    try:
        root = Path(blobs_root).resolve()
        target = (root / str(revision["content_path"])).resolve()
        if target == root or root not in target.parents:
            raise ValueError("revision content path escapes the blob root")
        text = target.read_text(encoding="utf-8")
    except (KeyError, OSError, TypeError, UnicodeError, ValueError) as exc:
        raise CanonicalTextValidationError(
            TEXT_REVISION_INTEGRITY_INVALID,
            f"{field} blob cannot be read safely",
        ) from exc
    return _validate_revision_text(text, revision, field=field)


__all__ = [
    "CanonicalTextValidationError",
    "TEXT_ENCODING_INVALID",
    "TEXT_REVISION_INTEGRITY_INVALID",
    "load_validated_text_revision",
    "load_validated_text_revision_from_root",
    "validate_canonical_text",
]
