"""Source reliability analyzer."""

# pyright: reportMissingImports=false, reportImplicitOverride=false

from __future__ import annotations

from app.agents.base import AnalysisAgent
from app.analyzers.base import BaseAnalyzer
from app.schemas import AnalysisCriterionResult, CrawlerOutput


class SourceAnalyzer(BaseAnalyzer):
    """Analyze source reliability from deterministic agent output."""

    name: str = "source_reliability"
    label: str = "출처 신뢰도"

    def __init__(self, agent: AnalysisAgent) -> None:
        super().__init__(agent)

    def analyze(self, payload: CrawlerOutput) -> AnalysisCriterionResult:
        return self._agent.analyze(payload, self.name)


__all__ = ["SourceAnalyzer"]

