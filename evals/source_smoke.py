"""Bounded live source inspection; no model calls, database writes or email."""
import argparse
import asyncio
import json
from pathlib import Path
from dataclasses import asdict

from src import scraper
from src.job_identity import build_job_identity


def summarize(source, jobs):
    identities = [build_job_identity(j.url, j.source).dedupe_key for j in jobs]
    invalid = [i for i, j in enumerate(jobs) if scraper.validate_raw_job(j)]
    normalized = scraper.normalize_jobs(jobs)
    unique_ids = [build_job_identity(j.url, j.source).dedupe_key for j in normalized]
    return {"source": source, "unique_jobs": len(normalized),
            "dedupe_passed": len(unique_ids) == len(set(unique_ids)), "jobs": len(jobs), "invalid_rows": invalid,
            "duplicate_identities": len(identities) - len(set(identities)),
            "missing_descriptions": sum(not j.description.strip() for j in jobs),
            "sample": [asdict(j) for j in jobs[:5]],
            "passed": bool(jobs) and not invalid and all(j.description.strip() for j in jobs) and bool(normalized) and len(unique_ids) == len(set(unique_ids))}


async def inspect(source, limit):
    if source == "greenhouse":
        return await scraper.scrape_greenhouse(max_per_board=limit)
    async with scraper.async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            fn = scraper.scrape_linkedin if source == "linkedin" else scraper.scrape_indeed
            return await fn(browser, max_per_query=limit)
        finally:
            await browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live", action="store_true", required=True)
    parser.add_argument("--source", choices=scraper.SOURCE_NAMES, required=True)
    parser.add_argument("--limit", type=int, choices=range(1, 4), default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new report path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump({"passed": False, "status": "started"}, stream)
    async def bounded():
        return await asyncio.wait_for(inspect(args.source, args.limit), timeout=120)
    try:
        report = summarize(args.source, asyncio.run(bounded()))
    except Exception as exc:
        report = {"passed": False, "source": args.source, "error_type": type(exc).__name__}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "report": str(args.output)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
