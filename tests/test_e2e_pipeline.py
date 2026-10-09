from __future__ import annotations

import os

import pytest

import src.cv_agent as cv_agent
import src.emailer as emailer
import src.ranking as ranking_module
import src.scraper as scraper
from src.scheduler import resume_pipeline, run_pipeline
from src.tracker import get_conn, get_pipeline_run


pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_URL"),
    reason="POSTGRES_URL is required for end-to-end integration tests",
)


def _cleanup() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM delivery_attempts")
            cur.execute("DELETE FROM notifications")
            cur.execute("DELETE FROM pipeline_events")
            cur.execute("DELETE FROM pipeline_runs")
            cur.execute(
                "UPDATE jobs SET cv_version_id = NULL WHERE source = 'phase2-e2e'"
            )
            cur.execute(
                """
                DELETE FROM cv_versions
                WHERE job_id IN (
                    SELECT id FROM jobs WHERE source = 'phase2-e2e'
                )
                """
            )
            cur.execute("DELETE FROM jobs WHERE source = 'phase2-e2e'")


@pytest.fixture(autouse=True)
def clean_e2e_rows():
    _cleanup()
    yield
    _cleanup()


@pytest.mark.asyncio
async def test_placeholder_asyncio_plugin_is_available():
    # Keeps the async test plugin exercised independently of Playwright/network.
    assert True


@pytest.mark.parametrize("review_enabled", [False, True])
def test_full_pipeline_is_rank_first_and_idempotent(monkeypatch, review_enabled) -> None:
    from src.settings import get_settings
    import src.scheduler as scheduler
    import src.agent_workflow as workflow
    settings = get_settings().model_copy(update={
        "cv_review_enabled": review_enabled, "agent_workflow_enabled": False,
        "ranking_mode": "deterministic",
    })
    monkeypatch.setattr(scheduler, "get_settings", lambda: settings)

    def forbidden_model_ranking(**kwargs):
        raise AssertionError("CV review must not enable model ranking")

    monkeypatch.setattr(workflow, "rank_job_agentic", forbidden_model_ranking)
    strong = scraper.RawJob(
        title="Senior AI Engineer",
        company="Example AI",
        location="Toronto, Canada",
        url="https://example.com/jobs/strong",
        description=(
            "Build production AI and machine learning systems in Python, "
            "evaluation tooling and model infrastructure."
        ),
        source="phase2-e2e",
        source_job_id="strong",
    )
    weak = scraper.RawJob(
        title="Registered Nurse",
        company="Example Health",
        location="Toronto, Canada",
        url="https://example.com/jobs/weak",
        description="Provide clinical nursing care.",
        source="phase2-e2e",
        source_job_id="weak",
    )

    async def fake_scrape_all(headless: bool = True):
        return [strong, weak]

    tailor_calls: list[str] = []

    def fake_tailor_cv(*, job_title, company, description, runtime=None):
        tailor_calls.append(job_title)
        return {
            "tailored_cv": (
                "# Tailored CV\n\n"
                "Evidence-backed AI engineering experience with Python and "
                "machine learning systems."
            ),
            "changes_made": "Front-loaded relevant AI engineering evidence.",
            "evidence_used": [
                {
                    "claim": "AI engineering evidence",
                    "source": "master_cv",
                    "source_text": "Python",
                }
            ],
            "keywords_added": ["AI"],
            "warnings": [],
            "model": "fake-model",
            "prompt_version": "phase2-cv-v1",
            "profile_version": "1",
            "source_cv_sha256": "fake-sha",
            "validation": {"valid": True},
        }

    delivered_batches: list[list[dict]] = []

    def fake_send_digest(jobs, **kwargs):
        delivered_batches.append(list(jobs))
        return True

    monkeypatch.setattr(scraper, "scrape_all", fake_scrape_all)
    if review_enabled:
        def forbidden_single_writer(**kwargs):
            raise AssertionError("CV review must use the reviewer workflow")
        monkeypatch.setattr(cv_agent, "tailor_cv", forbidden_single_writer)
        monkeypatch.setattr(workflow, "tailor_cv_agentic", fake_tailor_cv)
    else:
        monkeypatch.setattr(cv_agent, "tailor_cv", fake_tailor_cv)
    monkeypatch.setattr(emailer, "send_digest", fake_send_digest)

    first_run_id = run_pipeline(trigger="manual")
    assert first_run_id is not None

    first = get_pipeline_run(first_run_id)
    assert first is not None
    assert first["status"] == "completed"
    assert first["jobs_discovered"] == 2
    assert first["jobs_inserted"] == 2
    assert first["jobs_ranked"] == 1
    assert first["jobs_shortlisted"] == 1
    assert first["jobs_tailored"] == 1
    assert first["jobs_notified"] == 1
    assert tailor_calls == ["Senior AI Engineer"]
    assert len(delivered_batches) == 1
    assert len(delivered_batches[0]) == 1
    assert delivered_batches[0][0]["title"] == "Senior AI Engineer"

    second_run_id = run_pipeline(trigger="manual")
    assert second_run_id is not None

    second = get_pipeline_run(second_run_id)
    assert second is not None
    assert second["status"] == "completed"
    assert second["jobs_discovered"] == 2
    assert second["jobs_inserted"] == 0
    assert second["jobs_ranked"] == 0
    assert second["jobs_shortlisted"] == 0
    assert second["jobs_tailored"] == 0
    assert second["jobs_notified"] == 0

    assert tailor_calls == ["Senior AI Engineer"]
    assert len(delivered_batches) == 1


