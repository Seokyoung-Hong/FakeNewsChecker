"""Expression risk analyzer."""

# pyright: reportMissingImports=false, reportImplicitOverride=false

from __future__ import annotations

from app.agents.base import AnalysisAgent
from app.analyzers.base import BaseAnalyzer
from app.schemas import AnalysisCriterionResult, CrawlerOutput


class ExpressionAnalyzer(BaseAnalyzer):
    """Analyze expression manipulation risk from deterministic agent output."""

    name: str = "expression_risk"
    label: str = "선동 표현 위험도"

    def __init__(self, agent: AnalysisAgent) -> None:
        super().__init__(agent)

    def analyze(self, payload: CrawlerOutput) -> AnalysisCriterionResult:
        return self._agent.analyze(payload, self.name)


__all__ = ["ExpressionAnalyzer"]

