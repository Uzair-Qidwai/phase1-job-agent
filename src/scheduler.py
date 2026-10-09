"""APScheduler orchestrator with persisted Phase 2 run and job state."""

from __future__ import annotations

import asyncio
import logging
import sys
import time

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.recovery import RUNNABLE_RESTART_STAGES, safe_restart_stage
from src.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")

PIPELINE_STAGE_ORDER = (
    "scraping",
    "persisting",
    "filtering",
    "ranking",
    "tailoring",
    "notifying",
)
PIPELINE_STAGE_INDEX = {
    stage: index for index, stage in enumerate(PIPELINE_STAGE_ORDER)
}


def _stage_enabled(stage: str, resume_from_stage: str) -> bool:
    return PIPELINE_STAGE_INDEX[stage] >= PIPELINE_STAGE_INDEX[resume_from_stage]


def run_pipeline(
    trigger: str = "scheduled", *, retry_of_run_id: str | None = None,
    resume_from_stage: str = "scraping",
) -> str | None:
    from src.tracker import PipelineAlreadyRunning, pipeline_execution_lock

    try:
        with pipeline_execution_lock():
            return _run_pipeline(trigger, retry_of_run_id=retry_of_run_id,
                                 resume_from_stage=resume_from_stage)
    except PipelineAlreadyRunning:
        logger.warning("Pipeline trigger ignored: worker or recovery operation active")
        return None


