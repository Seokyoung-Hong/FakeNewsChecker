from __future__ import annotations

import unittest
from typing import cast

from app.services.crawler_service import (
    DeterministicCrawlerService,
    _HyperbrowserClientProtocol,
    HyperbrowserCrawlerError,
    HyperbrowserCrawlerService,
)
from app.services.hyperbrowser_client import HyperbrowserClientError, HyperbrowserDownloadResult
from app.schemas import URLSubmission


class _FakeHyperbrowserClient:
    def __init__(
        self,
        *,
        download_result: HyperbrowserDownloadResult | None = None,
        download_error: Exception | None = None,
    ) -> None:
        self._download_result: HyperbrowserDownloadResult | None = download_result
        self._download_error: Exception | None = download_error

    def download(self, url: str) -> HyperbrowserDownloadResult:
        del url
        if self._download_error is not None:
            raise self._download_error
        if self._download_result is None:
            raise RuntimeError("download_result must be provided when no download_error exists")
        return self._download_result


class DeterministicCrawlerServiceTests(unittest.TestCase):
    def test_collect_returns_stable_analysis_identifier_for_normalized_urls(self) -> None:
        service = DeterministicCrawlerService()

        first = service.collect(URLSubmission.model_validate({"url": "https://Example.com/news-story/"}))
        second = service.collect(URLSubmission.model_validate({"url": "https://example.com/news-story"}))

        self.assertEqual(first.analysis_id, second.analysis_id)
        self.assertTrue(first.title)
        self.assertTrue(first.content)
        self.assertIsInstance(first.images, list)
        self.assertIsInstance(first.metadata, dict)


class HyperbrowserCrawlerServiceTests(unittest.TestCase):
    def test_collect_maps_download_result_into_crawler_output(self) -> None:
        client = _FakeHyperbrowserClient(
            download_result=HyperbrowserDownloadResult(
                requested_url="https://example.com/news-story",
                final_url="https://m.example.com/news-story?ref=home",
                title="기사 제목",
                content="기사 본문입니다.",
                images=[
                    "https://cdn.example.com/article-main.jpg",
                    "https://example.com/images/card-1.png",
                ],
                metadata={
                    "selected_root_selector": "article",
                    "visible_text_length": 123,
                },
            )
        )
        service = HyperbrowserCrawlerService(cast(_HyperbrowserClientProtocol, client))

        result = service.collect(
            URLSubmission.model_validate({"url": "https://example.com/news-story"})
        )

        self.assertEqual(result.title, "기사 제목")
        self.assertEqual(result.content, "기사 본문입니다.")
        self.assertIn("https://cdn.example.com/article-main.jpg", result.images)
        self.assertIn("https://example.com/images/card-1.png", result.images)
        self.assertEqual(result.metadata["provider"], "hyperbrowser")
        self.assertEqual(result.metadata["selected_root_selector"], "article")
        self.assertEqual(result.metadata["host"], "m.example.com")
        self.assertEqual(result.metadata["path"], "/news-story")
        self.assertEqual(result.metadata["query"], "ref=home")
        self.assertEqual(result.metadata["final_url"], "https://m.example.com/news-story?ref=home")

    def test_collect_uses_fallback_title_when_download_title_missing(self) -> None:
        client = _FakeHyperbrowserClient(
            download_result=HyperbrowserDownloadResult(
                requested_url="https://example.com/news-story",
                final_url="https://example.com/news-story",
                title="",
                content="스크랩 본문입니다.",
                images=[],
                metadata={},
            )
        )
        service = HyperbrowserCrawlerService(cast(_HyperbrowserClientProtocol, client))

        result = service.collect(
            URLSubmission.model_validate({"url": "https://example.com/news-story"})
        )

        self.assertEqual(result.title, "example.com · news-story")

    def test_collect_raises_when_no_content_is_available(self) -> None:
        client = _FakeHyperbrowserClient(
            download_result=HyperbrowserDownloadResult(
                requested_url="https://example.com/news-story",
                final_url="https://example.com/news-story",
                title="기사 제목",
                content="",
                images=[],
                metadata={},
            )
        )
        service = HyperbrowserCrawlerService(cast(_HyperbrowserClientProtocol, client))

        with self.assertRaises(HyperbrowserCrawlerError):
            service.collect(URLSubmission.model_validate({"url": "https://example.com/news-story"}))

    def test_collect_raises_when_download_fails(self) -> None:
        client = _FakeHyperbrowserClient(
            download_error=HyperbrowserClientError("download failed"),
        )
        service = HyperbrowserCrawlerService(cast(_HyperbrowserClientProtocol, client))

        with self.assertRaises(HyperbrowserCrawlerError):
            service.collect(URLSubmission.model_validate({"url": "https://example.com/news-story"}))


if __name__ == "__main__":
    unittest.main()