def test_pipeline_records_fatal_stage_failure(monkeypatch) -> None:
    async def broken_scraper(headless: bool = True):
        raise RuntimeError("simulated source outage")

    monkeypatch.setattr(scraper, "scrape_all", broken_scraper)

    with pytest.raises(RuntimeError, match="simulated source outage"):
        run_pipeline(trigger="manual")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, current_stage, error_type, error_message
                FROM pipeline_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()

    assert row["status"] == "failed"
    assert row["current_stage"] == "scraping"
    assert row["error_type"] == "RuntimeError"
    assert "simulated source outage" in row["error_message"]


def test_failed_tailoring_is_retried_from_shortlisted_state(monkeypatch) -> None:
    strong = scraper.RawJob(
        title="Senior AI Engineer",
        company="Example AI",
        location="Toronto, Canada",
        url="https://example.com/jobs/retry-tailor",
        description="Build AI and machine learning systems in Python.",
        source="phase2-e2e",
        source_job_id="retry-tailor",
    )

    async def fake_scrape_all(headless: bool = True):
        return [strong]

    attempts = {"count": 0}

    def flaky_tailor_cv(*, job_title, company, description, runtime=None):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("simulated CV provider failure")
        return {
            "tailored_cv": (
                "# Tailored CV\n\n"
                "Evidence-backed AI engineering experience with Python and "
                "machine learning systems."
            ),
            "changes_made": "Front-loaded relevant AI engineering evidence.",
            "evidence_used": [
                {
                    "claim": "Python experience",
                    "source": "master_cv",
                    "source_text": "Python",
                }
            ],
            "keywords_added": ["AI"],
            "warnings": [],
            "model": "fake-model",
            "prompt_version": "phase2-cv-v1",
            "profile_version": "1",
            "source_cv_sha256": "fake-sha",
            "validation": {"valid": True},
        }

    monkeypatch.setattr(scraper, "scrape_all", fake_scrape_all)
    monkeypatch.setattr(cv_agent, "tailor_cv", flaky_tailor_cv)
    monkeypatch.setattr(emailer, "send_digest", lambda jobs, **kwargs: True)

    with pytest.raises(RuntimeError, match="CV job"):
        run_pipeline(trigger="manual")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM pipeline_runs ORDER BY started_at DESC LIMIT 1")
        first_run = str(cur.fetchone()["id"])
    assert get_pipeline_run(first_run)["status"] == "failed"
    first = get_pipeline_run(first_run)
    assert first["jobs_inserted"] == 1
    assert first["jobs_shortlisted"] == 1
    assert first["jobs_tailored"] == 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT system_state
                FROM jobs
                WHERE source = 'phase2-e2e' AND source_job_id = 'retry-tailor'
                """
            )
            row = cur.fetchone()
    assert row["system_state"] == "shortlisted"

    second_run = run_pipeline(trigger="retry")
    assert second_run is not None
    second = get_pipeline_run(second_run)

    assert second["jobs_inserted"] == 0
    assert second["jobs_ranked"] == 0
    assert second["jobs_shortlisted"] == 0
    assert second["jobs_tailored"] == 1
    assert attempts["count"] == 2

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT system_state
                FROM jobs
                WHERE source = 'phase2-e2e' AND source_job_id = 'retry-tailor'
                """
            )
            row = cur.fetchone()
    assert row["system_state"] == "notified"


