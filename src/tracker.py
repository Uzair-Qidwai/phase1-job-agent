"""
tracker.py — PostgreSQL CRUD for job records and CV versions.
All DB interaction goes through this module.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import contextmanager
from typing import Any, Generator

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

POSTGRES_URL = os.environ["POSTGRES_URL"]

# Use dict cursor so rows come back as dicts everywhere
psycopg2.extras.register_uuid()


@contextmanager
def get_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    conn = psycopg2.connect(POSTGRES_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────────

def upsert_job(
    title: str,
    company: str,
    location: str,
    url: str,
    description: str,
    source: str,
) -> tuple[str, bool]:
    """
    Insert a job if url is new. Returns (job_id, is_new).
    On conflict (duplicate URL) returns existing id with is_new=False.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO jobs (title, company, location, url, description, source)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING
                RETURNING id
                """,
                (title, company, location, url, description, source),
            )
            row = cur.fetchone()
            if row:
                return str(row["id"]), True

            # Already existed — fetch the existing id
            cur.execute("SELECT id FROM jobs WHERE url = %s", (url,))
            existing = cur.fetchone()
            return str(existing["id"]), False


def update_job_score_and_cv(job_id: str, match_score: float, cv_version_id: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs
                SET match_score = %s, cv_version_id = %s
                WHERE id = %s
                """,
                (match_score, uuid.UUID(cv_version_id), uuid.UUID(job_id)),
            )


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
                       j.match_score, j.source, j.status, j.found_at,
                       j.notes, j.updated_at, cv.changes_made
                FROM jobs j
                LEFT JOIN cv_versions cv ON cv.id = j.cv_version_id
                WHERE (%s IS NULL OR j.status = %s)
                  AND (j.match_score IS NULL OR j.match_score >= %s)
                ORDER BY j.match_score DESC NULLS LAST, j.found_at DESC
                LIMIT %s
            """
            cur.execute(query, (status, status, min_score, limit))
            return [dict(r) for r in cur.fetchall()]


def get_new_jobs_for_digest(min_score: float = 0.6) -> list[dict[str, Any]]:
    """Jobs found in the last 24 h with score >= min_score."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT j.id, j.title, j.company, j.location, j.url,
                       j.match_score, j.source, j.status, j.found_at,
                       cv.changes_made
                FROM jobs j
                LEFT JOIN cv_versions cv ON cv.id = j.cv_version_id
                WHERE j.found_at >= NOW() - INTERVAL '24 hours'
                  AND j.match_score >= %s
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


def add_note(job_id: str, note: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET notes = %s WHERE id = %s",
                (note, uuid.UUID(job_id)),
            )


# ─────────────────────────────────────────────
# CV Versions
# ─────────────────────────────────────────────

def save_cv_version(job_id: str, tailored_cv: str, changes_made: str) -> str:
    """Insert a cv_version row and return its id."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cv_versions (job_id, tailored_cv, changes_made)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (uuid.UUID(job_id), tailored_cv, changes_made),
            )
            return str(cur.fetchone()["id"])
