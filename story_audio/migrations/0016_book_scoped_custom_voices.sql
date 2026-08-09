-- Migration 0016: Custom voices are owned by one book for normal product use.
-- Existing rows deliberately remain NULL-book legacy voices so immutable
-- historical casting/job references continue to resolve by their voice ID.

ALTER TABLE custom_voices
ADD COLUMN book_id INTEGER REFERENCES books(id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS idx_custom_voices_book_active_name
ON custom_voices(book_id, is_active, display_name);
