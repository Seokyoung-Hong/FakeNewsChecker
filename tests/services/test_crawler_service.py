from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

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
        self.call_count = 0

    def download(self, url: str) -> HyperbrowserDownloadResult:
        del url
        self.call_count += 1
        if self._download_error is not None:
            raise self._download_error
        if self._download_result is None:
            raise RuntimeError("download_result must be provided when no download_error exists")
        return self._download_result


class DeterministicCrawlerServiceTests(unittest.TestCase):
    def test_collect_returns_stable_analysis_identifier_for_safe_canonical_url_variants(self) -> None:
        service = DeterministicCrawlerService()

        first = service.collect(URLSubmission.model_validate({"url": " https://Example.com:443/news-story#top "}))
        second = service.collect(URLSubmission.model_validate({"url": "https://example.com/news-story"}))

        self.assertEqual(first.analysis_id, second.analysis_id)
        self.assertTrue(first.title)
        self.assertTrue(first.content)
        self.assertIsInstance(first.images, list)
        self.assertIsInstance(first.metadata, dict)

    def test_collect_preserves_path_case_in_analysis_identifier(self) -> None:
        service = DeterministicCrawlerService()

        upper = service.collect(URLSubmission.model_validate({"url": "https://example.com/News-Story"}))
        lower = service.collect(URLSubmission.model_validate({"url": "https://example.com/news-story"}))

        self.assertNotEqual(upper.analysis_id, lower.analysis_id)

    def test_collect_preserves_query_parameter_order_in_analysis_identifier(self) -> None:
        service = DeterministicCrawlerService()

        first = service.collect(URLSubmission.model_validate({"url": "https://example.com/news?a=1&b=2"}))
        second = service.collect(URLSubmission.model_validate({"url": "https://example.com/news?b=2&a=1"}))

        self.assertNotEqual(first.analysis_id, second.analysis_id)

    def test_collect_treats_non_root_trailing_slash_as_distinct(self) -> None:
        service = DeterministicCrawlerService()

        first = service.collect(URLSubmission.model_validate({"url": "https://example.com/news-story/"}))
        second = service.collect(URLSubmission.model_validate({"url": "https://example.com/news-story"}))

        self.assertNotEqual(first.analysis_id, second.analysis_id)

    def test_collect_treats_empty_root_path_and_slash_as_equivalent(self) -> None:
        service = DeterministicCrawlerService()

        first = service.collect(URLSubmission.model_validate({"url": "https://example.com"}))
        second = service.collect(URLSubmission.model_validate({"url": "https://example.com/"}))

        self.assertEqual(first.analysis_id, second.analysis_id)


class HyperbrowserCrawlerServiceTests(unittest.TestCase):
    _tmp_dir: tempfile.TemporaryDirectory[str] | None = None
    _env_patcher: Any = None

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        cache_root = str(Path(self._tmp_dir.name, "artifact-cache"))
        self._env_patcher = patch.dict("os.environ", {"ANALYSIS_ARTIFACT_ROOT": cache_root}, clear=False)
        self._env_patcher.start()

    def tearDown(self) -> None:
        assert self._env_patcher is not None
        assert self._tmp_dir is not None
        self._env_patcher.stop()
        self._tmp_dir.cleanup()

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

    def test_collect_reuses_cached_result_within_ttl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = {"ANALYSIS_ARTIFACT_ROOT": str(Path(tmp_dir, "artifact-cache"))}
            client = _FakeHyperbrowserClient(
                download_result=HyperbrowserDownloadResult(
                    requested_url="https://example.com/news-story",
                    final_url="https://example.com/news-story",
                    title="기사 제목",
                    content="기사 본문입니다.",
                    images=["https://cdn.example.com/article-main.jpg"],
                    metadata={},
                )
            )
            service = HyperbrowserCrawlerService(cast(_HyperbrowserClientProtocol, client))

            with patch.dict("os.environ", env, clear=False):
                first = service.collect(
                    URLSubmission.model_validate({"url": "https://example.com/news-story"})
                )
                second = service.collect(
                    URLSubmission.model_validate({"url": "https://example.com/news-story"})
                )

        self.assertEqual(first.content, second.content)
        self.assertEqual(client.call_count, 1)

    def test_collect_uses_cache_across_service_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = {"ANALYSIS_ARTIFACT_ROOT": str(Path(tmp_dir, "artifact-cache"))}
            client = _FakeHyperbrowserClient(
                download_result=HyperbrowserDownloadResult(
                    requested_url="https://example.com/news-story",
                    final_url="https://example.com/news-story",
                    title="기사 제목",
                    content="기사 본문입니다.",
                    images=["https://cdn.example.com/article-main.jpg"],
                    metadata={},
                )
            )
            first_service = HyperbrowserCrawlerService(cast(_HyperbrowserClientProtocol, client))

            with patch.dict("os.environ", env, clear=False):
                _ = first_service.collect(URLSubmission.model_validate({"url": "https://example.com/news-story"}))

                failing_client = _FakeHyperbrowserClient(
                    download_error=HyperbrowserClientError("should not be called"),
                )
                second_service = HyperbrowserCrawlerService(cast(_HyperbrowserClientProtocol, failing_client))
                cached = second_service.collect(
                    URLSubmission.model_validate({"url": "https://example.com/news-story"})
                )

        self.assertEqual(cached.title, "기사 제목")
        self.assertEqual(failing_client.call_count, 0)


if __name__ == "__main__":
    unittest.main()
