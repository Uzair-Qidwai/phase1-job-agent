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


_NUMERIC_TOKEN = re.compile(r"(?<!\w)(?:[$€£]?\d[\d,]*(?:\.\d+)?%?)(?!\w)")


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalize_number(value: str) -> str:
    return (\n        value.casefold()\n        .replace(",", "")\n        .replace("$", "")\n        .replace("€", "")\n        .replace("£", "")\n        .rstrip("+")\n    )


def _material_numeric_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for raw in _NUMERIC_TOKEN.findall(value):
        normalized = _normalize_number(raw)
        digits = "".join(char for char in normalized if char.isdigit())
        # Ignore incidental one-digit list numbering unless it is explicitly
        # a percentage/currency-style value.
        if len(digits) < 2 and "%" not in raw and raw[:1] not in "$€£":
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
