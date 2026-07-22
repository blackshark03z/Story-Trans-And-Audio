CREATE UNIQUE INDEX IF NOT EXISTS ux_batch_prepare_requests_id_identity
ON batch_prepare_requests(id, request_identity);

CREATE TABLE IF NOT EXISTS batch_prepare_job_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_prepare_request_id INTEGER NOT NULL,
    request_identity TEXT NOT NULL,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    plan_fingerprint TEXT NOT NULL,
    chapter_snapshot_digest TEXT NOT NULL,
    expected_chapter_count INTEGER NOT NULL,
    actual_chapter_count INTEGER NOT NULL,
    prepared_status TEXT NOT NULL,
    transaction_evidence_version INTEGER NOT NULL,
    transaction_committed_at TEXT NOT NULL,
    worker_woken INTEGER NOT NULL,
    render_started INTEGER NOT NULL,
    result_schema_version INTEGER NOT NULL,
    transaction_reference TEXT,
    evidence_source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(batch_prepare_request_id),
    UNIQUE(request_identity),
    UNIQUE(job_id),
    FOREIGN KEY(batch_prepare_request_id, request_identity)
        REFERENCES batch_prepare_requests(id, request_identity)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK(length(request_identity) = 64),
    CHECK(length(plan_fingerprint) = 64),
    CHECK(length(chapter_snapshot_digest) = 64),
    CHECK(expected_chapter_count > 0),
    CHECK(actual_chapter_count > 0),
    CHECK(expected_chapter_count = actual_chapter_count),
    CHECK(prepared_status = 'prepared'),
    CHECK(transaction_evidence_version = 1),
    CHECK(length(transaction_committed_at) > 0),
    CHECK(worker_woken = 0),
    CHECK(render_started = 0),
    CHECK(result_schema_version = 1),
    CHECK(transaction_reference IS NULL OR length(transaction_reference) <= 200),
    CHECK(length(evidence_source) BETWEEN 1 AND 200)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_batch_prepare_job_links_request
ON batch_prepare_job_links(batch_prepare_request_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_batch_prepare_job_links_identity
ON batch_prepare_job_links(request_identity);

CREATE UNIQUE INDEX IF NOT EXISTS ux_batch_prepare_job_links_job
ON batch_prepare_job_links(job_id);

CREATE INDEX IF NOT EXISTS idx_batch_prepare_job_links_committed
ON batch_prepare_job_links(transaction_committed_at);