def test_notification_failure_resumes_without_repeating_expensive_stages(monkeypatch) -> None:
    strong = scraper.RawJob(
        title="Senior AI Engineer",
        company="Example AI",
        location="Toronto, Canada",
        url="https://example.com/jobs/resume-notify",
        description="Build production AI and machine learning systems in Python.",
        source="phase2-e2e",
        source_job_id="resume-notify",
    )

    calls = {"scrape": 0, "tailor": 0, "send": 0}

    async def fake_scrape_all(headless: bool = True):
        calls["scrape"] += 1
        return [strong]

    def fake_tailor_cv(*, job_title, company, description, runtime=None):
        calls["tailor"] += 1
        return {
            "tailored_cv": (
                "# Tailored CV\n\n"
                "Evidence-backed AI engineering experience with Python and "
                "machine learning systems."
            ),
            "changes_made": "Front-loaded relevant AI engineering evidence.",
            "evidence_used": [
                {
                    "claim": "Python experience",
                    "source": "master_cv",
                    "source_text": "Python",
                }
            ],
            "keywords_added": ["AI"],
            "warnings": [],
            "model": "fake-model",
            "prompt_version": "phase2-cv-v1",
            "profile_version": "1",
            "source_cv_sha256": "fake-sha",
            "validation": {"valid": True},
        }

    def flaky_send_digest(jobs, **kwargs):
        calls["send"] += 1
        return calls["send"] > 1

    monkeypatch.setattr(scraper, "scrape_all", fake_scrape_all)
    monkeypatch.setattr(cv_agent, "tailor_cv", fake_tailor_cv)
    monkeypatch.setattr(emailer, "send_digest", flaky_send_digest)

    with pytest.raises(RuntimeError, match="Digest delivery failed"):
        run_pipeline(trigger="manual")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, current_stage
                FROM pipeline_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            failed = cur.fetchone()

    assert failed["status"] == "failed"
    assert failed["current_stage"] == "notifying"

    from src.delivery import list_attempts, reconcile
    for attempt in list_attempts():
        if attempt["status"] == "ambiguous":
            with pytest.raises(RuntimeError, match="Unresolved delivery"):
                resume_pipeline(str(failed["id"]))
            assert calls["send"] == 1
            reconcile(str(attempt["id"]), sent=False,
                      reason="Test transport confirms no send occurred", workers_stopped=True)
    retry_id = resume_pipeline(str(failed["id"]))
    assert retry_id is not None
    retry = get_pipeline_run(retry_id)
    assert retry is not None
    assert retry["status"] == "completed"
    assert str(retry["retry_of_run_id"]) == str(failed["id"])
    assert retry["jobs_discovered"] == 0
    assert retry["jobs_inserted"] == 0
    assert retry["jobs_ranked"] == 0
    assert retry["jobs_shortlisted"] == 0
    assert retry["jobs_tailored"] == 0
    assert retry["jobs_notified"] == 1

    assert calls == {"scrape": 1, "tailor": 1, "send": 2}


