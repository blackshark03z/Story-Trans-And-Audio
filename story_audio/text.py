from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher


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


@dataclass(frozen=True)
class OrthographicChangeCluster:
    source_token_range: tuple[int, int]
    candidate_token_range: tuple[int, int]
    source_tokens: tuple[str, ...]
    candidate_tokens: tuple[str, ...]
    source_skeleton: str
    candidate_skeleton: str
    skeletons_match: bool


@dataclass(frozen=True)
class OrthographicComparisonResult:
    qualifies: bool
    reason_code: str | None
    reason: str | None
    changed_cluster_count: int
    total_changed_source_tokens: int
    total_changed_candidate_tokens: int
    clusters: tuple[OrthographicChangeCluster, ...]


@dataclass(frozen=True)
class RepairCandidateValidation:
    accepted_text: str
    classification: str
    strict_reason: str | None
    orthographic_comparison: OrthographicComparisonResult | None = None


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
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>'\"]+")
NUMBER_RE = re.compile(r"(?<![^\W_])\d+(?:[.,]\d+)*(?![^\W_])", flags=re.UNICODE)
PROTECTED_STRUCTURAL_MARKER_RE = re.compile(
    r"<!--.*?-->|</?[^>\s]+(?:\s+[^<>]*?)?>|\{\{[^{}]*\}\}|\[[A-Z0-9_][A-Z0-9_ .:-]*\]|"
    r"^\s*(?:#{1,6}\s+|[-*_]{3,}\s*$)",
    flags=re.MULTILINE,
)


def lexical_tokens(text: str) -> list[str]:
    return LEXICAL_TOKEN_RE.findall(unicodedata.normalize("NFC", text))


