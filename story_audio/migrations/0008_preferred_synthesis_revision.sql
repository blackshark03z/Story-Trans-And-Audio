-- Migration 0008: Preferred Synthesis Revision for Custom Voices
-- Allows users to pin a specific immutable revision for chapter synthesis

ALTER TABLE custom_voices
ADD COLUMN preferred_synthesis_revision_id INTEGER
REFERENCES custom_voice_revisions(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_custom_voices_preferred_revision
ON custom_voices(preferred_synthesis_revision_id);
