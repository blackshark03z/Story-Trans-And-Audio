CREATE TABLE IF NOT EXISTS speaker_assignment_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    text_revision_id INTEGER NOT NULL REFERENCES text_revisions(id),
    input_fingerprint TEXT NOT NULL,
    character_bible_fingerprint TEXT NOT NULL,
    model_id TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    response_schema TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('unassigned_only','reanalyze')),
    status TEXT NOT NULL CHECK(status IN ('generated','partially_invalid','failed','superseded')),
    content_path TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    target_count INTEGER NOT NULL,
    valid_count INTEGER NOT NULL,
    invalid_count INTEGER NOT NULL,
    cache_hit_count INTEGER NOT NULL DEFAULT 0,
    cache_miss_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(input_fingerprint, content_sha256)
);

CREATE TABLE IF NOT EXISTS speaker_assignment_draft_characters (
    draft_id INTEGER NOT NULL REFERENCES speaker_assignment_drafts(id) ON DELETE CASCADE,
    character_id INTEGER NOT NULL REFERENCES characters(id),
    PRIMARY KEY(draft_id, character_id)
);

CREATE INDEX IF NOT EXISTS idx_speaker_drafts_chapter_created
ON speaker_assignment_drafts(chapter_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_speaker_drafts_input
ON speaker_assignment_drafts(input_fingerprint);
