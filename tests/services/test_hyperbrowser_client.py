from __future__ import annotations

import types
import os
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from app.services.hyperbrowser_client import HyperbrowserClient, HyperbrowserClientError


class _FakeFetchOutputJson:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class _FakeFetchOutputOptions:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class _FakeFetchNavigationOptions:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class _FakeFetchParams:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class _FakeResponse:
    def __init__(self, *, status: str, data: object, error: str | None = None) -> None:
        self.status = status
        self.data = data
        self.error = error


class _FakeWebClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.last_params: object | None = None

    def fetch(self, params: object) -> _FakeResponse:
        self.last_params = params
        return self._response


class _FakeHyperbrowserSDKClient:
    def __init__(self, *, api_key: str, response: _FakeResponse) -> None:
        self.api_key = api_key
        self.web = _FakeWebClient(response)


class HyperbrowserClientTests(unittest.TestCase):
    def _build_modules(
        self, response: _FakeResponse
    ) -> tuple[types.SimpleNamespace, types.SimpleNamespace, dict[str, object]]:
        holder: dict[str, object] = {}

        def factory(*, api_key: str) -> _FakeHyperbrowserSDKClient:
            client = _FakeHyperbrowserSDKClient(api_key=api_key, response=response)
            holder["client"] = client
            return client

        hyperbrowser_module = types.SimpleNamespace(Hyperbrowser=factory)
        models_module = types.SimpleNamespace(
            FetchParams=_FakeFetchParams,
            FetchOutputJson=_FakeFetchOutputJson,
            FetchOutputOptions=_FakeFetchOutputOptions,
            FetchNavigationOptions=_FakeFetchNavigationOptions,
        )
        holder["models"] = models_module
        return hyperbrowser_module, models_module, holder

    def test_download_returns_normalized_payload(self) -> None:
        response = _FakeResponse(
            status="completed",
            data=types.SimpleNamespace(
                metadata=types.SimpleNamespace(
                    title="기사 제목",
                    sourceURL="https://example.com/final",
                ),
                markdown="기사 본문입니다.\n\n두 번째 문장입니다.",
                html='''
                    <html>
                      <head><meta property="og:image" content="https://cdn.example.com/og.jpg"></head>
                      <body><img src="https://cdn.example.com/body.png"></body>
                    </html>
                ''',
                links=[
                    "https://example.com/read-more",
                    "https://cdn.example.com/from-links.webp",
                ],
                json_=types.SimpleNamespace(
                    title="구조화 제목",
                    article_text="구조화 본문입니다.",
                    image_urls=["https://cdn.example.com/from-json.jpg"],
                ),
            ),
        )
        hyperbrowser_module, models_module, holder = self._build_modules(response)

        with patch(
            "app.services.hyperbrowser_client._import_hyperbrowser",
            return_value=(hyperbrowser_module, models_module),
        ):
            result = HyperbrowserClient(
                api_key="secret",
                wait_until="networkidle",
                wait_for_ms=2000,
                timeout_ms=45000,
            ).download("https://example.com/news-story")

        self.assertEqual(result.title, "구조화 제목")
        self.assertEqual(result.content, "구조화 본문입니다.")
        self.assertEqual(result.final_url, "https://example.com/final")
        self.assertEqual(result.metadata["provider"], "hyperbrowser")
        self.assertIn("https://cdn.example.com/from-json.jpg", result.images)
        self.assertIn("https://cdn.example.com/og.jpg", result.images)
        self.assertIn("https://cdn.example.com/body.png", result.images)
        self.assertIn("https://cdn.example.com/from-links.webp", result.images)

        client = holder["client"]
        assert isinstance(client, _FakeHyperbrowserSDKClient)
        params = client.web.last_params
        assert isinstance(params, _FakeFetchParams)
        navigation = params.kwargs["navigation"]
        assert isinstance(navigation, _FakeFetchNavigationOptions)
        self.assertEqual(navigation.kwargs["wait_until"], "networkidle")
        self.assertEqual(navigation.kwargs["wait_for"], 2000)
        self.assertEqual(navigation.kwargs["timeout_ms"], 45000)

    def test_download_loads_fetch_prompt_from_prompt_dir(self) -> None:
        response = _FakeResponse(
            status="completed",
            data=types.SimpleNamespace(
                metadata=types.SimpleNamespace(title="기사 제목", sourceURL="https://example.com/final"),
                markdown="기사 본문입니다.",
                html="<html></html>",
                links=[],
                json_=types.SimpleNamespace(title="기사 제목", article_text="기사 본문입니다.", image_urls=[]),
            ),
        )
        hyperbrowser_module, models_module, holder = self._build_modules(response)

        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_dir = Path(temp_dir)
            (prompt_dir / "hyperbrowser_fetch_article.txt").write_text("CUSTOM FETCH PROMPT", encoding="utf-8")

            with patch.dict(os.environ, {"PROMPT_DIR": temp_dir}, clear=False):
                with patch(
                    "app.services.hyperbrowser_client._import_hyperbrowser",
                    return_value=(hyperbrowser_module, models_module),
                ):
                    _ = HyperbrowserClient(api_key="secret").download("https://example.com/news-story")

        client = holder["client"]
        assert isinstance(client, _FakeHyperbrowserSDKClient)
        params = client.web.last_params
        assert isinstance(params, _FakeFetchParams)
        params_kwargs = cast(dict[str, object], params.kwargs)
        outputs = params_kwargs["outputs"]
        assert isinstance(outputs, _FakeFetchOutputOptions)
        output_kwargs = cast(dict[str, object], outputs.kwargs)
        formats = output_kwargs["formats"]
        self.assertIsInstance(formats, list)
        assert isinstance(formats, list)
        fetch_output = formats[3]
        assert isinstance(fetch_output, _FakeFetchOutputJson)
        self.assertEqual(fetch_output.kwargs["prompt"], "CUSTOM FETCH PROMPT")

    def test_download_normalizes_relative_image_urls_against_final_url(self) -> None:
        response = _FakeResponse(
            status="completed",
            data=types.SimpleNamespace(
                metadata=types.SimpleNamespace(
                    title="기사 제목",
                    sourceURL="https://example.com/news/article",
                ),
                markdown="기사 본문입니다.",
                html='''
                    <html>
                      <head><meta property="og:image" content="/images/og.jpg"></head>
                      <body><img src="gallery/cover.png"></body>
                    </html>
                ''',
                links=["/assets/card.webp"],
                json_=types.SimpleNamespace(
                    title="기사 제목",
                    article_text="기사 본문입니다.",
                    image_urls=["thumb.jpg"],
                ),
            ),
        )
        hyperbrowser_module, models_module, _ = self._build_modules(response)

        with patch(
            "app.services.hyperbrowser_client._import_hyperbrowser",
            return_value=(hyperbrowser_module, models_module),
        ):
            result = HyperbrowserClient(api_key="secret").download("https://example.com/news/article")

        self.assertIn("https://example.com/news/thumb.jpg", result.images)
        self.assertIn("https://example.com/images/og.jpg", result.images)
        self.assertIn("https://example.com/news/gallery/cover.png", result.images)
        self.assertIn("https://example.com/assets/card.webp", result.images)

    def test_download_raises_when_status_is_not_completed(self) -> None:
        response = _FakeResponse(
            status="running",
            data=types.SimpleNamespace(
                metadata=types.SimpleNamespace(title="기사 제목", sourceURL="https://example.com/final"),
                markdown="기사 본문입니다.",
                html="<html></html>",
                links=[],
                json_=types.SimpleNamespace(title="기사 제목", article_text="기사 본문입니다.", image_urls=[]),
            ),
        )
        hyperbrowser_module, models_module, _ = self._build_modules(response)

        with patch(
            "app.services.hyperbrowser_client._import_hyperbrowser",
            return_value=(hyperbrowser_module, models_module),
        ):
            with self.assertRaises(HyperbrowserClientError):
                HyperbrowserClient(api_key="secret").download("https://example.com/news-story")

    def test_download_raises_when_content_missing(self) -> None:
        response = _FakeResponse(
            status="completed",
            data=types.SimpleNamespace(
                metadata=types.SimpleNamespace(title="기사 제목", sourceURL="https://example.com/final"),
                markdown="",
                html="<html></html>",
                links=[],
                json_=types.SimpleNamespace(title="기사 제목", article_text="", image_urls=[]),
            ),
        )
        hyperbrowser_module, models_module, _ = self._build_modules(response)

        with patch(
            "app.services.hyperbrowser_client._import_hyperbrowser",
            return_value=(hyperbrowser_module, models_module),
        ):
            with self.assertRaises(HyperbrowserClientError):
                HyperbrowserClient(api_key="secret").download("https://example.com/news-story")


if __name__ == "__main__":
    unittest.main()
