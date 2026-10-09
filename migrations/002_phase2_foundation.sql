-- Phase 2 foundation: stable source identity + pipeline execution ledger.
-- Run after 001_jobs.sql.

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS source_job_id TEXT;

DO $phase2$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'jobs'
          AND column_name = 'system_state'
    ) THEN
        ALTER TABLE jobs ADD COLUMN system_state TEXT;
        UPDATE jobs SET system_state = 'legacy';
        ALTER TABLE jobs ALTER COLUMN system_state SET DEFAULT 'discovered';
        ALTER TABLE jobs ALTER COLUMN system_state SET NOT NULL;
    END IF;
END
$phase2$;

ALTER TABLE cv_versions
    ADD COLUMN IF NOT EXISTS model TEXT,
    ADD COLUMN IF NOT EXISTS prompt_version TEXT,
    ADD COLUMN IF NOT EXISTS profile_version TEXT,
    ADD COLUMN IF NOT EXISTS source_cv_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS validation JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS usage JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS estimated_cost_usd NUMERIC(12,6) NOT NULL DEFAULT 0;

DO $phase2state$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'jobs_system_state_valid'
    ) THEN
        ALTER TABLE jobs
            ADD CONSTRAINT jobs_system_state_valid
            CHECK (
                system_state IN (
                    'legacy',
                    'discovered',
                    'filtered_out',
                    'ranked_out',
                    'shortlisted',
                    'tailored',
                    'notified'
                )
            )
            NOT VALID;
    END IF;
END
$phase2state$;

ALTER TABLE jobs VALIDATE CONSTRAINT jobs_system_state_valid;

CREATE INDEX IF NOT EXISTS idx_jobs_system_state
    ON jobs (system_state);

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
    model_input_tokens INTEGER NOT NULL DEFAULT 0,
    model_output_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_model_cost_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
    error_type      TEXT,
    error_message   TEXT,
    retry_of_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE pipeline_runs
    ADD COLUMN IF NOT EXISTS retry_of_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_retry_of
    ON pipeline_runs (retry_of_run_id)
    WHERE retry_of_run_id IS NOT NULL;

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


-- Pipeline metrics are monotonic counters/costs and must never be negative.
DO $phase2runmetrics$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'pipeline_runs_nonnegative_metrics'
    ) THEN
        ALTER TABLE pipeline_runs
            ADD CONSTRAINT pipeline_runs_nonnegative_metrics
            CHECK (
                jobs_discovered >= 0
                AND jobs_inserted >= 0
                AND jobs_ranked >= 0
                AND jobs_shortlisted >= 0
                AND jobs_tailored >= 0
                AND jobs_notified >= 0
                AND model_input_tokens >= 0
                AND model_output_tokens >= 0
                AND estimated_model_cost_usd >= 0
            )
            NOT VALID;
    END IF;
END
$phase2runmetrics$;

ALTER TABLE pipeline_runs
    VALIDATE CONSTRAINT pipeline_runs_nonnegative_metrics;

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


DO $phase2eventlevel$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'pipeline_events_level_valid'
    ) THEN
        ALTER TABLE pipeline_events
            ADD CONSTRAINT pipeline_events_level_valid
            CHECK (level IN ('info', 'warning', 'error'))
            NOT VALID;
    END IF;
END
$phase2eventlevel$;

ALTER TABLE pipeline_events
    VALIDATE CONSTRAINT pipeline_events_level_valid;

DROP TRIGGER IF EXISTS trg_pipeline_runs_updated_at ON pipeline_runs;
CREATE TRIGGER trg_pipeline_runs_updated_at
    BEFORE UPDATE ON pipeline_runs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


CREATE TABLE IF NOT EXISTS notifications (
    id          BIGSERIAL PRIMARY KEY,
    job_id      UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    run_id      UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    channel     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent')),
    sent_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (job_id, channel)
);

CREATE INDEX IF NOT EXISTS idx_notifications_sent_at
    ON notifications (sent_at DESC);


CREATE TABLE IF NOT EXISTS source_health (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    source          TEXT NOT NULL,
    jobs_discovered INTEGER NOT NULL DEFAULT 0 CHECK (jobs_discovered >= 0),
    zero_results    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, source)
);

CREATE INDEX IF NOT EXISTS idx_source_health_source_created
    ON source_health (source, created_at DESC);


CREATE TABLE IF NOT EXISTS ranking_results (
    id                  BIGSERIAL PRIMARY KEY,
    job_id              UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    run_id              UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    total_score         NUMERIC(6,3) NOT NULL CHECK (
                            total_score >= 0 AND total_score <= 100
                        ),
    hard_mismatch       BOOLEAN NOT NULL DEFAULT FALSE,
    component_scores    JSONB NOT NULL DEFAULT '{}'::jsonb,
    explanation         JSONB NOT NULL DEFAULT '[]'::jsonb,
    profile_version     TEXT NOT NULL,
    ranking_version     TEXT NOT NULL,
    model               TEXT,
    usage               JSONB NOT NULL DEFAULT '{}'::jsonb,
    estimated_cost_usd  NUMERIC(12,6) NOT NULL DEFAULT 0 CHECK (
                            estimated_cost_usd >= 0
                        ),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ranking_results_job_created
    ON ranking_results (job_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ranking_results_run
    ON ranking_results (run_id)
    WHERE run_id IS NOT NULL;
