"""Analyzer abstractions for deterministic criterion-level analysis."""

# pyright: reportMissingImports=false

from __future__ import annotations

from abc import ABC, abstractmethod

from app.agents.base import AnalysisAgent
from app.schemas import AnalysisCriterionResult, CrawlerOutput


class BaseAnalyzer(ABC):
    """Base class for one criterion analyzer."""

    name: str = "base"
    label: str = "기준"
    _agent: AnalysisAgent

    def __init__(self, agent: AnalysisAgent) -> None:
        self._agent = agent

    @abstractmethod
    def analyze(self, payload: CrawlerOutput) -> AnalysisCriterionResult:
        """Return a typed per-criterion result."""

        raise NotImplementedError


__all__ = ["BaseAnalyzer"]

