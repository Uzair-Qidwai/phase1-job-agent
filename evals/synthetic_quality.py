"""Explicit, paced live evaluation using fictional evidence only.

Never loads the personal candidate profile or master CV. No database writes or mail.
"""
import argparse
import asyncio
import contextlib
import hashlib
import io
import json
import logging
import time
from pathlib import Path
from unittest.mock import patch

from agents import Model
from agents.extensions.models.litellm_model import LitellmModel

from evals.run_semantic_eval import _metrics
from src import agent_workflow as workflow, cv_agent, semantic_ranking
from src.candidate_profile import CandidateProfile
from src.model_runtime import AgentRuntime, RunBudget
from src.ranking import rank_job
from src.settings import get_settings

FIXTURE = Path(__file__).parent / 'fixtures' / 'synthetic_quality.json'


@contextlib.contextmanager
def fictional_evidence(dataset):
    profile = CandidateProfile.model_validate(dataset['profile'])
    with contextlib.ExitStack() as stack:
        for module in (workflow, cv_agent, semantic_ranking):
            stack.enter_context(patch.object(module, '_load_master_cv', lambda: dataset['master_cv']))
        for module in (workflow, cv_agent):
            stack.enter_context(patch.object(module, 'load_candidate_profile', lambda: profile))
        yield profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-live', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=['ranking', 'cv'], required=True)
    parser.add_argument('--cv-job-id', help='Inspect one fictional CV case; not a full quality gate')
    parser.add_argument('--max-calls', type=int, default=160)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.max_calls <= 200:
        parser.error('Use a new output path and 1–200 calls')
    settings = get_settings()
    if settings.model_provider != 'gemini' or settings.agent_models:
        parser.error('This bounded trial requires a single explicitly configured Gemini model')
    if settings.model_input_cost_per_mtok != 0 or settings.model_output_cost_per_mtok != 0:
        parser.error('This request-capped trial requires explicitly configured free-tier zero prices')
    settings.require_model_key('gemini')
    settings = settings.model_copy(update={
        'agent_workflow_enabled': True, 'agent_max_model_calls': 24,
        'agent_max_turns': 6, 'agent_transient_retries': 1,
        'agent_retry_backoff_seconds': 5, 'agent_timeout_seconds': 120,
        'model_spend_stop_usd': None,
    })
    dataset = json.loads(FIXTURE.read_text())
    if args.cv_job_id and (args.phase != 'cv' or args.cv_job_id not in dataset['cv_job_ids']):
        parser.error('--cv-job-id must select an existing fictional CV case')
    budget = RunBudget(args.max_calls)
    last_start = [0.0]
    steps = []
    report = dict(phase=args.phase, model=settings.model_name, passed=False,
                  scope=dataset['scope'], personal_data_sent=False,
                  fixture_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                  request_cap=args.max_calls, cases=[], steps=steps,
                  human_acceptance='pending', promotion_authorized=False, selected_cv_job=args.cv_job_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write('{}\n')
    args.output.chmod(0o600)

    class PacedModel(Model):
        def __init__(self, config):
            self.inner = LitellmModel(model=f'gemini/{config.model}', api_key=settings.gemini_api_key)

        async def get_response(self, *a, **kw):
            await asyncio.sleep(max(0, 5 - (time.monotonic() - last_start[0])))
            last_start[0] = time.monotonic()
            return await self.inner.get_response(*a, **kw)

        async def stream_response(self, *a, **kw):
            raise NotImplementedError
            yield

        async def close(self):
            await self.inner.close()

    def save():
        report['model_requests'] = budget.used
        args.output.write_text(json.dumps(report, indent=2, default=str) + '\n')

    logging.disable(logging.CRITICAL)
    started = time.monotonic()
    try:
        with fictional_evidence(dataset) as profile:
            baseline, candidate = {}, {}
            jobs = dataset['jobs'] if args.phase == 'ranking' else [
                j for j in dataset['jobs'] if j['id'] in dataset['cv_job_ids']
                and (not args.cv_job_id or j['id'] == args.cv_job_id)]
            for job in jobs:
                row = dict(job_id=job['id'], label=job['label'], passed=False)
                report['cases'].append(row)
                class CapturingRuntime(AgentRuntime):
                    def run(self, role, **kwargs):
                        result = super().run(role, **kwargs)
                        captured = dict(role=role, output=result.output.model_dump())
                        if role == 'writer':
                            from src.cv_validation import validate_tailored_cv
                            captured['validation'] = validate_tailored_cv(
                                result.output, master_cv=dataset['master_cv'],
                                candidate_profile_text=profile.model_dump_json()).model_dump()
                        row.setdefault('synthetic_outputs', []).append(captured)
                        return result
                runtime = CapturingRuntime(settings=settings, run_budget=budget,
                                       model_factory=PacedModel, on_step=steps.append)
                try:
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        if args.phase == 'ranking':
                            common = {k: job[k] for k in ('title', 'company', 'location', 'description')}
                            baseline[job['id']] = rank_job(**common, profile=profile).total_score
                            result = workflow.rank_job_agentic(**common, profile=profile, runtime=runtime)
                            candidate[job['id']] = result.total_score
                            row['result'] = result.model_dump()
                            row['passed'] = job['label'] != 'excluded' or (result.hard_mismatch and result.total_score == 0)
                        else:
                            row['result'] = workflow.tailor_cv_agentic(
                                job_title=job['title'], company=job['company'],
                                description=job['description'], runtime=runtime)
                            row['passed'] = row['result']['validation']['valid']
                except Exception as exc:
                    row['error_type'] = type(exc).__name__
                save()
                print(json.dumps(dict(job_id=job['id'], passed=row['passed'], requests=budget.used)), flush=True)
            report['passed'] = all(r['passed'] for r in report['cases'])
            if args.phase == 'ranking' and len(candidate) == len(jobs):
                report['baseline'] = _metrics(dataset, baseline)
                report['candidate'] = _metrics(dataset, candidate)
                report['synthetic_quality_gate_passed'] = all(
                    report['candidate'][k] >= v for k, v in report['baseline'].items())
                report['passed'] &= report['synthetic_quality_gate_passed']
    finally:
        report['elapsed_seconds'] = round(time.monotonic() - started, 2)
        save()
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
