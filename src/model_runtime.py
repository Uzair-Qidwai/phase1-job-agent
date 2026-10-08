"""Bounded, provider-independent specialist execution using the Agents SDK."""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
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
class StepUsage:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    complete: bool = True


class BudgetedModel(Model):
    def __init__(self, model: Model, budget: RequestBudget, usage: StepUsage):
        self.delegate, self.budget, self.usage = model, budget, usage

    async def get_response(self, *args, **kwargs) -> ModelResponse:
        self.budget.reserve()
        self.usage.requests += 1
        try:
            response = await self.delegate.get_response(*args, **kwargs)
        except BaseException:
            self.usage.complete = False
            raise
        self.usage.input_tokens += response.usage.input_tokens
        self.usage.output_tokens += response.usage.output_tokens
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
    budget: RequestBudget = field(init=False)

    def __post_init__(self):
        self.budget = RequestBudget(self.settings.agent_max_model_calls)

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
                model=BudgetedModel(model, self.budget, usage),
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
        step = {"role": role, "provider": config.provider, "model": config.model,
                "prompt_version": prompt_version, "status": "failed"}
        try:
            if legacy_client is not None:
                # Compatibility for callers injecting the original Anthropic client.
                # Production execution always uses the bounded SDK runner above.
                if config.provider != "anthropic" or tools:
                    raise ValueError("Legacy client injection supports Anthropic calls without tools only")
                self.budget.reserve()
                usage.requests = 1
                response = legacy_client.messages.create(
                    model=config.model, max_tokens=config.max_output_tokens, system=instructions,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = re.sub(r"```(?:json)?\s*", "", response.content[0].text).strip().rstrip("`")
                for name in ("input_tokens", "output_tokens"):
                    value = getattr(response.usage, name, 0)
                    setattr(usage, name, value if isinstance(value, int) else 0)
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
                         "latency_seconds": round(time.perf_counter() - start, 3)})
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
