"""Typed CV generation contract and deterministic factuality checks."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    claim: str = Field(min_length=3)
    source: Literal["master_cv", "candidate_profile"]
    source_text: str = Field(min_length=3)


class TailoredCVResult(BaseModel):
    tailored_cv: str = Field(min_length=50)
    changes_made: str = Field(min_length=3)
    evidence_used: list[EvidenceItem] = Field(min_length=1)
    keywords_added: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CVValidationResult(BaseModel):
    valid: bool
    evidence_items_checked: int
    invalid_evidence: list[str] = Field(default_factory=list)
    unsupported_numeric_claims: list[str] = Field(default_factory=list)


# Captures material numeric claims including:
# 100, 100+, 50%, $15,000, $100M+, 2.5B.
# Magnitude suffixes matter: 100M and 250M are intentionally different tokens.
_NUMERIC_TOKEN = re.compile(
    r"(?<!\w)(?:[$€£]?\d[\d,]*(?:\.\d+)?(?:[kKmMbB])?(?:%|\+)?)(?!\w)"
)
_CLAIM_TERM = re.compile(r"[a-z][a-z0-9+#.-]{2,}")
_CLAIM_STOPWORDS = {
    "and",
    "the",
    "with",
    "for",
    "from",
    "that",
    "this",
    "into",
    "using",
    "used",
    "role",
    "work",
    "experience",
}


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _meaningful_terms(value: str) -> set[str]:
    return {
        term
        for term in _CLAIM_TERM.findall(value.casefold())
        if term not in _CLAIM_STOPWORDS
    }


def _normalize_number(value: str) -> str:
    # A source claim of "$100M+" supports a conservative rewrite as "$100M".
    # Currency symbols/commas are formatting differences; magnitude and percent
    # suffixes remain meaningful.
    return (
        value.casefold()
        .replace(",", "")
        .replace("$", "")
        .replace("€", "")
        .replace("£", "")
        .rstrip("+")
    )


def _material_numeric_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for raw in _NUMERIC_TOKEN.findall(value):
        normalized = _normalize_number(raw)
        digits = "".join(char for char in normalized if char.isdigit())

        # Ignore incidental one-digit list numbering unless the token carries
        # percentage, currency, or magnitude semantics.
        has_material_suffix = (
            "%" in raw
            or raw[:1] in "$€£"
            or normalized.endswith(("k", "m", "b"))
        )
        if len(digits) < 2 and not has_material_suffix:
            continue

        tokens.add(normalized)
    return tokens


def validate_tailored_cv(
    result: TailoredCVResult,
    *,
    master_cv: str,
    candidate_profile_text: str,
) -> CVValidationResult:
    """Validate source evidence and detect newly invented numeric claims."""

    corpora = {
        "master_cv": _normalize_text(master_cv),
        "candidate_profile": _normalize_text(candidate_profile_text),
    }

    invalid_evidence: list[str] = []
    for item in result.evidence_used:
        source_text = _normalize_text(item.source_text)
        if source_text not in corpora[item.source]:
            invalid_evidence.append(
                f"{item.source}: evidence not found for claim '{item.claim}'"
            )
            continue

        claim_terms = _meaningful_terms(item.claim)
        evidence_terms = _meaningful_terms(item.source_text)
        if claim_terms and not claim_terms.intersection(evidence_terms):
            invalid_evidence.append(
                f"{item.source}: evidence is not relevant to claim '{item.claim}'"
            )

    allowed_numbers = _material_numeric_tokens(master_cv)
    allowed_numbers |= _material_numeric_tokens(candidate_profile_text)
    output_numbers = _material_numeric_tokens(result.tailored_cv)
    unsupported_numbers = sorted(output_numbers - allowed_numbers)

    return CVValidationResult(
        valid=not invalid_evidence and not unsupported_numbers,
        evidence_items_checked=len(result.evidence_used),
        invalid_evidence=invalid_evidence,
        unsupported_numeric_claims=unsupported_numbers,
    )
