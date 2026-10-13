-- An unresolved external send blocks automatic resend, including after a crash.
CREATE TABLE delivery_attempts (
    id UUID PRIMARY KEY,
    run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    job_ids UUID[] NOT NULL CHECK (cardinality(job_ids) > 0),
    message_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('ambiguous', 'sent', 'not_sent')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolution_reason TEXT,
    CHECK ((status = 'ambiguous') = (resolved_at IS NULL))
);
CREATE UNIQUE INDEX one_unresolved_delivery ON delivery_attempts ((true))
    WHERE status = 'ambiguous';
