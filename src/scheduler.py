"""
scheduler.py — APScheduler orchestrator.
Runs the full scrape → tailor → digest pipeline daily at 8 AM local time.
Can also be triggered manually: python -m src.scheduler --run-now
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")


# ─────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────

def run_pipeline() -> None:
    """Full pipeline: scrape → persist → tailor → persist scores → email digest."""
    from src.scraper import scrape_all
    from src.cv_agent import tailor_cv
    from src.tracker import upsert_job, save_cv_version, update_job_score_and_cv, get_new_jobs_for_digest
    from src.emailer import send_digest

    logger.info("━━━ Pipeline started ━━━")
    t0 = time.perf_counter()

    # 1. Scrape
    logger.info("Step 1/4 — Scraping jobs …")
    raw_jobs = asyncio.run(scrape_all(headless=True))
    logger.info("Scraped %d unique jobs", len(raw_jobs))

    # 2. Persist new jobs (dedup handled by upsert_job)
    logger.info("Step 2/4 — Persisting to DB …")
    new_job_records: list[dict] = []
    for rj in raw_jobs:
        job_id, is_new = upsert_job(
            title=rj.title,
            company=rj.company,
            location=rj.location,
            url=rj.url,
            description=rj.description,
            source=rj.source,
        )
        if is_new:
            new_job_records.append({
                "id": job_id,
                "title": rj.title,
                "company": rj.company,
                "description": rj.description,
            })

    logger.info("%d new jobs inserted", len(new_job_records))

    # 3. Tailor CVs for new jobs
    logger.info("Step 3/4 — Tailoring CVs for %d new jobs …", len(new_job_records))
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
            logger.info(
                "  ✓ %s @ %s → score=%.2f",
                job["title"], job["company"], result["match_score"]
            )
        except Exception as exc:
            logger.error("  ✗ CV tailor failed for job %s: %s", job["id"], exc)

    # 4. Email digest
    logger.info("Step 4/4 — Sending daily digest …")
    digest_jobs = get_new_jobs_for_digest(min_score=0.6)
    send_digest(digest_jobs)

    elapsed = time.perf_counter() - t0
    logger.info("━━━ Pipeline complete in %.1fs ━━━", elapsed)


# ─────────────────────────────────────────────
# Entry points
# ─────────────────────────────────────────────

def start_scheduler(hour: int = 8, minute: int = 0, timezone: str = "America/Toronto") -> None:
    scheduler = BlockingScheduler(timezone=timezone)
    scheduler.add_job(
        run_pipeline,
        CronTrigger(hour=hour, minute=minute, timezone=timezone),
        id="daily_pipeline",
        name="Daily job scrape + tailor + digest",
        misfire_grace_time=3600,  # tolerate up to 1h late start
        replace_existing=True,
    )
    logger.info("Scheduler started — pipeline runs daily at %02d:%02d %s", hour, minute, timezone)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    if "--run-now" in sys.argv:
        run_pipeline()
    else:
        start_scheduler()
