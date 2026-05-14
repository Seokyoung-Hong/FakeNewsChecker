from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.gemini_multimodal_analyzer import analyze_multimodal
from app.schemas import CrawlerOutput, URLSubmission


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


class _FakePart:
    @staticmethod
    def from_text(text: str) -> dict[str, object]:
        return {"kind": "text", "text": text}

    @staticmethod
    def from_bytes(*, data: bytes, mime_type: str) -> dict[str, object]:
        return {"kind": "bytes", "size": len(data), "mime_type": mime_type}


class _FakeTypes:
    Part = _FakePart


class _FakeClient:
    def __init__(self, response_text: str) -> None:
        self.models = _FakeModels(response_text)


class _FakeGenaiModule:
    types = _FakeTypes

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.last_client: _FakeClient | None = None

    def Client(self, api_key: str) -> _FakeClient:
        del api_key
        client = _FakeClient(self._response_text)
        self.last_client = client
        return client


class GeminiMultimodalAnalyzerTests(unittest.TestCase):
    def test_sends_prompt_and_image_parts(self) -> None:
        response_text = '{"score": 72, "summary": "이미지와 본문이 대체로 일치합니다.", "risk": "low", "signals": ["장면 일치"]}'
        fake_module = _FakeGenaiModule(response_text)

        with TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "image.jpg"
            image_path.write_bytes(b"image-bytes")
            payload = CrawlerOutput(
                analysis_id="analysis-1",
                url=URLSubmission.model_validate({"url": "https://example.com/article"}).url,
                title="기사 제목",
                content="기사 본문",
                images=[],
                metadata={},
            )

            with patch("app.gemini_multimodal_analyzer.GEMINI_API_KEY", "secret"), patch(
                "app.gemini_multimodal_analyzer._import_genai", return_value=fake_module
            ), patch("app.gemini_multimodal_analyzer._analysis_date", return_value="2026-05-14"):
                result = analyze_multimodal(
                    payload,
                    {"score": 40, "summary": "Hive 분석", "risk": "medium"},
                    [str(image_path)],
                )

        self.assertEqual(result["score"], 72)
        assert fake_module.last_client is not None
        last_call = fake_module.last_client.models.last_call
        assert last_call is not None
        contents = last_call["contents"]
        assert isinstance(contents, list)
        self.assertEqual(last_call["model"], "gemini-2.5-flash")
        self.assertEqual(contents[0]["kind"], "text")
        self.assertEqual(contents[1]["kind"], "bytes")
        self.assertIn("기준일(분석 기준일): 2026-05-14", contents[0]["text"])
        self.assertIn("지식 컷오프", contents[0]["text"])
