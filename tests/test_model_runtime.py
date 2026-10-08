import pytest
from agents import function_tool
from openai.types.responses import ResponseFunctionToolCall
from pydantic import BaseModel, ValidationError

from evals.fake_models import FakeModel, message
from src.model_runtime import AgentRuntime, SpecialistError
from src.settings import Settings


class Answer(BaseModel):
    answer: str



def config(**kwargs):
    return Settings(_env_file=None, MODEL_PROVIDER="openai", MODEL_NAME="test-model", **kwargs)


def invoke(runtime, **kwargs):
    return runtime.run("researcher", instructions="Use the evidence tool.", prompt="Test input",
                       output_type=Answer, prompt_version="test-v1", **kwargs)


def test_real_sdk_executes_tool_loop_and_accounts_each_request():
    calls = []
    @function_tool
    def read_evidence() -> str:
        """Read the supplied evidence."""
        calls.append(True)
        return "verified source"

    model = FakeModel([
        ResponseFunctionToolCall(type="function_call", call_id="call_1", name="read_evidence", arguments="{}"),
        message({"answer": "verified source"}),
    ])
    runtime = AgentRuntime(settings=config(MODEL_INPUT_COST_PER_MTOK=1, MODEL_OUTPUT_COST_PER_MTOK=2), model_factory=lambda _: model)
    result = invoke(runtime, tools=[read_evidence])
    assert result.output.answer == "verified source"
    assert calls == [True]
    assert "verified source" in str(model.inputs[1])
    assert result.step["model_requests"] == 2
    assert result.step["input_tokens"] == 200
    assert result.step["estimated_cost_usd"] == pytest.approx(0.00028)
    assert runtime.totals()["cost_estimate_complete"] is True
    assert "Test input" not in str(result.step)


def test_budget_blocks_second_request_and_records_partial_usage():
    model = FakeModel([message({"answer": "first"}), message({"answer": "never"})])
    runtime = AgentRuntime(settings=config(AGENT_MAX_MODEL_CALLS=1), model_factory=lambda _: model)
    invoke(runtime)
    with pytest.raises(SpecialistError, match="BudgetExceeded"):
        invoke(runtime)
    assert len(model.inputs) == 1
    assert runtime.steps[-1]["model_requests"] == 0
    assert runtime.totals()["usage"]["input_tokens"] == 100


def test_timeout_stops_run_and_reports_unknown_usage():
    import asyncio
    class SlowModel(FakeModel):
        async def get_response(self, *args, **kwargs):
            await asyncio.sleep(5)
    runtime = AgentRuntime(settings=config(AGENT_TIMEOUT_SECONDS=0.01), model_factory=lambda _: SlowModel([]))
    with pytest.raises(SpecialistError, match="TimeoutError"):
        invoke(runtime)
    assert runtime.steps[0]["usage_complete"] is False
    assert runtime.steps[0]["estimated_cost_usd"] is None


def test_provider_error_is_sanitized():
    model = FakeModel([RuntimeError("secret-key and private prompt")])
    runtime = AgentRuntime(settings=config(), model_factory=lambda _: model)
    with pytest.raises(SpecialistError) as caught:
        invoke(runtime)
    assert "secret-key" not in str(caught.value)
    assert "secret-key" not in str(runtime.steps)
    assert runtime.steps[0]["status"] == "failed"


