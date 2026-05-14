"""Shared dependency providers for the app runtime layer.

This module wires implementation-ready seams for services and repositories while
keeping providers lightweight and offline-safe.
"""

# pyright: reportMissingImports=false

from functools import lru_cache
import logging
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.config import CrawlerSettings
from app.config import OllamaSettings
from app.config import is_production_mode
from app.agents.base import AnalysisAgent
from app.agents.multimodal_agent import MultimodalAnalysisAgent
from app.artifact_store import CrawlArtifactStore, FilesystemCrawlArtifactStore
from app.agents.jiwon_agent import JiwonAnalysisAgent
from app.agents.local_agent import LocalAgent
from app.agents.ollama_agent import OllamaAnalysisAgent
from app.gemini_multimodal_analyzer import analyze_multimodal as analyze_gemini_multimodal
from app.ollama_multimodal_analyzer import analyze_multimodal as analyze_ollama_multimodal
from app.analyzers.claim_analyzer import ClaimAnalyzer
from app.analyzers.expression_analyzer import ExpressionAnalyzer
from app.analyzers.multimodal_analyzer import MultimodalAnalyzer
from app.analyzers.source_analyzer import SourceAnalyzer
from app.repositories import AnalysisResultRepository, InMemoryAnalysisResultRepository
from app.services.analysis_service import AnalysisService, DeterministicAnalysisService
from app.services.crawler_service import (
    CrawlerService,
    DeterministicCrawlerService,
    HyperbrowserCrawlerService,
    LocalBrowserCrawlerService,
    PrefixedCrawlerService,
)
from app.services.hyperbrowser_client import HyperbrowserClient
from app.services.local_browser_client import LocalBrowserClient
from app.services.report_service import ReportService, DeterministicReportService
from app.services.scoring_service import ScoringService, DeterministicScoringService


logger = logging.getLogger(__name__)


def get_templates() -> Jinja2Templates:
    """Return a Jinja2 templates helper rooted at ``app/templates``."""

    templates_dir = Path(__file__).resolve().parent / "templates"
    logger.debug("Resolved templates directory", extra={"event": "templates_resolved", "directory": str(templates_dir)})
    return Jinja2Templates(directory=str(templates_dir))


def get_production_mode() -> bool:
    """Return whether production-mode UI restrictions are enabled."""

    return is_production_mode()


@lru_cache(maxsize=1)
def get_analysis_repository() -> AnalysisResultRepository:
    """Return the active repository implementation for analysis results.

    In-memory storage is sufficient for this task and keeps runtime deterministic
    and offline-safe.
    """

    repository = InMemoryAnalysisResultRepository()
    logger.debug("Created analysis repository", extra={"event": "analysis_repository_created", "repository_class": type(repository).__name__})
    return repository


def get_active_analysis_repository() -> AnalysisResultRepository:
    """Alias for explicit dependency naming in orchestration callers."""

    return get_analysis_repository()


@lru_cache(maxsize=1)
def get_crawler_settings() -> CrawlerSettings:
    """Return crawler runtime settings derived from environment variables."""

    return CrawlerSettings.from_env()


@lru_cache(maxsize=1)
def get_crawler_service() -> CrawlerService:
    """Return the active crawler implementation for URL collection."""

    settings = get_crawler_settings()
    if settings.provider == "hyperbrowser":
        client = HyperbrowserClient(
            api_key=settings.hyperbrowser_api_key or "",
            wait_until=settings.hyperbrowser_wait_until,
            wait_for_ms=settings.hyperbrowser_wait_for_ms,
            timeout_ms=settings.hyperbrowser_timeout_ms,
        )
        service = HyperbrowserCrawlerService(client)
        logger.debug("Selected crawler service", extra={"event": "crawler_service_selected", "provider": settings.provider, "service_class": type(service).__name__})
        return service

    service = DeterministicCrawlerService()
    logger.debug("Selected crawler service", extra={"event": "crawler_service_selected", "provider": settings.provider, "service_class": type(service).__name__})
    return service


@lru_cache(maxsize=1)
def get_local_crawler_service() -> CrawlerService:
    """Return the local crawler implementation used by local-search flows."""

    settings = get_crawler_settings()
    client = LocalBrowserClient(
        backend=settings.local_crawler_backend,
        headless=settings.local_crawler_headless,
        wait_until=settings.local_crawler_wait_until,
        wait_for_ms=settings.local_crawler_wait_for_ms,
        timeout_ms=settings.local_crawler_timeout_ms,
        block_media=settings.local_crawler_block_media,
        user_agent=settings.local_crawler_user_agent,
        navigation_settings=get_ollama_settings(),
    )
    service = LocalBrowserCrawlerService(client)
    logger.debug(
        "Selected local crawler service",
        extra={
            "event": "local_crawler_service_selected",
            "backend": settings.local_crawler_backend,
            "service_class": type(service).__name__,
        },
    )
    return service


