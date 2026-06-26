-- Migration 0006: Custom Reference Voices
-- Immutable revision-based custom voice management with content-addressed audio storage

CREATE TABLE IF NOT EXISTS custom_voices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL UNIQUE,
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_custom_voices_active
ON custom_voices(is_active, display_name);

CREATE TABLE IF NOT EXISTS custom_voice_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    custom_voice_id INTEGER NOT NULL REFERENCES custom_voices(id) ON DELETE RESTRICT,
    revision_number INTEGER NOT NULL CHECK(revision_number > 0),
    audio_storage_key TEXT NOT NULL,
    audio_sha256 TEXT NOT NULL,
    reference_transcript TEXT NOT NULL,
    transcript_sha256 TEXT NOT NULL,
    duration_ms INTEGER NOT NULL CHECK(duration_ms > 0),
    sample_rate INTEGER NOT NULL CHECK(sample_rate > 0),
    channels INTEGER NOT NULL CHECK(channels > 0),
    audio_format TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(custom_voice_id, revision_number)
);

CREATE INDEX IF NOT EXISTS idx_custom_voice_revisions_audio_sha
ON custom_voice_revisions(audio_sha256);
