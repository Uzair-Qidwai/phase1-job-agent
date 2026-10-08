from src.job_identity import build_job_identity, canonicalize_url, extract_source_job_id


def test_indeed_distinct_jk_values_remain_distinct():
    first = build_job_identity(
        "https://ca.indeed.com/viewjob?jk=ABC123&utm_source=email",
        "indeed",
    )
    second = build_job_identity(
        "https://ca.indeed.com/viewjob?jk=XYZ789&utm_source=email",
        "indeed",
    )

    assert first.source_job_id == "ABC123"
    assert second.source_job_id == "XYZ789"
    assert first.dedupe_key != second.dedupe_key
    assert first.canonical_url == "https://ca.indeed.com/viewjob?jk=ABC123"
    assert second.canonical_url == "https://ca.indeed.com/viewjob?jk=XYZ789"


def test_indeed_tracking_parameters_do_not_change_identity():
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


def test_linkedin_tracking_parameters_removed():
    raw = "https://www.linkedin.com/jobs/view/ai-engineer-1234567890/?trackingId=foo&utm_source=x"
    assert canonicalize_url(raw, "linkedin") == (
        "https://www.linkedin.com/jobs/view/ai-engineer-1234567890"
    )
    assert extract_source_job_id(raw, "linkedin") == "1234567890"


def test_fragment_is_removed():
    assert canonicalize_url(
        "https://example.com/jobs/42?utm_source=x#apply",
        "greenhouse",
    ) == "https://example.com/jobs/42"
