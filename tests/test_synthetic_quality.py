import json

from evals.synthetic_quality import FIXTURE, fictional_evidence
from evals.run_semantic_eval import _metrics
from src import agent_workflow, cv_agent, semantic_ranking
from src.ranking import rank_job


def test_fictional_evidence_replaces_every_personal_loader_and_restores_it():
    dataset = json.loads(FIXTURE.read_text())
    original = agent_workflow._load_master_cv
    with fictional_evidence(dataset) as profile:
        for module in (agent_workflow, cv_agent, semantic_ranking):
            assert module._load_master_cv() == dataset['master_cv']
        assert agent_workflow.load_candidate_profile() == profile
        assert cv_agent.load_candidate_profile() == profile
    assert agent_workflow._load_master_cv is original


def test_synthetic_benchmark_is_complete_and_has_a_strict_baseline():
    dataset = json.loads(FIXTURE.read_text())
    with fictional_evidence(dataset) as profile:
        scores = {j['id']: rank_job(**{k: j[k] for k in (
            'title', 'company', 'location', 'description')}, profile=profile).total_score
                  for j in dataset['jobs']}
    assert len(scores) == 30
    assert _metrics(dataset, scores) == {'precision_at_5': 1.0, 'pairwise_accuracy': 0.975}
    assert all(scores[j['id']] == 0 for j in dataset['jobs'] if j['label'] == 'excluded')
    assert set(dataset['cv_job_ids']) <= scores.keys()
