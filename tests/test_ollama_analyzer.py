from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from types import TracebackType
from typing import cast, final
from unittest.mock import patch

import httpx

from app.config import OllamaSettings
from app.ollama_analyzer import analyze_text


@final
class _FakeStreamResponse:
    _lines: list[str]

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self):
        for line in self._lines:
            yield line


@final
class _FakeStreamContext:
    _response: _FakeStreamResponse

    def __init__(self, response: _FakeStreamResponse) -> None:
        self._response = response

    def __enter__(self) -> _FakeStreamResponse:
        return self._response

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        del exc_type, exc, tb


def _response_lines_for(payload: Mapping[str, object]) -> list[str]:
    return [
        json.dumps({"message": {"content": json.dumps(payload, ensure_ascii=False)}, "done": False}, ensure_ascii=False),
        json.dumps({"done": True}, ensure_ascii=False),
    ]


class OllamaAnalyzerTests(unittest.TestCase):
    def test_returns_structured_payload_when_ollama_returns_valid_json(self) -> None:
        payload = {
            "overall_summary": {"verdict": "주의 필요", "reasons": ["근거 부족"]},
            "source_reliability": {"score": 72, "summary": "출처는 보통 수준입니다.", "risk": "medium"},
            "claim_consistency": {"score": 64, "summary": "주장 정합성은 일부 흔들립니다.", "risk": "medium"},
            "evidence_quality": {"score": 58, "summary": "근거 제시가 부족합니다.", "risk": "high"},
            "expression_risk": {"score": 81, "summary": "표현은 비교적 차분합니다.", "risk": "low"},
        }
        response_lines = _response_lines_for(payload)

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
        call_args = stream_mock.call_args
        assert call_args is not None
        request_kwargs = cast(dict[str, object], call_args.kwargs)
        json_payload = request_kwargs["json"]
        self.assertIsInstance(json_payload, dict)
        assert isinstance(json_payload, dict)
        self.assertEqual(json_payload["stream"], True)

    def test_falls_back_to_secondary_host_when_primary_is_unavailable(self) -> None:
        payload = {
            "overall_summary": {"verdict": "주의 필요", "reasons": ["근거 부족"]},
            "source_reliability": {"score": 72, "summary": "출처는 보통 수준입니다.", "risk": "medium"},
            "claim_consistency": {"score": 64, "summary": "주장 정합성은 일부 흔들립니다.", "risk": "medium"},
            "evidence_quality": {"score": 58, "summary": "근거 제시가 부족합니다.", "risk": "high"},
            "expression_risk": {"score": 81, "summary": "표현은 비교적 차분합니다.", "risk": "low"},
        }
        attempted_urls: list[str] = []

        def fake_stream(method: str, url: str, **kwargs: object) -> _FakeStreamContext:
            del method, kwargs
            attempted_urls.append(url)
            if url.startswith("http://desktop:11434"):
                raise httpx.ConnectError("down")
            return _FakeStreamContext(_FakeStreamResponse(_response_lines_for(payload)))

        with patch("app.ollama_analyzer.httpx.stream", side_effect=fake_stream):
            result = analyze_text(
                title="기사 제목",
                url="https://example.com/article",
                text="기사 본문",
                settings=OllamaSettings(
                    host="http://desktop:11434",
                    fallback_hosts=("http://server:11434",),
                ),
            )

        criterion = result.get("source_reliability")
        self.assertIsInstance(criterion, dict)
        assert isinstance(criterion, dict)
        self.assertEqual(criterion, payload["source_reliability"])
        self.assertEqual(
            attempted_urls,
            [
                "http://desktop:11434/api/chat",
                "http://server:11434/api/chat",
            ],
        )

    def test_falls_back_using_matching_fallback_model_for_each_host(self) -> None:
        payload = {
            "overall_summary": {"verdict": "주의 필요", "reasons": ["근거 부족"]},
            "source_reliability": {"score": 72, "summary": "출처는 보통 수준입니다.", "risk": "medium"},
            "claim_consistency": {"score": 64, "summary": "주장 정합성은 일부 흔들립니다.", "risk": "medium"},
            "evidence_quality": {"score": 58, "summary": "근거 제시가 부족합니다.", "risk": "high"},
            "expression_risk": {"score": 81, "summary": "표현은 비교적 차분합니다.", "risk": "low"},
        }

        attempted_host_models: list[tuple[str, str]] = []

        def fake_stream(method: str, url: str, **kwargs: object) -> _FakeStreamContext:
            del method
            request_json = cast(dict[str, object], kwargs["json"])
            model = cast(str, request_json["model"])
            if url.startswith("http://primary:11434"):
                attempted_host_models.append(("http://primary:11434", model))
                raise httpx.ConnectError("primary down")
            if url.startswith("http://backup:11434"):
                attempted_host_models.append(("http://backup:11434", model))
                raise httpx.ConnectError("backup down")
            if url.startswith("http://fallback:11434"):
                attempted_host_models.append(("http://fallback:11434", model))
                return _FakeStreamContext(_FakeStreamResponse(_response_lines_for(payload)))
            self.fail(f"Unexpected host {url}")

        with patch("app.ollama_analyzer.httpx.stream", side_effect=fake_stream):
            _ = analyze_text(
                title="기사 제목",
                url="https://example.com/article",
                text="기사 본문",
                settings=OllamaSettings(
                    host="http://primary:11434",
                    fallback_hosts=("http://backup:11434", "http://fallback:11434"),
                    model="primary-model",
                    fallback_models=("backup-model",),
                ),
            )

        self.assertEqual(
            attempted_host_models,
            [
                ("http://primary:11434", "primary-model"),
                ("http://backup:11434", "backup-model"),
                ("http://fallback:11434", "primary-model"),
            ],
        )

    def test_calls_failover_callback_with_host_and_model_pair(self) -> None:
        payload = {
            "overall_summary": {"verdict": "주의 필요", "reasons": ["근거 부족"]},
            "source_reliability": {"score": 72, "summary": "출처는 보통 수준입니다.", "risk": "medium"},
            "claim_consistency": {"score": 64, "summary": "주장 정합성은 일부 흔들립니다.", "risk": "medium"},
            "evidence_quality": {"score": 58, "summary": "근거 제시가 부족합니다.", "risk": "high"},
            "expression_risk": {"score": 81, "summary": "표현은 비교적 차분합니다.", "risk": "low"},
        }
        observed: list[tuple[str, str, str]] = []

        def fake_stream(method: str, url: str, **kwargs: object) -> _FakeStreamContext:
            del method, kwargs
            if url.startswith("http://primary:11434"):
                raise httpx.ConnectError("primary down")
            return _FakeStreamContext(_FakeStreamResponse(_response_lines_for(payload)))

        def on_failover(failed_host: str, next_host: str, next_model: str) -> None:
            observed.append((failed_host, next_host, next_model))

        with patch("app.ollama_analyzer.httpx.stream", side_effect=fake_stream):
            result = analyze_text(
                title="기사 제목",
                url="https://example.com/article",
                text="기사 본문",
                settings=OllamaSettings(
                    host="http://primary:11434",
                    fallback_hosts=("http://backup:11434",),
                    model="qwen3.5",
                    fallback_models=("qwen3.5-fallback",),
                ),
                on_failover=on_failover,
            )

        criterion = result.get("source_reliability")
        self.assertIsInstance(criterion, dict)
        assert isinstance(criterion, dict)
        self.assertEqual(criterion, payload["source_reliability"])
        self.assertEqual(observed, [("http://primary:11434", "http://backup:11434", "qwen3.5-fallback")])

    def test_uses_fallback_model_for_fallback_host(self) -> None:
        payload = {
            "overall_summary": {"verdict": "주의 필요", "reasons": ["근거 부족"]},
            "source_reliability": {"score": 72, "summary": "출처는 보통 수준입니다.", "risk": "medium"},
            "claim_consistency": {"score": 64, "summary": "주장 정합성은 일부 흔들립니다.", "risk": "medium"},
            "evidence_quality": {"score": 58, "summary": "근거 제시가 부족합니다.", "risk": "high"},
            "expression_risk": {"score": 81, "summary": "표현은 비교적 차분합니다.", "risk": "low"},
        }
        attempted_models: list[str] = []

        def fake_stream(method: str, url: str, **kwargs: object) -> _FakeStreamContext:
            del method
            request_json = cast(dict[str, object], kwargs["json"])
            model = request_json["model"]
            assert isinstance(model, str)
            attempted_models.append(model)
            if url.startswith("http://primary:11434"):
                raise httpx.ConnectError("primary down")
            return _FakeStreamContext(_FakeStreamResponse(_response_lines_for(payload)))

        with patch("app.ollama_analyzer.httpx.stream", side_effect=fake_stream):
            _ = analyze_text(
                title="기사 제목",
                url="https://example.com/article",
                text="기사 본문",
                settings=OllamaSettings(
                    host="http://primary:11434",
                    fallback_hosts=("http://backup:11434",),
                    model="primary-model",
                    fallback_models=("backup-model",),
                ),
            )

        self.assertEqual(attempted_models, ["primary-model", "backup-model"])

    def test_returns_fallback_when_ollama_request_fails(self) -> None:
        attempted_urls: list[str] = []

        def fake_stream(method: str, url: str, **kwargs: object) -> _FakeStreamContext:
            del method, kwargs
            attempted_urls.append(url)
            raise httpx.ConnectError("down")

        with patch("app.ollama_analyzer.httpx.stream", side_effect=fake_stream):
            result = analyze_text(
                title="기사 제목",
                url="https://example.com/article",
                text="기사 본문",
                settings=OllamaSettings(
                    host="http://desktop:11434",
                    fallback_hosts=("http://server:11434",),
                ),
            )

        criterion = result.get("source_reliability")
        self.assertIsInstance(criterion, dict)
        assert isinstance(criterion, dict)
        self.assertEqual(
            criterion["summary"],
            "로컬 모델을 사용할 수 없어 분석을 건너뜁니다.",
        )
        self.assertEqual(
            attempted_urls,
            [
                "http://desktop:11434/api/chat",
                "http://server:11434/api/chat",
            ],
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
