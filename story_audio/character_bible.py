from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import Database, utcnow


SCHEMA = "story-audio-character-bible/v1"
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_CHARACTERS = 2_000
MAX_KEY = 120
MAX_NAME = 120
MAX_ALIAS = 120
MAX_METADATA = 4_000
GENDERS = {"male", "female", "unknown"}
ROLES = {"main", "supporting", "minor", "unknown"}
AGE_GROUPS = {"child", "teen", "young_adult", "adult", "elder", "unknown"}
COMMON_ALIAS_WARNINGS = {"hắn", "nàng", "lão giả", "thiếu niên", "người nọ"}
REQUIRED = {"external_key", "canonical_name", "aliases", "gender", "role"}
OPTIONAL = {
    "age_group", "description", "speech_style", "visual_notes", "notes", "voice_override_id"
}
UPDATE_FIELDS = {
    "gender", "role", "age_group", "description", "speech_style", "visual_notes", "notes"
}


class CharacterBibleError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedBible:
    schema: str
    book_title: str | None
    records: tuple[dict[str, Any], ...]
    source_sha256: str
    source_label: str


def normalize_identity(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).strip().split()).casefold()


def _display(value: Any, field: str, maximum: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise CharacterBibleError(f"{field} must be a string")
    cleaned = " ".join(unicodedata.normalize("NFC", value).strip().split())
    if not cleaned and not allow_empty:
        raise CharacterBibleError(f"{field} must not be empty")
    if len(cleaned) > maximum:
        raise CharacterBibleError(f"{field} exceeds {maximum} characters")
    return cleaned


def parse_character_bible(raw: bytes, *, source_label: str = "character_bible.json") -> ParsedBible:
    if not isinstance(raw, bytes):
        raise CharacterBibleError("Character Bible input must be bytes")
    if len(raw) > MAX_FILE_BYTES:
        raise CharacterBibleError(f"Character Bible exceeds {MAX_FILE_BYTES} bytes")
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CharacterBibleError(f"Invalid Character Bible JSON: {type(exc).__name__}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise CharacterBibleError(f"Unsupported Character Bible schema; expected {SCHEMA}")
    book = payload.get("book") or {}
    if not isinstance(book, dict):
        raise CharacterBibleError("book must be an object")
    title = book.get("title")
    book_title = _display(title, "book.title", 300) if title is not None else None
    items = payload.get("characters")
    if not isinstance(items, list):
        raise CharacterBibleError("characters must be an array")
    if len(items) > MAX_CHARACTERS:
        raise CharacterBibleError(f"Character count exceeds {MAX_CHARACTERS}")
    records: list[dict[str, Any]] = []
    seen_keys: dict[str, list[int]] = {}
    seen_names: dict[str, list[int]] = {}
    for index, item in enumerate(items):
        errors: list[str] = []
        warnings: list[str] = []
        record: dict[str, Any] = {"index": index, "errors": errors, "warnings": warnings}
        if not isinstance(item, dict):
            errors.append("character record must be an object")
            records.append(record)
            continue
        missing = sorted(REQUIRED - item.keys())
        if missing:
            errors.append(f"missing required fields: {', '.join(missing)}")
        unknown = sorted(set(item) - REQUIRED - OPTIONAL)
        if unknown:
            warnings.append(f"ignored unknown fields: {', '.join(unknown)}")
        for field, maximum in (("external_key", MAX_KEY), ("canonical_name", MAX_NAME)):
            try:
                record[field] = _display(item.get(field), field, maximum)
            except CharacterBibleError as exc:
                errors.append(str(exc))
        aliases = item.get("aliases")
        clean_aliases: list[str] = []
        if not isinstance(aliases, list):
            errors.append("aliases must be an array of strings")
        else:
            alias_norms: set[str] = set()
            canonical_norm = normalize_identity(record.get("canonical_name", ""))
            for alias_index, alias in enumerate(aliases):
                try:
                    cleaned = _display(alias, f"aliases[{alias_index}]", MAX_ALIAS)
                except CharacterBibleError as exc:
                    errors.append(str(exc))
                    continue
                normalized = normalize_identity(cleaned)
                if normalized == canonical_norm:
                    errors.append(f"alias duplicates canonical name: {cleaned}")
                elif normalized in alias_norms:
                    errors.append(f"duplicate alias: {cleaned}")
                else:
                    alias_norms.add(normalized)
                    clean_aliases.append(cleaned)
                    if normalized in COMMON_ALIAS_WARNINGS:
                        warnings.append(f"generic alias may be ambiguous: {cleaned}")
        record["aliases"] = clean_aliases
        for field, allowed in (("gender", GENDERS), ("role", ROLES)):
            value = item.get(field)
            if value not in allowed:
                errors.append(f"invalid {field}: {value}")
            else:
                record[field] = value
        age = item.get("age_group")
        if age is not None and age not in AGE_GROUPS:
            errors.append(f"invalid age_group: {age}")
        record["age_group"] = age
        for field in ("description", "speech_style", "visual_notes", "notes"):
            try:
                record[field] = _display(item.get(field, ""), field, MAX_METADATA, allow_empty=True)
            except CharacterBibleError as exc:
                errors.append(str(exc))
        voice = item.get("voice_override_id")
        if voice is not None:
            try:
                voice = _display(voice, "voice_override_id", 200)
            except CharacterBibleError as exc:
                errors.append(str(exc))
                voice = None
        record["voice_override_id"] = voice
        if record.get("external_key"):
            seen_keys.setdefault(normalize_identity(record["external_key"]), []).append(index)
        if record.get("canonical_name"):
            seen_names.setdefault(normalize_identity(record["canonical_name"]), []).append(index)
        records.append(record)
    for label, values in (("external_key", seen_keys), ("canonical_name", seen_names)):
        for normalized, indexes in values.items():
            if len(indexes) > 1:
                for index in indexes:
                    records[index]["errors"].append(f"duplicate normalized {label} in file: {normalized}")
    safe_label = Path(source_label).name[:255] or "character_bible.json"
    return ParsedBible(
        schema=SCHEMA,
        book_title=book_title,
        records=tuple(records),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        source_label=safe_label,
    )


def _character_maps(db: Database, book_id: int) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    characters = [dict(row) for row in db.fetch_all(
        "SELECT * FROM characters WHERE book_id=? AND active=1 ORDER BY id", (book_id,)
    )]
    aliases: dict[int, list[dict[str, Any]]] = {int(row["id"]): [] for row in characters}
    for row in db.fetch_all("SELECT * FROM character_aliases WHERE book_id=? ORDER BY id", (book_id,)):
        aliases.setdefault(int(row["character_id"]), []).append(dict(row))
    return characters, aliases


def plan_character_bible_import(
    db: Database,
    book_id: int,
    parsed: ParsedBible,
    *,
    allowed_voice_ids: set[str] | None = None,
    update_existing: bool = False,
) -> dict[str, Any]:
    book = db.fetch_one("SELECT id,title FROM books WHERE id=?", (book_id,))
    if not book:
        raise CharacterBibleError("Book not found")
    characters, aliases_by_character = _character_maps(db, book_id)
    external_map: dict[str, list[int]] = {}
    canonical_map: dict[str, list[int]] = {}
    alias_map: dict[str, set[int]] = {}
    by_id = {int(row["id"]): row for row in characters}
    for row in characters:
        character_id = int(row["id"])
        if row.get("external_key"):
            external_map.setdefault(normalize_identity(row["external_key"]), []).append(character_id)
        canonical = row.get("canonical_name") or row["display_name"]
        canonical_map.setdefault(normalize_identity(canonical), []).append(character_id)
        for alias in aliases_by_character.get(character_id, []):
            alias_map.setdefault(normalize_identity(alias["alias"]), set()).add(character_id)
    planned: list[dict[str, Any]] = []
    for record in parsed.records:
        item = {"index": record["index"], "external_key": record.get("external_key"),
                "canonical_name": record.get("canonical_name"), "warnings": list(record["warnings"]),
                "errors": list(record["errors"]), "character_id": None, "changes": {}, "aliases_to_add": []}
        if item["errors"]:
            item["action"] = "invalid"
            planned.append(item)
            continue
        key_norm = normalize_identity(record["external_key"])
        name_norm = normalize_identity(record["canonical_name"])
        ext_ids = external_map.get(key_norm, [])
        name_ids = canonical_map.get(name_norm, [])
        if len(ext_ids) > 1 or len(name_ids) > 1:
            item["action"] = "conflict"; item["errors"].append("existing identity is not unique")
            planned.append(item); continue
        if ext_ids and name_ids and ext_ids[0] != name_ids[0]:
            item["action"] = "conflict"; item["errors"].append("external key and canonical name match different characters")
            planned.append(item); continue
        matched_id = ext_ids[0] if ext_ids else (name_ids[0] if name_ids else None)
        if matched_id is None:
            alias_candidates: set[int] = set(alias_map.get(name_norm, set()))
            for alias in record["aliases"]:
                normalized = normalize_identity(alias)
                alias_candidates.update(alias_map.get(normalized, set()))
                alias_candidates.update(canonical_map.get(normalized, []))
            if len(alias_candidates) > 1:
                item["action"] = "conflict"; item["errors"].append("alias matches multiple characters")
                planned.append(item); continue
            matched_id = next(iter(alias_candidates), None)
        voice = record.get("voice_override_id")
        valid_voice = voice is None or allowed_voice_ids is None or voice in allowed_voice_ids
        if voice and not valid_voice:
            item["warnings"].append(f"voice preset is unavailable and will be ignored: {voice}")
        if matched_id is None:
            changes = {field: record.get(field) for field in (
                "external_key", "canonical_name", "gender", "role", "age_group", "description",
                "speech_style", "visual_notes", "notes"
            )}
            changes["voice_override_id"] = voice if valid_voice else None
            item.update(action="create", changes=changes, aliases_to_add=list(record["aliases"]))
            planned.append(item); continue
        current = by_id[matched_id]
        item["character_id"] = matched_id
        if current.get("external_key") and normalize_identity(current["external_key"]) != key_norm:
            item["action"] = "conflict"; item["errors"].append("matched character already has a different external key")
            planned.append(item); continue
        changes: dict[str, Any] = {}
        if not current.get("external_key"):
            changes["external_key"] = record["external_key"]
        for field in UPDATE_FIELDS:
            incoming = record.get(field)
            existing = current.get(field)
            empty = existing is None or existing == "" or (field in {"gender", "role", "age_group"} and existing == "unknown")
            if incoming not in (None, "") and incoming != existing and (empty or update_existing):
                changes[field] = incoming
        if update_existing and voice and valid_voice and voice != current.get("voice_override_id"):
            changes["voice_override_id"] = voice
        existing_aliases = {normalize_identity(row["alias"]) for row in aliases_by_character.get(matched_id, [])}
        aliases_to_add = [alias for alias in record["aliases"] if normalize_identity(alias) not in existing_aliases]
        item.update(action="update" if changes or aliases_to_add else "match", changes=changes, aliases_to_add=aliases_to_add)
        planned.append(item)
    summary = {
        "characters_total": len(planned),
        "create_count": sum(item["action"] == "create" for item in planned),
        "match_count": sum(item["action"] in {"match", "update"} for item in planned),
        "update_count": sum(item["action"] == "update" for item in planned),
        "alias_add_count": sum(len(item["aliases_to_add"]) for item in planned),
        "conflict_count": sum(item["action"] == "conflict" for item in planned),
        "warning_count": sum(len(item["warnings"]) for item in planned),
        "invalid_count": sum(item["action"] == "invalid" for item in planned),
    }
    return {"schema": parsed.schema, "book_id": book_id, "book_title": book["title"],
            "source_sha256": parsed.source_sha256, "source_label": parsed.source_label,
            "update_existing": update_existing, "summary": summary, "records": planned,
            "parsed_records": [dict(record) for record in parsed.records]}


def apply_character_bible_import(db: Database, plan: dict[str, Any]) -> dict[str, Any]:
    summary = plan["summary"]
    if summary["conflict_count"] or summary["invalid_count"]:
        raise CharacterBibleError("Import plan contains conflicts or invalid records; nothing was applied")
    records_by_index = {int(record["index"]): record for record in plan["parsed_records"]}
    now = utcnow()
    changed = 0
    with db.transaction() as connection:
        for item in plan["records"]:
            if item["action"] == "match":
                continue
            record = records_by_index[int(item["index"])]
            changes = dict(item["changes"])
            if item["action"] == "create":
                canonical = changes.pop("canonical_name")
                external = changes.pop("external_key")
                voice = changes.pop("voice_override_id", None)
                character_id = int(connection.execute(
                    """INSERT INTO characters(
                       book_id,display_name,default_voice_id,gender,voice_override_id,created_at,updated_at,
                       external_key,external_key_normalized,canonical_name,canonical_name_normalized,role,
                       age_group,description,speech_style,visual_notes,notes,bible_schema,bible_source_sha256,
                       bible_source_label,bible_imported_at,bible_last_imported_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (plan["book_id"], canonical, voice or "", changes.get("gender"), voice, now, now,
                     external, normalize_identity(external), canonical, normalize_identity(canonical),
                     changes.get("role") or "unknown", changes.get("age_group"), changes.get("description") or "",
                     changes.get("speech_style") or "", changes.get("visual_notes") or "", changes.get("notes") or "",
                     plan["schema"], plan["source_sha256"], plan["source_label"], now, now),
                ).lastrowid)
                item["character_id"] = character_id
            else:
                character_id = int(item["character_id"])
                fields: list[str] = []
                params: list[Any] = []
                for field, value in changes.items():
                    fields.append(f"{field}=?"); params.append(value)
                    if field == "external_key":
                        fields.append("external_key_normalized=?"); params.append(normalize_identity(value))
                if fields:
                    fields.extend(["bible_schema=?", "bible_source_sha256=?", "bible_source_label=?",
                                   "bible_imported_at=COALESCE(bible_imported_at,?)",
                                   "bible_last_imported_at=?", "updated_at=?"])
                    params.extend([plan["schema"], plan["source_sha256"], plan["source_label"],
                                   now, now, now, character_id])
                    connection.execute(f"UPDATE characters SET {','.join(fields)} WHERE id=?", tuple(params))
            for alias in item["aliases_to_add"]:
                connection.execute(
                    """INSERT OR IGNORE INTO character_aliases(
                       book_id,character_id,alias,alias_normalized,source_sha256,created_at
                       ) VALUES(?,?,?,?,?,?)""",
                    (plan["book_id"], character_id, alias, normalize_identity(alias), plan["source_sha256"], now),
                )
            changed += 1
        if changed:
            connection.execute(
                """INSERT INTO character_bible_imports(
                   book_id,schema_name,source_sha256,source_label,character_count,create_count,
                   update_count,alias_add_count,imported_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (plan["book_id"], plan["schema"], plan["source_sha256"], plan["source_label"],
                 summary["characters_total"], summary["create_count"], summary["update_count"],
                 summary["alias_add_count"], now),
            )
    if changed:
        db.audit("character_bible_imported", details={
            "book_id": plan["book_id"], "source_sha256": plan["source_sha256"],
            "create_count": summary["create_count"], "update_count": summary["update_count"],
            "alias_add_count": summary["alias_add_count"],
        })
    return {"applied": bool(changed), "changed_records": changed, "summary": summary}


__all__ = [
    "CharacterBibleError", "ParsedBible", "SCHEMA", "apply_character_bible_import",
    "normalize_identity", "parse_character_bible", "plan_character_bible_import",
]
