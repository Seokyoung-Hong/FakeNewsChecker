"""Orchestration service for crawler -> analysis -> scoring -> report pipeline."""

# pyright: reportMissingImports=false, reportImplicitOverride=false

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from app.agents.base import AnalysisAgent
from app.agents.local_agent import LocalAgent
from app.analyzers.base import BaseAnalyzer
from app.schemas import (
    AnalysisCriterionResult,
    AnalysisOutput,
    AnalysisResult,
    CrawlerOutput,
    DownloadArtifactManifest,
    URLSubmission,
)
from app.artifact_store import CrawlArtifactStore
from .crawler_service import CrawlerService
from .report_service import ReportService
from .scoring_service import ScoringService


class AnalysisService(ABC):
    """Contract for a complete analysis orchestration service."""

    @abstractmethod
    def run(self, submission: URLSubmission) -> AnalysisResult:
        """Run crawler/analysis/scoring/report for one URL submission."""


class DeterministicAnalysisService(AnalysisService):
    """Deterministic orchestrator for offline URL analysis."""

    _crawler_service: CrawlerService
    _analyzers: Sequence[BaseAnalyzer]
    _scoring_service: ScoringService
    _report_service: ReportService
    _evidence_agent: AnalysisAgent
    _artifact_store: CrawlArtifactStore | None

    def __init__(
        self,
        crawler_service: CrawlerService,
        analyzers: Sequence[BaseAnalyzer],
        scoring_service: ScoringService,
        report_service: ReportService,
        evidence_agent: AnalysisAgent | None = None,
        artifact_store: CrawlArtifactStore | None = None,
    ) -> None:
        self._crawler_service = crawler_service
        self._analyzers = analyzers
        self._scoring_service = scoring_service
        self._report_service = report_service
        self._evidence_agent = evidence_agent or LocalAgent()
        self._artifact_store = artifact_store

    def run(self, submission: URLSubmission) -> AnalysisResult:
        """Execute deterministic, network-free full pipeline."""

        crawler_output = self._crawler_service.collect(submission)
        artifacts = self._persist_artifacts(crawler_output)
        analysis_output = self._run_analysis(crawler_output)
        scoring_output = self._scoring_service.score(analysis_output)
        report_output = self._report_service.build_report(analysis_output, scoring_output)

        return AnalysisResult(
            analysis_id=analysis_output.analysis_id,
            url=analysis_output.url,
            title=crawler_output.title,
            original_content=crawler_output.content,
            score=scoring_output.score,
            label=scoring_output.score_band,
            summary=report_output.summary,
            details=report_output.details,
            artifacts=artifacts,
        )

    def _persist_artifacts(
        self,
        crawler_output: CrawlerOutput,
    ) -> DownloadArtifactManifest | None:
        if self._artifact_store is None:
            return None
        return self._artifact_store.persist(crawler_output)

    def _run_analysis(self, crawler_output: CrawlerOutput) -> AnalysisOutput:
        criterion_results = self._run_analyzers(crawler_output)
        criteria: Mapping[str, AnalysisCriterionResult] = self._ensure_complete_criteria(
            criterion_results,
            crawler_output,
        )

        return AnalysisOutput(
            analysis_id=crawler_output.analysis_id,
            url=crawler_output.url,
            source_reliability=criteria["source_reliability"],
            claim_consistency=criteria["claim_consistency"],
            evidence_quality=criteria["evidence_quality"],
            expression_risk=criteria["expression_risk"],
            multimodal_risk=criteria["multimodal_risk"],
            overall_summary=self._compose_overall_summary(criteria),
        )

    def _run_analyzers(
        self,
        crawler_output: CrawlerOutput,
    ) -> dict[str, AnalysisCriterionResult]:
        results: dict[str, AnalysisCriterionResult] = {}
        for analyzer in self._analyzers:
            result = analyzer.analyze(crawler_output)
            results[analyzer.name] = result
        return results

    def _ensure_complete_criteria(
        self,
        results: dict[str, AnalysisCriterionResult],
        crawler_output: CrawlerOutput,
    ) -> dict[str, AnalysisCriterionResult]:
        if "evidence_quality" not in results:
            results["evidence_quality"] = self._evidence_agent.analyze(
                crawler_output,
                "evidence_quality",
            )

        required = (
            "source_reliability",
            "claim_consistency",
            "evidence_quality",
            "expression_risk",
            "multimodal_risk",
        )
        missing = [name for name in required if name not in results]
        if missing:
            missing_fields = ", ".join(missing)
            raise ValueError(f"Missing analysis criteria: {missing_fields}")

        return results

    def _compose_overall_summary(self, criteria: Mapping[str, AnalysisCriterionResult]) -> str:
        ordered = sorted(criteria.items(), key=lambda item: item[1].score)
        weakest_key, weakest = ordered[0]
        strongest_key, strongest = ordered[-1]
        return (
            f"가장 낮은 항목은 '{weakest_key}'({weakest.score}점), "
            f"가장 높은 항목은 '{strongest_key}'({strongest.score}점)입니다."
        )


__all__ = ["AnalysisService", "DeterministicAnalysisService"]