@lru_cache(maxsize=1)
def get_ollama_settings() -> OllamaSettings:
    """Return local-model settings derived from environment variables."""

    settings = OllamaSettings.from_env()
    logger.debug(
        "Loaded Ollama settings via dependency",
        extra={
            "event": "ollama_settings_loaded",
            "host": settings.host,
            "fallback_hosts": settings.fallback_hosts,
            "host_count": len(settings.hosts),
            "model": settings.model,
        },
    )
    return settings


@lru_cache(maxsize=1)
def get_crawl_artifact_store() -> CrawlArtifactStore:
    """Return the filesystem-backed artifact store for saved downloads."""

    settings = get_crawler_settings()
    project_root = Path(__file__).resolve().parent.parent
    artifact_root = project_root / settings.artifact_root_dir
    store = FilesystemCrawlArtifactStore(artifact_root)
    logger.debug("Created crawl artifact store", extra={"event": "artifact_store_created", "root": str(artifact_root), "store_class": type(store).__name__})
    return store


def _build_analysis_service(
    crawler_service: CrawlerService,
    scoring_service: ScoringService,
    report_service: ReportService,
    artifact_store: CrawlArtifactStore,
    analysis_agent: AnalysisAgent,
) -> AnalysisService:
    """Build a deterministic analysis orchestration service.

    Separated as a helper to keep dependency graph explicit while keeping this
    module's provider functions straightforward.
    """

    analyzers = (
        SourceAnalyzer(analysis_agent),
        ClaimAnalyzer(analysis_agent),
        ExpressionAnalyzer(analysis_agent),
        MultimodalAnalyzer(analysis_agent),
    )
    service = DeterministicAnalysisService(
        crawler_service=crawler_service,
        analyzers=analyzers,
        scoring_service=scoring_service,
        report_service=report_service,
        evidence_agent=analysis_agent,
        artifact_store=artifact_store,
    )
    logger.debug(
        "Built analysis service",
        extra={
            "event": "analysis_service_built",
            "crawler_class": type(crawler_service).__name__,
            "agent_class": type(analysis_agent).__name__,
            "analyzer_classes": [type(analyzer).__name__ for analyzer in analyzers],
            "scoring_class": type(scoring_service).__name__,
            "report_class": type(report_service).__name__,
            "artifact_store_class": type(artifact_store).__name__,
        },
    )
    return service


@lru_cache(maxsize=1)
def get_analysis_service() -> AnalysisService:
    """Return the active orchestration service for URL analysis."""

    crawler_service = get_crawler_service()
    scoring_service = DeterministicScoringService()
    report_service = DeterministicReportService()
    artifact_store = get_crawl_artifact_store()
    fallback_agent = LocalAgent()
    multimodal_agent = MultimodalAnalysisAgent(
        multimodal_provider=analyze_gemini_multimodal,
        fallback_agent=fallback_agent,
    )
    analysis_agent = JiwonAnalysisAgent(
        fallback_agent=fallback_agent,
        multimodal_agent=multimodal_agent,
    )
    logger.debug("Constructing online analysis service", extra={"event": "analysis_service_construct", "flow": "online"})
    return _build_analysis_service(
        crawler_service=crawler_service,
        scoring_service=scoring_service,
        report_service=report_service,
        artifact_store=artifact_store,
        analysis_agent=analysis_agent,
    )


def get_local_analysis_service() -> AnalysisService:
    """Return the local-model analysis service for local crawling + local inference."""

    crawler_service = PrefixedCrawlerService(get_local_crawler_service(), prefix="local-")
    scoring_service = DeterministicScoringService()
    report_service = DeterministicReportService()
    artifact_store = get_crawl_artifact_store()
    fallback_agent = LocalAgent()
    ollama_settings = get_ollama_settings()
    analysis_agent = OllamaAnalysisAgent(
        settings=ollama_settings,
        fallback_agent=fallback_agent,
    )
    multimodal_agent = MultimodalAnalysisAgent(
        multimodal_provider=lambda crawler_output, hive_result, image_paths: analyze_ollama_multimodal(
            crawler_output,
            hive_result,
            list(image_paths),
            ollama_settings,
            on_failover=analysis_agent._report_failover_status,
        ),
        fallback_agent=fallback_agent,
    )
    analysis_agent._multimodal_agent = multimodal_agent
    logger.debug("Constructing local analysis service", extra={"event": "analysis_service_construct", "flow": "local-model"})
    return _build_analysis_service(
        crawler_service=crawler_service,
        scoring_service=scoring_service,
        report_service=report_service,
        artifact_store=artifact_store,
        analysis_agent=analysis_agent,
    )


def get_active_local_analysis_service() -> AnalysisService:
    """Alias for explicit dependency naming in local-model callers."""

    return get_local_analysis_service()


def get_active_analysis_service() -> AnalysisService:
    """Alias for explicit dependency naming in orchestration callers."""

    return get_analysis_service()


__all__ = [
    "get_templates",
    "get_analysis_repository",
    "get_active_analysis_repository",
    "get_crawler_settings",
    "get_crawler_service",
    "get_local_crawler_service",
    "get_ollama_settings",
    "get_crawl_artifact_store",
    "get_analysis_service",
    "get_active_analysis_service",
    "get_local_analysis_service",
    "get_active_local_analysis_service",
]

