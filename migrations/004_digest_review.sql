-- Immutable content snapshots; approval and delivery state are separate from jobs.
CREATE TABLE digest_batches (
    id UUID PRIMARY KEY,
    snapshot JSONB NOT NULL,
    fingerprint TEXT NOT NULL CHECK (length(fingerprint) = 64),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'sending', 'sent', 'cancelled')),
    approved_fingerprint TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMPTZ,
    attempt_id UUID REFERENCES delivery_attempts(id) ON DELETE RESTRICT,
    CHECK ((status IN ('approved', 'sending', 'sent')) = (approved_fingerprint IS NOT NULL)),
    CHECK (approved_fingerprint IS NULL OR approved_fingerprint = fingerprint)
);
CREATE UNIQUE INDEX one_open_digest_batch ON digest_batches ((true))
    WHERE status IN ('pending', 'approved', 'sending');
