"""Claim consistency analyzer."""

# pyright: reportMissingImports=false, reportImplicitOverride=false

from __future__ import annotations

from app.agents.base import AnalysisAgent
from app.analyzers.base import BaseAnalyzer
from app.schemas import AnalysisCriterionResult, CrawlerOutput


class ClaimAnalyzer(BaseAnalyzer):
    """Analyze claim consistency from deterministic agent output."""

    name: str = "claim_consistency"
    label: str = "주장 일관성"

    def __init__(self, agent: AnalysisAgent) -> None:
        super().__init__(agent)

    def analyze(self, payload: CrawlerOutput) -> AnalysisCriterionResult:
        return self._agent.analyze(payload, self.name)


__all__ = ["ClaimAnalyzer"]

