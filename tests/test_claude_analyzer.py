from __future__ import annotations

import unittest
from typing import cast
from unittest.mock import patch

from app.claude_analyzer import analyze_text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.last_call: dict[str, object] | None = None

    def generate_content(self, **kwargs: object) -> _FakeResponse:
        self.last_call = kwargs
        return _FakeResponse(self._response_text)


class _FakeClient:
    def __init__(self, response_text: str) -> None:
        self.models = _FakeModels(response_text)


class _FakeGenaiModule:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.last_client: _FakeClient | None = None

    def Client(self, api_key: str) -> _FakeClient:
        del api_key
        client = _FakeClient(self._response_text)
        self.last_client = client
        return client


class ClaudeAnalyzerTests(unittest.TestCase):
    def test_returns_fallback_shape_without_api_key(self) -> None:
        with patch("app.claude_analyzer.GEMINI_API_KEY", ""), patch(
            "app.claude_analyzer._import_genai", return_value=None
        ):
            result = analyze_text("제목", "https://example.com", "본문")

        self.assertIn("overall_summary", result)
        self.assertIn("claim_consistency", result)
        self.assertIn("evidence_quality", result)
        self.assertNotIn("multimodal_risk", result)

    def test_logs_metadata_and_uses_current_contract(self) -> None:
        response_text = """{
          \"overall_summary\": {\"verdict\": \"주의 필요\", \"reasons\": [\"근거 부족\"]},
          \"source_reliability\": {\"score\": 80, \"summary\": \"출처 보통\"},
          \"claim_consistency\": {\"score\": 65, \"summary\": \"주장 일부 흔들림\"},
          \"evidence_quality\": {\"score\": 55, \"summary\": \"근거가 부족함\"},
          \"expression_risk\": {\"score\": 70, \"summary\": \"표현 위험 보통\"}
        }"""
        fake_module = _FakeGenaiModule(response_text)

        with patch("app.claude_analyzer.GEMINI_API_KEY", "secret"), patch(
            "app.claude_analyzer._import_genai", return_value=fake_module
        ), self.assertLogs("app.claude_analyzer", level="DEBUG") as logs:
            result = analyze_text("제목", "https://example.com", "본문")

        claim = cast(dict[str, object], result["claim_consistency"])
        self.assertEqual(claim["score"], 65)
        self.assertTrue(any("Gemini response received" in message for message in logs.output))
        assert fake_module.last_client is not None
        last_call = fake_module.last_client.models.last_call
        assert last_call is not None
        prompt = last_call["contents"]
        self.assertIn("가짜뉴스 판별", str(prompt))

    def test_bridges_legacy_contract(self) -> None:
        response_text = """```json
        {
          \"overall_summary\": {\"verdict\": \"의심 필요\", \"reasons\": [\"검증 부족\"]},
          \"source_reliability\": {\"score\": 81, \"summary\": \"출처 양호\"},
          \"context_consistency\": {\"score\": 50, \"summary\": \"맥락 흔들림\"},
          \"claim_clarity\": {\"score\": 70, \"summary\": \"주장은 비교적 명확\"},
          \"evidence_match\": {\"score\": 40, \"summary\": \"근거 약함\"},
          \"cross_verification\": {\"score\": 60, \"summary\": \"교차검증 제한\"},
          \"expression_risk\": {\"score\": 55, \"summary\": \"과장 표현 존재\"}
        }
        ```"""
        fake_module = _FakeGenaiModule(response_text)

        with patch("app.claude_analyzer.GEMINI_API_KEY", "secret"), patch(
            "app.claude_analyzer._import_genai", return_value=fake_module
        ):
            result = analyze_text("제목", "https://example.com", "본문")

        self.assertIn("claim_consistency", result)
        self.assertIn("evidence_quality", result)
        claim = cast(dict[str, object], result["claim_consistency"])
        evidence = cast(dict[str, object], result["evidence_quality"])
        self.assertEqual(claim["score"], 60)
        self.assertEqual(evidence["score"], 50)

    def test_does_not_fill_missing_criterion_with_api_key_message(self) -> None:
        response_text = """{
          \"overall_summary\": {\"verdict\": \"주의 필요\", \"reasons\": [\"근거 부족\"]},
          \"source_reliability\": {\"score\": 80, \"summary\": \"출처 보통\"},
          \"claim_consistency\": {\"score\": 65, \"summary\": \"주장 일부 흔들림\"},
          \"expression_risk\": {\"score\": 70, \"summary\": \"표현 위험 보통\"}
        }"""
        fake_module = _FakeGenaiModule(response_text)

        with patch("app.claude_analyzer.GEMINI_API_KEY", "secret"), patch(
            "app.claude_analyzer._import_genai", return_value=fake_module
        ):
            result = analyze_text("제목", "https://example.com", "본문")

        self.assertNotIn("evidence_quality", result)


if __name__ == "__main__":
    unittest.main()
