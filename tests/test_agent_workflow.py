import pytest
from openai.types.responses import ResponseFunctionToolCall

import src.agent_workflow as workflow
from evals.fake_models import FakeModel, message
from src.candidate_profile import load_candidate_profile
from src.model_runtime import AgentRuntime
from src.settings import Settings

MASTER = "Built Python systems for financial analytics and reporting."
DRAFT = {"tailored_cv": MASTER, "changes_made": "Prioritized supported experience.",
         "evidence_used": [{"claim": MASTER, "source": "master_cv", "source_text": MASTER}],
         "keywords_added": [], "warnings": []}
APPROVE = {"decision": "approve", "issues": [], "reason": "Evidence and relevance checked."}
RANKING = {"components": {"role_fit": 90, "technical_fit": 80, "experience_fit": 85,
                           "domain_fit": 90, "seniority_fit": 80, "location_fit": 100},
           "explanation": ["Supported fit"], "warnings": []}


@pytest.fixture(autouse=True)
def source(monkeypatch):
    monkeypatch.setattr(workflow, "_load_master_cv", lambda: MASTER)


def runtime_for(outputs, **kwargs):
    model = FakeModel(outputs)
    settings = Settings(_env_file=None, MODEL_PROVIDER="openai", MODEL_NAME="fake", **kwargs)
    return AgentRuntime(settings=settings, model_factory=lambda _: model)


def tailor(runtime):
    return workflow.tailor_cv_agentic(job_title="AI Engineer", company="Example",
                                     description="Build Python systems.", runtime=runtime)


def test_research_tools_and_analyst_share_bounded_usage():
    runtime = runtime_for([
        ResponseFunctionToolCall(type="function_call", call_id="source_1", name="read_captured_job", arguments="{}"),
        message({"requirement_quotes": ["Build Python systems."], "missing_information": []}),
        message(RANKING),
    ])
    result = workflow.rank_job_agentic(title="AI Engineer", company="Example", location="Toronto",
                                      description="Build Python systems.", profile=load_candidate_profile(), runtime=runtime)
    assert result.total_score == 87
    assert [step["role"] for step in runtime.steps] == ["researcher", "analyst"]
    assert runtime.steps[0]["tool_calls"] == ["read_captured_job"]
    assert result.usage == {"input_tokens": 300, "output_tokens": 60}


def test_invented_research_quote_blocks_analyst():
    runtime = runtime_for([message({"requirement_quotes": ["Invented requirement"], "missing_information": []})])
    with pytest.raises(workflow.WorkflowRejected, match="absent"):
        workflow.rank_job_agentic(title="AI Engineer", company="Example", location="Toronto",
                                  description="Build Python systems.", profile=load_candidate_profile(), runtime=runtime)
    assert len(runtime.steps) == 1


def test_hard_filter_skips_all_specialists():
    runtime = runtime_for([])
    result = workflow.rank_job_agentic(title="Registered Nurse", company="Example", location="Toronto",
                                      description="Nursing", profile=load_candidate_profile(), runtime=runtime)
    assert result.hard_mismatch
    assert runtime.steps == []


def test_writer_review_repair_is_bounded_and_accumulates_usage():
    invalid = {**DRAFT, "tailored_cv": MASTER + " Awarded a Stanford doctorate."}
    runtime = runtime_for([message(invalid), message({"decision": "revise", "issues": ["Remove invented doctorate"],
                                                    "reason": "Unsupported credential"}),
                           message(DRAFT), message(APPROVE)])
    result = tailor(runtime)
    assert result["validation"]["valid"]
    assert result["validation"]["agent_review"]["revisions"] == 1
    assert result["usage"] == {"input_tokens": 400, "output_tokens": 80}
    assert [step["role"] for step in result["agent_steps"]] == ["writer", "reviewer", "writer", "reviewer"]


def test_reviewer_approval_cannot_override_deterministic_gate():
    invalid = {**DRAFT, "tailored_cv": MASTER + " Awarded a Stanford doctorate."}
    runtime = runtime_for([message(invalid), message(APPROVE)], AGENT_MAX_REVISIONS=0)
    with pytest.raises(workflow.WorkflowRejected, match="revision limit"):
        tailor(runtime)


def test_reviewer_can_read_deterministic_check_and_approve():
    runtime = runtime_for([message(DRAFT),
                           ResponseFunctionToolCall(type="function_call", call_id="validate_1", name="check_draft_evidence", arguments="{}"),
                           message(APPROVE)])
    result = tailor(runtime)
    assert result["validation"]["agent_review"]["reviews"][0]["decision"] == "approve"
    assert runtime.steps[-1]["tool_calls"] == ["check_draft_evidence"]


def test_reviewer_rejection_does_not_trigger_unbounded_rewrites():
    runtime = runtime_for([message(DRAFT), message({"decision": "reject", "issues": ["Material context problem"],
                                                  "reason": "Cannot repair from evidence"})])
    with pytest.raises(workflow.WorkflowRejected, match="rejected"):
        tailor(runtime)
    assert len(runtime.steps) == 2


def test_inconsistent_approval_with_issues_does_not_pass():
    runtime = runtime_for([message(DRAFT), message({**APPROVE, "issues": ["Unresolved issue"]})], AGENT_MAX_REVISIONS=0)
    with pytest.raises(workflow.WorkflowRejected):
        tailor(runtime)


def test_tool_surfaces_are_read_only():
    tools = workflow.source_tools({"description": "untrusted"}, MASTER, "preferences")
    assert {tool.name for tool in tools} == {"read_captured_job", "read_candidate_evidence", "read_search_preferences"}


def test_writer_and_reviewer_use_independent_models_and_prices():
    model = FakeModel([message(DRAFT), message(APPROVE)])
    configured = []
    def factory(config):
        configured.append((config.provider, config.model))
        return model
    settings = Settings(_env_file=None, AGENT_MODELS={
        "writer": {"provider": "openai", "model": "writer-choice", "input_cost_per_mtok": 1,
                   "output_cost_per_mtok": 2},
        "reviewer": {"provider": "gemini", "model": "reviewer-choice"},
    })
    result = tailor(AgentRuntime(settings=settings, model_factory=factory))
    assert configured == [("openai", "writer-choice"), ("gemini", "reviewer-choice")]
    assert result["model"] == "writer-choice"
    assert result["validation"]["agent_review"]["model"] == "reviewer-choice"
    assert result["cost_estimate_complete"] is False
    assert result["agent_steps"][0]["estimated_cost_usd"] == pytest.approx(0.00014)
    assert result["agent_steps"][1]["estimated_cost_usd"] is None
