"""Live candidate-vs-baseline ranking evaluation.

Usage:
    python -m evals.run_semantic_eval

Requires the configured analyst provider credential and model.
The command exits non-zero if semantic ranking regresses on Precision@5 or
pairwise preference accuracy against the deterministic baseline.
"""

from __future__ import annotations

import json
from pathlib import Path

from evals.metrics import pairwise_accuracy, precision_at_k
from src.candidate_profile import load_candidate_profile
from src.ranking import rank_job
from src.semantic_ranking import rank_job_semantic
from src.settings import get_settings


GOLD = Path(__file__).parent / "ranking_gold.json"


def _metrics(dataset: dict, scores: dict[str, float]) -> dict[str, float]:
    ordered = sorted(scores, key=scores.get, reverse=True)
    strong = {
        job["id"]
        for job in dataset["jobs"]
        if job["label"] == "strong"
    }
    pairs = [tuple(pair) for pair in dataset["preferred_pairs"]]
    return {
        "precision_at_5": precision_at_k(ordered, strong, 5),
        "pairwise_accuracy": pairwise_accuracy(scores, pairs),
    }


def main() -> int:
    settings = get_settings()
    config = settings.agent_config("analyst")
    settings.require_model_key(config.provider)
    profile = load_candidate_profile()
    dataset = json.loads(GOLD.read_text(encoding="utf-8"))

    baseline_scores: dict[str, float] = {}
    candidate_scores: dict[str, float] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    estimated_cost_usd = 0.0
    cost_estimate_complete = True

    for job in dataset["jobs"]:
        common = {
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "description": job["description"],
            "profile": profile,
        }
        baseline = rank_job(**common)
        candidate = rank_job_semantic(
            **common,

        )

        baseline_scores[job["id"]] = baseline.total_score
        candidate_scores[job["id"]] = candidate.total_score
        total_input_tokens += candidate.usage.get("input_tokens", 0)
        total_output_tokens += candidate.usage.get("output_tokens", 0)
        estimated_cost_usd += candidate.estimated_cost_usd
        cost_estimate_complete = cost_estimate_complete and candidate.cost_estimate_complete

    baseline_metrics = _metrics(dataset, baseline_scores)
    candidate_metrics = _metrics(dataset, candidate_scores)

    passed = (
        candidate_metrics["precision_at_5"]
        >= baseline_metrics["precision_at_5"]
        and candidate_metrics["pairwise_accuracy"]
        >= baseline_metrics["pairwise_accuracy"]
    )

    report = {
        "ranking_model": config.model,
        "provider": config.provider,
        "profile_version": profile.version,
        "dataset_jobs": len(dataset["jobs"]),
        "baseline": baseline_metrics,
        "candidate": candidate_metrics,
        "candidate_usage": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "estimated_cost_usd": round(estimated_cost_usd, 6),
            "cost_estimate_complete": cost_estimate_complete,
        },
        "promotion_gate_passed": passed,
        "scores": {
            "baseline": baseline_scores,
            "candidate": candidate_scores,
        },
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
