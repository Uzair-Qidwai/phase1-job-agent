"""Offline live-test readiness check. Never contacts a provider, database or Gmail."""
from __future__ import annotations
import json
from src.settings import Settings, get_settings


def check(settings: Settings) -> dict:
    from src.cv_agent import MASTER_CV_PATH
    roles = ("researcher", "analyst", "writer", "reviewer") if settings.agent_workflow_enabled else ("analyst", "writer")
    issues, models = [], []
    for role in roles:
        try:
            config = settings.agent_config(role)
        except ValueError:
            issues.append(f"{role}: configure an explicit model")
            continue
        try:
            settings.require_model_key(config.provider)
            key_present = True
        except RuntimeError:
            key_present = False
            issues.append(f"{role}: configure {config.provider.upper()}_API_KEY locally")
        priced = config.input_cost_per_mtok is not None and config.output_cost_per_mtok is not None
        if not priced:
            issues.append(f"{role}: configure both model cost rates")
        models.append({"role": role, "provider": config.provider, "model": config.model,
                       "credential_configured": key_present, "prices_configured": priced})
    if settings.model_spend_stop_usd is None:
        issues.append("Set MODEL_SPEND_STOP_USD for the controlled live test")
    if not MASTER_CV_PATH.exists():
        issues.append("Master CV is missing")
    return {"mode": "offline_preflight", "agent_workflow_enabled": settings.agent_workflow_enabled,
            "models": models, "request_limit": settings.pipeline_max_model_calls,
            "spend_stop_usd": settings.model_spend_stop_usd, "issues": issues,
            "ready_for_model_calls": not issues,
            "manual_checks": ["Review master CV dates, expected qualifications and placeholder contact details",
                              "Confirm intended models and prices with provider accounts",
                              "Live email needs an explicitly authorized recipient and send"]}


def require_live_ready(settings: Settings):
    report = check(settings)
    if not report["ready_for_model_calls"]:
        raise ValueError("Live preflight incomplete: " + "; ".join(report["issues"]))


def main():
    report = check(get_settings())
    print(json.dumps(report, indent=2))
    return 0 if report["ready_for_model_calls"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
