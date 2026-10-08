"""Deterministic metrics used by the Phase 2 ranking evaluation harness."""

from __future__ import annotations


def precision_at_k(predicted_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    top = predicted_ids[:k]
    if not top:
        return 0.0
    return sum(job_id in relevant_ids for job_id in top) / len(top)


def pairwise_accuracy(
    scores: dict[str, float],
    preferred_pairs: list[tuple[str, str]],
) -> float:
    """Fraction of (preferred, less_preferred) pairs ordered correctly."""
    if not preferred_pairs:
        return 1.0
    correct = sum(scores[a] > scores[b] for a, b in preferred_pairs)
    return correct / len(preferred_pairs)
