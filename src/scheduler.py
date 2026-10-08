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
    """Run the current pipeline while persisting stage state and run metrics."""
    from src.cv_agent import tailor_cv
    from src.emailer import send_digest
    from src.scraper import scrape_all
    from src.tracker import (
        PipelineAlreadyRunning,
        complete_pipeline_run,
        fail_pipeline_run,
        get_new_jobs_for_digest,
        record_pipeline_event,
        save_cv_version,
        start_pipeline_run,
        update_job_score_and_cv,
        update_pipeline_run,
        upsert_job,
    )

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
        logger.info("Step 1/4 — Scraping jobs …")
        raw_jobs = asyncio.run(scrape_all(headless=True))
        update_pipeline_run(run_id, jobs_discovered=len(raw_jobs))
        record_pipeline_event(
            run_id,
            "scrape_complete",
            stage=stage,
            payload={"jobs_discovered": len(raw_jobs)},
        )
        logger.info("Scraped %d unique jobs", len(raw_jobs))

        stage = "persisting"
        update_pipeline_run(run_id, status=stage, current_stage=stage)
        logger.info("Step 2/4 — Persisting to DB …")
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
        logger.info("%d new jobs inserted", len(new_job_records))

        # Phase 2 will split eligibility/ranking from generation. Until that
        # workstream lands, the current tailoring behavior remains intact.
        stage = "tailoring"
        update_pipeline_run(run_id, status=stage, current_stage=stage)
        logger.info("Step 3/4 — Tailoring CVs for %d new jobs …", len(new_job_records))

        tailored_count = 0
        for job in new_job_records:
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
                )
                update_job_score_and_cv(
                    job_id=job["id"],
                    match_score=result["match_score"],
                    cv_version_id=cv_id,
                )
                tailored_count += 1
                logger.info(
                    "  ✓ %s @ %s → score=%.2f",
                    job["title"],
                    job["company"],
                    result["match_score"],
                )
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
        logger.info("Step 4/4 — Sending daily digest …")
        digest_jobs = get_new_jobs_for_digest(min_score=0.6)
        send_digest(digest_jobs)

        complete_pipeline_run(run_id, jobs_notified=len(digest_jobs))
        elapsed = time.perf_counter() - t0
        record_pipeline_event(
            run_id,
            "run_metrics",
            stage="completed",
            payload={"elapsed_seconds": round(elapsed, 3)},
        )
        logger.info("━━━ Pipeline %s complete in %.1fs ━━━", run_id, elapsed)
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
        name="Daily job scrape + tailor + digest",
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
