"""
tests/test_cv_agent.py — Unit tests for CV tailoring agent.
Run: pytest tests/ -v
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from src.cv_agent import _parse_response, tailor_cv


SAMPLE_RESPONSE = {
    "tailored_cv": "# Uzair Qidwai\n\nTailored CV content here...",
    "match_score": 0.82,
    "changes_made": (
        "Moved DeFi protocol experience to top of experience section. "
        "Added 'Solidity' and 'smart contracts' keywords to skills. "
        "Adjusted summary to highlight blockchain engineering depth."
    ),
}


class TestParseResponse(unittest.TestCase):
    def test_bare_json(self):
        raw = json.dumps(SAMPLE_RESPONSE)
        result = _parse_response(raw)
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
    @patch("src.cv_agent.anthropic.Anthropic")
    def test_tailor_returns_structured_data(self, MockAnthropic):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(SAMPLE_RESPONSE))]
        mock_client.messages.create.return_value = mock_response
        MockAnthropic.return_value = mock_client

        result = tailor_cv(
            job_title="DeFi Protocol Engineer",
            company="Uniswap Labs",
            description="We need a senior Solidity engineer to build AMM contracts...",
        )

        self.assertIn("tailored_cv", result)
        self.assertIn("match_score", result)
        self.assertIn("changes_made", result)
        self.assertGreaterEqual(result["match_score"], 0.0)
        self.assertLessEqual(result["match_score"], 1.0)

    @patch("src.cv_agent.anthropic.Anthropic")
    def test_score_clamped_to_range(self, MockAnthropic):
        """Model returns score > 1.0 — should be clamped."""
        bad_response = {**SAMPLE_RESPONSE, "match_score": 1.5}
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(bad_response))]
        mock_client.messages.create.return_value = mock_response
        MockAnthropic.return_value = mock_client

        result = tailor_cv("AI Engineer", "OpenAI", "Build LLM products")
        self.assertLessEqual(result["match_score"], 1.0)

    @patch("src.cv_agent.anthropic.Anthropic")
    def test_cv_is_nonempty(self, MockAnthropic):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(SAMPLE_RESPONSE))]
        mock_client.messages.create.return_value = mock_response
        MockAnthropic.return_value = mock_client

        result = tailor_cv("ML Engineer", "Cohere", "Train large language models...")
        self.assertTrue(len(result["tailored_cv"]) > 50)

    @patch("src.cv_agent.anthropic.Anthropic")
    def test_api_called_with_system_prompt(self, MockAnthropic):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(SAMPLE_RESPONSE))]
        mock_client.messages.create.return_value = mock_response
        MockAnthropic.return_value = mock_client

        tailor_cv("Quant Researcher", "Citadel", "Alpha generation, ML signals...")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn("system", call_kwargs)
        self.assertIn("Uzair Qidwai", call_kwargs["system"])


if __name__ == "__main__":
    unittest.main()
