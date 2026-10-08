"""Controlled live-provider smoke test for Phase 2 AI boundaries.

Usage:
    python -m evals.live_provider_smoke

Requires ANTHROPIC_API_KEY. This performs one semantic ranking call and one CV
generation call. It does not write to PostgreSQL and does not send email.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.candidate_profile import load_candidate_profile
from src.cv_agent import tailor_cv
from src.semantic_ranking import rank_job_semantic
from src.settings import get_settings


GOLD = Path(__file__).parent / "ranking_gold.json"


def main() -> int:
    settings = get_settings()
    settings.require_anthropic_api_key()

    dataset = json.loads(GOLD.read_text(encoding="utf-8"))
    job = next(item for item in dataset["jobs"] if item["id"] == "ai-platform")
    profile = load_candidate_profile()

    ranking = rank_job_semantic(
        title=job["title"],
        company=job["company"],
        location=job["location"],
        description=job["description"],
        profile=profile,
        model=settings.ranking_model,
    )

    tailored = tailor_cv(
        job_title=job["title"],
        company=job["company"],
        description=job["description"],
    )

    report = {
        "job_id": job["id"],
        "semantic_ranking": {
            "score": ranking.total_score,
            "version": ranking.ranking_version,
            "model": ranking.model,
            "usage": ranking.usage,
            "estimated_cost_usd": ranking.estimated_cost_usd,
        },
        "cv_generation": {
            "model": tailored["model"],
            "prompt_version": tailored["prompt_version"],
            "profile_version": tailored["profile_version"],
            "evidence_items": len(tailored["evidence_used"]),
            "warnings": tailored["warnings"],
            "validation": tailored["validation"],
            "usage": tailored["usage"],
            "estimated_cost_usd": tailored["estimated_cost_usd"],
        },
        "passed": bool(
            ranking.total_score >= 0
            and tailored["validation"]["valid"]
            and tailored["evidence_used"]
        ),
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
