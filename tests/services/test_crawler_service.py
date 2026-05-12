from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from app.services.local_browser_client import _assess_extraction_quality
from app.services.local_browser_client import _build_navigation_prompt
from app.services.local_browser_client import _NavigationCandidate
from app.services.local_browser_client import _NavigationActionPayload
from app.services.local_browser_client import _PageSnapshotPayload
from app.services.local_browser_client import _prefer_snapshot

from app.services.crawler_service import (
    DeterministicCrawlerService,
    _HyperbrowserClientProtocol,
    HyperbrowserCrawlerError,
    HyperbrowserCrawlerService,
    LocalBrowserCrawlerError,
    LocalBrowserCrawlerService,
)
from app.services.hyperbrowser_client import HyperbrowserClientError, HyperbrowserDownloadResult
from app.services.local_browser_client import LocalBrowserClientError, LocalBrowserDownloadResult
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


class _FakeLocalBrowserClient:
    def __init__(
        self,
        *,
        download_result: LocalBrowserDownloadResult | None = None,
        download_error: Exception | None = None,
    ) -> None:
        self._download_result = download_result
        self._download_error = download_error
        self.call_count = 0

    def download(self, url: str) -> LocalBrowserDownloadResult:
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

    def test_navigation_prompt_loads_from_prompt_dir(self) -> None:
        snapshot = _PageSnapshotPayload(
            title="기사 제목",
            final_url="https://example.com/article",
            article_text="본문 미리보기입니다.",
        )
        candidates = [
            _NavigationCandidate(
                index=1,
                text="기사 링크",
                href="https://example.com/article/1",
                score_hint=42,
            )
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_dir = Path(temp_dir)
            (prompt_dir / "local_browser_navigation.txt").write_text(
                "URL=$current_url\nTITLE=$current_title\nEXCERPT=$excerpt\nCANDIDATES=$candidate_lines",
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"PROMPT_DIR": temp_dir}, clear=False):
                prompt = _build_navigation_prompt(snapshot=snapshot, candidates=candidates)

        self.assertEqual(
            prompt,
            "URL=https://example.com/article\n"
            "TITLE=기사 제목\n"
            "EXCERPT=본문 미리보기입니다.\n"
            "CANDIDATES=- index=1 score_hint=42 text=기사 링크 href=https://example.com/article/1",
        )

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


class LocalBrowserCrawlerServiceTests(unittest.TestCase):
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
        client = _FakeLocalBrowserClient(
            download_result=LocalBrowserDownloadResult(
                requested_url="https://example.com/news-story",
                final_url="https://m.example.com/news-story?ref=local",
                title="로컬 기사 제목",
                content="로컬 기사 본문입니다.",
                images=["https://cdn.example.com/local-main.jpg"],
                metadata={"selected_root_selector": "article", "browser_backend": "playwright"},
            )
        )
        service = LocalBrowserCrawlerService(client)

        result = service.collect(URLSubmission.model_validate({"url": "https://example.com/news-story"}))

        self.assertEqual(result.title, "로컬 기사 제목")
        self.assertEqual(result.content, "로컬 기사 본문입니다.")
        self.assertEqual(result.metadata["provider"], "playwright-local")
        self.assertEqual(result.metadata["host"], "m.example.com")
        self.assertEqual(result.metadata["query"], "ref=local")
        self.assertEqual(result.metadata["selected_root_selector"], "article")

    def test_collect_raises_when_download_fails(self) -> None:
        client = _FakeLocalBrowserClient(
            download_error=LocalBrowserClientError("browser failed"),
        )
        service = LocalBrowserCrawlerService(client)

        with self.assertRaises(LocalBrowserCrawlerError):
            service.collect(URLSubmission.model_validate({"url": "https://example.com/news-story"}))

    def test_collect_rejects_private_network_targets_before_browser_fetch(self) -> None:
        client = _FakeLocalBrowserClient(
            download_result=LocalBrowserDownloadResult(
                requested_url="http://127.0.0.1/article",
                final_url="http://127.0.0.1/article",
                title="ignored",
                content="ignored",
            )
        )
        service = LocalBrowserCrawlerService(client)

        with self.assertRaises(LocalBrowserCrawlerError):
            service.collect(URLSubmission.model_validate({"url": "http://127.0.0.1/article"}))

        self.assertEqual(client.call_count, 0)


class LocalBrowserClientHeuristicTests(unittest.TestCase):
    def test_assess_extraction_quality_flags_landing_page_content_as_weak(self) -> None:
        snapshot = _PageSnapshotPayload(
            title="BBC News - Breaking news",
            final_url="https://www.bbc.com/news",
            article_text="ADVERTISEMENT\nLIVE\nTop stories\nBreaking news from around the world",
            selected_root_selector="body",
            candidate_targets=[
                _NavigationCandidate(index=index, text=f"Headline {index}", href=f"https://www.bbc.com/news/article-{index}", score_hint=20)
                for index in range(10)
            ],
            paragraph_count=1,
        )

        quality = _assess_extraction_quality(snapshot)

        self.assertFalse(quality.is_sufficient)
        self.assertLess(quality.score, 55)

    def test_assess_extraction_quality_accepts_article_like_content(self) -> None:
        snapshot = _PageSnapshotPayload(
            title="기사 제목",
            final_url="https://example.com/news-story",
            article_text="\n".join(["이 문단은 충분히 긴 기사 본문입니다. " * 12 for _ in range(4)]),
            selected_root_selector="article",
            paragraph_count=4,
        )

        quality = _assess_extraction_quality(snapshot)

        self.assertTrue(quality.is_sufficient)
        self.assertGreaterEqual(quality.score, 55)

    def test_prefer_snapshot_selects_higher_quality_content(self) -> None:
        weak = _PageSnapshotPayload(
            title="홈",
            final_url="https://example.com",
            article_text="LIVE\nTop stories",
            selected_root_selector="body",
            paragraph_count=1,
        )
        strong = _PageSnapshotPayload(
            title="기사",
            final_url="https://example.com/news-story",
            article_text="\n".join(["이 문단은 충분히 긴 기사 본문입니다. " * 12 for _ in range(4)]),
            selected_root_selector="article",
            paragraph_count=4,
        )

        preferred = _prefer_snapshot(weak, strong)

        self.assertEqual(preferred.final_url, "https://example.com/news-story")


if __name__ == "__main__":
    unittest.main()
