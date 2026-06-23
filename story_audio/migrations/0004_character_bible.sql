ALTER TABLE characters ADD COLUMN external_key TEXT;
ALTER TABLE characters ADD COLUMN external_key_normalized TEXT;
ALTER TABLE characters ADD COLUMN canonical_name TEXT;
ALTER TABLE characters ADD COLUMN canonical_name_normalized TEXT;
ALTER TABLE characters ADD COLUMN role TEXT NOT NULL DEFAULT 'unknown'
    CHECK(role IN ('main','supporting','minor','unknown'));
ALTER TABLE characters ADD COLUMN age_group TEXT
    CHECK(age_group IS NULL OR age_group IN ('child','teen','young_adult','adult','elder','unknown'));
ALTER TABLE characters ADD COLUMN description TEXT;
ALTER TABLE characters ADD COLUMN speech_style TEXT;
ALTER TABLE characters ADD COLUMN visual_notes TEXT;
ALTER TABLE characters ADD COLUMN notes TEXT;
ALTER TABLE characters ADD COLUMN bible_schema TEXT;
ALTER TABLE characters ADD COLUMN bible_source_sha256 TEXT;
ALTER TABLE characters ADD COLUMN bible_source_label TEXT;
ALTER TABLE characters ADD COLUMN bible_imported_at TEXT;
ALTER TABLE characters ADD COLUMN bible_last_imported_at TEXT;

UPDATE characters
SET canonical_name=display_name,
    canonical_name_normalized=lower(trim(display_name))
WHERE canonical_name IS NULL;

CREATE TABLE IF NOT EXISTS character_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_normalized TEXT NOT NULL,
    source_sha256 TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(character_id, alias_normalized)
);

CREATE TABLE IF NOT EXISTS character_bible_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    schema_name TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_label TEXT NOT NULL,
    character_count INTEGER NOT NULL,
    create_count INTEGER NOT NULL,
    update_count INTEGER NOT NULL,
    alias_add_count INTEGER NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_characters_book_external_key
ON characters(book_id, external_key_normalized)
WHERE external_key_normalized IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_characters_book_canonical
ON characters(book_id, canonical_name_normalized, active);

CREATE INDEX IF NOT EXISTS idx_character_aliases_book_normalized
ON character_aliases(book_id, alias_normalized);

CREATE INDEX IF NOT EXISTS idx_character_bible_imports_book_hash
ON character_bible_imports(book_id, source_sha256);