def _run_pipeline(
    trigger: str = "scheduled",
    *,
    retry_of_run_id: str | None = None,
    resume_from_stage: str = "scraping",
    admitted_run_id: str | None = None,
) -> str | None:
    """Run ingestion → filter → rank → tailor → notify with recoverable state."""
    from src.candidate_profile import load_candidate_profile
    from src.cv_agent import tailor_cv
    from src.emailer import send_digest
    from src.eligibility import evaluate_eligibility
    from src.ranking import rank_job
    from src.scraper import SOURCE_NAMES, scrape_all
    from src.semantic_ranking import rank_job_semantic
    from src.tracker import (
        PipelineAlreadyRunning,
        attach_cv_version,
        complete_pipeline_run,
        fail_pipeline_run,
        get_jobs_by_system_states,
        get_new_jobs_for_digest,
        record_pipeline_event,
        record_source_health,
        save_cv_version,
        save_ranking_result,
        source_has_consecutive_zero_results,
        start_pipeline_run,
        update_job_score,
        update_job_system_state,
        update_pipeline_run,
        upsert_job,
    )

    if resume_from_stage not in RUNNABLE_RESTART_STAGES:
        raise ValueError(
            f"Unsupported resume stage '{resume_from_stage}'. "
            f"Allowed: {sorted(RUNNABLE_RESTART_STAGES)}"
        )

    settings = get_settings()
    profile = load_candidate_profile()

    try:
        run_id = admitted_run_id or start_pipeline_run(
            trigger,
            retry_of_run_id=retry_of_run_id,
        )
    except PipelineAlreadyRunning:
        logger.warning("Pipeline trigger ignored: another run is already active")
        return None

    logger.info("━━━ Pipeline %s started (%s) ━━━", run_id, trigger)
    t0 = time.perf_counter()
    stage = "created"

    raw_jobs = []
    inserted_count = 0
    eligible_jobs: list[dict] = []
    filtered_count = 0
    newly_shortlisted = 0
    tailoring_failures = 0
    tailored_count = 0
    notified_count = 0
    model_input_tokens = 0
    model_output_tokens = 0
    estimated_model_cost_usd = 0.0

    from src.model_runtime import RunBudget
    model_budget = RunBudget(settings.pipeline_max_model_calls, settings.model_spend_stop_usd)

    def agent_runtime(job_id: str):
        from src.model_runtime import AgentRuntime

        def on_step(step):
            nonlocal model_input_tokens, model_output_tokens, estimated_model_cost_usd
            record_pipeline_event(run_id, "agent_step", stage=stage,
                                  level="info" if step["status"] == "completed" else "error",
                                  payload={"job_id": job_id, **step})
            model_input_tokens += step["input_tokens"]
            model_output_tokens += step["output_tokens"]
            estimated_model_cost_usd += step["estimated_cost_usd"] or 0
            update_pipeline_run(run_id, model_input_tokens=model_input_tokens,
                                model_output_tokens=model_output_tokens,
                                estimated_model_cost_usd=estimated_model_cost_usd)
        return AgentRuntime(settings=settings, on_step=on_step, run_budget=model_budget)

    if resume_from_stage != "scraping":
        update_pipeline_run(
            run_id,
            status="resuming",
            current_stage=resume_from_stage,
        )
        record_pipeline_event(
            run_id,
            "run_resuming",
            stage=resume_from_stage,
            payload={
                "retry_of_run_id": retry_of_run_id,
                "resume_from_stage": resume_from_stage,
            },
        )

    try:
        if _stage_enabled("scraping", resume_from_stage):
            stage = "scraping"
            update_pipeline_run(run_id, status=stage, current_stage=stage)
            logger.info("Step 1/6 — Scraping jobs …")
            raw_jobs = asyncio.run(scrape_all(headless=True))
            source_counts = {
                source: sum(job.source == source for job in raw_jobs)
                for source in SOURCE_NAMES
            }
            for job in raw_jobs:
                source_counts.setdefault(job.source, 0)
                if job.source not in SOURCE_NAMES:
                    source_counts[job.source] += 1

            record_source_health(run_id, source_counts)
            for source, count in source_counts.items():
                if count == 0 and source_has_consecutive_zero_results(
                    source,
                    runs=settings.source_zero_alert_runs,
                ):
                    logger.warning(
                        "[SourceHealth] %s returned zero jobs for %d consecutive runs",
                        source,
                        settings.source_zero_alert_runs,
                    )
                    record_pipeline_event(
                        run_id,
                        "source_zero_results_alert",
                        stage=stage,
                        level="warning",
                        payload={
                            "source": source,
                            "consecutive_zero_runs": settings.source_zero_alert_runs,
                        },
                    )

            update_pipeline_run(run_id, jobs_discovered=len(raw_jobs))
            record_pipeline_event(
                run_id,
                "scrape_complete",
                stage=stage,
                payload={
                    "jobs_discovered": len(raw_jobs),
                    "source_counts": source_counts,
                },
            )

        if _stage_enabled("persisting", resume_from_stage):
            stage = "persisting"
            update_pipeline_run(run_id, status=stage, current_stage=stage)
            logger.info("Step 2/6 — Persisting to DB …")
            inserted_count = 0

            for raw_job in raw_jobs:
                _, is_new = upsert_job(
                    title=raw_job.title,
                    company=raw_job.company,
                    location=raw_job.location,
                    url=raw_job.url,
                    description=raw_job.description,
                    source=raw_job.source,
                    source_job_id=raw_job.source_job_id,
                )
                inserted_count += int(is_new)

            update_pipeline_run(run_id, jobs_inserted=inserted_count)
            record_pipeline_event(
                run_id,
                "persist_complete",
                stage=stage,
                payload={"jobs_inserted": inserted_count},
            )

        if _stage_enabled("filtering", resume_from_stage):
            stage = "filtering"
            update_pipeline_run(run_id, status=stage, current_stage=stage)
            discovered_jobs = get_jobs_by_system_states(["discovered"])
            logger.info(
                "Step 3/6 — Filtering %d discovered/backlog jobs …",
                len(discovered_jobs),
            )
            eligible_jobs: list[dict] = []
            filtered_count = 0

            for job in discovered_jobs:
                eligibility = evaluate_eligibility(
                    title=job["title"],
                    company=job["company"],
                    location=job["location"],
                    profile=profile,
                )
                if eligibility.eligible:
                    eligible_jobs.append(job)
                else:
                    update_job_score(str(job["id"]), 0.0)
                    update_job_system_state(str(job["id"]), "filtered_out")
                    filtered_count += 1
                    record_pipeline_event(
                        run_id,
                        "job_filtered_out",
                        stage=stage,
                        payload={
                            "job_id": str(job["id"]),
                            "reasons": eligibility.hard_mismatch_reasons,
                        },
                    )

            record_pipeline_event(
                run_id,
                "filter_complete",
                stage=stage,
                payload={
                    "eligible": len(eligible_jobs),
                    "filtered_out": filtered_count,
                },
            )

        if _stage_enabled("ranking", resume_from_stage):
            stage = "ranking"
            update_pipeline_run(run_id, status=stage, current_stage=stage)
            logger.info(
                "Step 4/6 — Ranking %d eligible jobs with %s mode …",
                len(eligible_jobs),
                "agentic" if settings.agent_workflow_enabled else settings.ranking_mode,
            )
            newly_shortlisted = 0
            model_input_tokens = 0
            model_output_tokens = 0
            estimated_model_cost_usd = 0.0
            ranker = (
                rank_job_semantic
                if settings.ranking_mode == "semantic"
                else rank_job
            )

            if settings.agent_workflow_enabled:
                from src.agent_workflow import rank_job_agentic
                ranker = rank_job_agentic

            for job in eligible_jobs:
                runtime = agent_runtime(str(job["id"])) if (settings.agent_workflow_enabled or settings.ranking_mode == "semantic") else None
                ranking = ranker(
                    title=job["title"],
                    company=job["company"],
                    location=job["location"],
                    description=job["description"],
                    profile=profile,
                    **({"runtime": runtime} if runtime else {}),
                )
                normalized_score = ranking.total_score / 100.0
                ranking_usage = ranking.usage or {}
                if runtime is None or not runtime.steps:
                    model_input_tokens += int(
                        ranking_usage.get("input_tokens", 0) or 0
                    )
                    model_output_tokens += int(
                        ranking_usage.get("output_tokens", 0) or 0
                    )
                    estimated_model_cost_usd += float(
                        ranking.estimated_cost_usd or 0.0
                    )
                    for step_info in ranking.agent_steps:
                        record_pipeline_event(run_id, "agent_step", stage=stage,
                                              payload={"job_id": str(job["id"]), **step_info})
                job_id = str(job["id"])
                save_ranking_result(
                    job_id=job_id,
                    run_id=run_id,
                    total_score=ranking.total_score,
                    hard_mismatch=ranking.hard_mismatch,
                    component_scores=ranking.component_scores,
                    explanation=ranking.explanation,
                    profile_version=ranking.profile_version,
                    ranking_version=ranking.ranking_version,
                    model=ranking.model,
                    usage=ranking.usage,
                    estimated_cost_usd=ranking.estimated_cost_usd,
                )
                update_job_score(job_id, normalized_score)

                shortlisted = (
                    not ranking.hard_mismatch
                    and normalized_score >= settings.shortlist_threshold
                )
                update_job_system_state(
                    job_id,
                    "shortlisted" if shortlisted else "ranked_out",
                )
                newly_shortlisted += int(shortlisted)

                record_pipeline_event(
                    run_id,
                    "job_ranked",
                    stage=stage,
                    payload={
                        "job_id": job_id,
                        "score": normalized_score,
                        "shortlisted": shortlisted,
                        "components": ranking.component_scores,
                        "ranking_version": ranking.ranking_version,
                        "profile_version": ranking.profile_version,
                        "model": ranking.model,
                        "provider": ranking.provider,
                        "cost_estimate_complete": ranking.cost_estimate_complete,
                        "usage": ranking.usage,
                        "estimated_cost_usd": ranking.estimated_cost_usd,
                    },
                )

            update_pipeline_run(
                run_id,
                jobs_ranked=len(eligible_jobs),
                jobs_shortlisted=newly_shortlisted,
                model_input_tokens=model_input_tokens,
                model_output_tokens=model_output_tokens,
                estimated_model_cost_usd=round(estimated_model_cost_usd, 6),
            )
            record_pipeline_event(
                run_id,
                "ranking_complete",
                stage=stage,
                payload={
                    "jobs_ranked": len(eligible_jobs),
                    "jobs_shortlisted": newly_shortlisted,
                    "shortlist_threshold": settings.shortlist_threshold,
                    "ranking_mode": "agentic" if settings.agent_workflow_enabled else settings.ranking_mode,
                    "model_input_tokens": model_input_tokens,
                    "model_output_tokens": model_output_tokens,
                    "estimated_model_cost_usd": round(
                        estimated_model_cost_usd, 6
                    ),
                },
            )

        if _stage_enabled("tailoring", resume_from_stage):
            stage = "tailoring"
            update_pipeline_run(run_id, status=stage, current_stage=stage)
            tailoring_jobs = get_jobs_by_system_states(["shortlisted"])
            logger.info(
                "Step 5/6 — Tailoring %d shortlisted/backlog jobs …",
                len(tailoring_jobs),
            )

            tailored_count = 0

            tailorer = tailor_cv
            if settings.agent_workflow_enabled or settings.cv_review_enabled:
                from src.agent_workflow import tailor_cv_agentic
                tailorer = tailor_cv_agentic

            for job in tailoring_jobs:
                job_id = str(job["id"])
                try:
                    runtime = agent_runtime(job_id)
                    result = tailorer(
                        job_title=job["title"],
                        company=job["company"],
                        description=job["description"],
                        runtime=runtime,
                    )
                    cv_id = save_cv_version(
                        job_id=job_id,
                        tailored_cv=result["tailored_cv"],
                        changes_made=result["changes_made"],
                        model=result["model"],
                        prompt_version=result["prompt_version"],
                        profile_version=result["profile_version"],
                        source_cv_sha256=result["source_cv_sha256"],
                        evidence=result["evidence_used"],
                        validation={**result["validation"],
                                    "provider": result.get("provider"),
                                    "cost_estimate_complete": result.get("cost_estimate_complete", False),
                                    "agent_steps": result.get("agent_steps", [])},
                        usage=result.get("usage", {}),
                        estimated_cost_usd=result.get("estimated_cost_usd", 0.0),
                    )
                    attach_cv_version(job_id, cv_id)
                    update_job_system_state(job_id, "tailored")
                    tailored_count += 1

                    usage = result.get("usage", {})
                    if not runtime.steps:
                        model_input_tokens += int(usage.get("input_tokens", 0) or 0)
                        model_output_tokens += int(usage.get("output_tokens", 0) or 0)
                        estimated_model_cost_usd += float(
                            result.get("estimated_cost_usd", 0.0) or 0.0
                        )
                        for step_info in result.get("agent_steps", []):
                            record_pipeline_event(run_id, "agent_step", stage=stage,
                                                  payload={"job_id": job_id, **step_info})
                except Exception as exc:
                    tailoring_failures += 1
                    # Keep state as 'shortlisted' so the next run retries this job.
                    record_pipeline_event(
                        run_id,
                        "job_tailor_failed",
                        stage=stage,
                        level="error",
                        payload={
                            "job_id": job_id,
                            "error_type": type(exc).__name__,
                            "error_message": str(exc)[:1000],
                        },
                    )
                    logger.exception("CV tailoring failed for job %s", job_id)

            update_pipeline_run(
                run_id,
                jobs_tailored=tailored_count,
                model_input_tokens=model_input_tokens,
                model_output_tokens=model_output_tokens,
                estimated_model_cost_usd=round(estimated_model_cost_usd, 6),
            )
            record_pipeline_event(
                run_id,
                "tailoring_complete",
                stage=stage,
                payload={
                    "jobs_tailored": tailored_count,
                    "model_input_tokens": model_input_tokens,
                    "model_output_tokens": model_output_tokens,
                    "estimated_model_cost_usd": round(
                        estimated_model_cost_usd, 6
                    ),
                },
            )

        if _stage_enabled("notifying", resume_from_stage):
            stage = "notifying"
            update_pipeline_run(run_id, status=stage, current_stage=stage)
            logger.info("Step 6/6 — Preparing digest (%s) …", settings.digest_delivery_mode)
            digest_jobs = get_new_jobs_for_digest(
                min_score=settings.shortlist_threshold
            )
            from src.delivery import deliver_digest
            if settings.digest_delivery_mode == "review":
                from src.digest_review import _prepare_batch
                batch = _prepare_batch()
                record_pipeline_event(run_id, "digest_awaiting_review", stage=stage,
                                      payload={"batch_id": str(batch["id"]) if batch else None,
                                               "emails_sent": 0})
            else:
                notified_count = deliver_digest(digest_jobs, run_id=run_id, send=send_digest)

        if tailoring_failures:
            # Successful CVs can be delivered, but failed jobs must remain visible
            # and resume from tailoring without scraping/ranking again.
            stage = "tailoring"
            raise RuntimeError(f"{tailoring_failures} CV job(s) failed; retry from tailoring")

        complete_pipeline_run(run_id, jobs_notified=notified_count)
        elapsed = time.perf_counter() - t0
        record_pipeline_event(
            run_id,
            "run_metrics",
            stage="completed",
            payload={"elapsed_seconds": round(elapsed, 3)},
        )
        logger.info(
            "━━━ Pipeline %s complete in %.1fs | discovered=%d new=%d ranked=%d shortlisted=%d tailored=%d notified=%d ━━━",
            run_id,
            elapsed,
            len(raw_jobs),
            inserted_count,
            len(eligible_jobs),
            newly_shortlisted,
            tailored_count,
            notified_count,
        )
        return run_id

    except Exception as exc:
        fail_pipeline_run(run_id, stage, exc)
        logger.exception("Pipeline %s failed during %s", run_id, stage)
        raise


