CREATE TABLE IF NOT EXISTS book_voice_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL UNIQUE REFERENCES books(id) ON DELETE CASCADE,
    narrator_voice_id TEXT NOT NULL,
    male_dialogue_voice_id TEXT NOT NULL,
    female_dialogue_voice_id TEXT NOT NULL,
    unknown_fallback TEXT NOT NULL DEFAULT 'narrator'
        CHECK(unknown_fallback IN ('narrator','male_dialogue','female_dialogue','explicit_voice')),
    unknown_voice_id TEXT,
    config_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK(unknown_fallback != 'explicit_voice' OR unknown_voice_id IS NOT NULL)
);

ALTER TABLE characters ADD COLUMN gender TEXT
    CHECK(gender IS NULL OR gender IN ('male','female','unknown'));
ALTER TABLE characters ADD COLUMN voice_override_id TEXT;

UPDATE characters
SET voice_override_id=default_voice_id
WHERE voice_override_id IS NULL AND default_voice_id != '';

CREATE INDEX IF NOT EXISTS idx_characters_book_gender ON characters(book_id, gender, active);
