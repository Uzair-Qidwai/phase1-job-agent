"""Reproducible Phase 2 acceptance metrics without provider, DB or email calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evals.run_semantic_eval import _metrics
from src.candidate_profile import load_candidate_profile
from src.cv_agent import CV_PROMPT_VERSION
from src.cv_validation import TailoredCVResult, validate_tailored_cv
from src.ranking import rank_job

ROOT = Path(__file__).resolve().parent


def evaluate() -> dict:
    ranking_path = ROOT / "ranking_gold.json"
    cv_path = ROOT / "cv_gold.json"
    dataset = json.loads(ranking_path.read_text())
    profile = load_candidate_profile()
    scores = {
        job["id"]: rank_job(**{key: job[key] for key in (
            "title", "company", "location", "description"
        )}, profile=profile).total_score
        for job in dataset["jobs"]
    }
    metrics = _metrics(dataset, scores)
    cases = json.loads(cv_path.read_text())
    outcomes = []
    for case in cases:
        validation = validate_tailored_cv(
            TailoredCVResult.model_validate(case["result"]),
            master_cv=case["master_cv"], candidate_profile_text=case["candidate_profile"],
        )
        outcomes.append({"name": case["name"], "expected_valid": case["expected_valid"],
                         "actual_valid": validation.valid,
                         "passed": validation.valid == case["expected_valid"]})
    return {
        "mode": "offline_deterministic",
        "profile_version": profile.version,
        "cv_prompt_version": CV_PROMPT_VERSION,
        "dataset_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in (ranking_path, cv_path)},
        "ranking": {"jobs": len(scores), **metrics},
        "cv": {"cases": len(outcomes), "passed": sum(row["passed"] for row in outcomes),
               "outcomes": outcomes},
        "live_validation": "pending; not performed by this evaluator",
        "passed": (metrics["precision_at_5"] >= 0.8 and metrics["pairwise_accuracy"] == 1.0
                   and all(row["passed"] for row in outcomes)),
    }


def main() -> int:
    report = evaluate()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
