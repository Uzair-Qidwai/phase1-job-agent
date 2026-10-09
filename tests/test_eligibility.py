from __future__ import annotations

import json
from pathlib import Path

from src.candidate_profile import CandidateProfile, load_candidate_profile
from src.eligibility import evaluate_eligibility


FIXTURE = Path(__file__).parent.parent / "evals" / "fixtures" / "eligibility.json"


def test_default_candidate_profile_loads() -> None:
    profile = load_candidate_profile()
    assert profile.version == "1"
    assert profile.target_roles


def test_eligibility_golden_cases() -> None:
    profile = load_candidate_profile()
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))

    for case in cases:
        result = evaluate_eligibility(profile=profile, **case["job"])
        assert result.eligible is case["expected_eligible"], case["name"]


def test_explicit_company_exclusion_is_hard_filter() -> None:
    profile = CandidateProfile(
        version="test",
        excluded_companies=["Blocked Corp"],
    )
    result = evaluate_eligibility(
        title="AI Engineer",
        company="Blocked Corp",
        location="Remote",
        profile=profile,
    )
    assert result.eligible is False
    assert "company is explicitly excluded" in result.hard_mismatch_reasons


def test_strict_location_filter_is_opt_in() -> None:
    profile = CandidateProfile(
        version="test",
        preferred_locations=["Toronto"],
        remote_allowed=False,
        strict_locations=True,
    )
    result = evaluate_eligibility(
        title="AI Engineer",
        company="Example",
        location="London, UK",
        profile=profile,
    )
    assert result.eligible is False