def lexical_sha256(text: str) -> str:
    payload = "\u001f".join(lexical_tokens(text)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def orthographic_skeleton(text: str) -> str:
    skeleton: list[str] = []
    normalized = unicodedata.normalize("NFD", text.casefold())
    for char in normalized:
        category = unicodedata.category(char)
        if category.startswith("M"):
            continue
        if category.startswith("L") or category == "Nd":
            skeleton.append(char)
    return "".join(skeleton)


def _extract_urls(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFC", text)
    trailing = ".,;:!?)]}”’\"'"
    return tuple(match.group(0).rstrip(trailing) for match in URL_RE.finditer(normalized))


def _extract_numbers(text: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in NUMBER_RE.finditer(unicodedata.normalize("NFC", text)))


def _extract_protected_structural_markers(text: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in PROTECTED_STRUCTURAL_MARKER_RE.finditer(unicodedata.normalize("NFC", text)))


def compare_bounded_orthographic_changes(source: str, candidate: str) -> OrthographicComparisonResult:
    source_urls = _extract_urls(source)
    candidate_urls = _extract_urls(candidate)
    if source_urls != candidate_urls:
        return OrthographicComparisonResult(
            False,
            "urls_changed",
            "URLs changed.",
            0,
            0,
            0,
            (),
        )

    source_numbers = _extract_numbers(source)
    candidate_numbers = _extract_numbers(candidate)
    if source_numbers != candidate_numbers:
        return OrthographicComparisonResult(
            False,
            "numbers_changed",
            "Numbers changed.",
            0,
            0,
            0,
            (),
        )

    source_markers = _extract_protected_structural_markers(source)
    candidate_markers = _extract_protected_structural_markers(candidate)
    if source_markers != candidate_markers:
        return OrthographicComparisonResult(
            False,
            "protected_structural_markers_changed",
            "Protected structural markers changed.",
            0,
            0,
            0,
            (),
        )

    source_tokens = lexical_tokens(source)
    candidate_tokens = lexical_tokens(candidate)
    clusters: list[OrthographicChangeCluster] = []
    matcher = SequenceMatcher(None, source_tokens, candidate_tokens, autojunk=False)
    for tag, source_start, source_end, candidate_start, candidate_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed_source = tuple(source_tokens[source_start:source_end])
        changed_candidate = tuple(candidate_tokens[candidate_start:candidate_end])
        source_skeleton = orthographic_skeleton("".join(changed_source))
        candidate_skeleton = orthographic_skeleton("".join(changed_candidate))
        clusters.append(
            OrthographicChangeCluster(
                source_token_range=(source_start, source_end),
                candidate_token_range=(candidate_start, candidate_end),
                source_tokens=changed_source,
                candidate_tokens=changed_candidate,
                source_skeleton=source_skeleton,
                candidate_skeleton=candidate_skeleton,
                skeletons_match=source_skeleton == candidate_skeleton,
            )
        )

    changed_cluster_count = len(clusters)
    total_source = sum(len(cluster.source_tokens) for cluster in clusters)
    total_candidate = sum(len(cluster.candidate_tokens) for cluster in clusters)

    for cluster in clusters:
        if len(cluster.source_tokens) > 3:
            return OrthographicComparisonResult(
                False,
                "cluster_source_token_limit_exceeded",
                "A changed cluster has more than 3 source tokens.",
                changed_cluster_count,
                total_source,
                total_candidate,
                tuple(clusters),
            )
        if len(cluster.candidate_tokens) > 3:
            return OrthographicComparisonResult(
                False,
                "cluster_candidate_token_limit_exceeded",
                "A changed cluster has more than 3 candidate tokens.",
                changed_cluster_count,
                total_source,
                total_candidate,
                tuple(clusters),
            )

    if changed_cluster_count > 2:
        return OrthographicComparisonResult(
            False,
            "changed_cluster_limit_exceeded",
            "More than 2 changed clusters.",
            changed_cluster_count,
            total_source,
            total_candidate,
            tuple(clusters),
        )
    if total_source > 4:
        return OrthographicComparisonResult(
            False,
            "total_source_token_limit_exceeded",
            "More than 4 total changed source tokens.",
            changed_cluster_count,
            total_source,
            total_candidate,
            tuple(clusters),
        )
    if total_candidate > 4:
        return OrthographicComparisonResult(
            False,
            "total_candidate_token_limit_exceeded",
            "More than 4 total changed candidate tokens.",
            changed_cluster_count,
            total_source,
            total_candidate,
            tuple(clusters),
        )

    for cluster in clusters:
        if not cluster.skeletons_match:
            if not cluster.source_tokens or not cluster.candidate_tokens:
                reason_code = "semantic_insertion_or_deletion"
                reason = "Semantic insertion or deletion changed the cluster skeleton."
            else:
                reason_code = "skeleton_mismatch"
                reason = "A changed cluster has different source and candidate skeletons."
            return OrthographicComparisonResult(
                False,
                reason_code,
                reason,
                changed_cluster_count,
                total_source,
                total_candidate,
                tuple(clusters),
            )

    return OrthographicComparisonResult(
        True,
        None,
        None,
        changed_cluster_count,
        total_source,
        total_candidate,
        tuple(clusters),
    )


def validate_lexical_identity(source: str, repaired: str) -> tuple[bool, str | None]:
    source_tokens = lexical_tokens(source)
    repaired_tokens = lexical_tokens(repaired)
    if source_tokens == repaired_tokens:
        return True, None
    for index, (left, right) in enumerate(zip(source_tokens, repaired_tokens)):
        if left != right:
            return False, f"Token #{index + 1} changed: {left!r} -> {right!r}"
    return False, f"Token count changed: {len(source_tokens)} -> {len(repaired_tokens)}"


def validate_repair_candidate(source: str, candidate: str) -> RepairCandidateValidation:
    normalized_candidate = unicodedata.normalize("NFC", candidate)
    valid, strict_reason = validate_lexical_identity(source, normalized_candidate)
    if valid:
        return RepairCandidateValidation(
            accepted_text=normalized_candidate,
            classification="strict_lexical_identity",
            strict_reason=None,
        )

    comparison = compare_bounded_orthographic_changes(source, normalized_candidate)
    if comparison.qualifies:
        return RepairCandidateValidation(
            accepted_text=normalized_candidate,
            classification="bounded_orthographic_repair",
            strict_reason=strict_reason,
            orthographic_comparison=comparison,
        )
    raise ValueError(strict_reason or comparison.reason or "Lexical integrity failed.")


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
