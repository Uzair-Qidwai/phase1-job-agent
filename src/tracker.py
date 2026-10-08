"""PostgreSQL repositories for jobs, CV versions, and pipeline execution."""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from typing import Any, Generator

import psycopg2
import psycopg2.extras

from src.settings import get_settings

logger = logging.getLogger(__name__)

psycopg2.extras.register_uuid()


class PipelineAlreadyRunning(RuntimeError):
    """Raised when a second process attempts to start an active pipeline."""


@contextmanager
def get_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    postgres_url = get_settings().require_postgres_url()
    conn = psycopg2.connect(
        postgres_url,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_job(
    title: str,
    company: str,
    location: str,
    url: str,
    description: str,
    source: str,
    source_job_id: str | None = None,
) -> tuple[str, bool]:
    """Insert a job using source identity first and canonical URL as fallback."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO jobs (
                    title,
                    company,
                    location,
                    url,
                    description,
                    source,
                    source_job_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                (
                    title,
                    company,
                    location,
                    url,
                    description,
                    source,
                    source_job_id,
                ),
            )
            row = cur.fetchone()
            if row:
                return str(row["id"]), True

            existing = None
            if source_job_id:
                cur.execute(
                    """
                    SELECT id, source_job_id
                    FROM jobs
                    WHERE source = %s AND source_job_id = %s
                    LIMIT 1
                    """,
                    (source, source_job_id),
                )
                existing = cur.fetchone()

            if not existing:
                cur.execute(
                    "SELECT id, source_job_id FROM jobs WHERE url = %s LIMIT 1",
                    (url,),
                )
                existing = cur.fetchone()

            if not existing:
                raise RuntimeError("Job insert conflicted but no existing job could be resolved")

            if source_job_id and not existing.get("source_job_id"):
                cur.execute(
                    """
                    UPDATE jobs
                    SET source_job_id = %s
                    WHERE id = %s AND source_job_id IS NULL
                    """,
                    (source_job_id, existing["id"]),
                )

            return str(existing["id"]), False


def update_job_score(job_id: str, match_score: float) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET match_score = %s WHERE id = %s",
                (match_score, uuid.UUID(job_id)),
            )


def attach_cv_version(job_id: str, cv_version_id: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET cv_version_id = %s WHERE id = %s",
                (uuid.UUID(cv_version_id), uuid.UUID(job_id)),
            )


def update_job_score_and_cv(job_id: str, match_score: float, cv_version_id: str) -> None:
    """Compatibility wrapper for Phase 1 callers; new code should separate ranking and CV."""
    update_job_score(job_id, match_score)
    attach_cv_version(job_id, cv_version_id)


def update_job_status(job_id: str, status: str) -> dict[str, Any] | None:
    valid = {"new", "applied", "interview", "offer", "rejected"}
    if status not in valid:
        raise ValueError(f"Invalid status '{status}'. Must be one of {valid}")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs SET status = %s WHERE id = %s
                RETURNING id, title, company, status, updated_at
                """,
                (status, uuid.UUID(job_id)),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_jobs(
    status: str | None = None,
    min_score: float = 0.0,
    limit: int = 200,
) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT j.id, j.title, j.company, j.location, j.url,
                       j.match_score, j.source, j.source_job_id, j.status, j.found_at,
                       j.notes, j.updated_at, cv.changes_made
                FROM jobs j
                LEFT JOIN cv_versions cv ON cv.id = j.cv_version_id
                WHERE (%s IS NULL OR j.status = %s)
                  AND (%s <= 0 OR j.match_score >= %s)
                ORDER BY j.match_score DESC NULLS LAST, j.found_at DESC
                LIMIT %s
            """
            cur.execute(query, (status, status, min_score, min_score, limit))
            return [dict(r) for r in cur.fetchall()]


def get_new_jobs_for_digest(min_score: float = 0.6) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT j.id, j.title, j.company, j.location, j.url,
                       j.match_score, j.source, j.status, j.found_at,
                       cv.changes_made
                FROM jobs j
                LEFT JOIN cv_versions cv ON cv.id = j.cv_version_id
                LEFT JOIN notifications n
                  ON n.job_id = j.id
                 AND n.channel = 'email'
                 AND n.status = 'sent'
                WHERE j.found_at >= NOW() - INTERVAL '24 hours'
                  AND j.match_score >= %s
                  AND n.id IS NULL
                ORDER BY j.match_score DESC
                """,
                (min_score,),
            )
            return [dict(r) for r in cur.fetchall()]


