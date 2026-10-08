from __future__ import annotations

import os

import pytest

import src.cv_agent as cv_agent
import src.emailer as emailer
import src.scraper as scraper
from src.scheduler import run_pipeline
from src.tracker import get_conn, get_pipeline_run


pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_URL"),
    reason="POSTGRES_URL is required for end-to-end integration tests",
)


def _cleanup() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM notifications")
            cur.execute("DELETE FROM pipeline_events")
            cur.execute("DELETE FROM pipeline_runs")
            cur.execute(
                "UPDATE jobs SET cv_version_id = NULL WHERE source = 'phase2-e2e'"
            )
            cur.execute(
                """
                DELETE FROM cv_versions
                WHERE job_id IN (
                    SELECT id FROM jobs WHERE source = 'phase2-e2e'
                )
                """
            )
            cur.execute("DELETE FROM jobs WHERE source = 'phase2-e2e'")


@pytest.fixture(autouse=True)
def clean_e2e_rows():
    _cleanup()
    yield
    _cleanup()


@pytest.mark.asyncio
async def test_placeholder_asyncio_plugin_is_available():
    # Keeps the async test plugin exercised independently of Playwright/network.
    assert True


def test_full_pipeline_is_rank_first_and_idempotent(monkeypatch) -> None:
    strong = scraper.RawJob(
        title="Senior AI Engineer",
        company="Example AI",
        location="Toronto, Canada",
        url="https://example.com/jobs/strong",
        description=(
            "Build production AI and machine learning systems in Python, "
            "evaluation tooling and model infrastructure."
        ),
        source="phase2-e2e",
        source_job_id="strong",
    )
    weak = scraper.RawJob(
        title="Registered Nurse",
        company="Example Health",
        location="Toronto, Canada",
        url="https://example.com/jobs/weak",
        description="Provide clinical nursing care.",
        source="phase2-e2e",
        source_job_id="weak",
    )

    async def fake_scrape_all(headless: bool = True):
        return [strong, weak]

    tailor_calls: list[str] = []

    def fake_tailor_cv(*, job_title, company, description):
        tailor_calls.append(job_title)
        return {
            "tailored_cv": (
                "# Tailored CV\n\n"
                "Evidence-backed AI engineering experience with Python and "
                "machine learning systems."
            ),
            "changes_made": "Front-loaded relevant AI engineering evidence.",
            "evidence_used": [
                {
                    "claim": "AI engineering evidence",
                    "source": "master_cv",
                    "source_text": "Python",
                }
            ],
            "keywords_added": ["AI"],
            "warnings": [],
            "model": "fake-model",
            "prompt_version": "phase2-cv-v1",
            "profile_version": "1",
            "source_cv_sha256": "fake-sha",
            "validation": {"valid": True},
        }

    delivered_batches: list[list[dict]] = []

    def fake_send_digest(jobs):
        delivered_batches.append(list(jobs))
        return True

    monkeypatch.setattr(scraper, "scrape_all", fake_scrape_all)
    monkeypatch.setattr(cv_agent, "tailor_cv", fake_tailor_cv)
    monkeypatch.setattr(emailer, "send_digest", fake_send_digest)

    first_run_id = run_pipeline(trigger="manual")
    assert first_run_id is not None

    first = get_pipeline_run(first_run_id)
    assert first is not None
    assert first["status"] == "completed"
    assert first["jobs_discovered"] == 2
    assert first["jobs_inserted"] == 2
    assert first["jobs_ranked"] == 1
    assert first["jobs_shortlisted"] == 1
    assert first["jobs_tailored"] == 1
    assert first["jobs_notified"] == 1
    assert tailor_calls == ["Senior AI Engineer"]
    assert len(delivered_batches) == 1
    assert len(delivered_batches[0]) == 1
    assert delivered_batches[0][0]["title"] == "Senior AI Engineer"

    second_run_id = run_pipeline(trigger="manual")
    assert second_run_id is not None

    second = get_pipeline_run(second_run_id)
    assert second is not None
    assert second["status"] == "completed"
    assert second["jobs_discovered"] == 2
    assert second["jobs_inserted"] == 0
    assert second["jobs_ranked"] == 0
    assert second["jobs_shortlisted"] == 0
    assert second["jobs_tailored"] == 0
    assert second["jobs_notified"] == 0

    assert tailor_calls == ["Senior AI Engineer"]
    assert len(delivered_batches) == 2
    assert delivered_batches[1] == []


def test_pipeline_records_fatal_stage_failure(monkeypatch) -> None:
    async def broken_scraper(headless: bool = True):
        raise RuntimeError("simulated source outage")

    monkeypatch.setattr(scraper, "scrape_all", broken_scraper)

    with pytest.raises(RuntimeError, match="simulated source outage"):
        run_pipeline(trigger="manual")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, current_stage, error_type, error_message
                FROM pipeline_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()

    assert row["status"] == "failed"
    assert row["current_stage"] == "scraping"
    assert row["error_type"] == "RuntimeError"
    assert "simulated source outage" in row["error_message"]
