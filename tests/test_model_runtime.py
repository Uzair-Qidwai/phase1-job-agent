import json

import pytest
from agents import Model, ModelResponse, function_tool
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
from pydantic import BaseModel, ValidationError

from src.model_runtime import AgentRuntime, SpecialistError
from src.settings import Settings


class Answer(BaseModel):
    answer: str


def message(payload):
    return ResponseOutputMessage(id="msg_1", type="message", role="assistant", status="completed",
                                 content=[ResponseOutputText(type="output_text", text=json.dumps(payload), annotations=[])])


class FakeModel(Model):
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.inputs = []

    async def get_response(self, *args, **kwargs):
        self.inputs.append(kwargs.get("input"))
        value = self.outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return ModelResponse(output=[value], usage=Usage(requests=1, input_tokens=100, output_tokens=20), response_id=None)

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError
        yield


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
