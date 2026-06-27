-- Migration 0007: Voice Snapshot Pinning
-- Add immutable voice resolution snapshot to segments for deterministic synthesis

ALTER TABLE segments ADD COLUMN voice_source_type TEXT DEFAULT NULL;
ALTER TABLE segments ADD COLUMN voice_provider TEXT DEFAULT NULL;
ALTER TABLE segments ADD COLUMN voice_model TEXT DEFAULT NULL;
ALTER TABLE segments ADD COLUMN logical_voice_ref TEXT DEFAULT NULL;
ALTER TABLE segments ADD COLUMN effective_voice_ref TEXT DEFAULT NULL;
ALTER TABLE segments ADD COLUMN custom_voice_revision_id INTEGER DEFAULT NULL REFERENCES custom_voice_revisions(id) ON DELETE RESTRICT;
ALTER TABLE segments ADD COLUMN reference_audio_sha256 TEXT DEFAULT NULL;
ALTER TABLE segments ADD COLUMN reference_audio_storage_key TEXT DEFAULT NULL;
ALTER TABLE segments ADD COLUMN reference_transcript TEXT DEFAULT NULL;
ALTER TABLE segments ADD COLUMN reference_transcript_sha256 TEXT DEFAULT NULL;
ALTER TABLE segments ADD COLUMN synthesis_settings_json TEXT DEFAULT NULL;
ALTER TABLE segments ADD COLUMN casting_plan_id INTEGER REFERENCES casting_plans(id) ON DELETE RESTRICT;
ALTER TABLE segments ADD COLUMN voice_resolution_reason TEXT DEFAULT NULL;
ALTER TABLE segments ADD COLUMN voice_snapshot_version INTEGER DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_segments_custom_voice_revision
ON segments(custom_voice_revision_id);

CREATE INDEX IF NOT EXISTS idx_segments_snapshot_version
ON segments(voice_snapshot_version);

CREATE INDEX IF NOT EXISTS idx_segments_casting_plan
ON segments(casting_plan_id);
