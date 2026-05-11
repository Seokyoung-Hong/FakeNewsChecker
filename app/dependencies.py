"""Shared dependency providers for the app runtime layer.

This module wires implementation-ready seams for services and repositories while
keeping providers lightweight and offline-safe.
"""

# pyright: reportMissingImports=false

from functools import lru_cache
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.config import CrawlerSettings
from app.artifact_store import CrawlArtifactStore, FilesystemCrawlArtifactStore
from app.agents.jiwon_agent import JiwonAnalysisAgent
from app.agents.local_agent import LocalAgent
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
)
from app.services.hyperbrowser_client import HyperbrowserClient
from app.services.report_service import ReportService, DeterministicReportService
from app.services.scoring_service import ScoringService, DeterministicScoringService


def get_templates() -> Jinja2Templates:
    """Return a Jinja2 templates helper rooted at ``app/templates``."""

    templates_dir = Path(__file__).resolve().parent / "templates"
    return Jinja2Templates(directory=str(templates_dir))


@lru_cache(maxsize=1)
def get_analysis_repository() -> AnalysisResultRepository:
    """Return the active repository implementation for analysis results.

    In-memory storage is sufficient for this task and keeps runtime deterministic
    and offline-safe.
    """

    return InMemoryAnalysisResultRepository()


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
        return HyperbrowserCrawlerService(client)

    return DeterministicCrawlerService()


@lru_cache(maxsize=1)
def get_crawl_artifact_store() -> CrawlArtifactStore:
    """Return the filesystem-backed artifact store for saved downloads."""

    settings = get_crawler_settings()
    project_root = Path(__file__).resolve().parent.parent
    artifact_root = project_root / settings.artifact_root_dir
    return FilesystemCrawlArtifactStore(artifact_root)


def _build_analysis_service(
    crawler_service: CrawlerService,
    scoring_service: ScoringService,
    report_service: ReportService,
    artifact_store: CrawlArtifactStore,
) -> AnalysisService:
    """Build a deterministic analysis orchestration service.

    Separated as a helper to keep dependency graph explicit while keeping this
    module's provider functions straightforward.
    """

    analysis_agent = JiwonAnalysisAgent(fallback_agent=LocalAgent())
    analyzers = (
        SourceAnalyzer(analysis_agent),
        ClaimAnalyzer(analysis_agent),
        ExpressionAnalyzer(analysis_agent),
        MultimodalAnalyzer(analysis_agent),
    )
    return DeterministicAnalysisService(
        crawler_service=crawler_service,
        analyzers=analyzers,
        scoring_service=scoring_service,
        report_service=report_service,
        evidence_agent=analysis_agent,
        artifact_store=artifact_store,
    )


@lru_cache(maxsize=1)
def get_analysis_service() -> AnalysisService:
    """Return the active orchestration service for URL analysis."""

    crawler_service = get_crawler_service()
    scoring_service = DeterministicScoringService()
    report_service = DeterministicReportService()
    artifact_store = get_crawl_artifact_store()
    return _build_analysis_service(
        crawler_service=crawler_service,
        scoring_service=scoring_service,
        report_service=report_service,
        artifact_store=artifact_store,
    )


def get_active_analysis_service() -> AnalysisService:
    """Alias for explicit dependency naming in orchestration callers."""

    return get_analysis_service()


__all__ = [
    "get_templates",
    "get_analysis_repository",
    "get_active_analysis_repository",
    "get_crawler_settings",
    "get_crawler_service",
    "get_crawl_artifact_store",
    "get_analysis_service",
    "get_active_analysis_service",
]

