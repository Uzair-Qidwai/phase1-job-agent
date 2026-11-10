from __future__ import annotations

import json
from pathlib import Path

from evals.metrics import pairwise_accuracy, precision_at_k
from src.candidate_profile import load_candidate_profile
from src.ranking import rank_job


GOLD = Path(__file__).parent.parent / "evals" / "ranking_gold.json"


def _rank_gold() -> tuple[dict, dict[str, float]]:
    dataset = json.loads(GOLD.read_text(encoding="utf-8"))
    profile = load_candidate_profile()
    scores = {}

    for job in dataset["jobs"]:
        result = rank_job(
            title=job["title"],
            company=job["company"],
            location=job["location"],
            description=job["description"],
            profile=profile,
        )
        scores[job["id"]] = result.total_score

    return dataset, scores


def test_ranking_contract_is_explainable() -> None:
    profile = load_candidate_profile()
    result = rank_job(
        title="Senior AI Engineer",
        company="Example AI",
        location="Toronto",
        description="Python machine learning AI systems",
        profile=profile,
    )

    assert result.hard_mismatch is False
    assert 0 <= result.total_score <= 100
    assert set(result.component_scores) == {
        "role_fit",
        "domain_skill_fit",
        "location_fit",
    }
    assert result.explanation
    assert result.profile_version == profile.version


def test_golden_pairwise_accuracy_is_perfect_for_baseline() -> None:
    dataset, scores = _rank_gold()
    pairs = [tuple(pair) for pair in dataset["preferred_pairs"]]
    assert pairwise_accuracy(scores, pairs) == 1.0


def test_strong_jobs_dominate_top_five() -> None:
    dataset, scores = _rank_gold()
    ordered = sorted(scores, key=scores.get, reverse=True)
    strong = {job["id"] for job in dataset["jobs"] if job["label"] == "strong"}

    assert precision_at_k(ordered, strong, 5) >= 0.8


def test_hard_mismatch_is_ranked_at_zero() -> None:
    dataset, scores = _rank_gold()
    assert scores["nurse"] == 0.0
