-- Phase 1 Job Agent: Initial Schema
-- Run: psql $POSTGRES_URL -f migrations/001_jobs.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS cv_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID,                          -- back-filled after jobs table created
    tailored_cv     TEXT NOT NULL,
    changes_made    TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    location        TEXT,
    url             TEXT UNIQUE NOT NULL,
    description     TEXT,
    match_score     FLOAT,
    source          TEXT,                          -- 'linkedin' | 'indeed' | 'greenhouse'
    found_at        TIMESTAMPTZ DEFAULT NOW(),
    status          TEXT DEFAULT 'new',            -- new | applied | interview | offer | rejected
    cv_version_id   UUID REFERENCES cv_versions(id),
    notes           TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Add FK now that both tables exist, without failing on a repeated migration run.
DO $
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_cv_job'
    ) THEN
        ALTER TABLE cv_versions
            ADD CONSTRAINT fk_cv_job
            FOREIGN KEY (job_id) REFERENCES jobs(id)
            ON DELETE SET NULL;
    END IF;
END $;

CREATE INDEX IF NOT EXISTS idx_jobs_status   ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_found_at ON jobs(found_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_score    ON jobs(match_score DESC NULLS LAST);

-- Auto-update updated_at on row changes
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_jobs_updated_at ON jobs;
CREATE TRIGGER trg_jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
