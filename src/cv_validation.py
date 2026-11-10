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
    validation_version: str = "deterministic-cv-v3"
    output_claims_checked: int = 0
    context_errors: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    evidence_items_checked: int
    invalid_evidence: list[str] = Field(default_factory=list)
    unsupported_numeric_claims: list[str] = Field(default_factory=list)


# Captures material numeric claims including:
# 100, 100+, 50%, $15,000, $100M+, 2.5B.
# Magnitude suffixes matter: 100M and 250M are intentionally different tokens.
_NUMERIC_TOKEN = re.compile(
    r"(?<!\w)(?:[$€£]?\d[\d,]*(?:\.\d+)?(?:[kKmMbB])?(?:%|\+)?)(?!\w)"
)

def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


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


# Only generic structural headings may bypass factual coverage. A heading such
# as "Stanford PhD" is still a claim, even when formatted as Markdown.
_HEADINGS = {
    "summary", "professional summary", "experience", "professional experience",
    "education", "skills", "technical skills", "certifications", "awards",
    "certifications & awards", "projects", "contact", "publications",
}
# Keep these terms when comparing claims: dropping them can reverse meaning or
# turn tentative/supporting work into a credential or ownership claim.
_QUALIFIERS = {
    "no", "not", "never", "without", "expected", "pursuing", "pursued",
    "applicant", "applied", "aspiring", "planned", "proposed", "assisted",
    "supported", "helped", "contributed", "intern", "volunteer", "supervised",
    "pending", "learning", "studying", "introductory", "basic", "limited", "unable",
}
_GRAMMAR_WORDS = {"a", "an", "the", "and", "of", "in", "on", "at", "for", "to", "with"}


def _canonical_claim(text: str) -> str:
    text = re.sub(r"^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+)", "", text)
    text = text.replace("**", "").strip(" *_")
    # Preserve meaning-bearing punctuation such as + and % in the claim text.
    return _normalize_text(text).rstrip(".!?")


def _claim_segments(text: str) -> list[str]:
    # Split on line/sentence boundaries, not decimal points or abbreviations
    # lacking a following space. Preserve semicolon-connected relationships.
    return [part for raw in re.split(r"\n+|(?<=[.!?])\s+", text)
            if (part := _canonical_claim(raw)) and set(part) - {"-", "_", "*"}]


def _fact_terms(text: str) -> set[str]:
    text = re.sub(r"n[’']t\b", " not", text.casefold())
    text = re.sub(r"\bcannot\b", "can not", text)
    normalized = _NUMERIC_TOKEN.sub(lambda match: _normalize_number(match[0]), text)
    return set(re.findall(r"[a-z0-9]+(?:[+#]+)?", normalized.casefold())) - _GRAMMAR_WORDS


def _ordered_terms(text: str) -> list[str]:
    normalized = _NUMERIC_TOKEN.sub(lambda match: _normalize_number(match[0]), text.casefold())
    return [term for term in re.findall(r"[a-z0-9]+(?:[+#]+)?", normalized)
            if term not in _GRAMMAR_WORDS]


def _same_order(claim: str, evidence: str) -> bool:
    # A bag of words cannot distinguish who mentored whom or which metric
    # belongs to which employer. Require factual terms in source order.
    remaining = iter(_ordered_terms(evidence))
    return all(any(term == candidate for candidate in remaining) for term in _ordered_terms(claim))


def _contexts(text: str) -> tuple[dict[str, set[tuple[str, ...]]], set[str]]:
    contexts: dict[str, set[tuple[str, ...]]] = {}
    headings: set[str] = set()
    stack: list[tuple[int, str]] = []
    aliases = {"professional experience": "experience", "professional summary": "summary"}
    for line in text.splitlines():
        heading = re.match(r"^\s*(#{2,6})\s+(.+)$", line)
        bold_heading = re.fullmatch(r"\s*\*\*([^*]+)\*\*\s*", line)
        canonical = _canonical_claim(line)
        if heading or bold_heading or canonical in _HEADINGS:
            depth = len(heading[1]) if heading else (2 if canonical in _HEADINGS else 3)
            label = aliases.get(canonical, canonical)
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, label))
            if canonical in _HEADINGS:
                headings.add(label)
        for segment in _claim_segments(line):
            contexts.setdefault(segment, set()).add(tuple(label for _, label in stack))
    return contexts, headings