def test_ranking_failure_resumes_from_filtering_without_rescraping(monkeypatch) -> None:
    strong = scraper.RawJob(
        title="Senior AI Engineer",
        company="Example AI",
        location="Toronto, Canada",
        url="https://example.com/jobs/resume-ranking",
        description="Build AI and machine learning systems in Python.",
        source="phase2-e2e",
        source_job_id="resume-ranking",
    )

    calls = {"scrape": 0, "rank": 0, "tailor": 0}
    real_rank_job = ranking_module.rank_job

    async def fake_scrape_all(headless: bool = True):
        calls["scrape"] += 1
        return [strong]

    def flaky_rank_job(**kwargs):
        calls["rank"] += 1
        if calls["rank"] == 1:
            raise RuntimeError("simulated ranking provider failure")
        return real_rank_job(**kwargs)

    def fake_tailor_cv(*, job_title, company, description, runtime=None):
        calls["tailor"] += 1
        return {
            "tailored_cv": (
                "# Tailored CV\n\n"
                "Evidence-backed AI engineering experience with Python and "
                "machine learning systems."
            ),
            "changes_made": "Front-loaded relevant AI engineering evidence.",
            "evidence_used": [
                {
                    "claim": "Python experience",
                    "source": "master_cv",
                    "source_text": "Python",
                }
            ],
            "keywords_added": ["AI"],
            "warnings": [],
            "model": "fake-model",
            "prompt_version": "phase2-cv-v1",
            "profile_version": "1",
            "source_cv_sha256": "fake-sha",
            "validation": {"valid": True},
        }

    monkeypatch.setattr(scraper, "scrape_all", fake_scrape_all)
    monkeypatch.setattr(ranking_module, "rank_job", flaky_rank_job)
    monkeypatch.setattr(cv_agent, "tailor_cv", fake_tailor_cv)
    monkeypatch.setattr(emailer, "send_digest", lambda jobs, **kwargs: True)

    with pytest.raises(RuntimeError, match="simulated ranking provider failure"):
        run_pipeline(trigger="manual")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, current_stage
                FROM pipeline_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            failed = cur.fetchone()

    assert failed["status"] == "failed"
    assert failed["current_stage"] == "ranking"

    retry_id = resume_pipeline(str(failed["id"]))
    assert retry_id is not None
    retry = get_pipeline_run(retry_id)
    assert retry is not None
    assert retry["status"] == "completed"
    assert str(retry["retry_of_run_id"]) == str(failed["id"])
    assert retry["jobs_discovered"] == 0
    assert retry["jobs_inserted"] == 0
    assert retry["jobs_ranked"] == 1
    assert retry["jobs_shortlisted"] == 1
    assert retry["jobs_tailored"] == 1
    assert retry["jobs_notified"] == 1

    assert calls["scrape"] == 1
    assert calls["rank"] == 2
    assert calls["tailor"] == 1


def test_admitted_retry_reuses_reserved_run_and_restart_stage(monkeypatch):
    from src.scheduler import execute_admitted_run
    from src.tracker import start_pipeline_run, fail_pipeline_run

    parent = start_pipeline_run("manual")
    fail_pipeline_run(parent, "notifying", RuntimeError("email unavailable"))
    reserved = start_pipeline_run("retry", retry_of_run_id=parent)

    async def unexpected_scrape(**kwargs):
        pytest.fail("Notification retry must not scrape")

    monkeypatch.setattr(scraper, "scrape_all", unexpected_scrape)
    monkeypatch.setattr(emailer, "send_digest", lambda jobs, **kwargs: True)
    assert execute_admitted_run(reserved) == reserved
    run = get_pipeline_run(reserved)
    assert run["status"] == "completed"
    assert str(run["retry_of_run_id"]) == parent
    with pytest.raises(ValueError, match="already claimed"):
        execute_admitted_run(reserved)
    assert get_pipeline_run(reserved)["status"] == "completed"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM pipeline_runs")
            assert cur.fetchone()["n"] == 2


