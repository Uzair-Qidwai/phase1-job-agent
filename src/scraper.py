"""
scraper.py — Playwright-based job scraper for LinkedIn, Indeed, and Greenhouse.

LinkedIn:   uses public /jobs/search endpoint (no login required for listings)
Indeed:     parses search results page + individual job pages
Greenhouse: public job board API for known companies
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from urllib.parse import quote_plus
from typing import Protocol

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import Page, async_playwright

from src.job_identity import build_job_identity

logger = logging.getLogger(__name__)

SOURCE_NAMES = ("greenhouse", "linkedin", "indeed")


@dataclass
class RawJob:
    title: str
    company: str
    location: str
    url: str
    description: str
    source: str
    source_job_id: str | None = None


class JobSource(Protocol):
    name: str

    async def discover(self, browser=None) -> list[RawJob]:
        ...


def validate_raw_job(job: RawJob) -> list[str]:
    errors: list[str] = []
    if not job.title.strip():
        errors.append("title is required")
    if not job.company.strip():
        errors.append("company is required")
    if not job.url.strip():
        errors.append("url is required")
    if not job.source.strip():
        errors.append("source is required")
    return errors


async def _wait_and_text(page: Page, selector: str, timeout: int = 5000) -> str:
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        el = await page.query_selector(selector)
        return (await el.inner_text()).strip() if el else ""
    except Exception:
        return ""


async def _human_delay(lo: float = 1.5, hi: float = 3.5) -> None:
    await asyncio.sleep(lo + (hi - lo) * __import__("random").random())


LINKEDIN_SEARCH_TERMS = [
    "AI Engineer",
    "DeFi Engineer",
    "Quantitative Analyst",
    "Technical Product Manager AI",
]

LINKEDIN_LOCATIONS = ["Toronto, Ontario, Canada", "Remote"]


async def scrape_linkedin(browser, max_per_query: int = 10) -> list[RawJob]:
    jobs: list[RawJob] = []
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    )

    for term in LINKEDIN_SEARCH_TERMS:
        for loc in LINKEDIN_LOCATIONS:
            url = (
                "https://www.linkedin.com/jobs/search/?"
                f"keywords={quote_plus(term)}&location={quote_plus(loc)}"
                "&f_TPR=r86400&sortBy=DD"
            )
            logger.info("[LinkedIn] %s | %s", term, loc)
            page = await context.new_page()

            try:
                await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
                await _human_delay()

                for _ in range(3):
                    await page.keyboard.press("End")
                    await _human_delay(0.8, 1.5)

                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")
                cards = soup.select("ul.jobs-search__results-list li")[:max_per_query]

                for card in cards:
                    link_tag = card.select_one("a.base-card__full-link")
                    if not link_tag:
                        continue

                    job_url = link_tag.get("href", "")
                    title_tag = card.select_one("h3.base-search-card__title")
                    company_tag = card.select_one("h4.base-search-card__subtitle")
                    loc_tag = card.select_one("span.job-search-card__location")

                    if not job_url or not title_tag:
                        continue

                    desc = await _fetch_linkedin_description(context, job_url)

                    jobs.append(
                        RawJob(
                            title=title_tag.get_text(strip=True),
                            company=company_tag.get_text(strip=True) if company_tag else "",
                            location=loc_tag.get_text(strip=True) if loc_tag else loc,
                            url=job_url,
                            description=desc,
                            source="linkedin",
                        )
                    )
                    await _human_delay(0.5, 1.2)

            except Exception as exc:
                logger.warning("[LinkedIn] Error scraping %s: %s", url, exc)
            finally:
                await page.close()

    await context.close()
    logger.info("[LinkedIn] Total raw jobs: %d", len(jobs))
    return jobs


async def _fetch_linkedin_description(context, job_url: str) -> str:
    page = await context.new_page()
    try:
        await page.goto(job_url, timeout=20_000, wait_until="domcontentloaded")
        await _human_delay(0.8, 1.5)
        desc = await _wait_and_text(page, "div.description__text", timeout=6000)
        if not desc:
            desc = await _wait_and_text(page, "div.show-more-less-html__markup")
        return desc[:8000]
    except Exception as exc:
        logger.debug("[LinkedIn] Desc fetch failed %s: %s", job_url, exc)
        return ""
    finally:
        await page.close()


INDEED_SEARCH_TERMS = [
    "AI Engineer",
    "DeFi blockchain engineer",
    "quantitative analyst",
    "technical product manager AI",
]


async def scrape_indeed(browser, max_per_query: int = 10) -> list[RawJob]:
    jobs: list[RawJob] = []
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    )

    for term in INDEED_SEARCH_TERMS:
        for location in ["Toronto, ON", "remote"]:
            url = (
                f"https://ca.indeed.com/jobs?q={quote_plus(term)}"
                f"&l={quote_plus(location)}&fromage=1&sort=date"
            )
            logger.info("[Indeed] %s | %s", term, location)
            page = await context.new_page()

            try:
                await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
                await _human_delay()

                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")
                cards = soup.select("div.job_seen_beacon")[:max_per_query]

                for card in cards:
                    link = card.select_one("a[data-jk]")
                    if not link:
                        continue

                    jk = link.get("data-jk", "")
                    job_url = f"https://ca.indeed.com/viewjob?jk={jk}"
                    title_tag = card.select_one("h2.jobTitle span[title]")
                    company_tag = card.select_one("span[data-testid='company-name']")
                    loc_tag = card.select_one("div[data-testid='text-location']")

                    if not jk or not title_tag:
                        continue

                    desc = await _fetch_indeed_description(context, job_url)

                    jobs.append(
                        RawJob(
                            title=title_tag.get("title", title_tag.get_text(strip=True)),
                            company=company_tag.get_text(strip=True) if company_tag else "",
                            location=loc_tag.get_text(strip=True) if loc_tag else location,
                            url=job_url,
                            description=desc,
                            source="indeed",
                            source_job_id=jk,
                        )
                    )
                    await _human_delay(0.5, 1.5)

            except Exception as exc:
                logger.warning("[Indeed] Error: %s", exc)
            finally:
                await page.close()

    await context.close()
    logger.info("[Indeed] Total raw jobs: %d", len(jobs))
    return jobs


async def _fetch_indeed_description(context, job_url: str) -> str:
    page = await context.new_page()
    try:
        await page.goto(job_url, timeout=20_000, wait_until="domcontentloaded")
        await _human_delay(0.8, 1.2)
        desc = await _wait_and_text(page, "div#jobDescriptionText", timeout=6000)
        return desc[:8000]
    except Exception as exc:
        logger.debug("[Indeed] Desc failed %s: %s", job_url, exc)
        return ""
    finally:
        await page.close()


GREENHOUSE_BOARDS = [
    "anthropic",
    "openai",
    "cohere",
    "chainalysis",
    "figment",
    "coinbase",
    "alchemy",
    "consensys",
]

GREENHOUSE_KEYWORDS = re.compile(
    r"(ai|machine.learning|ml|defi|blockchain|quant|quantitative|crypto|web3|"
    r"product.manager|engineer|solidity|python)",
    re.IGNORECASE,
)


async def scrape_greenhouse(max_per_board: int = 20) -> list[RawJob]:
    jobs: list[RawJob] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for board in GREENHOUSE_BOARDS:
            url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                for job in data.get("jobs", [])[:max_per_board]:
                    title = job.get("title", "")
                    if not GREENHOUSE_KEYWORDS.search(title):
                        continue

                    content = BeautifulSoup(
                        job.get("content", ""), "html.parser"
                    ).get_text(separator="\n")
                    jobs.append(
                        RawJob(
                            title=title,
                            company=board.title(),
                            location=job.get("location", {}).get("name", "Remote"),
                            url=job.get("absolute_url", ""),
                            description=content[:8000],
                            source="greenhouse",
                            source_job_id=str(job.get("id")) if job.get("id") is not None else None,
                        )
                    )
            except Exception as exc:
                logger.warning("[Greenhouse] %s failed: %s", board, exc)

    logger.info("[Greenhouse] Total raw jobs: %d", len(jobs))
    return jobs


class LinkedInSource:
    name = "linkedin"

    async def discover(self, browser=None) -> list[RawJob]:
        if browser is None:
            raise ValueError("LinkedInSource requires a browser")
        return await scrape_linkedin(browser)


class IndeedSource:
    name = "indeed"

    async def discover(self, browser=None) -> list[RawJob]:
        if browser is None:
            raise ValueError("IndeedSource requires a browser")
        return await scrape_indeed(browser)


class GreenhouseSource:
    name = "greenhouse"

    async def discover(self, browser=None) -> list[RawJob]:
        return await scrape_greenhouse()


async def scrape_all(headless: bool = True) -> list[RawJob]:
    """Run source adapters and return validated, source-aware unique jobs."""

    greenhouse_source = GreenhouseSource()
    linkedin_source = LinkedInSource()
    indeed_source = IndeedSource()

    greenhouse_jobs = await greenhouse_source.discover()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        linkedin_jobs, indeed_jobs = await asyncio.gather(
            linkedin_source.discover(browser),
            indeed_source.discover(browser),
        )
        await browser.close()

    source_batches = {
        greenhouse_source.name: greenhouse_jobs,
        linkedin_source.name: linkedin_jobs,
        indeed_source.name: indeed_jobs,
    }
    for source_name, jobs in source_batches.items():
        logger.info("[SourceHealth] %s discovered=%d", source_name, len(jobs))

    all_jobs = greenhouse_jobs + linkedin_jobs + indeed_jobs

    seen: set[str] = set()
    unique: list[RawJob] = []

    for job in all_jobs:
        validation_errors = validate_raw_job(job)
        if validation_errors:
            logger.warning(
                "[SourceContract] dropping invalid %s job: %s",
                job.source or "unknown",
                "; ".join(validation_errors),
            )
            continue

        identity = build_job_identity(job.url, job.source)
        if not identity.canonical_url:
            continue

        if not job.source_job_id:
            job.source_job_id = identity.source_job_id

        if identity.dedupe_key in seen:
            continue

        seen.add(identity.dedupe_key)

        # Persist/use the canonical URL so downstream DB deduplication agrees
        # with the ingestion harness.
        job.url = identity.canonical_url
        unique.append(job)

    logger.info("Total unique jobs this run: %d", len(unique))
    return unique


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    jobs = asyncio.run(scrape_all(headless=False))
    for job in jobs:
        print(f"[{job.source}] {job.title} @ {job.company} — {job.location}")
