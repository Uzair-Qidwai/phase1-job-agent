"""Explainable Stage 2 ranking contract and deterministic baseline."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from src.candidate_profile import CandidateProfile
from src.eligibility import evaluate_eligibility


TOKEN_RE = re.compile(r"[a-z0-9+#.-]+")


class RankingResult(BaseModel):
    total_score: float = Field(ge=0.0, le=100.0)
    hard_mismatch: bool
    component_scores: dict[str, float]
    explanation: list[str] = Field(default_factory=list)
    profile_version: str
    ranking_version: str = "deterministic-v1"


def _tokens(value: str) -> set[str]:
    return set(TOKEN_RE.findall(value.casefold()))


def _target_role_score(title: str, target_roles: list[str]) -> float:
    title_tokens = _tokens(title)
    if not target_roles:
        return 50.0

    best = 0.0
    for role in target_roles:
        role_tokens = _tokens(role)
        if not role_tokens:
            continue
        overlap = len(title_tokens & role_tokens) / len(role_tokens)
        best = max(best, overlap * 100.0)
    return best


def _keyword_score(text: str, keywords: list[str]) -> tuple[float, list[str]]:
    if not keywords:
        return 50.0, []

    matches = [keyword for keyword in keywords if keyword.casefold() in text.casefold()]
    # Five distinct configured signals are enough to saturate this component.
    score = min(100.0, (len(set(matches)) / 5.0) * 100.0)
    return score, list(dict.fromkeys(matches))


def _location_score(location: str, profile: CandidateProfile) -> float:
    location_folded = location.casefold()

    if "remote" in location_folded and profile.remote_allowed:
        return 100.0

    if any(item.casefold() in location_folded for item in profile.preferred_locations):
        return 100.0

    # Location is a preference unless strict_locations is enabled at Stage 1.
    return 60.0


def rank_job(
    *,
    title: str,
    company: str,
    location: str,
    description: str,
    profile: CandidateProfile,
) -> RankingResult:
    eligibility = evaluate_eligibility(
        title=title,
        company=company,
        location=location,
        profile=profile,
    )

    if not eligibility.eligible:
        return RankingResult(
            total_score=0.0,
            hard_mismatch=True,
            component_scores={
                "role_fit": 0.0,
                "domain_skill_fit": 0.0,
                "location_fit": 0.0,
            },
            explanation=eligibility.hard_mismatch_reasons,
            profile_version=profile.version,
        )

    role_fit = _target_role_score(title, profile.target_roles)
    domain_fit, keyword_matches = _keyword_score(
        f"{title}\n{description}",
        profile.role_keywords,
    )
    location_fit = _location_score(location, profile)

    total = (role_fit * 0.55) + (domain_fit * 0.30) + (location_fit * 0.15)

    explanation = list(eligibility.positive_signals)
    if keyword_matches:
        explanation.append(
            "matched configured role/domain signals: " + ", ".join(keyword_matches[:8])
        )

    return RankingResult(
        total_score=round(total, 2),
        hard_mismatch=False,
        component_scores={
            "role_fit": round(role_fit, 2),
            "domain_skill_fit": round(domain_fit, 2),
            "location_fit": round(location_fit, 2),
        },
        explanation=explanation,
        profile_version=profile.version,
    )
