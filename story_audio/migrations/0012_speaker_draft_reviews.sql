PRAGMA foreign_keys=OFF;

CREATE TABLE speaker_assignment_drafts_new (
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
    status TEXT NOT NULL CHECK(status IN ('generated','partially_invalid','failed','superseded','approved')),
    content_path TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    target_count INTEGER NOT NULL,
    valid_count INTEGER NOT NULL,
    invalid_count INTEGER NOT NULL,
    cache_hit_count INTEGER NOT NULL DEFAULT 0,
    cache_miss_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    UNIQUE(input_fingerprint, content_sha256)
);

INSERT INTO speaker_assignment_drafts_new(
    id,book_id,chapter_id,text_revision_id,input_fingerprint,character_bible_fingerprint,
    model_id,prompt_version,response_schema,mode,status,content_path,content_sha256,
    target_count,valid_count,invalid_count,cache_hit_count,cache_miss_count,created_at,approved_at
)
SELECT
    id,book_id,chapter_id,text_revision_id,input_fingerprint,character_bible_fingerprint,
    model_id,prompt_version,response_schema,mode,status,content_path,content_sha256,
    target_count,valid_count,invalid_count,cache_hit_count,cache_miss_count,created_at,NULL
FROM speaker_assignment_drafts;

DROP TABLE speaker_assignment_drafts;
ALTER TABLE speaker_assignment_drafts_new RENAME TO speaker_assignment_drafts;

CREATE INDEX IF NOT EXISTS idx_speaker_drafts_chapter_created
ON speaker_assignment_drafts(chapter_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_speaker_drafts_input
ON speaker_assignment_drafts(input_fingerprint);

CREATE TABLE IF NOT EXISTS speaker_assignment_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL REFERENCES speaker_assignment_drafts(id) ON DELETE CASCADE,
    utterance_id TEXT NOT NULL,
    speaker_type TEXT NOT NULL,
    character_id INTEGER REFERENCES characters(id),
    decision_source TEXT NOT NULL,
    operator_note TEXT,
    reviewed_by TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(draft_id, utterance_id)
);

CREATE INDEX IF NOT EXISTS idx_speaker_assignment_reviews_draft
ON speaker_assignment_reviews(draft_id, utterance_id);

PRAGMA foreign_keys=ON;
