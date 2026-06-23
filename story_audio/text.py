from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass


TERMINAL = re.compile(r"[.!?…][\"”’')\]]*$")
AD_PATTERNS = (
    re.compile(r"(?i)bản dịch tại"),
    re.compile(r"(?i)vui lòng không copy"),
    re.compile(r"(?i)truyenfull\.?vn"),
    re.compile(r"(?i)bach\s*[,._-]?\s*ngoc\s*[,._-]?\s*sach"),
)
REPAIR_BLOCK_STRATEGY_VERSION = "repair-block-v1-target1900-max2500"
LEXICAL_VALIDATOR_VERSION = "lexical-token-v1"


@dataclass(frozen=True)
class QaIssue:
    code: str
    severity: str
    message: str
    details: dict


def normalize_space(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    return re.sub(r"[ \t\f\v]+", " ", text).strip()


def is_ad_line(text: str) -> bool:
    return any(pattern.search(text) for pattern in AD_PATTERNS)


def reflow_paragraphs(paragraphs: list[str], chapter_title: str) -> tuple[str, list[QaIssue]]:
    kept: list[str] = []
    issues: list[QaIssue] = []
    title_key = normalize_space(chapter_title).casefold()
    for index, raw in enumerate(paragraphs):
        value = normalize_space(raw)
        if not value:
            continue
        if value.casefold() == title_key:
            issues.append(QaIssue("duplicate_title", "info", "Đã bỏ tiêu đề chương lặp.", {"index": index, "text": value}))
            continue
        if is_ad_line(value):
            issues.append(QaIssue("advertisement", "warning", "Đã loại dòng quảng cáo/watermark.", {"index": index, "text": value}))
            continue
        kept.append(value)
    text = normalize_space(" ".join(kept))
    return text, issues


LEXICAL_TOKEN_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", flags=re.UNICODE)


def lexical_tokens(text: str) -> list[str]:
    return LEXICAL_TOKEN_RE.findall(unicodedata.normalize("NFC", text))


def lexical_sha256(text: str) -> str:
    payload = "\u001f".join(lexical_tokens(text)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_lexical_identity(source: str, repaired: str) -> tuple[bool, str | None]:
    source_tokens = lexical_tokens(source)
    repaired_tokens = lexical_tokens(repaired)
    if source_tokens == repaired_tokens:
        return True, None
    for index, (left, right) in enumerate(zip(source_tokens, repaired_tokens)):
        if left != right:
            return False, f"Token #{index + 1} changed: {left!r} -> {right!r}"
    return False, f"Token count changed: {len(source_tokens)} -> {len(repaired_tokens)}"


def restore_source_token_spelling(source: str, repaired: str) -> str:
    """Keep Gemini punctuation/spacing but restore every source token exactly."""
    source_tokens = lexical_tokens(source)
    matches = list(LEXICAL_TOKEN_RE.finditer(unicodedata.normalize("NFC", repaired)))
    repaired_tokens = [match.group(0) for match in matches]
    if [token.casefold() for token in source_tokens] != [token.casefold() for token in repaired_tokens]:
        valid, reason = validate_lexical_identity(source, repaired)
        raise ValueError(reason or "Gemini changed lexical tokens.")
    parts: list[str] = []
    cursor = 0
    normalized = unicodedata.normalize("NFC", repaired)
    for source_token, match in zip(source_tokens, matches):
        parts.append(normalized[cursor : match.start()])
        parts.append(source_token)
        cursor = match.end()
    parts.append(normalized[cursor:])
    return "".join(parts)


def qa_text(text: str) -> list[QaIssue]:
    issues: list[QaIssue] = []
    if len(text) < 100:
        issues.append(QaIssue("too_short", "error", "Chương quá ngắn để tạo audio.", {"char_count": len(text)}))
    if re.search(r"<[^>]+>", text):
        issues.append(QaIssue("html_residue", "error", "Text còn chứa HTML.", {}))
    if "�" in text or re.search(r"Ã.|á»|Ä.", text):
        issues.append(QaIssue("encoding_noise", "error", "Text có dấu hiệu lỗi mã hóa.", {}))
    chinese = re.findall(r"[\u4e00-\u9fff]", text)
    if chinese:
        issues.append(QaIssue("han_characters", "warning", "Text chứa ký tự Hán cần kiểm tra.", {"count": len(chinese)}))
    long_runs = [part for part in re.split(r"(?<=[.!?…])\s+", text) if len(part) > 500]
    if long_runs:
        issues.append(QaIssue("missing_punctuation", "warning", "Có đoạn rất dài thiếu điểm ngắt mạnh.", {"count": len(long_runs), "max_chars": max(map(len, long_runs))}))
    for pattern in AD_PATTERNS:
        if pattern.search(text):
            issues.append(QaIssue("advertisement_residue", "warning", "Text vẫn có dấu hiệu quảng cáo/watermark.", {}))
            break
    return issues


def split_repair_blocks(text: str, target: int = 1900, maximum: int = 2500) -> list[str]:
    sentences = re.split(r"(?<=[.!?…])\s+", normalize_space(text))
    blocks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > target:
            blocks.append(current)
            current = sentence
        else:
            current = candidate
        while len(current) > maximum:
            cut = current.rfind(" ", 0, maximum)
            cut = cut if cut > maximum // 2 else maximum
            blocks.append(current[:cut].strip())
            current = current[cut:].strip()
    if current:
        blocks.append(current)
    return blocks


def split_tts_segments(text: str, maximum: int = 256, target: int = 230) -> list[str]:
    sentences = re.split(r"(?<=[.!?…])\s+", normalize_space(text))
    segments: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > target:
            segments.append(current)
            current = sentence
        else:
            current = candidate
        while len(current) > maximum:
            cut = max(
                current.rfind(", ", 0, maximum),
                current.rfind("; ", 0, maximum),
                current.rfind(": ", 0, maximum),
                current.rfind(" ", 0, maximum),
            )
            cut = cut + 1 if cut > maximum // 2 else maximum
            segments.append(current[:cut].strip())
            current = current[cut:].strip()
    if current:
        segments.append(current)
    return [segment for segment in segments if segment]
