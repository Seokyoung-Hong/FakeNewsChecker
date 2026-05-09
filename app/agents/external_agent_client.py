"""External agent client seam placeholder.

This module intentionally does not perform HTTP calls. It exists so the service
pipeline can later swap local and external implementations without changing the
orchestration API.
"""

# pyright: reportMissingImports=false, reportImplicitOverride=false

from __future__ import annotations

from app.agents.base import AnalysisAgent
from app.schemas import AnalysisCriterionResult, CrawlerOutput


class ExternalAgentClient(AnalysisAgent):
    """Stub client for a future external AI/LLM endpoint."""

    name: str = "external-agent-client"
    _endpoint: str

    def __init__(self, endpoint: str = "") -> None:
        super().__init__()
        self._endpoint = endpoint

    def analyze(self, crawler_output: CrawlerOutput, criterion: str) -> AnalysisCriterionResult:
        """Return a deterministic fallback result without outbound communication."""

        del crawler_output
        del criterion
        # Placeholder result keeps pipeline functional when a route opts into this
        # stub path while avoiding network traffic in the prototype.
        return AnalysisCriterionResult(
            score=60,
            summary="외부 에이전트는 현재 시드 단계이므로 로컬 기본 값으로 처리했습니다.",
            risk="unknown",
        )


__all__ = ["ExternalAgentClient"]