def get_job_by_id(job_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT j.*, cv.tailored_cv, cv.changes_made
                FROM jobs j
                LEFT JOIN cv_versions cv ON cv.id = j.cv_version_id
                WHERE j.id = %s
                """,
                (uuid.UUID(job_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def add_note(job_id: str, note: str) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET notes = %s WHERE id = %s RETURNING id",
                (note, uuid.UUID(job_id)),
            )
            return cur.fetchone() is not None


def save_cv_version(
    job_id: str,
    tailored_cv: str,
    changes_made: str,
    *,
    model: str | None = None,
    prompt_version: str | None = None,
    profile_version: str | None = None,
    source_cv_sha256: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
    validation: dict[str, Any] | None = None,
) -> str:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cv_versions (
                    job_id,
                    tailored_cv,
                    changes_made,
                    model,
                    prompt_version,
                    profile_version,
                    source_cv_sha256,
                    evidence,
                    validation
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    uuid.UUID(job_id),
                    tailored_cv,
                    changes_made,
                    model,
                    prompt_version,
                    profile_version,
                    source_cv_sha256,
                    psycopg2.extras.Json(evidence or []),
                    psycopg2.extras.Json(validation or {}),
                ),
            )
            return str(cur.fetchone()["id"])


def start_pipeline_run(trigger: str) -> str:
    """Create a run and atomically acquire the cross-process active-run slot."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pipeline_runs (trigger, status, current_stage)
                    VALUES (%s, 'created', 'created')
                    RETURNING id
                    """,
                    (trigger,),
                )
                run_id = str(cur.fetchone()["id"])
                cur.execute(
                    """
                    INSERT INTO pipeline_events (run_id, stage, event_type, payload)
                    VALUES (%s, 'created', 'run_started', %s)
                    """,
                    (uuid.UUID(run_id), psycopg2.extras.Json({"trigger": trigger})),
                )
                return run_id
    except psycopg2.errors.UniqueViolation as exc:
        if exc.diag.constraint_name == "uq_pipeline_runs_single_active":
            raise PipelineAlreadyRunning("A pipeline run is already active") from exc
        raise


def update_pipeline_run(
    run_id: str,
    *,
    status: str | None = None,
    current_stage: str | None = None,
    jobs_discovered: int | None = None,
    jobs_inserted: int | None = None,
    jobs_ranked: int | None = None,
    jobs_shortlisted: int | None = None,
    jobs_tailored: int | None = None,
    jobs_notified: int | None = None,
) -> None:
    fields: list[str] = []
    values: list[Any] = []

    for column, value in (
        ("status", status),
        ("current_stage", current_stage),
        ("jobs_discovered", jobs_discovered),
        ("jobs_inserted", jobs_inserted),
        ("jobs_ranked", jobs_ranked),
        ("jobs_shortlisted", jobs_shortlisted),
        ("jobs_tailored", jobs_tailored),
        ("jobs_notified", jobs_notified),
    ):
        if value is not None:
            fields.append(f"{column} = %s")
            values.append(value)

    if not fields:
        return

    values.append(uuid.UUID(run_id))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE pipeline_runs SET {', '.join(fields)} WHERE id = %s",
                values,
            )


def record_pipeline_event(
    run_id: str,
    event_type: str,
    *,
    stage: str | None = None,
    level: str = "info",
    payload: dict[str, Any] | None = None,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pipeline_events (run_id, stage, level, event_type, payload)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    uuid.UUID(run_id),
                    stage,
                    level,
                    event_type,
                    psycopg2.extras.Json(payload or {}),
                ),
            )


def complete_pipeline_run(run_id: str, *, jobs_notified: int = 0) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pipeline_runs
                SET status = 'completed',
                    current_stage = 'completed',
                    jobs_notified = %s,
                    finished_at = NOW()
                WHERE id = %s
                """,
                (jobs_notified, uuid.UUID(run_id)),
            )
            cur.execute(
                """
                INSERT INTO pipeline_events (run_id, stage, event_type)
                VALUES (%s, 'completed', 'run_completed')
                """,
                (uuid.UUID(run_id),),
            )


def fail_pipeline_run(run_id: str, stage: str, exc: Exception) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pipeline_runs
                SET status = 'failed',
                    current_stage = %s,
                    error_type = %s,
                    error_message = %s,
                    finished_at = NOW()
                WHERE id = %s
                """,
                (
                    stage,
                    type(exc).__name__,
                    str(exc)[:2000],
                    uuid.UUID(run_id),
                ),
            )
            cur.execute(
                """
                INSERT INTO pipeline_events (
                    run_id, stage, level, event_type, payload
                )
                VALUES (%s, %s, 'error', 'run_failed', %s)
                """,
                (
                    uuid.UUID(run_id),
                    stage,
                    psycopg2.extras.Json(
                        {
                            "error_type": type(exc).__name__,
                            "error_message": str(exc)[:2000],
                        }
                    ),
                ),
            )


def get_pipeline_run(run_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM pipeline_runs WHERE id = %s",
                (uuid.UUID(run_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def mark_jobs_notified(
    job_ids: list[str],
    *,
    run_id: str | None,
    channel: str = "email",
) -> int:
    """Persist successful delivery state; duplicate job/channel pairs are ignored."""
    if not job_ids:
        return 0

    inserted = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for job_id in job_ids:
                cur.execute(
                    """
                    INSERT INTO notifications (job_id, run_id, channel, status)
                    VALUES (%s, %s, %s, 'sent')
                    ON CONFLICT (job_id, channel) DO NOTHING
                    RETURNING id
                    """,
                    (
                        uuid.UUID(job_id),
                        uuid.UUID(run_id) if run_id else None,
                        channel,
                    ),
                )
                if cur.fetchone():
                    inserted += 1
    return inserted
