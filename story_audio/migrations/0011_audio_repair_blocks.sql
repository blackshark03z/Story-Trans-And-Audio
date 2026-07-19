CREATE TABLE IF NOT EXISTS audio_repair_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    job_chapter_id INTEGER NOT NULL REFERENCES job_chapters(id),
    chapter_id INTEGER NOT NULL REFERENCES chapters(id),
    text_revision_id INTEGER NOT NULL REFERENCES text_revisions(id),
    casting_plan_id INTEGER REFERENCES casting_plans(id),
    casting_plan_sha256 TEXT,
    first_segment_id INTEGER NOT NULL REFERENCES segments(id),
    last_segment_id INTEGER NOT NULL REFERENCES segments(id),
    covered_segment_ids_json TEXT NOT NULL,
    first_sequence INTEGER NOT NULL,
    last_sequence INTEGER NOT NULL,
    source_start_offset INTEGER NOT NULL,
    source_end_offset INTEGER NOT NULL,
    source_text TEXT NOT NULL,
    source_text_sha256 TEXT NOT NULL,
    speaker_role TEXT NOT NULL,
    character_id INTEGER,
    resolved_voice_id TEXT NOT NULL,
    effective_voice_ref TEXT NOT NULL,
    custom_voice_revision_id INTEGER,
    voice_source_type TEXT NOT NULL,
    voice_provider TEXT NOT NULL,
    voice_model TEXT NOT NULL,
    logical_voice_ref TEXT NOT NULL,
    voice_resolution_reason TEXT NOT NULL,
    reference_audio_sha256 TEXT,
    reference_audio_storage_key TEXT,
    reference_transcript TEXT,
    reference_transcript_sha256 TEXT,
    synthesis_settings_json TEXT NOT NULL,
    synthesis_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('candidate','accepted','rejected','superseded')),
    candidate_wav_path TEXT NOT NULL,
    candidate_audio_sha256 TEXT NOT NULL,
    candidate_duration_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    accepted_at TEXT,
    rejected_at TEXT,
    superseded_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_audio_repair_blocks_job_chapter
ON audio_repair_blocks(job_chapter_id, status);

CREATE INDEX IF NOT EXISTS idx_audio_repair_blocks_segments
ON audio_repair_blocks(first_segment_id, last_segment_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_audio_repair_blocks_one_candidate_identity
ON audio_repair_blocks(job_chapter_id, first_segment_id, last_segment_id, source_text_sha256, effective_voice_ref)
WHERE status = 'candidate';
