-- Migration 0009: Segment Attempt History for Verified Segment Regeneration
-- Allows regenerating verified segments with side-by-side comparison before accepting

CREATE TABLE IF NOT EXISTS segment_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'candidate', 'rejected', 'superseded')),
    wav_path TEXT NOT NULL,
    audio_sha256 TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    accepted_at TEXT, -- when promoted to active
    rejected_at TEXT, -- when rejected
    superseded_at TEXT, -- when replaced by a newer active
    UNIQUE(segment_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_segment_attempts_segment
ON segment_attempts(segment_id, status);

CREATE INDEX IF NOT EXISTS idx_segment_attempts_status
ON segment_attempts(status);

-- Partial unique indexes: only one active and one candidate per segment
CREATE UNIQUE INDEX IF NOT EXISTS idx_segment_attempts_one_active
ON segment_attempts(segment_id) WHERE status = 'active';

CREATE UNIQUE INDEX IF NOT EXISTS idx_segment_attempts_one_candidate
ON segment_attempts(segment_id) WHERE status = 'candidate';