def test_missing_key_fails_without_a_provider_call(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runtime = AgentRuntime(settings=config())
    with pytest.raises(SpecialistError, match="RuntimeError"):
        invoke(runtime)
    assert runtime.steps[0]["model_requests"] == 0


def test_unknown_pricing_is_not_reported_as_free():
    runtime = AgentRuntime(settings=config(), model_factory=lambda _: FakeModel([message({"answer": "ok"})]))
    result = invoke(runtime)
    assert result.step["estimated_cost_usd"] is None
    assert runtime.totals()["cost_estimate_complete"] is False


def test_role_override_and_explicit_model_validation():
    settings = config(AGENT_MODELS={"writer": {"provider": "gemini", "model": "configured-writer"}})
    assert settings.agent_config("writer").provider == "gemini"
    assert settings.agent_config("analyst").provider == "openai"
    with pytest.raises(ValueError, match="conflicts"):
        settings.agent_config("writer", model="different")
    with pytest.raises(ValueError, match="MODEL_NAME"):
        Settings(_env_file=None, MODEL_PROVIDER="gemini").agent_config("writer")
    with pytest.raises(ValidationError):
        config(AGENT_MODELS={"typo-role": {"provider": "openai", "model": "test"}})


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
def test_provider_adapter_routing_without_network(provider, monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    import agents
    import openai
    import agents.extensions.models.litellm_model as adapters
    seen = {}
    fake = FakeModel([message({"answer": "ok"})])
    class Client:
        def __init__(self, **kwargs):
            seen["client_key"] = kwargs["api_key"]
        async def close(self):
            seen["closed"] = True
    def adapter(**kwargs):
        seen.update(kwargs)
        return fake
    monkeypatch.setattr(openai, "AsyncOpenAI", Client)
    monkeypatch.setattr(agents, "OpenAIResponsesModel", adapter)
    monkeypatch.setattr(adapters, "LitellmModel", adapter)
    settings = Settings(_env_file=None, MODEL_PROVIDER=provider, MODEL_NAME="configured-model",
                        **{provider.upper() + "_API_KEY": "test-key"})
    result = invoke(AgentRuntime(settings=settings))
    assert result.step["provider"] == provider
    assert seen["model"] == ("configured-model" if provider == "openai" else f"{provider}/configured-model")
    if provider == "openai":
        assert seen["closed"] is True
    else:
        assert seen["api_key"] == "test-key"


def test_malformed_structured_output_is_rejected_but_usage_is_kept():
    runtime = AgentRuntime(settings=config(), model_factory=lambda _: FakeModel([message({"wrong_field": "bad"})]))
    with pytest.raises(SpecialistError):
        invoke(runtime)
    assert runtime.steps[0]["status"] == "failed"
    assert runtime.steps[0]["input_tokens"] == 100
    assert runtime.steps[0]["usage_complete"] is True


def test_sdk_turn_limit_stops_tool_loop():
    @function_tool
    def read_evidence() -> str:
        """Read evidence."""
        return "source"
    model = FakeModel([ResponseFunctionToolCall(type="function_call", call_id="one", name="read_evidence", arguments="{}"),
                       message({"answer": "must not reach"})])
    runtime = AgentRuntime(settings=config(AGENT_MAX_TURNS=1), model_factory=lambda _: model)
    with pytest.raises(SpecialistError, match="MaxTurnsExceeded"):
        invoke(runtime, tools=[read_evidence])
    assert len(model.inputs) == 1
    assert runtime.steps[0]["tool_calls"] == ["read_evidence"]


def test_explicit_model_override_does_not_inherit_another_models_prices():
    settings = config(MODEL_INPUT_COST_PER_MTOK=1, MODEL_OUTPUT_COST_PER_MTOK=2)
    override = settings.agent_config("writer", model="different-model")
    assert override.input_cost_per_mtok is None
    assert override.output_cost_per_mtok is None


def test_pipeline_budget_is_shared_across_jobs():
    from src.model_runtime import RunBudget
    budget = RunBudget(1)
    model = FakeModel([message({"answer": "ok"})])
    invoke(AgentRuntime(settings=config(), run_budget=budget, model_factory=lambda _: model))
    with pytest.raises(SpecialistError, match="BudgetExceeded"):
        invoke(AgentRuntime(settings=config(), run_budget=budget, model_factory=lambda _: model))
    assert len(model.inputs) == 1


def test_spend_threshold_stops_followup_calls_and_requires_pricing():
    settings = config(MODEL_SPEND_STOP_USD=0.0001, MODEL_INPUT_COST_PER_MTOK=1,
                      MODEL_OUTPUT_COST_PER_MTOK=2)
    model = FakeModel([message({"answer": "ok"})])
    runtime = AgentRuntime(settings=settings, model_factory=lambda _: model)
    invoke(runtime)
    with pytest.raises(SpecialistError, match="BudgetExceeded"):
        invoke(runtime)
    assert runtime.run_budget.known_cost == pytest.approx(0.00014)
    unpriced = AgentRuntime(settings=config(MODEL_SPEND_STOP_USD=1), model_factory=lambda _: model)
    with pytest.raises(SpecialistError, match="BudgetExceeded"):
        invoke(unpriced)
    assert unpriced.run_budget.used == 0


@pytest.mark.parametrize("status, expected_calls", [(429, 2), (503, 2), (401, 1), (400, 1)])
def test_only_transient_provider_errors_retry_with_shared_budget(status, expected_calls):
    class ProviderFailure(RuntimeError):
        status_code = status
    model = FakeModel([ProviderFailure("private failure"), message({"answer": "recovered"})])
    runtime = AgentRuntime(settings=config(AGENT_RETRY_BACKOFF_SECONDS=0), model_factory=lambda _: model)
    if expected_calls == 2:
        assert invoke(runtime).output.answer == "recovered"
    else:
        with pytest.raises(SpecialistError):
            invoke(runtime)
    assert len(model.inputs) == expected_calls
    assert runtime.steps[0]["model_requests"] == expected_calls
    assert runtime.steps[0]["usage_complete"] is False


def test_spend_guard_stops_after_unknown_failed_request():
    class RateLimit(RuntimeError):
        status_code = 429
    model = FakeModel([RateLimit("unknown usage"), message({"answer": "unused"})])
    runtime = AgentRuntime(settings=config(MODEL_SPEND_STOP_USD=1,
                           MODEL_INPUT_COST_PER_MTOK=1, MODEL_OUTPUT_COST_PER_MTOK=2),
                           model_factory=lambda _: model)
    with pytest.raises(SpecialistError):
        invoke(runtime)
    with pytest.raises(SpecialistError, match="BudgetExceeded"):
        invoke(runtime)
    assert len(model.inputs) == 1


def test_full_request_size_is_bounded_before_network():
    model = FakeModel([])
    runtime = AgentRuntime(settings=config(AGENT_MAX_INPUT_BYTES=1000), model_factory=lambda _: model)
    with pytest.raises(SpecialistError, match="BudgetExceeded"):
        runtime.run("writer", instructions="x" * 2000, prompt="test", output_type=Answer,
                    prompt_version="test")
    assert model.inputs == []


@pytest.mark.parametrize("provider, tool_count, expected", [
    ("gemini", 2, None), ("gemini", 1, False),
    ("openai", 2, False), ("anthropic", 2, False),
])
def test_multiple_tools_use_provider_compatible_parallel_setting(provider, tool_count, expected):
    @function_tool
    def read_job() -> str:
        """Read captured job data."""
        return "Synthetic job"

    @function_tool
    def read_cv() -> str:
        """Read candidate evidence."""
        return "Synthetic evidence"

    class ContractModel(FakeModel):
        async def get_response(self, *args, **kwargs):
            assert kwargs["model_settings"].parallel_tool_calls is expected
            return await super().get_response(*args, **kwargs)

    model = ContractModel([message({"answer": "ok"})])
    settings = Settings(_env_file=None, MODEL_PROVIDER=provider, MODEL_NAME="test-model")
    runtime = AgentRuntime(settings=settings, model_factory=lambda _: model)
    assert invoke(runtime, tools=[read_job, read_cv][:tool_count]).output.answer == "ok"


def test_default_turn_budget_allows_four_evidence_reads_and_final_answer():
    seen = []
    @function_tool
    def read_evidence(which: str) -> str:
        """Read the requested synthetic evidence item."""
        seen.append(which)
        return "Verified synthetic evidence"

    # A reviewer may read candidate, validation, job and preferences separately.
    # Tool turns alone must not consume every turn before the final answer.
    import json
    outputs = [ResponseFunctionToolCall(type="function_call", call_id=f"call_{i}",
               name="read_evidence", arguments=json.dumps({"which": name}))
               for i, name in enumerate(("candidate", "validation", "job", "preferences"))]
    model = FakeModel(outputs + [message({"answer": "review completed"})])
    runtime = AgentRuntime(settings=config(), model_factory=lambda _: model)
    assert invoke(runtime, tools=[read_evidence]).output.answer == "review completed"
    assert seen == ["candidate", "validation", "job", "preferences"]
    assert runtime.steps[0]["model_requests"] == 5


def test_gemini_finishes_after_reading_all_immutable_evidence_tools():
    @function_tool
    def read_captured_job() -> str:
        """Read the captured job."""
        return "Synthetic job"

    @function_tool
    def read_candidate_evidence() -> str:
        """Read candidate evidence."""
        return "Synthetic CV"

    class ContractModel(FakeModel):
        async def get_response(self, *args, **kwargs):
            choice = kwargs["model_settings"].tool_choice
            if len(self.inputs) == 2:
                assert choice == "none"
            else:
                assert choice != "none"
            return await super().get_response(*args, **kwargs)

    model = ContractModel([
        ResponseFunctionToolCall(type="function_call", call_id="job", name="read_captured_job", arguments="{}"),
        ResponseFunctionToolCall(type="function_call", call_id="cv", name="read_candidate_evidence", arguments="{}"),
        message({"answer": "Evidence reviewed"}),
    ])
    runtime = AgentRuntime(settings=Settings(_env_file=None, MODEL_PROVIDER="gemini", MODEL_NAME="test"),
                           model_factory=lambda _: model)
    assert invoke(runtime, tools=[read_captured_job, read_candidate_evidence]).output.answer == "Evidence reviewed"
    assert runtime.steps[0]["model_requests"] == 3
