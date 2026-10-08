"""Generate three representative CVs for explicit human factuality/quality review."""
import json
from pathlib import Path
from src.model_runtime import AgentRuntime
from src.cv_agent import tailor_cv
from src.agent_workflow import tailor_cv_agentic
from evals.live_support import run_live


def evaluate(settings, budget, steps):
    dataset = json.loads((Path(__file__).parent / "ranking_gold.json").read_text())
    jobs = [j for j in dataset["jobs"] if j["label"] == "strong"][:3]
    results = []
    tailorer = tailor_cv_agentic if settings.agent_workflow_enabled else tailor_cv
    for job in jobs:
        try:
            result = tailorer(job_title=job["title"], company=job["company"], description=job["description"],
                              runtime=AgentRuntime(settings=settings, run_budget=budget, on_step=steps.append))
            results.append({"job_id": job["id"], "generated": True, "result": result,
                            "human_review": {"factual": None, "relevant": None, "false_rejection": None,
                                             "notes": "Pending human review"}})
        except Exception as exc:
            results.append({"job_id": job["id"], "generated": False, "error_type": type(exc).__name__,
                            "human_review": {"false_rejection": None, "notes": "Inspect rejection before promotion"}})
    return {"passed": all(row["generated"] for row in results), "human_acceptance": "pending",
            "cases": results, "generated": sum(row["generated"] for row in results),
            "writer_calls": sum(step["role"] == "writer" for step in steps),
            "reviewer_calls": sum(step["role"] == "reviewer" for step in steps)}


def main():
    return run_live(evaluate)


if __name__ == "__main__":
    raise SystemExit(main())
