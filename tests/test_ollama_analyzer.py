from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import httpx

from app.config import OllamaSettings
from app.ollama_analyzer import analyze_text


class _FakeStreamResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamContext:
    def __init__(self, response: _FakeStreamResponse) -> None:
        self._response = response

    def __enter__(self) -> _FakeStreamResponse:
        return self._response

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb


class OllamaAnalyzerTests(unittest.TestCase):
    def test_returns_structured_payload_when_ollama_returns_valid_json(self) -> None:
        payload = {
            "overall_summary": {"verdict": "주의 필요", "reasons": ["근거 부족"]},
            "source_reliability": {"score": 72, "summary": "출처는 보통 수준입니다.", "risk": "medium"},
            "claim_consistency": {"score": 64, "summary": "주장 정합성은 일부 흔들립니다.", "risk": "medium"},
            "evidence_quality": {"score": 58, "summary": "근거 제시가 부족합니다.", "risk": "high"},
            "expression_risk": {"score": 81, "summary": "표현은 비교적 차분합니다.", "risk": "low"},
        }
        response_lines = [
            json.dumps({"message": {"content": json.dumps(payload, ensure_ascii=False)}, "done": False}, ensure_ascii=False),
            json.dumps({"done": True}, ensure_ascii=False),
        ]

        with patch(
            "app.ollama_analyzer.httpx.stream",
            return_value=_FakeStreamContext(_FakeStreamResponse(response_lines)),
        ) as stream_mock:
            result = analyze_text(
                title="기사 제목",
                url="https://example.com/article",
                text="기사 본문",
                settings=OllamaSettings(),
            )

        criterion = result.get("source_reliability")
        self.assertIsInstance(criterion, dict)
        assert isinstance(criterion, dict)
        self.assertEqual(criterion, payload["source_reliability"])
        self.assertTrue(stream_mock.called)
        _, kwargs = stream_mock.call_args
        self.assertEqual(kwargs["json"]["stream"], True)

    def test_returns_fallback_when_ollama_request_fails(self) -> None:
        with patch("app.ollama_analyzer.httpx.stream", side_effect=httpx.ConnectError("down")):
            result = analyze_text(
                title="기사 제목",
                url="https://example.com/article",
                text="기사 본문",
                settings=OllamaSettings(),
            )

        criterion = result.get("source_reliability")
        self.assertIsInstance(criterion, dict)
        assert isinstance(criterion, dict)
        self.assertEqual(
            criterion["summary"],
            "로컬 모델을 사용할 수 없어 분석을 건너뜁니다.",
        )

    def test_returns_fallback_when_stream_has_no_content(self) -> None:
        with patch(
            "app.ollama_analyzer.httpx.stream",
            return_value=_FakeStreamContext(_FakeStreamResponse([json.dumps({"done": True})])),
        ):
            result = analyze_text(
                title="기사 제목",
                url="https://example.com/article",
                text="기사 본문",
                settings=OllamaSettings(),
            )

        criterion = result.get("source_reliability")
        self.assertIsInstance(criterion, dict)
        assert isinstance(criterion, dict)
        self.assertEqual(criterion["summary"], "로컬 모델을 사용할 수 없어 분석을 건너뜁니다.")
