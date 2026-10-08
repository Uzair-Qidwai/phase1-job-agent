from src.emailer import _build_html


def test_digest_escapes_untrusted_job_content() -> None:
    html = _build_html(
        [
            {
                "title": "<script>alert(1)</script>",
                "company": "<b>Bad Corp</b>",
                "location": "Toronto",
                "url": "javascript:alert(1)",
                "match_score": 0.9,
                "changes_made": "<svg onload=alert(1)>",
                "source": "<img src=x onerror=alert(1)>",
            }
        ]
    )

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert 'href="#"' in html
    assert "javascript:alert(1)" not in html