def resume_pipeline(failed_run_id: str) -> str | None:
    """Retry a failed run from the earliest safe persisted restart point."""
    from src.tracker import get_pipeline_run

    failed = get_pipeline_run(failed_run_id)
    if not failed:
        raise ValueError("Failed pipeline run does not exist")
    if failed["status"] != "failed":
        raise ValueError("Only failed pipeline runs can be resumed")

    restart_stage = safe_restart_stage(str(failed["current_stage"]))
    return run_pipeline(
        trigger="retry",
        retry_of_run_id=failed_run_id,
        resume_from_stage=restart_stage,
    )


def execute_admitted_run(run_id: str) -> str | None:
    from src.tracker import pipeline_execution_lock

    # Acquire before consuming the reservation so recovery and child startup
    # cannot interleave. A recovered reservation can no longer be claimed.
    with pipeline_execution_lock(wait=True):
        return _execute_admitted_run(run_id)


def _execute_admitted_run(run_id: str) -> str | None:
    from src.tracker import claim_admitted_run, fail_pipeline_run, get_pipeline_run

    # Claim outside the failure handler: a duplicate claimant must never mark
    # the legitimate worker's run as failed or release its active slot.
    run = claim_admitted_run(run_id)
    try:
        parent_id = str(run["retry_of_run_id"]) if run["retry_of_run_id"] else None
        restart = "scraping"
        if parent_id:
            parent = get_pipeline_run(parent_id)
            if not parent or parent["status"] != "failed":
                raise ValueError("Retry parent must exist and be failed")
            restart = safe_restart_stage(parent["current_stage"])
        return _run_pipeline(
            trigger=run["trigger"], retry_of_run_id=parent_id,
            resume_from_stage=restart, admitted_run_id=run_id,
        )
    except Exception as exc:
        current = get_pipeline_run(run_id)
        if current and current["status"] not in {"failed", "completed"}:
            fail_pipeline_run(run_id, current["current_stage"] or "created", exc)
        raise


