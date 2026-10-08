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