def test_running_pipeline_holds_execution_lock_until_completion(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from src.tracker import PipelineAlreadyRunning, get_active_pipeline_run, recover_abandoned_run
    entered = Event()
    release = Event()

    async def paused_scrape(**kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return []

    monkeypatch.setattr(scraper, "scrape_all", paused_scrape)
    monkeypatch.setattr(emailer, "send_digest", lambda jobs, **kwargs: True)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run_pipeline, "manual")
        try:
            assert entered.wait(timeout=10)
            active = get_active_pipeline_run()
            assert active is not None
            with pytest.raises(PipelineAlreadyRunning):
                recover_abandoned_run(str(active["id"]), reason="Operator claims worker stopped",
                                      workers_stopped=True)
        finally:
            release.set()
        run_id = future.result(timeout=10)
    assert get_pipeline_run(run_id)["status"] == "completed"


@pytest.mark.parametrize("review_decision", ["approve", "reject"])
def test_agent_pipeline_persists_role_audit_and_accounts_rejected_work(monkeypatch, review_decision):
    import src.agent_workflow as workflow
    import src.model_runtime as runtime_module
    import src.semantic_ranking as semantic
    from evals.fake_models import FakeModel, message
    from src.settings import get_settings

    master = "Built Python systems for financial analytics and reporting."
    description = "Build AI and machine learning systems in Python."
    draft = {"tailored_cv": master, "changes_made": "Prioritized supported evidence.",
             "evidence_used": [{"claim": master, "source": "master_cv", "source_text": master}],
             "keywords_added": [], "warnings": []}
    ranking = {"components": {name: 90 for name in ("role_fit", "technical_fit", "experience_fit",
                                                    "domain_fit", "seniority_fit", "location_fit")},
               "explanation": ["Strong supported fit"], "warnings": []}
    fake = FakeModel([
        message({"requirement_quotes": [description], "missing_information": []}),
        message(ranking), message(draft),
        message({"decision": review_decision, "issues": [] if review_decision == "approve" else ["Requires review"],
                 "reason": "Evidence review completed"}),
    ])
    original = runtime_module.AgentRuntime
    class OfflineRuntime(original):
        def __post_init__(self):
            super().__post_init__()
            self.model_factory = lambda config: fake

    async def fake_scrape(**kwargs):
        return [scraper.RawJob(title="AI Engineer", company="Example", location="Toronto",
                               url="https://example.com/agent-flow", description=description,
                               source="phase2-e2e", source_job_id="agent-flow")]
    sent = []
    monkeypatch.setenv("AGENT_WORKFLOW_ENABLED", "true")
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("MODEL_NAME", "offline-model")
    get_settings.cache_clear()
    monkeypatch.setattr(runtime_module, "AgentRuntime", OfflineRuntime)
    monkeypatch.setattr(workflow, "_load_master_cv", lambda: master)
    monkeypatch.setattr(semantic, "_load_master_cv", lambda: master)
    monkeypatch.setattr(scraper, "scrape_all", fake_scrape)
    monkeypatch.setattr(emailer, "send_digest", lambda jobs, **kwargs: sent.extend(jobs) or True)
    try:
        if review_decision == "reject":
            with pytest.raises(RuntimeError, match="CV job"):
                run_pipeline("manual")
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute("SELECT id FROM pipeline_runs ORDER BY started_at DESC LIMIT 1")
                run_id = str(cur.fetchone()["id"])
        else:
            run_id = run_pipeline("manual")
        run = get_pipeline_run(run_id)
        assert run["model_input_tokens"] == 400
        assert run["model_output_tokens"] == 80
        assert run["jobs_tailored"] == (1 if review_decision == "approve" else 0)
        assert len(sent) == (1 if review_decision == "approve" else 0)
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM pipeline_events WHERE run_id = %s AND event_type = 'agent_step' ORDER BY id", (run_id,))
                steps = [row["payload"] for row in cur.fetchall()]
                assert [step["role"] for step in steps] == ["researcher", "analyst", "writer", "reviewer"]
                assert all(step["provider"] == "openai" for step in steps)
                assert all(step["estimated_cost_usd"] is None for step in steps)
                assert master not in str(steps)
                cur.execute("SELECT system_state, cv_version_id FROM jobs WHERE source = 'phase2-e2e'")
                job = cur.fetchone()
                if review_decision == "reject":
                    assert job["system_state"] == "shortlisted"
                    assert job["cv_version_id"] is None
                else:
                    assert job["system_state"] == "notified"
                    cur.execute("SELECT validation, usage FROM cv_versions WHERE id = %s", (job["cv_version_id"],))
                    cv = cur.fetchone()
                    assert cv["validation"]["agent_review"]["reviews"][0]["decision"] == "approve"
                    assert cv["validation"]["provider"] == "openai"
                    assert cv["usage"]["input_tokens"] == 200
    finally:
        get_settings.cache_clear()