def start_scheduler(
    hour: int | None = None,
    minute: int | None = None,
    timezone: str | None = None,
) -> None:
    settings = get_settings()
    hour = settings.pipeline_hour if hour is None else hour
    minute = settings.pipeline_minute if minute is None else minute
    timezone = settings.pipeline_timezone if timezone is None else timezone

    scheduler = BlockingScheduler(timezone=timezone)
    scheduler.add_job(
        run_pipeline,
        CronTrigger(hour=hour, minute=minute, timezone=timezone),
        kwargs={"trigger": "scheduled"},
        id="daily_pipeline",
        name="Daily job intelligence pipeline",
        misfire_grace_time=3600,
        replace_existing=True,
    )
    logger.info(
        "Scheduler started — pipeline runs daily at %02d:%02d %s",
        hour,
        minute,
        timezone,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    if "--admitted-run" in sys.argv:
        index = sys.argv.index("--admitted-run")
        if index + 1 >= len(sys.argv):
            raise SystemExit("--admitted-run requires a reserved run UUID")
        execute_admitted_run(sys.argv[index + 1])
    elif "--retry-run" in sys.argv:
        index = sys.argv.index("--retry-run")
        if index + 1 >= len(sys.argv):
            raise SystemExit("--retry-run requires a failed run UUID")
        resume_pipeline(sys.argv[index + 1])
    elif "--run-now" in sys.argv:
        run_pipeline(trigger="manual")
    else:
        start_scheduler()
