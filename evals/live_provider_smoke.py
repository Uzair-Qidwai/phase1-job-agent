"""Controlled live-provider smoke test for Phase 2 AI boundaries.

Usage:
    python -m evals.live_provider_smoke --allow-live --output .local/report.json

Requires configured specialist provider credentials. This performs ranking and CV generation; when AGENT_WORKFLOW_ENABLED is true it
uses the four bounded specialists (and can make multiple model/tool calls). It does not write to PostgreSQL and does not send email.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.candidate_profile import load_candidate_profile
from src.cv_agent import tailor_cv
from src.semantic_ranking import rank_job_semantic
from src.model_runtime import AgentRuntime
from evals.live_support import run_live


GOLD = Path(__file__).parent / "ranking_gold.json"


def evaluate(settings, budget, steps) -> dict:
    roles = ("researcher", "analyst", "writer", "reviewer") if settings.agent_workflow_enabled else ("analyst", "writer")
    if settings.cv_review_enabled and "reviewer" not in roles:
        roles += ("reviewer",)
    for role in roles:
        settings.require_model_key(settings.agent_config(role).provider)

    dataset = json.loads(GOLD.read_text(encoding="utf-8"))
    job = next(item for item in dataset["jobs"] if item["id"] == "ai-platform")
    profile = load_candidate_profile()

    ranker, tailorer = rank_job_semantic, tailor_cv
    if settings.agent_workflow_enabled:
        from src.agent_workflow import rank_job_agentic, tailor_cv_agentic
        ranker, tailorer = rank_job_agentic, tailor_cv_agentic
    elif settings.cv_review_enabled:
        from src.agent_workflow import tailor_cv_agentic
        tailorer = tailor_cv_agentic

    ranking = ranker(
        title=job["title"],
        company=job["company"],
        location=job["location"],
        description=job["description"],
        profile=profile,
        runtime=AgentRuntime(settings=settings, run_budget=budget, on_step=steps.append),
    )

    tailored = tailorer(
        job_title=job["title"],
        company=job["company"],
        description=job["description"],
        runtime=AgentRuntime(settings=settings, run_budget=budget, on_step=steps.append),
    )

    report = {
        "job_id": job["id"],
        "agent_workflow_enabled": settings.agent_workflow_enabled,
            "cv_review_enabled": settings.cv_review_enabled,
        "agent_steps": ranking.agent_steps + tailored["agent_steps"],
        "semantic_ranking": {
            "score": ranking.total_score,
            "version": ranking.ranking_version,
            "model": ranking.model,
            "provider": ranking.provider,
            "cost_estimate_complete": ranking.cost_estimate_complete,
            "usage": ranking.usage,
            "estimated_cost_usd": ranking.estimated_cost_usd,
        },
        "cv_generation": {
            "model": tailored["model"],
            "provider": tailored["provider"],
            "cost_estimate_complete": tailored["cost_estimate_complete"],
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

    return report


def main() -> int:
    return run_live(evaluate)


if __name__ == "__main__":
    raise SystemExit(main())
