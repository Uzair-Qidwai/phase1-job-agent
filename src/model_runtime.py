"""Bounded, provider-independent specialist execution using the Agents SDK."""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from uuid import uuid4
from dataclasses import dataclass, field
from typing import Callable

from agents import Agent, Model, ModelResponse, ModelSettings, RunConfig, Runner
from agents.model_settings import ModelRetrySettings
from pydantic import BaseModel

from src.settings import AgentModelConfig, AgentRole, Settings, get_settings


class BudgetExceeded(RuntimeError):
    pass


class SpecialistError(RuntimeError):
    """Safe error surface; raw provider payloads/credentials never enter logs."""


@dataclass
class RequestBudget:
    limit: int
    used: int = 0

    def reserve(self) -> None:
        if self.used >= self.limit:
            raise BudgetExceeded("Specialist model-call budget exhausted")
        self.used += 1


@dataclass
class RunBudget:
    """Shared across every job/stage; spend is a stop threshold, not a bill cap."""
    limit: int
    spend_stop_usd: float | None = None
    used: int = 0
    known_cost: float = 0.0
    cost_complete: bool = True

    def reserve(self, config: AgentModelConfig):
        if self.used >= self.limit:
            raise BudgetExceeded("Pipeline model-call budget exhausted")
        if self.spend_stop_usd is not None:
            if not self.cost_complete or config.input_cost_per_mtok is None or config.output_cost_per_mtok is None:
                raise BudgetExceeded("Spend guard requires complete usage and configured prices")
            if self.known_cost >= self.spend_stop_usd:
                raise BudgetExceeded("Model spending stop threshold reached")
        self.used += 1

    def charge(self, config, input_tokens, output_tokens):
        if (input_tokens + output_tokens == 0 or config.input_cost_per_mtok is None
                or config.output_cost_per_mtok is None):
            self.cost_complete = False
        else:
            self.known_cost += (input_tokens * config.input_cost_per_mtok
                                + output_tokens * config.output_cost_per_mtok) / 1_000_000


@dataclass
class StepUsage:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    complete: bool = True
    tool_calls: list[str] = field(default_factory=list)


class BudgetedModel(Model):
    def __init__(self, model, budget, usage, run_budget, config, settings):
        self.delegate, self.budget, self.usage = model, budget, usage
        self.run_budget, self.config, self.settings = run_budget, config, settings

    async def get_response(self, *args, **kwargs) -> ModelResponse:
        # Bound the full SDK request, including accumulated tool results.
        if len(json.dumps([args, kwargs], default=str).encode()) > self.settings.agent_max_input_bytes:
            raise BudgetExceeded("Specialist input-size budget exceeded")
        for attempt in range(self.settings.agent_transient_retries + 1):
            self.budget.reserve()
            self.run_budget.reserve(self.config)
            self.usage.requests += 1
            try:
                response = await self.delegate.get_response(*args, **kwargs)
                break
            except BaseException as exc:
                self.usage.complete = False
                self.run_budget.cost_complete = False
                status = getattr(exc, "status_code", None)
                transient = status == 429 or (isinstance(status, int) and 500 <= status < 600)
                # No blind retry of timeouts, malformed output, auth errors or
                # unknown spend under a configured monetary guard.
                if (not transient or attempt >= self.settings.agent_transient_retries
                        or self.run_budget.spend_stop_usd is not None):
                    raise
                await asyncio.sleep(self.settings.agent_retry_backoff_seconds * (2 ** attempt))
        self.usage.tool_calls.extend(item.name for item in response.output
                                     if getattr(item, "type", None) == "function_call")
        self.usage.input_tokens += response.usage.input_tokens
        self.usage.output_tokens += response.usage.output_tokens
        self.run_budget.charge(self.config, response.usage.input_tokens, response.usage.output_tokens)
        if response.usage.input_tokens + response.usage.output_tokens == 0:
            self.usage.complete = False
        return response

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError("Specialists use bounded non-streaming runs")
        yield  # pragma: no cover


@dataclass
class SpecialistResult:
    output: BaseModel
    step: dict


