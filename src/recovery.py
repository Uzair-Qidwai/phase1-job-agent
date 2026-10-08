"""Safe restart policy for failed Phase 2 pipeline runs."""

from __future__ import annotations


SAFE_RESTART_STAGE_BY_FAILURE = {
    "created": "scraping",
    "scraping": "scraping",
    "persisting": "scraping",
    "filtering": "filtering",
    "ranking": "filtering",
    "tailoring": "tailoring",
    "notifying": "notifying",
}

RUNNABLE_RESTART_STAGES = frozenset(SAFE_RESTART_STAGE_BY_FAILURE.values())


def safe_restart_stage(failed_stage: str) -> str:
    """Return the earliest stage that can safely reconstruct required state."""
    try:
        return SAFE_RESTART_STAGE_BY_FAILURE[failed_stage]
    except KeyError as exc:
        raise ValueError(f"Unsupported failed pipeline stage: {failed_stage}") from exc
