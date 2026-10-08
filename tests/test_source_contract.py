from __future__ import annotations

import pytest

from src.scraper import (
    GreenhouseSource,
    IndeedSource,
    LinkedInSource,
    RawJob,
    validate_raw_job,
)


def test_raw_job_contract_accepts_valid_job() -> None:
    job = RawJob(
        title="AI Engineer",
        company="Example",
        location="Remote",
        url="https://example.com/jobs/1",
        description="Build AI systems",
        source="greenhouse",
        source_job_id="1",
    )
    assert validate_raw_job(job) == []


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("title", "title is required"),
        ("company", "company is required"),
        ("url", "url is required"),
        ("source", "source is required"),
    ],
)
def test_raw_job_contract_rejects_missing_required_fields(field: str, expected: str) -> None:
    payload = {
        "title": "AI Engineer",
        "company": "Example",
        "location": "Remote",
        "url": "https://example.com/jobs/1",
        "description": "Build AI systems",
        "source": "greenhouse",
    }
    payload[field] = ""
    job = RawJob(**payload)
    assert expected in validate_raw_job(job)


def test_browser_sources_require_browser() -> None:
    with pytest.raises(ValueError):
        import asyncio
        asyncio.run(LinkedInSource().discover())

    with pytest.raises(ValueError):
        import asyncio
        asyncio.run(IndeedSource().discover())


def test_adapters_expose_stable_source_names() -> None:
    assert LinkedInSource.name == "linkedin"
    assert IndeedSource.name == "indeed"
    assert GreenhouseSource.name == "greenhouse"


def test_live_overlapping_search_results_use_production_deduplication():
    from src.scraper import normalize_jobs
    from evals.source_smoke import summarize
    rows = [RawJob('Engineer', 'Example', 'Toronto', url, 'Python systems', 'linkedin')
            for url in ['https://www.linkedin.com/jobs/view/123?trk=first',
                        'https://www.linkedin.com/jobs/view/123?trk=second']]
    report = summarize('linkedin', rows)
    assert report['duplicate_identities'] == 1
    assert report['unique_jobs'] == 1
    assert report['dedupe_passed'] and report['passed']
    assert normalize_jobs(rows)[0].url == 'https://www.linkedin.com/jobs/view/123'
