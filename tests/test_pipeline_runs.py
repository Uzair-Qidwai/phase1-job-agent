from __future__ import annotations

import os

import psycopg2
import pytest

from src.tracker import (
    PipelineAlreadyRunning,
    complete_pipeline_run,
    fail_pipeline_run,
    get_conn,
    get_new_jobs_for_digest,
    get_pipeline_run,
    get_source_health,
    mark_jobs_notified,
    record_source_health,
    save_cv_version,
    source_has_consecutive_zero_results,
    start_pipeline_run,
    update_job_score,
    update_job_system_state,
    update_pipeline_run,
    upsert_job,
)


pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_URL"),
    reason="POSTGRES_URL is required for database integration tests",
)


@pytest.fixture(autouse=True)
def clean_test_rows():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM notifications")
            cur.execute("DELETE FROM pipeline_events")
            cur.execute("DELETE FROM pipeline_runs")
            cur.execute(
                "UPDATE jobs SET cv_version_id = NULL WHERE source = 'phase2-test'"
            )
            cur.execute(
                """
                DELETE FROM cv_versions
                WHERE job_id IN (
                    SELECT id FROM jobs WHERE source = 'phase2-test'
                )
                """
            )
            cur.execute("DELETE FROM jobs WHERE source = 'phase2-test'")
    yield
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM notifications")
            cur.execute("DELETE FROM pipeline_events")
            cur.execute("DELETE FROM pipeline_runs")
            cur.execute(
                "UPDATE jobs SET cv_version_id = NULL WHERE source = 'phase2-test'"
            )
            cur.execute(
                """
                DELETE FROM cv_versions
                WHERE job_id IN (
                    SELECT id FROM jobs WHERE source = 'phase2-test'
                )
                """
            )
            cur.execute("DELETE FROM jobs WHERE source = 'phase2-test'")


def test_only_one_pipeline_run_can_be_active() -> None:
    first = start_pipeline_run("manual")

    with pytest.raises(PipelineAlreadyRunning):
        start_pipeline_run("scheduled")

    complete_pipeline_run(first)

    second = start_pipeline_run("scheduled")
    assert second != first
    complete_pipeline_run(second)


def test_failed_run_releases_active_slot_and_records_stage() -> None:
    run_id = start_pipeline_run("manual")
    error = RuntimeError("simulated provider failure")

    fail_pipeline_run(run_id, "tailoring", error)

    run = get_pipeline_run(run_id)
    assert run is not None
    assert run["status"] == "failed"
    assert run["current_stage"] == "tailoring"
    assert run["error_type"] == "RuntimeError"
    assert "simulated provider failure" in run["error_message"]

    retry_id = start_pipeline_run("retry", retry_of_run_id=run_id)
    retry = get_pipeline_run(retry_id)
    assert retry is not None
    assert str(retry["retry_of_run_id"]) == run_id
    complete_pipeline_run(retry_id)


def test_source_job_id_prevents_duplicate_jobs() -> None:
    first_id, first_is_new = upsert_job(
        title="AI Engineer",
        company="Example",
        location="Toronto",
        url="https://example.com/jobs/1?view=a",
        description="first",
        source="phase2-test",
        source_job_id="native-123",
    )
    second_id, second_is_new = upsert_job(
        title="AI Engineer",
        company="Example",
        location="Toronto",
        url="https://example.com/jobs/1?view=b",
        description="same native job",
        source="phase2-test",
        source_job_id="native-123",
    )

    assert first_is_new is True
    assert second_is_new is False
    assert first_id == second_id