def _compatible_contexts(output: set[tuple[str, ...]], source: set[tuple[str, ...]]) -> bool:
    # Unstructured source excerpts may gain neutral section headings, never an
    # employer/role heading. Structured sources must retain their attribution.
    return all(context in source or (() in source and all(label in _HEADINGS for label in context))
               for context in output)


def _supported_rewrite(claim: str, evidence: str) -> bool:
    claim_terms = _fact_terms(claim)
    evidence_terms = _fact_terms(evidence)
    return (bool(claim_terms) and _same_order(claim, evidence) and claim_terms <= evidence_terms
            and (evidence_terms & _QUALIFIERS) <= claim_terms
            and _material_numeric_tokens(claim) <= _material_numeric_tokens(evidence))


def validate_tailored_cv(
    result: TailoredCVResult,
    *,
    master_cv: str,
    candidate_profile_text: str,
) -> CVValidationResult:
    """Conservative lexical coverage gate, not a semantic entailment proof.

    Copied source sentences are covered automatically. Rewritten full sentences
    or bullets need a citation to a complete source statement, with all factual
    terms supported in that one statement and qualifiers retained. Current
    candidate profiles contain targeting preferences, not factual credentials.
    """
    del candidate_profile_text
    source_segments = set(_claim_segments(master_cv))
    output_segments = _claim_segments(result.tailored_cv)
    factual_segments = [segment for segment in output_segments if segment not in _HEADINGS]
    source_contexts, source_headings = _contexts(master_cv)
    output_contexts, output_headings = _contexts(result.tailored_cv)
    context_errors = [f"Missing source section: {heading}" for heading in sorted(source_headings - output_headings)]
    for claim in factual_segments:
        if claim in source_segments and not _compatible_contexts(output_contexts.get(claim, set()), source_contexts.get(claim, set())):
            context_errors.append(f"Source statement moved outside its section/role: {claim}")
    invalid_evidence: list[str] = []
    supported_claims: set[str] = set()
    for item in result.evidence_used:
        claim = _canonical_claim(item.claim)
        if item.source != "master_cv":
            invalid_evidence.append("candidate_profile contains preferences, not CV facts")
            continue
        if _normalize_text(item.source_text) not in _normalize_text(master_cv):
            invalid_evidence.append(f"master_cv: evidence not found for claim '{item.claim}'")
            continue
        evidence_segments = _claim_segments(item.source_text)
        if not evidence_segments or any(segment not in source_segments for segment in evidence_segments):
            invalid_evidence.append(f"Evidence must quote complete source statements: '{item.claim}'")
            continue
        if claim not in factual_segments:
            invalid_evidence.append(f"Evidence claim is not a complete output statement: '{item.claim}'")
            continue
        if not any(_supported_rewrite(claim, segment) for segment in evidence_segments):
            invalid_evidence.append(f"Evidence is not relevant or does not support all facts: '{item.claim}'")
            continue
        supported_contexts = set().union(*(source_contexts.get(segment, set())
                                          for segment in evidence_segments
                                          if _supported_rewrite(claim, segment)))
        if not _compatible_contexts(output_contexts.get(claim, set()), supported_contexts):
            context_errors.append(f"Rewrite changes source section/role: {claim}")
        supported_claims.add(claim)

    unsupported_claims = [segment for segment in factual_segments
                          if segment not in source_segments and segment not in supported_claims]
    unsupported_numbers = sorted(_material_numeric_tokens(result.tailored_cv)
                                 - _material_numeric_tokens(master_cv))
    return CVValidationResult(
        valid=not invalid_evidence and not unsupported_numbers and not unsupported_claims and not context_errors,
        context_errors=context_errors,
        evidence_items_checked=len(result.evidence_used),
        output_claims_checked=len(factual_segments),
        invalid_evidence=invalid_evidence,
        unsupported_numeric_claims=unsupported_numbers,
        unsupported_claims=unsupported_claims,
    )
