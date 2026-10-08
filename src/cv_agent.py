"""
cv_agent.py — Tailors master CV per job description using Claude API.
Returns a scored, tailored CV and a plain-English summary of changes.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from src.settings import get_settings

load_dotenv()
logger = logging.getLogger(__name__)

MASTER_CV_PATH = Path(__file__).parent.parent / "data" / "master_cv.md"

SYSTEM_PROMPT = """
You are a job search assistant for Uzair Qidwai — a candidate with:
- CFA designation + MBA (Imperial College London, 2018)
- Master of Applied Science – Computer Science with AI concentration (MAS-CS) at Penn Engineering
- Background: DeFi protocol founder ($100M lifetime DEX volume), TA at Penn Engineering, AI/ML engineering
- Target roles: AI Engineer, DeFi/Web3, Quantitative, Technical PM (AI/Crypto)
- Based in Toronto, Canada (TN visa eligible for US roles)

When tailoring a CV you MUST respond with a single JSON object — no markdown fences, no commentary.
Schema:
{
  "tailored_cv": "<full tailored CV as plain text / markdown>",
  "match_score": <float 0.0–1.0>,
  "changes_made": "<2–4 sentence plain-English summary of what was changed and why>"
}

Rules for tailoring:
1. Mirror keywords from the job description naturally — do not keyword-stuff
2. Reorder bullet points to front-load the most relevant experience
3. Adjust the summary paragraph for the specific role
4. NEVER fabricate experience, credentials, companies, or metrics
5. Keep the full CV — do not omit sections; compress if needed

Scoring guide:
- 0.8–1.0 → strong match, apply immediately
- 0.5–0.8 → decent match, apply if volume is low
- 0.0–0.5 → weak match, likely skip
""".strip()


def _load_master_cv() -> str:
    return MASTER_CV_PATH.read_text(encoding="utf-8")


def _parse_response(raw: str) -> dict:
    """
    Extract the JSON payload from the model response.
    Handles both bare JSON and JSON wrapped in markdown fences.
    """
    # Strip any ```json ... ``` wrapper if the model slipped one in
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Last-resort: try to find the first { ... } blob
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Could not parse JSON from model response:\n{raw[:500]}")


def tailor_cv(
    job_title: str,
    company: str,
    description: str,
    model: str = "claude-sonnet-4-5",
    max_tokens: int = 4096,
    client=None,
) -> dict:
    """
    Call Claude API to produce a tailored CV for a specific job.

    Returns:
        {
            "tailored_cv": str,
            "match_score": float,
            "changes_made": str,
        }
    """
    if client is None:
        client = anthropic.Anthropic(api_key=get_settings().require_anthropic_api_key())
    master_cv = _load_master_cv()

    user_message = f"""
Job Title: {job_title}
Company: {company}

--- JOB DESCRIPTION ---
{description[:6000]}  # cap to keep context manageable
--- END DESCRIPTION ---

--- MASTER CV ---
{master_cv}
--- END CV ---

Produce a tailored CV for this role. Respond ONLY with the JSON object described in your instructions.
""".strip()

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text
    result = _parse_response(raw)

    # Clamp score to valid range
    result["match_score"] = max(0.0, min(1.0, float(result.get("match_score", 0.5))))
    return result


def batch_tailor(
    jobs: list[dict],
    skip_below_score: float | None = None,
) -> list[dict]:
    """
    Tailor CVs for a list of job dicts.
    Each dict needs: id, title, company, description.
    Returns list of result dicts with original job_id attached.
    """
    results = []
    for job in jobs:
        logger.info("Tailoring CV for %s @ %s …", job["title"], job["company"])
        try:
            result = tailor_cv(
                job_title=job["title"],
                company=job["company"],
                description=job.get("description", ""),
            )
            result["job_id"] = job["id"]
            results.append(result)
            logger.info(
                "  → score=%.2f | %s", result["match_score"], result["changes_made"][:80]
            )
        except Exception as exc:
            logger.error("  ✗ Failed for job %s: %s", job["id"], exc)

    return results
