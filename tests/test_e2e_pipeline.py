from __future__ import annotations

import os

import pytest

import src.cv_agent as cv_agent
import src.emailer as emailer
import src.ranking as ranking_module
import src.scraper as scraper
from src.scheduler import resume_pipeline, run_pipeline
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


def test_failed_tailoring_is_retried_from_shortlisted_state(monkeypatch) -> None:
    strong = scraper.RawJob(
        title="Senior AI Engineer",
        company="Example AI",
        location="Toronto, Canada",
        url="https://example.com/jobs/retry-tailor",
        description="Build AI and machine learning systems in Python.",
        source="phase2-e2e",
        source_job_id="retry-tailor",
    )

    async def fake_scrape_all(headless: bool = True):
        return [strong]

    attempts = {"count": 0}

    def flaky_tailor_cv(*, job_title, company, description):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("simulated CV provider failure")
        return {
            "tailored_cv": (
                "# Tailored CV\n\n"
                "Evidence-backed AI engineering experience with Python and "
                "machine learning systems."
            ),
            "changes_made": "Front-loaded relevant AI engineering evidence.",
            "evidence_used": [
                {
                    "claim": "Python experience",
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

    monkeypatch.setattr(scraper, "scrape_all", fake_scrape_all)
    monkeypatch.setattr(cv_agent, "tailor_cv", flaky_tailor_cv)
    monkeypatch.setattr(emailer, "send_digest", lambda jobs: True)

    first_run = run_pipeline(trigger="manual")
    assert first_run is not None
    first = get_pipeline_run(first_run)
    assert first["jobs_inserted"] == 1
    assert first["jobs_shortlisted"] == 1
    assert first["jobs_tailored"] == 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT system_state
                FROM jobs
                WHERE source = 'phase2-e2e' AND source_job_id = 'retry-tailor'
                """
            )
            row = cur.fetchone()
    assert row["system_state"] == "shortlisted"

    second_run = run_pipeline(trigger="retry")
    assert second_run is not None
    second = get_pipeline_run(second_run)

    assert second["jobs_inserted"] == 0
    assert second["jobs_ranked"] == 0
    assert second["jobs_shortlisted"] == 0
    assert second["jobs_tailored"] == 1
    assert attempts["count"] == 2

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT system_state
                FROM jobs
                WHERE source = 'phase2-e2e' AND source_job_id = 'retry-tailor'
                """
            )
            row = cur.fetchone()
    assert row["system_state"] == "notified"


def test_notification_failure_resumes_without_repeating_expensive_stages(monkeypatch) -> None:
    strong = scraper.RawJob(
        title="Senior AI Engineer",
        company="Example AI",
        location="Toronto, Canada",
        url="https://example.com/jobs/resume-notify",
        description="Build production AI and machine learning systems in Python.",
        source="phase2-e2e",
        source_job_id="resume-notify",
    )

    calls = {"scrape": 0, "tailor": 0, "send": 0}

    async def fake_scrape_all(headless: bool = True):
        calls["scrape"] += 1
        return [strong]

    def fake_tailor_cv(*, job_title, company, description):
        calls["tailor"] += 1
        return {
            "tailored_cv": (
                "# Tailored CV\n\n"
                "Evidence-backed AI engineering experience with Python and "
                "machine learning systems."
            ),
            "changes_made": "Front-loaded relevant AI engineering evidence.",
            "evidence_used": [
                {
                    "claim": "Python experience",
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

    def flaky_send_digest(jobs):
        calls["send"] += 1
        return calls["send"] > 1

    monkeypatch.setattr(scraper, "scrape_all", fake_scrape_all)
    monkeypatch.setattr(cv_agent, "tailor_cv", fake_tailor_cv)
    monkeypatch.setattr(emailer, "send_digest", flaky_send_digest)

    with pytest.raises(RuntimeError, match="Digest delivery failed"):
        run_pipeline(trigger="manual")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, current_stage
                FROM pipeline_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            failed = cur.fetchone()

    assert failed["status"] == "failed"
    assert failed["current_stage"] == "notifying"

    retry_id = resume_pipeline(str(failed["id"]))
    assert retry_id is not None
    retry = get_pipeline_run(retry_id)
    assert retry is not None
    assert retry["status"] == "completed"
    assert str(retry["retry_of_run_id"]) == str(failed["id"])
    assert retry["jobs_discovered"] == 0
    assert retry["jobs_inserted"] == 0
    assert retry["jobs_ranked"] == 0
    assert retry["jobs_shortlisted"] == 0
    assert retry["jobs_tailored"] == 0
    assert retry["jobs_notified"] == 1

    assert calls == {"scrape": 1, "tailor": 1, "send": 2}


def test_ranking_failure_resumes_from_filtering_without_rescraping(monkeypatch) -> None:
    strong = scraper.RawJob(
        title="Senior AI Engineer",
        company="Example AI",
        location="Toronto, Canada",
        url="https://example.com/jobs/resume-ranking",
        description="Build AI and machine learning systems in Python.",
        source="phase2-e2e",
        source_job_id="resume-ranking",
    )

    calls = {"scrape": 0, "rank": 0, "tailor": 0}
    real_rank_job = ranking_module.rank_job

    async def fake_scrape_all(headless: bool = True):
        calls["scrape"] += 1
        return [strong]

    def flaky_rank_job(**kwargs):
        calls["rank"] += 1
        if calls["rank"] == 1:
            raise RuntimeError("simulated ranking provider failure")
        return real_rank_job(**kwargs)

    def fake_tailor_cv(*, job_title, company, description):
        calls["tailor"] += 1
        return {
            "tailored_cv": (
                "# Tailored CV\n\n"
                "Evidence-backed AI engineering experience with Python and "
                "machine learning systems."
            ),
            "changes_made": "Front-loaded relevant AI engineering evidence.",
            "evidence_used": [
                {
                    "claim": "Python experience",
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

    monkeypatch.setattr(scraper, "scrape_all", fake_scrape_all)
    monkeypatch.setattr(ranking_module, "rank_job", flaky_rank_job)
    monkeypatch.setattr(cv_agent, "tailor_cv", fake_tailor_cv)
    monkeypatch.setattr(emailer, "send_digest", lambda jobs: True)

    with pytest.raises(RuntimeError, match="simulated ranking provider failure"):
        run_pipeline(trigger="manual")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, current_stage
                FROM pipeline_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            failed = cur.fetchone()

    assert failed["status"] == "failed"
    assert failed["current_stage"] == "ranking"

    retry_id = resume_pipeline(str(failed["id"]))
    assert retry_id is not None
    retry = get_pipeline_run(retry_id)
    assert retry is not None
    assert retry["status"] == "completed"
    assert str(retry["retry_of_run_id"]) == str(failed["id"])
    assert retry["jobs_discovered"] == 0
    assert retry["jobs_inserted"] == 0
    assert retry["jobs_ranked"] == 1
    assert retry["jobs_shortlisted"] == 1
    assert retry["jobs_tailored"] == 1
    assert retry["jobs_notified"] == 1

    assert calls["scrape"] == 1
    assert calls["rank"] == 2
    assert calls["tailor"] == 1