@dataclass
class AgentRuntime:
    settings: Settings = field(default_factory=get_settings)
    # Test seam executes the real SDK runner with offline Model implementations.
    model_factory: Callable[[AgentModelConfig], Model] | None = None
    on_step: Callable[[dict], None] | None = None
    steps: list[dict] = field(default_factory=list)
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    run_budget: RunBudget | None = None
    budget: RequestBudget = field(init=False)

    def __post_init__(self):
        self.budget = RequestBudget(self.settings.agent_max_model_calls)
        if self.run_budget is None:
            self.run_budget = RunBudget(self.settings.pipeline_max_model_calls,
                                        self.settings.model_spend_stop_usd)

    async def _execute(self, config, role, instructions, prompt, output_type, tools, usage):
        owner = None
        model = None
        try:
            if self.model_factory:
                model = self.model_factory(config)
            else:
                key = self.settings.require_model_key(config.provider)
                if "/" in config.model:
                    raise ValueError("Use an unprefixed model name; provider is configured separately")
                if config.provider == "openai":
                    from openai import AsyncOpenAI
                    from agents import OpenAIResponsesModel
                    owner = AsyncOpenAI(api_key=key, max_retries=0,
                                        timeout=self.settings.agent_timeout_seconds)
                    model = OpenAIResponsesModel(model=config.model, openai_client=owner)
                else:
                    # Do not fetch pricing or send telemetry while importing adapters.
                    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
                    import litellm
                    litellm.telemetry = False
                    from agents.extensions.models.litellm_model import LitellmModel
                    model = LitellmModel(model=f"{config.provider}/{config.model}", api_key=key)
            agent = Agent(
                name=role, instructions=instructions,
                model=BudgetedModel(model, self.budget, usage, self.run_budget, config, self.settings),
                output_type=output_type, tools=tools,
                model_settings=ModelSettings(max_tokens=config.max_output_tokens,
                                             retry=ModelRetrySettings(max_retries=0),
                                             parallel_tool_calls=False),
            )
            result = await Runner.run(
                agent, prompt, max_turns=self.settings.agent_max_turns,
                run_config=RunConfig(tracing_disabled=True, trace_include_sensitive_data=False),
            )
            return output_type.model_validate(result.final_output)
        finally:
            if owner:
                await owner.close()
            elif model:
                await model.close()

    def run(self, role: AgentRole, *, instructions: str, prompt: str,
            output_type: type[BaseModel], tools=None, prompt_version: str,
            model: str | None = None, max_tokens: int = 4096, legacy_client=None) -> SpecialistResult:
        config = self.settings.agent_config(role, model=model, max_tokens=max_tokens)
        usage = StepUsage()
        start = time.perf_counter()
        step = {"execution_id": self.execution_id, "sequence": len(self.steps) + 1, "role": role, "provider": config.provider, "model": config.model,
                "prompt_version": prompt_version, "status": "failed"}
        try:
            if legacy_client is not None:
                # Compatibility for callers injecting the original Anthropic client.
                # Production execution always uses the bounded SDK runner above.
                if config.provider != "anthropic" or tools:
                    raise ValueError("Legacy client injection supports Anthropic calls without tools only")
                self.budget.reserve()
                self.run_budget.reserve(config)
                usage.requests = 1
                response = legacy_client.messages.create(
                    model=config.model, max_tokens=config.max_output_tokens, system=instructions,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = re.sub(r"```(?:json)?\s*", "", response.content[0].text).strip().rstrip("`")
                for name in ("input_tokens", "output_tokens"):
                    value = getattr(response.usage, name, 0)
                    setattr(usage, name, value if isinstance(value, int) else 0)
                self.run_budget.charge(config, usage.input_tokens, usage.output_tokens)
                output = output_type.model_validate(json.loads(raw))
            else:
                async def bounded():
                    return await asyncio.wait_for(
                        self._execute(config, role, instructions, prompt, output_type, tools or [], usage),
                        timeout=self.settings.agent_timeout_seconds,
                    )
                output = asyncio.run(bounded())
            step["status"] = "completed"
            return SpecialistResult(output=output, step=step)
        except Exception as exc:
            if usage.requests and usage.input_tokens + usage.output_tokens == 0:
                self.run_budget.cost_complete = False
            step["error_type"] = type(exc).__name__
            raise SpecialistError(f"{role} failed ({type(exc).__name__}); see agent execution metadata") from None
        finally:
            known = usage.complete and usage.input_tokens + usage.output_tokens > 0
            priced = known and config.input_cost_per_mtok is not None and config.output_cost_per_mtok is not None
            cost = ((usage.input_tokens * config.input_cost_per_mtok
                     + usage.output_tokens * config.output_cost_per_mtok) / 1_000_000) if priced else None
            step.update({"model_requests": usage.requests, "input_tokens": usage.input_tokens,
                         "output_tokens": usage.output_tokens, "usage_complete": known,
                         "estimated_cost_usd": round(cost, 6) if cost is not None else None,
                         "latency_seconds": round(time.perf_counter() - start, 3),
                         "tool_calls": list(usage.tool_calls)})
            self.steps.append(step)
            if self.on_step:
                self.on_step(dict(step))

    def totals(self) -> dict:
        return {
            "usage": {name: sum(step[name] for step in self.steps)
                      for name in ("input_tokens", "output_tokens")},
            # Existing numeric DB counters hold the known subtotal. Explicit
            # completeness metadata distinguishes unpriced usage from free usage.
            "estimated_cost_usd": round(sum(step["estimated_cost_usd"] or 0 for step in self.steps), 6),
            "cost_estimate_complete": bool(self.steps) and all(
                step["estimated_cost_usd"] is not None for step in self.steps),
        }
