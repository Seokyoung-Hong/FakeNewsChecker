from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import TracebackType
from typing import cast, final
from unittest.mock import patch

from app.config import OllamaSettings
from app.ollama_multimodal_analyzer import analyze_multimodal
from app.schemas import CrawlerOutput, URLSubmission


@final
class _FakeStreamResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self):
        for line in self._lines:
            yield line


@final
class _FakeStreamContext:
    def __init__(self, response: _FakeStreamResponse) -> None:
        self._response = response

    def __enter__(self) -> _FakeStreamResponse:
        return self._response

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        del exc_type, exc, tb


class OllamaMultimodalAnalyzerTests(unittest.TestCase):
    def test_sends_base64_images_in_user_message(self) -> None:
        payload = {"score": 68, "summary": "이미지에 보이는 문구와 본문이 일부 어긋납니다.", "risk": "medium", "signals": ["문구 불일치"]}
        lines = [
            json.dumps({"message": {"content": json.dumps(payload, ensure_ascii=False)}, "done": False}, ensure_ascii=False),
            json.dumps({"done": True}, ensure_ascii=False),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "image.png"
            image_bytes = b"png-bytes"
            image_path.write_bytes(image_bytes)
            crawler_output = CrawlerOutput(
                analysis_id="analysis-1",
                url=URLSubmission.model_validate({"url": "https://example.com/article"}).url,
                title="기사 제목",
                content="기사 본문",
                images=[],
                metadata={},
            )

            with patch(
                "app.ollama_multimodal_analyzer.httpx.stream",
                return_value=_FakeStreamContext(_FakeStreamResponse(lines)),
            ) as stream_mock, patch("app.ollama_multimodal_analyzer._analysis_date", return_value="2026-05-14"):
                result = analyze_multimodal(
                    crawler_output,
                    {"score": 40, "summary": "Hive 분석", "risk": "medium"},
                    [str(image_path)],
                    OllamaSettings(),
                )

        self.assertEqual(result["score"], 68)
        call_args = stream_mock.call_args
        assert call_args is not None
        request_kwargs = cast(dict[str, object], call_args.kwargs)
        json_payload = request_kwargs["json"]
        assert isinstance(json_payload, dict)
        messages = json_payload["messages"]
        assert isinstance(messages, list)
        user_message = messages[1]
        assert isinstance(user_message, dict)
        self.assertEqual(user_message["images"], [base64.b64encode(image_bytes).decode("utf-8")])
        self.assertIn("기준일(분석 기준일): 2026-05-14", str(user_message["content"]))
        self.assertIn("지식 컷오프", str(user_message["content"]))
