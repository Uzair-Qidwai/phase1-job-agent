from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.cv_validation import TailoredCVResult, validate_tailored_cv


GOLD = Path(__file__).parent.parent / "evals" / "cv_gold.json"


@pytest.mark.parametrize("case", json.loads(GOLD.read_text(encoding="utf-8")), ids=lambda case: case["name"])
def test_cv_factuality_golden_cases(case) -> None:
    result = TailoredCVResult.model_validate(case["result"])
    validation = validate_tailored_cv(
        result,
        master_cv=case["master_cv"],
        candidate_profile_text=case["candidate_profile"],
    )
    assert validation.valid is case["expected_valid"], validation.model_dump()
    assert validation.output_claims_checked > 0
    assert validation.validation_version == "deterministic-cv-v3"


def test_unsupported_numeric_claim_is_reported() -> None:
    result = TailoredCVResult.model_validate(
        {
            "tailored_cv": "Engineer with 15 years experience building Python systems for enterprise clients.",
            "changes_made": "Strengthened summary.",
            "evidence_used": [
                {
                    "claim": "Python systems",
                    "source": "master_cv",
                    "source_text": "Built Python systems.",
                }
            ],
        }
    )
    validation = validate_tailored_cv(
        result,
        master_cv="Built Python systems.",
        candidate_profile_text="{}",
    )

    assert validation.valid is False
    assert "15" in validation.unsupported_numeric_claims


def test_numeric_magnitude_suffixes_are_compared() -> None:
    supported = TailoredCVResult.model_validate(
        {
            "tailored_cv": (
                "Reached $100M lifetime volume and taught 100 students."
            ),
            "changes_made": "Rephrased existing metrics.",
            "evidence_used": [
                {
                    "claim": "Reached $100M lifetime volume and taught 100 students.",
                    "source": "master_cv",
                    "source_text": "Reached $100M+ lifetime volume and taught 100+ students.",
                }
            ],
        }
    )
    supported_validation = validate_tailored_cv(
        supported,
        master_cv="Reached $100M+ lifetime volume and taught 100+ students.",
        candidate_profile_text="{}",
    )
    assert supported_validation.valid is True

    invented = supported.model_copy(
        update={
            "tailored_cv": (
                "Engineer who helped build a protocol with $250M lifetime volume "
                "and supported 100 students."
            )
        }
    )
    invented_validation = validate_tailored_cv(
        invented,
        master_cv="Reached $100M+ lifetime volume and taught 100+ students.",
        candidate_profile_text="{}",
    )
    assert invented_validation.valid is False
    assert "250m" in invented_validation.unsupported_numeric_claims


def test_irrelevant_evidence_is_rejected() -> None:
    result = TailoredCVResult.model_validate(
        {
            "tailored_cv": (
                "Engineering leader who managed platform delivery across teams "
                "and owned technical execution."
            ),
            "changes_made": "Strengthened leadership framing.",
            "evidence_used": [
                {
                    "claim": "Engineering leader who managed platform delivery across teams and owned technical execution.",
                    "source": "master_cv",
                    "source_text": "Python, SQL, FastAPI",
                }
            ],
        }
    )

    validation = validate_tailored_cv(
        result,
        master_cv="Python, SQL, FastAPI",
        candidate_profile_text="{}",
    )

    assert validation.valid is False
    assert any(
        "not relevant" in message for message in validation.invalid_evidence
    )
