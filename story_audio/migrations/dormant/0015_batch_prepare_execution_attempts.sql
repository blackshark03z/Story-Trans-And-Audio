CREATE TABLE IF NOT EXISTS batch_prepare_execution_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_prepare_request_id INTEGER NOT NULL,
    request_identity TEXT NOT NULL,
    attempt_generation INTEGER NOT NULL,
    owner_token_hash TEXT NOT NULL,
    lease_acquired_at TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL,
    transaction_reference TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN (
        'OWNED','COMMITTED','ROLLBACK_CONFIRMED','OUTCOME_AMBIGUOUS','EXPIRED'
    )),
    plan_fingerprint TEXT NOT NULL,
    chapter_snapshot_digest TEXT NOT NULL,
    committed_job_link_id INTEGER REFERENCES batch_prepare_job_links(id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    committed_at TEXT,
    rolled_back_at TEXT,
    ambiguity_reason_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(batch_prepare_request_id, attempt_generation),
    UNIQUE(transaction_reference),
    FOREIGN KEY(batch_prepare_request_id, request_identity)
        REFERENCES batch_prepare_requests(id, request_identity)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK(attempt_generation > 0),
    CHECK(length(request_identity) = 64 AND request_identity = lower(request_identity)
          AND request_identity NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(owner_token_hash) = 64 AND owner_token_hash = lower(owner_token_hash)
          AND owner_token_hash NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(plan_fingerprint) = 64 AND plan_fingerprint = lower(plan_fingerprint)
          AND plan_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(chapter_snapshot_digest) = 64 AND chapter_snapshot_digest = lower(chapter_snapshot_digest)
          AND chapter_snapshot_digest NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(transaction_reference) BETWEEN 1 AND 200),
    CHECK(length(lease_acquired_at) > 0 AND lease_expires_at > lease_acquired_at),
    CHECK(ambiguity_reason_code IS NULL OR length(ambiguity_reason_code) BETWEEN 1 AND 100),
    CHECK(
        (state = 'OWNED' AND committed_job_link_id IS NULL AND committed_at IS NULL
            AND rolled_back_at IS NULL AND ambiguity_reason_code IS NULL)
        OR (state = 'COMMITTED' AND committed_job_link_id IS NOT NULL AND committed_at IS NOT NULL
            AND rolled_back_at IS NULL AND ambiguity_reason_code IS NULL)
        OR (state = 'ROLLBACK_CONFIRMED' AND committed_job_link_id IS NULL AND committed_at IS NULL
            AND rolled_back_at IS NOT NULL AND ambiguity_reason_code IS NULL)
        OR (state = 'OUTCOME_AMBIGUOUS' AND committed_job_link_id IS NULL AND committed_at IS NULL
            AND rolled_back_at IS NULL AND ambiguity_reason_code IS NOT NULL)
        OR (state = 'EXPIRED' AND committed_job_link_id IS NULL AND committed_at IS NULL
            AND rolled_back_at IS NULL AND ambiguity_reason_code IS NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_batch_prepare_execution_attempts_live_owner
ON batch_prepare_execution_attempts(batch_prepare_request_id)
WHERE state = 'OWNED';

CREATE INDEX IF NOT EXISTS idx_batch_prepare_execution_attempts_request_generation
ON batch_prepare_execution_attempts(batch_prepare_request_id, attempt_generation DESC);

CREATE INDEX IF NOT EXISTS idx_batch_prepare_execution_attempts_lease
ON batch_prepare_execution_attempts(state, lease_expires_at);

CREATE INDEX IF NOT EXISTS idx_batch_prepare_execution_attempts_link
ON batch_prepare_execution_attempts(committed_job_link_id);
