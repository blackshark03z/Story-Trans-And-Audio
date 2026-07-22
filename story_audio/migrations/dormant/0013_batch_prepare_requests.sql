CREATE TABLE IF NOT EXISTS batch_prepare_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_request_id TEXT NOT NULL,
    request_identity TEXT NOT NULL,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE RESTRICT,
    from_chapter INTEGER NOT NULL,
    to_chapter INTEGER NOT NULL,
    target_phase TEXT NOT NULL CHECK(target_phase IN ('PREPARE')),
    plan_fingerprint TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('PLANNED','APPLYING','APPLIED','REJECTED','FAILED')),
    job_id INTEGER REFERENCES jobs(id) ON DELETE RESTRICT,
    result_schema_version INTEGER CHECK(result_schema_version IS NULL OR result_schema_version = 1),
    result_payload_json TEXT CHECK(result_payload_json IS NULL OR length(result_payload_json) <= 16384),
    error_code TEXT,
    error_message TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    applying_started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(client_request_id),
    UNIQUE(request_identity),
    CHECK(length(client_request_id) BETWEEN 1 AND 200),
    CHECK(length(request_identity) = 64),
    CHECK(length(plan_fingerprint) = 64),
    CHECK(error_message IS NULL OR length(error_message) <= 1000),
    CHECK(from_chapter <= to_chapter),
    CHECK(attempt_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_batch_prepare_requests_client
ON batch_prepare_requests(client_request_id);

CREATE INDEX IF NOT EXISTS idx_batch_prepare_requests_identity
ON batch_prepare_requests(request_identity);

CREATE INDEX IF NOT EXISTS idx_batch_prepare_requests_state_updated
ON batch_prepare_requests(state, updated_at);

CREATE INDEX IF NOT EXISTS idx_batch_prepare_requests_stale_applying
ON batch_prepare_requests(state, applying_started_at);

CREATE INDEX IF NOT EXISTS idx_batch_prepare_requests_job
ON batch_prepare_requests(job_id);

CREATE INDEX IF NOT EXISTS idx_batch_prepare_requests_scope
ON batch_prepare_requests(book_id, from_chapter, to_chapter, target_phase);
