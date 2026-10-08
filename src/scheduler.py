"""APScheduler orchestrator with persisted Phase 2 run state."""

from __future__ import annotations

import asyncio
import logging
import sys
import time

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")


def run_pipeline(trigger: str = "scheduled") -> str | None:
    """Run ingestion → filter → rank → tailor → notify with persisted state."""
    from src.candidate_profile import load_candidate_profile
    from src.cv_agent import tailor_cv
    from src.emailer import send_digest
    from src.eligibility import evaluate_eligibility
    from src.ranking import rank_job
    from src.scraper import scrape_all
    from src.tracker import (
        PipelineAlreadyRunning,
        attach_cv_version,
        complete_pipeline_run,
        fail_pipeline_run,
        get_new_jobs_for_digest,
        mark_jobs_notified,
        record_pipeline_event,
        save_cv_version,
        start_pipeline_run,
        update_job_score,
        update_pipeline_run,
        upsert_job,
    )

    settings = get_settings()
    profile = load_candidate_profile()

    try:
        run_id = start_pipeline_run(trigger)
    except PipelineAlreadyRunning:
        logger.warning("Pipeline trigger ignored: another run is already active")
        return None

    logger.info("━━━ Pipeline %s started (%s) ━━━", run_id, trigger)
    t0 = time.perf_counter()
    stage = "created"

    try:
        stage = "scraping"
        update_pipeline_run(run_id, status=stage, current_stage=stage)
        logger.info("Step 1/6 — Scraping jobs …")
        raw_jobs = asyncio.run(scrape_all(headless=True))
        update_pipeline_run(run_id, jobs_discovered=len(raw_jobs))
        record_pipeline_event(
            run_id,
            "scrape_complete",
            stage=stage,
            payload={"jobs_discovered": len(raw_jobs)},
        )

        stage = "persisting"
        update_pipeline_run(run_id, status=stage, current_stage=stage)
        logger.info("Step 2/6 — Persisting to DB …")
        new_job_records: list[dict] = []

        for raw_job in raw_jobs:
            job_id, is_new = upsert_job(
                title=raw_job.title,
                company=raw_job.company,
                location=raw_job.location,
                url=raw_job.url,
                description=raw_job.description,
                source=raw_job.source,
                source_job_id=raw_job.source_job_id,
            )
            if is_new:
                new_job_records.append(
                    {
                        "id": job_id,
                        "title": raw_job.title,
                        "company": raw_job.company,
                        "location": raw_job.location,
                        "description": raw_job.description,
                    }
                )

        update_pipeline_run(run_id, jobs_inserted=len(new_job_records))
        record_pipeline_event(
            run_id,
            "persist_complete",
            stage=stage,
            payload={"jobs_inserted": len(new_job_records)},
        )

        stage = "filtering"
        update_pipeline_run(run_id, status=stage, current_stage=stage)
        logger.info("Step 3/6 — Applying deterministic eligibility filters …")
        eligible_jobs: list[dict] = []

        for job in new_job_records:
            eligibility = evaluate_eligibility(
                title=job["title"],
                company=job["company"],
                location=job["location"],
                profile=profile,
            )
            if eligibility.eligible:
                eligible_jobs.append(job)
            else:
                update_job_score(job["id"], 0.0)
                record_pipeline_event(
                    run_id,
                    "job_filtered_out",
                    stage=stage,
                    payload={
                        "job_id": job["id"],
                        "reasons": eligibility.hard_mismatch_reasons,
                    },
                )

        record_pipeline_event(
            run_id,
            "filter_complete",
            stage=stage,
            payload={
                "eligible": len(eligible_jobs),
                "filtered_out": len(new_job_records) - len(eligible_jobs),
            },
        )

        stage = "ranking"
        update_pipeline_run(run_id, status=stage, current_stage=stage)
        logger.info("Step 4/6 — Ranking %d eligible jobs …", len(eligible_jobs))
        shortlisted_jobs: list[dict] = []

        for job in eligible_jobs:
            ranking = rank_job(
                title=job["title"],
                company=job["company"],
                location=job["location"],
                description=job["description"],
                profile=profile,
            )
            normalized_score = ranking.total_score / 100.0
            update_job_score(job["id"], normalized_score)

            record_pipeline_event(
                run_id,
                "job_ranked",
                stage=stage,
                payload={
                    "job_id": job["id"],
                    "score": normalized_score,
                    "components": ranking.component_scores,
                    "ranking_version": ranking.ranking_version,
                    "profile_version": ranking.profile_version,
                },
            )

            if (
                not ranking.hard_mismatch
                and normalized_score >= settings.shortlist_threshold
            ):
                shortlisted_jobs.append(job)

        update_pipeline_run(
            run_id,
            jobs_ranked=len(eligible_jobs),
            jobs_shortlisted=len(shortlisted_jobs),
        )
        record_pipeline_event(
            run_id,
            "ranking_complete",
            stage=stage,
            payload={
                "jobs_ranked": len(eligible_jobs),
                "jobs_shortlisted": len(shortlisted_jobs),
                "shortlist_threshold": settings.shortlist_threshold,
            },
        )

        stage = "tailoring"
        update_pipeline_run(run_id, status=stage, current_stage=stage)
        logger.info(
            "Step 5/6 — Tailoring CVs for %d shortlisted jobs …",
            len(shortlisted_jobs),
        )

        tailored_count = 0
        for job in shortlisted_jobs:
            try:
                result = tailor_cv(
                    job_title=job["title"],
                    company=job["company"],
                    description=job["description"],
                )
                cv_id = save_cv_version(
                    job_id=job["id"],
                    tailored_cv=result["tailored_cv"],
                    changes_made=result["changes_made"],
                    model=result["model"],
                    prompt_version=result["prompt_version"],
                    profile_version=result["profile_version"],
                    source_cv_sha256=result["source_cv_sha256"],
                    evidence=result["evidence_used"],
                    validation=result["validation"],
                )
                attach_cv_version(job["id"], cv_id)
                tailored_count += 1
            except Exception as exc:
                record_pipeline_event(
                    run_id,
                    "job_tailor_failed",
                    stage=stage,
                    level="error",
                    payload={
                        "job_id": job["id"],
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:1000],
                    },
                )
                logger.exception("CV tailoring failed for job %s", job["id"])

        update_pipeline_run(run_id, jobs_tailored=tailored_count)
        record_pipeline_event(
            run_id,
            "tailoring_complete",
            stage=stage,
            payload={"jobs_tailored": tailored_count},
        )

        stage = "notifying"
        update_pipeline_run(run_id, status=stage, current_stage=stage)
        logger.info("Step 6/6 — Sending digest …")
        digest_jobs = get_new_jobs_for_digest(
            min_score=settings.shortlist_threshold
        )
        sent = send_digest(digest_jobs)
        if not sent:
            raise RuntimeError("Digest delivery failed")

        notified_count = mark_jobs_notified(
            [str(job["id"]) for job in digest_jobs],
            run_id=run_id,
            channel="email",
        )

        complete_pipeline_run(run_id, jobs_notified=notified_count)
        elapsed = time.perf_counter() - t0
        record_pipeline_event(
            run_id,
            "run_metrics",
            stage="completed",
            payload={"elapsed_seconds": round(elapsed, 3)},
        )
        logger.info(
            "━━━ Pipeline %s complete in %.1fs | discovered=%d new=%d ranked=%d shortlisted=%d tailored=%d ━━━",
            run_id,
            elapsed,
            len(raw_jobs),
            len(new_job_records),
            len(eligible_jobs),
            len(shortlisted_jobs),
            tailored_count,
        )
        return run_id

    except Exception as exc:
        fail_pipeline_run(run_id, stage, exc)
        logger.exception("Pipeline %s failed during %s", run_id, stage)
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
    if "--run-now" in sys.argv:
        run_pipeline(trigger="manual")
    else:
        start_scheduler()
