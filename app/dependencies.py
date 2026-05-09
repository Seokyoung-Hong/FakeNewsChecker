"""Shared dependency providers for the app runtime layer.

This module wires implementation-ready seams for services and repositories while
keeping providers lightweight and offline-safe.
"""

# pyright: reportMissingImports=false

from functools import lru_cache
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.agents.local_agent import LocalAgent
from app.analyzers.claim_analyzer import ClaimAnalyzer
from app.analyzers.expression_analyzer import ExpressionAnalyzer
from app.analyzers.multimodal_analyzer import MultimodalAnalyzer
from app.analyzers.source_analyzer import SourceAnalyzer
from app.repositories import AnalysisResultRepository, InMemoryAnalysisResultRepository
from app.services.analysis_service import AnalysisService, DeterministicAnalysisService
from app.services.crawler_service import CrawlerService, DeterministicCrawlerService
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


def _build_analysis_service(
    crawler_service: CrawlerService,
    scoring_service: ScoringService,
    report_service: ReportService,
) -> AnalysisService:
    """Build a deterministic analysis orchestration service.

    Separated as a helper to keep dependency graph explicit while keeping this
    module's provider functions straightforward.
    """

    local_agent = LocalAgent()
    analyzers = (
        SourceAnalyzer(local_agent),
        ClaimAnalyzer(local_agent),
        ExpressionAnalyzer(local_agent),
        MultimodalAnalyzer(local_agent),
    )
    return DeterministicAnalysisService(
        crawler_service=crawler_service,
        analyzers=analyzers,
        scoring_service=scoring_service,
        report_service=report_service,
    )


@lru_cache(maxsize=1)
def get_analysis_service() -> AnalysisService:
    """Return the active orchestration service for URL analysis."""

    crawler_service = DeterministicCrawlerService()
    scoring_service = DeterministicScoringService()
    report_service = DeterministicReportService()
    return _build_analysis_service(
        crawler_service=crawler_service,
        scoring_service=scoring_service,
        report_service=report_service,
    )


def get_active_analysis_service() -> AnalysisService:
    """Alias for explicit dependency naming in orchestration callers."""

    return get_analysis_service()


__all__ = [
    "get_templates",
    "get_analysis_repository",
    "get_active_analysis_repository",
    "get_analysis_service",
    "get_active_analysis_service",
]

