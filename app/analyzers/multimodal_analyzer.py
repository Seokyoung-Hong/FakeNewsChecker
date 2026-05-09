"""Multimodal risk analyzer."""

# pyright: reportMissingImports=false, reportImplicitOverride=false

from __future__ import annotations

from app.agents.base import AnalysisAgent
from app.analyzers.base import BaseAnalyzer
from app.schemas import AnalysisCriterionResult, CrawlerOutput


class MultimodalAnalyzer(BaseAnalyzer):
    """Analyze multimodal manipulation signals from deterministic agent output."""

    name: str = "multimodal_risk"
    label: str = "멀티모달 조작 위험도"

    def __init__(self, agent: AnalysisAgent) -> None:
        super().__init__(agent)

    def analyze(self, payload: CrawlerOutput) -> AnalysisCriterionResult:
        return self._agent.analyze(payload, self.name)


__all__ = ["MultimodalAnalyzer"]

