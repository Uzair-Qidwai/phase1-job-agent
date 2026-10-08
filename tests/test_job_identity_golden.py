import json
from pathlib import Path

import pytest

from src.job_identity import build_job_identity


FIXTURE_PATH = Path(__file__).parent.parent / "evals" / "fixtures" / "job_identity_cases.json"


@pytest.mark.parametrize(
    "case",
    json.loads(FIXTURE_PATH.read_text(encoding="utf-8")),
    ids=lambda case: case["name"],
)
def test_job_identity_golden(case):
    identity = build_job_identity(case["input_url"], case["source"])

    assert identity.source_job_id == case["expected_source_job_id"]
    assert identity.canonical_url == case["expected_canonical_url"]
