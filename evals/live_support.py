"""Explicit live-test entry boundary with durable sanitized failure evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from src.settings import get_settings
from src.model_runtime import RunBudget
from evals.preflight import require_live_ready


def run_live(evaluate):
    parser = argparse.ArgumentParser(description=evaluate.__doc__)
    parser.add_argument("--allow-live", action="store_true", required=True,
                        help="Permit bounded paid model calls; no email or database writes")
    parser.add_argument("--output", type=Path, required=True,
                        help="Private report path; CV evaluations include personal drafts")
    args = parser.parse_args()
    settings = get_settings()
    require_live_ready(settings)
    if args.output.exists():
        parser.error("Choose a new report path to preserve previous evidence")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Verify report destination before any paid calls.
    with args.output.open("x") as stream:
        json.dump({"status": "started", "passed": False}, stream)
    args.output.chmod(0o600)
    budget = RunBudget(settings.pipeline_max_model_calls, settings.model_spend_stop_usd)
    steps = []
    root = Path(__file__).resolve().parent.parent
    inputs = [root / "evals/ranking_gold.json", root / "data/master_cv.md"]
    report = {"passed": False, "started_at": datetime.now(timezone.utc).isoformat(),
              "input_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
              "agent_workflow_enabled": settings.agent_workflow_enabled}
    try:
        report.update(evaluate(settings, budget, steps))
    except Exception as exc:
        report.update({"status": "failed", "error_type": type(exc).__name__})
    finally:
        report.update({"agent_steps": steps, "requests": budget.used,
                       "known_cost_usd": budget.known_cost, "cost_complete": budget.cost_complete,
                       "finished_at": datetime.now(timezone.utc).isoformat()})
        args.output.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({"report": str(args.output), "passed": report["passed"],
                      "requests": budget.used, "error_type": report.get("error_type")}))
    return 0 if report["passed"] else 1
