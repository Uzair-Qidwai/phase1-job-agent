"""Unit tests for CV tailoring agent."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock

from src.cv_agent import _parse_response, tailor_cv


SAMPLE_RESPONSE = {
    "tailored_cv": "# Uzair Qidwai\n\nToronto, Canada\n\n## Summary\n\nFinance-trained AI/ML engineer with CFA, MBA, and MAS-CS at Penn. Founded DeFi protocols with $100M lifetime volume. Teaching Lead at Penn Engineering across OS, Algorithms, and ML courses.\n\n## Experience\n\n### Teaching Lead — Penn Engineering\n- Lead sections for 100+ graduate students across three courses\n\n## Skills\n\nPython, Solidity, SQL, PyTorch, FastAPI",
    "match_score": 0.82,
    "changes_made": (
        "Moved DeFi protocol experience to top of experience section. "
        "Added 'Solidity' and 'smart contracts' keywords to skills. "
        "Adjusted summary to highlight blockchain engineering depth."
    ),
}


def fake_client(payload: dict = SAMPLE_RESPONSE) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.content = [MagicMock(text=json.dumps(payload))]
    client.messages.create.return_value = response
    return client


class TestParseResponse(unittest.TestCase):
    def test_bare_json(self):
        result = _parse_response(json.dumps(SAMPLE_RESPONSE))
        self.assertEqual(result["match_score"], 0.82)

    def test_json_in_fences(self):
        raw = f"```json\n{json.dumps(SAMPLE_RESPONSE)}\n```"
        result = _parse_response(raw)
        self.assertEqual(result["tailored_cv"], SAMPLE_RESPONSE["tailored_cv"])

    def test_json_with_preamble(self):
        raw = "Here is the response:\n\n" + json.dumps(SAMPLE_RESPONSE)
        result = _parse_response(raw)
        self.assertAlmostEqual(result["match_score"], 0.82)

    def test_invalid_raises(self):
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            _parse_response("not json at all")


class TestTailorCV(unittest.TestCase):
    def test_tailor_returns_structured_data(self):
        result = tailor_cv(
            job_title="DeFi Protocol Engineer",
            company="Uniswap Labs",
            description="We need a senior Solidity engineer to build AMM contracts...",
            client=fake_client(),
        )
        self.assertIn("tailored_cv", result)
        self.assertIn("match_score", result)
        self.assertIn("changes_made", result)
        self.assertGreaterEqual(result["match_score"], 0.0)
        self.assertLessEqual(result["match_score"], 1.0)

    def test_score_clamped_to_range(self):
        bad_response = {**SAMPLE_RESPONSE, "match_score": 1.5}
        result = tailor_cv(
            "AI Engineer",
            "OpenAI",
            "Build LLM products",
            client=fake_client(bad_response),
        )
        self.assertLessEqual(result["match_score"], 1.0)

    def test_cv_is_nonempty(self):
        result = tailor_cv(
            "ML Engineer",
            "Cohere",
            "Train large language models...",
            client=fake_client(),
        )
        self.assertTrue(len(result["tailored_cv"]) > 50)

    def test_api_called_with_system_prompt(self):
        client = fake_client()
        tailor_cv(
            "Quant Researcher",
            "Citadel",
            "Alpha generation, ML signals...",
            client=client,
        )
        call_kwargs = client.messages.create.call_args.kwargs
        self.assertIn("system", call_kwargs)
        self.assertIn("Uzair Qidwai", call_kwargs["system"])


if __name__ == "__main__":
    unittest.main()