def test_cv_version_audit_metadata_is_persisted() -> None:
    job_id, _ = upsert_job(
        title="AI Engineer",
        company="Example",
        location="Toronto",
        url="https://example.com/jobs/audit-cv",
        description="Build AI systems.",
        source="phase2-test",
        source_job_id="audit-cv",
    )
    cv_id = save_cv_version(
        job_id,
        "# Tailored CV\n\nEvidence-backed content long enough for storage.",
        "Reordered existing experience.",
        model="test-model",
        prompt_version="phase2-cv-v1",
        profile_version="1",
        source_cv_sha256="abc123",
        evidence=[
            {
                "claim": "Python experience",
                "source": "master_cv",
                "source_text": "Python",
            }
        ],
        validation={"valid": True},
        usage={"input_tokens": 123, "output_tokens": 45},
        estimated_cost_usd=0.012345,
    )

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT model, prompt_version, profile_version, source_cv_sha256,
                       evidence, validation, usage, estimated_cost_usd
                FROM cv_versions
                WHERE id = %s
                """,
                (cv_id,),
            )
            row = cur.fetchone()

    assert row["model"] == "test-model"
    assert row["prompt_version"] == "phase2-cv-v1"
    assert row["profile_version"] == "1"
    assert row["source_cv_sha256"] == "abc123"
    assert row["validation"]["valid"] is True
    assert row["evidence"][0]["claim"] == "Python experience"
    assert row["usage"]["input_tokens"] == 123
    assert row["usage"]["output_tokens"] == 45
    assert float(row["estimated_cost_usd"]) == pytest.approx(0.012345)


def test_digest_notification_is_exactly_once() -> None:
    job_id, _ = upsert_job(
        title="AI Engineer",
        company="Example",
        location="Toronto",
        url="https://example.com/jobs/notify-once",
        description="Build AI systems.",
        source="phase2-test",
        source_job_id="notify-once",
    )
    update_job_score(job_id, 0.95)
    update_job_system_state(job_id, "tailored")

    first_digest = get_new_jobs_for_digest(min_score=0.65)
    assert any(str(job["id"]) == job_id for job in first_digest)

    run_id = start_pipeline_run("manual")
    inserted = mark_jobs_notified([job_id], run_id=run_id, channel="email")
    complete_pipeline_run(run_id, jobs_notified=inserted)

    assert inserted == 1
    second_digest = get_new_jobs_for_digest(min_score=0.65)
    assert all(str(job["id"]) != job_id for job in second_digest)

    duplicate = mark_jobs_notified([job_id], run_id=None, channel="email")
    assert duplicate == 0


def test_source_health_is_persisted_per_run() -> None:
    run_id = start_pipeline_run("manual")
    record_source_health(
        run_id,
        {"linkedin": 12, "indeed": 0, "greenhouse": 7},
    )
    complete_pipeline_run(run_id)

    rows = get_source_health(limit=10)
    by_source = {row["source"]: row for row in rows}

    assert by_source["linkedin"]["jobs_discovered"] == 12
    assert by_source["linkedin"]["zero_results"] is False
    assert by_source["indeed"]["jobs_discovered"] == 0
    assert by_source["indeed"]["zero_results"] is True
    assert by_source["greenhouse"]["jobs_discovered"] == 7


def test_consecutive_zero_source_runs_trigger_health_detector() -> None:
    for _ in range(3):
        run_id = start_pipeline_run("manual")
        record_source_health(run_id, {"indeed": 0})
        complete_pipeline_run(run_id)

    assert source_has_consecutive_zero_results("indeed", runs=3) is True
    assert source_has_consecutive_zero_results("indeed", runs=4) is False

    run_id = start_pipeline_run("manual")
    record_source_health(run_id, {"indeed": 2})
    complete_pipeline_run(run_id)

    assert source_has_consecutive_zero_results("indeed", runs=3) is False


def test_invalid_pipeline_trigger_is_rejected_before_database_write() -> None:
    with pytest.raises(ValueError, match="Invalid pipeline trigger"):
        start_pipeline_run("untrusted")


def test_negative_pipeline_metrics_are_rejected_by_application_validation() -> None:
    run_id = start_pipeline_run("manual")
    try:
        with pytest.raises(ValueError, match="non-negative"):
            update_pipeline_run(run_id, jobs_discovered=-1)
    finally:
        complete_pipeline_run(run_id)


def test_database_rejects_negative_pipeline_metrics() -> None:
    run_id = start_pipeline_run("manual")
    try:
        with pytest.raises(psycopg2.errors.CheckViolation):
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE pipeline_runs SET jobs_discovered = -1 WHERE id = %s",
                        (run_id,),
                    )
    finally:
        complete_pipeline_run(run_id)


def test_database_rejects_invalid_pipeline_event_level() -> None:
    run_id = start_pipeline_run("manual")
    try:
        with pytest.raises(psycopg2.errors.CheckViolation):
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO pipeline_events (run_id, stage, level, event_type)
                        VALUES (%s, 'ranking', 'debug', 'invalid_test_event')
                        """,
                        (run_id,),
                    )
    finally:
        complete_pipeline_run(run_id)


def test_database_enforces_match_score_range() -> None:
    job_id, _ = upsert_job(
        title="AI Engineer",
        company="Example",
        location="Toronto",
        url="https://example.com/jobs/score-range",
        description="Build AI systems.",
        source="phase2-test",
        source_job_id="score-range",
    )

    with pytest.raises(psycopg2.errors.CheckViolation):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE jobs SET match_score = 1.5 WHERE id = %s",
                    (job_id,),
                )


def test_retry_requires_failed_parent_run() -> None:
    with pytest.raises(ValueError, match="must reference a failed run"):
        start_pipeline_run("retry")

    completed = start_pipeline_run("manual")
    complete_pipeline_run(completed)

    with pytest.raises(ValueError, match="must be failed"):
        start_pipeline_run("retry", retry_of_run_id=completed)
