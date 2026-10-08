import json
import sys

import pytest

from evals.preflight import check
from src.settings import Settings


def test_preflight_is_offline_and_redacts_credentials():
    settings = Settings(_env_file=None, MODEL_PROVIDER="openai", MODEL_NAME="configured-model",
                        OPENAI_API_KEY="secret-not-in-report", MODEL_INPUT_COST_PER_MTOK=1,
                        MODEL_OUTPUT_COST_PER_MTOK=2, MODEL_SPEND_STOP_USD=1)
    report = check(settings)
    assert report["ready_for_model_calls"] is True
    assert "secret-not-in-report" not in json.dumps(report)
    assert report["models"][0]["credential_configured"] is True


def test_preflight_lists_missing_configuration_without_calls():
    report = check(Settings(_env_file=None, MODEL_PROVIDER="gemini"))
    assert report["ready_for_model_calls"] is False
    assert any("explicit model" in issue for issue in report["issues"])


def test_live_entrypoint_requires_explicit_flag_before_evaluation(monkeypatch, tmp_path):
    from evals.live_support import run_live
    monkeypatch.setattr(sys, "argv", ["test", "--output", str(tmp_path / "report.json")])
    with pytest.raises(SystemExit) as error:
        run_live(lambda *args: pytest.fail("Live execution reached"))
    assert error.value.code == 2


def test_failed_live_eval_preserves_sanitized_audit(monkeypatch, tmp_path):
    import evals.live_support as support
    path = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["test", "--allow-live", "--output", str(path)])
    monkeypatch.setattr(support, "require_live_ready", lambda settings: None)
    def fail(settings, budget, steps):
        steps.append({"role": "writer", "status": "failed"})
        budget.used = 1
        raise RuntimeError("private prompt and secret")
    assert support.run_live(fail) == 1
    report = json.loads(path.read_text())
    assert report["requests"] == 1
    assert report["agent_steps"][0]["role"] == "writer"
    assert "private prompt" not in path.read_text()


def test_delivery_preview_cannot_send(monkeypatch, tmp_path):
    from evals.delivery_preview import main
    import src.emailer as emailer
    monkeypatch.setattr(emailer, "_get_gmail_service", lambda: pytest.fail("Gmail contacted"))
    path = tmp_path / "digest.html"
    assert main(["--output", str(path)]) == 0
    assert "Example AI Engineer" in path.read_text()


def test_source_summary_detects_missing_and_duplicate_data():
    from evals.source_smoke import summarize
    from src.scraper import RawJob
    job = RawJob(title="Engineer", company="Example", location="Toronto",
                 url="https://example.com/job", description="", source="greenhouse")
    report = summarize("greenhouse", [job, job])
    assert report["duplicate_identities"] == 1
    assert report["missing_descriptions"] == 2
    assert report["passed"] is False
