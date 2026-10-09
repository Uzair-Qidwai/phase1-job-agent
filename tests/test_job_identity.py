"""Golden regression tests for source-aware job identity."""

from __future__ import annotations

import json
from pathlib import Path

from src.job_identity import build_job_identity, canonicalize_url, extract_source_job_id


FIXTURES = Path(__file__).parent.parent / "evals" / "fixtures" / "job_identity.json"


def _cases() -> list[dict]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def test_job_identity_golden_fixtures() -> None:
    for case in _cases():
        identity = build_job_identity(case["url"], case["source"])
        assert identity.source_job_id == case["expected_source_job_id"], case["name"]
        assert identity.canonical_url == case["expected_canonical_url"], case["name"]


def test_indeed_distinct_jk_values_remain_distinct() -> None:
    first = build_job_identity("https://ca.indeed.com/viewjob?jk=ABC123", "indeed")
    second = build_job_identity("https://ca.indeed.com/viewjob?jk=XYZ789", "indeed")
    assert first.dedupe_key != second.dedupe_key


def test_indeed_tracking_parameters_do_not_change_identity() -> None:
    a = build_job_identity(
        "https://ca.indeed.com/viewjob?jk=ABC123&utm_source=a&utm_campaign=x",
        "indeed",
    )
    b = build_job_identity(
        "https://ca.indeed.com/viewjob?utm_campaign=y&jk=ABC123&utm_source=b",
        "indeed",
    )
    assert a.dedupe_key == b.dedupe_key
    assert a.canonical_url == b.canonical_url


def test_linkedin_source_id_is_extracted() -> None:
    raw = "https://www.linkedin.com/jobs/view/ai-engineer-1234567890/?trackingId=foo"
    assert extract_source_job_id(raw, "linkedin") == "1234567890"


def test_fragment_is_removed() -> None:
    assert canonicalize_url(
        "https://example.com/jobs/42?utm_source=x#apply",
        "greenhouse",
    ) == "https://example.com/jobs/42"
