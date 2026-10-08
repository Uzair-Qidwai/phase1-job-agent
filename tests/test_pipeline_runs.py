from __future__ import annotations

import os

import pytest

from src.tracker import (
    PipelineAlreadyRunning,
    complete_pipeline_run,
    fail_pipeline_run,
    get_conn,
    get_pipeline_run,
    start_pipeline_run,
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
            cur.execute("DELETE FROM pipeline_events")
            cur.execute("DELETE FROM pipeline_runs")
            cur.execute("DELETE FROM jobs WHERE source = 'phase2-test'")
    yield
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pipeline_events")
            cur.execute("DELETE FROM pipeline_runs")
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

    retry_id = start_pipeline_run("retry")
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
