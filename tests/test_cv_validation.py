from __future__ import annotations

import json
from pathlib import Path

from src.cv_validation import TailoredCVResult, validate_tailored_cv


GOLD = Path(__file__).parent.parent / "evals" / "cv_gold.json"


def test_cv_factuality_golden_cases() -> None:
    cases = json.loads(GOLD.read_text(encoding="utf-8"))

    for case in cases:
        result = TailoredCVResult.model_validate(case["result"])
        validation = validate_tailored_cv(
            result,
            master_cv=case["master_cv"],
            candidate_profile_text=case["candidate_profile"],
        )
        assert validation.valid is case["expected_valid"], case["name"]


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
