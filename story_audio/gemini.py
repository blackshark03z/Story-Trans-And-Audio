from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .text import restore_source_token_spelling, validate_lexical_identity


SYSTEM_PROMPT = """Bạn là bộ phục hồi dấu câu tiếng Việt cho văn bản truyện.

CHỈ ĐƯỢC:
- thêm, xóa hoặc thay đổi dấu câu;
- thay đổi khoảng trắng và xuống đoạn;
- chuẩn hóa kiểu dấu ngoặc kép.

TUYỆT ĐỐI KHÔNG ĐƯỢC:
- thêm, xóa, thay hoặc đảo thứ tự bất kỳ từ/chữ/số nào;
- sửa tên riêng, thuật ngữ, lỗi chính tả hoặc văn phong;
- tóm tắt, giải thích, dịch hoặc xóa quảng cáo.

Giữ chính xác toàn bộ chuỗi từ theo đúng thứ tự. Trả về JSON object đúng schema, không markdown."""

REPAIR_CONTRACT_VERSION = "punctuation-only-v1"
GENERATION_SETTINGS = {"temperature": 0, "response_mime_type": "application/json"}


@dataclass(frozen=True)
class RepairResult:
    text: str
    raw_response: str


class GeminiRepairError(RuntimeError):
    pass


def _extract_json_text(body: dict) -> str:
    candidates = body.get("candidates") or []
    if not candidates:
        raise GeminiRepairError("Gemini không trả candidate.")
    parts = candidates[0].get("content", {}).get("parts", [])
    value = "\n".join(str(part.get("text", "")) for part in parts).strip()
    if not value:
        raise GeminiRepairError("Gemini trả nội dung rỗng.")
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", value, flags=re.DOTALL)
    return fence.group(1).strip() if fence else value


def repair_punctuation(
    *,
    api_key: str,
    model: str,
    block_id: str,
    text: str,
    max_attempts: int = 3,
) -> RepairResult:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": json.dumps(
                            {"block_id": block_id, "source_text": text},
                            ensure_ascii=False,
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "block_id": {"type": "STRING"},
                    "repaired_text": {"type": "STRING"},
                },
                "required": ["block_id", "repaired_text"],
            },
        },
    }
    request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        request = urllib.request.Request(
            url,
            data=request_body,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                body_text = response.read().decode("utf-8")
            body = json.loads(body_text)
            raw_json = _extract_json_text(body)
            result = json.loads(raw_json)
            if str(result.get("block_id")) != block_id:
                raise GeminiRepairError("Gemini trả sai block_id.")
            repaired = str(result.get("repaired_text") or "").strip()
            if not repaired:
                raise GeminiRepairError("Gemini trả repaired_text rỗng.")
            try:
                repaired = restore_source_token_spelling(text, repaired)
            except ValueError as exc:
                raise GeminiRepairError(f"Lexical integrity failed: {exc}") from exc
            valid, reason = validate_lexical_identity(text, repaired)
            if not valid:
                raise GeminiRepairError(f"Lexical integrity failed: {reason}")
            return RepairResult(repaired, raw_json)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = f"Gemini HTTP {exc.code}: {detail[:500]}"
            if exc.code in {400, 401, 403}:
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, GeminiRepairError) as exc:
            last_error = str(exc)
            if "Lexical integrity" in last_error and attempt >= max_attempts:
                break
        if attempt < max_attempts:
            time.sleep(min(8.0, (2 ** (attempt - 1)) + random.random()))
    raise GeminiRepairError(last_error or "Gemini punctuation repair thất bại.")
