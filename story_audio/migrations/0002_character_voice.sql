CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    default_voice_id TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(book_id, display_name)
);

CREATE TABLE IF NOT EXISTS casting_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    text_revision_id INTEGER NOT NULL REFERENCES text_revisions(id),
    plan_revision INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft','approved','archived')),
    content_path TEXT NOT NULL,
    plan_sha256 TEXT NOT NULL,
    narrator_voice_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    archived_at TEXT,
    UNIQUE(chapter_id, plan_revision)
);

CREATE TABLE IF NOT EXISTS casting_plan_characters (
    casting_plan_id INTEGER NOT NULL REFERENCES casting_plans(id) ON DELETE CASCADE,
    character_id INTEGER NOT NULL REFERENCES characters(id),
    PRIMARY KEY(casting_plan_id, character_id)
);

ALTER TABLE jobs ADD COLUMN casting_plan_id INTEGER REFERENCES casting_plans(id);
ALTER TABLE jobs ADD COLUMN casting_snapshot_json TEXT;

ALTER TABLE job_chapters ADD COLUMN casting_plan_id INTEGER REFERENCES casting_plans(id);
ALTER TABLE job_chapters ADD COLUMN casting_plan_sha256 TEXT;
ALTER TABLE job_chapters ADD COLUMN voice_snapshot_json TEXT;

ALTER TABLE segments ADD COLUMN utterance_sequence INTEGER;
ALTER TABLE segments ADD COLUMN speaker_role TEXT;
ALTER TABLE segments ADD COLUMN character_id INTEGER REFERENCES characters(id);
ALTER TABLE segments ADD COLUMN resolved_voice_id TEXT;
ALTER TABLE segments ADD COLUMN synthesis_hash TEXT;

CREATE INDEX IF NOT EXISTS idx_characters_book_active ON characters(book_id, active);
CREATE INDEX IF NOT EXISTS idx_casting_plans_chapter_revision ON casting_plans(chapter_id, plan_revision);
CREATE INDEX IF NOT EXISTS idx_segments_synthesis_hash ON segments(synthesis_hash);
