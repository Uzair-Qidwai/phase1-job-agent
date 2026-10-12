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
        ("description", "description is required"),
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


def test_normalization_rejects_blank_description_without_losing_complete_duplicate():
    from src.scraper import normalize_jobs
    rows = [
        RawJob('AI Engineer', 'Example', 'Toronto',
               'https://www.linkedin.com/jobs/view/123?trk=incomplete', '  \n', 'linkedin'),
        RawJob('AI Engineer', 'Example', 'Toronto',
               'https://www.linkedin.com/jobs/view/123?trk=complete',
               'Build evaluation systems.', 'linkedin'),
    ]
    normalized = normalize_jobs(rows)
    assert len(normalized) == 1
    assert normalized[0].description == 'Build evaluation systems.'
    assert normalized[0].url == 'https://www.linkedin.com/jobs/view/123'


@pytest.mark.asyncio
async def test_greenhouse_preserves_sponsorship_tail_and_filters_before_limit(monkeypatch):
    import httpx
    import src.scraper as scraper

    class Response:
        status_code = 200

        def json(self):
            return {'jobs': [
                {'title': 'Office Administrator'},
                {'title': 'Applied AI Engineer', 'location': {'name': 'London, UK'},
                 'absolute_url': 'https://example.com/job', 'id': 1,
                 'content': '&lt;p&gt;' + 'Responsibilities ' * 700 +
                            '&lt;/p&gt;&lt;p&gt;We cannot sponsor visas.&lt;/p&gt;'},
            ]}

    async def get(self, url):
        return Response()

    monkeypatch.setattr(httpx.AsyncClient, 'get', get)
    monkeypatch.setattr(scraper, 'GREENHOUSE_BOARDS', ['example'])
    jobs = await scraper.scrape_greenhouse(max_per_board=1)
    assert len(jobs) == 1
    assert jobs[0].description.endswith('We cannot sponsor visas.')
    assert '<p>' not in jobs[0].description


@pytest.mark.asyncio
async def test_ashby_skips_unlisted_and_preserves_secondary_locations(monkeypatch):
    import httpx
    import src.scraper as scraper
    posting = {'id': 'abc', 'title': 'Applied AI Engineer', 'isListed': True,
               'location': 'New York, NY', 'secondaryLocations': [{'location': 'Toronto, Canada'}],
               'jobUrl': 'https://jobs.ashbyhq.com/example/abc',
               'descriptionPlain': 'Build AI. We do sponsor visas.'}

    async def get(self, url):
        return httpx.Response(200, request=httpx.Request('GET', url),
                              json={'jobs': [posting, {**posting, 'id': 'hidden', 'isListed': False}]})

    monkeypatch.setattr(httpx.AsyncClient, 'get', get)
    monkeypatch.setattr(scraper, 'ASHBY_BOARDS', ['example'])
    jobs = await scraper.AshbySource().discover()
    assert len(jobs) == 1
    assert jobs[0].source_job_id == 'abc'
    assert jobs[0].location == 'New York, NY | Toronto, Canada'
    assert jobs[0].description.endswith('We do sponsor visas.')


@pytest.mark.asyncio
async def test_ashby_failed_board_does_not_drop_other_board(monkeypatch):
    import httpx
    import src.scraper as scraper

    async def get(self, url):
        if '/bad' in url:
            raise httpx.ConnectError('unreachable')
        return httpx.Response(200, request=httpx.Request('GET', url), json={'jobs': [{
            'id': 'ok', 'title': 'AI Engineer', 'isListed': True, 'location': 'Toronto',
            'jobUrl': 'https://jobs.ashbyhq.com/good/ok', 'descriptionPlain': 'Build AI'}]})

    monkeypatch.setattr(httpx.AsyncClient, 'get', get)
    monkeypatch.setattr(scraper, 'ASHBY_BOARDS', ['bad', 'good'])
    assert len(await scraper.AshbySource().discover()) == 1
