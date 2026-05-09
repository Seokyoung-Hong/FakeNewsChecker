"""Agent seam for deterministic analysis implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import AnalysisCriterionResult, CrawlerOutput


class AnalysisAgent(ABC):
    """Shared interface for criterion-level analysis agents."""

    name: str = "analysis-agent"

    @abstractmethod
    def analyze(
        self,
        crawler_output: CrawlerOutput,
        criterion: str,
    ) -> AnalysisCriterionResult:
        """Analyze one criterion from crawler output and return structured DTO."""

        raise NotImplementedError


__all__ = ["AnalysisAgent"]

