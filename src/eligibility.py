"""Conservative deterministic eligibility filtering for Phase 2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.candidate_profile import CandidateProfile


class EligibilityResult(BaseModel):
    eligible: bool
    hard_mismatch_reasons: list[str] = Field(default_factory=list)
    positive_signals: list[str] = Field(default_factory=list)


def _contains(value: str, needle: str) -> bool:
    return needle.casefold() in value.casefold()


def evaluate_eligibility(
    *,
    title: str,
    company: str,
    location: str,
    profile: CandidateProfile,
) -> EligibilityResult:
    """Apply only explicit/conservative hard filters.

    The purpose of Stage 1 is to avoid wasting semantic-ranking/model calls on
    jobs that are clearly disallowed by configured constraints. Ambiguous jobs
    remain eligible and are decided by Stage 2 ranking.
    """

    hard_mismatches: list[str] = []
    signals: list[str] = []

    excluded_companies = {item.casefold().strip() for item in profile.excluded_companies}
    if company.casefold().strip() in excluded_companies:
        hard_mismatches.append("company is explicitly excluded")

    for keyword in profile.excluded_title_keywords:
        if _contains(title, keyword):
            hard_mismatches.append(f"title contains excluded keyword: {keyword}")
            break

    is_remote = _contains(location, "remote")
    if is_remote and not profile.remote_allowed:
        hard_mismatches.append("remote role is not allowed by candidate profile")

    if profile.strict_locations and not is_remote:
        location_match = any(
            _contains(location, preferred)
            for preferred in profile.preferred_locations
            if preferred.casefold() != "remote"
        )
        if not location_match:
            hard_mismatches.append("location is outside configured allowed locations")

    for keyword in profile.role_keywords:
        if _contains(title, keyword):
            signals.append(f"title matches role keyword: {keyword}")
            break

    if is_remote and profile.remote_allowed:
        signals.append("remote-compatible")

    if any(_contains(location, item) for item in profile.preferred_locations):
        signals.append("preferred-location match")

    return EligibilityResult(
        eligible=not hard_mismatches,
        hard_mismatch_reasons=hard_mismatches,
        positive_signals=signals,
    )
