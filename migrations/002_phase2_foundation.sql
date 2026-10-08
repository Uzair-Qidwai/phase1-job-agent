-- Phase 2 foundation: stable source identity + pipeline execution ledger.
-- Run after 001_jobs.sql.

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS source_job_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_source_job_id
    ON jobs (source, source_job_id)
    WHERE source_job_id IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'jobs_match_score_range'
    ) THEN
        ALTER TABLE jobs
            ADD CONSTRAINT jobs_match_score_range
            CHECK (match_score IS NULL OR (match_score >= 0.0 AND match_score <= 1.0))
            NOT VALID;
    END IF;
END $$;

ALTER TABLE jobs VALIDATE CONSTRAINT jobs_match_score_range;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'jobs_status_valid'
    ) THEN
        ALTER TABLE jobs
            ADD CONSTRAINT jobs_status_valid
            CHECK (status IN ('new', 'applied', 'interview', 'offer', 'rejected'))
            NOT VALID;
    END IF;
END $$;

ALTER TABLE jobs VALIDATE CONSTRAINT jobs_status_valid;

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger         TEXT NOT NULL CHECK (trigger IN ('scheduled', 'manual', 'retry')),
    status          TEXT NOT NULL CHECK (
                        status IN (
                            'created',
                            'scraping',
                            'persisting',
                            'filtering',
                            'ranking',
                            'tailoring',
                            'notifying',
                            'resuming',
                            'completed',
                            'failed'
                        )
                    ),
    current_stage   TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    jobs_discovered INTEGER NOT NULL DEFAULT 0,
    jobs_inserted   INTEGER NOT NULL DEFAULT 0,
    jobs_ranked     INTEGER NOT NULL DEFAULT 0,
    jobs_shortlisted INTEGER NOT NULL DEFAULT 0,
    jobs_tailored   INTEGER NOT NULL DEFAULT 0,
    jobs_notified   INTEGER NOT NULL DEFAULT 0,
    error_type      TEXT,
    error_message   TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Cross-process lock: there can be at most one active run regardless of whether
-- it was started by APScheduler, the API, or a manual CLI process.
CREATE UNIQUE INDEX IF NOT EXISTS uq_pipeline_runs_single_active
    ON pipeline_runs ((1))
    WHERE status IN (
        'created',
        'scraping',
        'persisting',
        'filtering',
        'ranking',
        'tailoring',
        'notifying',
        'resuming'
    );

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started_at
    ON pipeline_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS pipeline_events (
    id          BIGSERIAL PRIMARY KEY,
    run_id      UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    stage       TEXT,
    level       TEXT NOT NULL DEFAULT 'info',
    event_type  TEXT NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_events_run_created
    ON pipeline_events (run_id, created_at);

DROP TRIGGER IF EXISTS trg_pipeline_runs_updated_at ON pipeline_runs;
CREATE TRIGGER trg_pipeline_runs_updated_at
    BEFORE UPDATE ON pipeline_runs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
