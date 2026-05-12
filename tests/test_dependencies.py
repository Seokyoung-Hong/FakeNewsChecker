from __future__ import annotations

import os
import unittest
from typing import cast
from unittest.mock import patch

from app import dependencies
from app.agents.ollama_agent import OllamaAnalysisAgent
from app.services.analysis_service import DeterministicAnalysisService
from app.services.crawler_service import (
    DeterministicCrawlerService,
    HyperbrowserCrawlerService,
    LocalBrowserCrawlerService,
    PrefixedCrawlerService,
)
from app.services.hyperbrowser_client import HyperbrowserClient


class DependencySelectionTests(unittest.TestCase):
    @staticmethod
    def _clear_local_analysis_service_cache() -> None:
        cache_clear = getattr(dependencies.get_local_analysis_service, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()

    def setUp(self) -> None:
        dependencies.get_crawler_settings.cache_clear()
        dependencies.get_crawl_artifact_store.cache_clear()
        dependencies.get_crawler_service.cache_clear()
        dependencies.get_local_crawler_service.cache_clear()
        dependencies.get_analysis_service.cache_clear()
        self._clear_local_analysis_service_cache()
        dependencies.get_ollama_settings.cache_clear()

    def tearDown(self) -> None:
        dependencies.get_crawler_settings.cache_clear()
        dependencies.get_crawl_artifact_store.cache_clear()
        dependencies.get_crawler_service.cache_clear()
        dependencies.get_local_crawler_service.cache_clear()
        dependencies.get_analysis_service.cache_clear()
        self._clear_local_analysis_service_cache()
        dependencies.get_ollama_settings.cache_clear()

    def test_deterministic_provider_is_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            service = dependencies.get_crawler_service()

        self.assertIsInstance(service, DeterministicCrawlerService)

    def test_hyperbrowser_provider_is_selected_when_configured(self) -> None:
        env = {
            "CRAWLER_PROVIDER": "hyperbrowser",
            "HYPERBROWSER_API_KEY": "secret",
        }
        with patch.dict(os.environ, env, clear=True):
            service = dependencies.get_crawler_service()

        self.assertIsInstance(service, HyperbrowserCrawlerService)
        crawler = cast(HyperbrowserCrawlerService, service)
        self.assertIsInstance(crawler._client, HyperbrowserClient)

    def test_hyperbrowser_provider_requires_api_key(self) -> None:
        with patch.dict(os.environ, {"CRAWLER_PROVIDER": "hyperbrowser"}, clear=True):
            with self.assertRaises(ValueError):
                dependencies.get_crawler_service()

    def test_invalid_provider_raises(self) -> None:
        with patch.dict(os.environ, {"CRAWLER_PROVIDER": "invalid"}, clear=True):
            with self.assertRaises(ValueError):
                dependencies.get_crawler_service()

    def test_hyperbrowser_provider_rejects_whitespace_api_key(self) -> None:
        env = {
            "CRAWLER_PROVIDER": "hyperbrowser",
            "HYPERBROWSER_API_KEY": "   ",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError):
                dependencies.get_crawler_service()

    def test_local_analysis_service_uses_prefixed_crawler_and_ollama_agent(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            service = cast(DeterministicAnalysisService, dependencies.get_local_analysis_service())

        self.assertIsInstance(service._crawler_service, PrefixedCrawlerService)
        prefixed_crawler = cast(PrefixedCrawlerService, service._crawler_service)
        self.assertEqual(prefixed_crawler._prefix, "local-")
        self.assertIsInstance(prefixed_crawler._inner, LocalBrowserCrawlerService)
        self.assertIsInstance(service._evidence_agent, OllamaAnalysisAgent)


if __name__ == "__main__":
    unittest.main()
