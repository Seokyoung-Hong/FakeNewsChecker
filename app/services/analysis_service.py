"""Orchestration service for crawler -> analysis -> scoring -> report pipeline."""

# pyright: reportMissingImports=false, reportImplicitOverride=false

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
import logging

from app.agents.base import AnalysisAgent
from app.agents.local_agent import LocalAgent
from app.analyzers.base import BaseAnalyzer
from app.progress_store import (
    STAGE_AI_ANALYSIS,
    STAGE_BODY_COLLECTION,
    STAGE_REPORT_BUILD,
    STAGE_SOURCE_CHECK,
)
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


logger = logging.getLogger(__name__)


class AnalysisService(ABC):
    """Contract for a complete analysis orchestration service."""

    @abstractmethod
    def run(
        self,
        submission: URLSubmission,
        progress_callback: Callable[[str], None] | None = None,
        status_message_callback: Callable[[str], None] | None = None,
    ) -> AnalysisResult:
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

    def run(
        self,
        submission: URLSubmission,
        progress_callback: Callable[[str], None] | None = None,
        status_message_callback: Callable[[str], None] | None = None,
    ) -> AnalysisResult:
        """Execute deterministic, network-free full pipeline."""

        logger.debug("Analysis run started", extra={"event": "analysis_run_start", "url": str(submission.url)})
        self._reset_analysis_agents()
        if progress_callback is not None:
            progress_callback(STAGE_BODY_COLLECTION)
        crawler_output = self._crawler_service.collect(submission)
        artifacts = self._persist_artifacts(crawler_output)
        analysis_output = self._run_analysis(
            crawler_output,
            progress_callback=progress_callback,
            status_message_callback=status_message_callback,
        )
        if progress_callback is not None:
            progress_callback(STAGE_REPORT_BUILD)
        scoring_output = self._scoring_service.score(analysis_output)
        report_output = self._report_service.build_report(analysis_output, scoring_output)

        logger.debug(
            "Analysis run completed",
            extra={
                "event": "analysis_run_done",
                "analysis_id": analysis_output.analysis_id,
                "score": scoring_output.score,
                "has_artifacts": artifacts is not None,
            },
        )
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

    def _reset_analysis_agents(self) -> None:
        seen: set[int] = set()
        agents: list[object] = [self._evidence_agent]
        agents.extend(getattr(analyzer, "_agent", None) for analyzer in self._analyzers)

        for agent in agents:
            if agent is None:
                continue
            marker = id(agent)
            if marker in seen:
                continue
            seen.add(marker)
            reset = getattr(agent, "reset_cache", None)
            if callable(reset):
                _ = reset()
        logger.debug("Reset analysis agent caches", extra={"event": "analysis_agents_reset", "agent_count": len(seen)})

    def _persist_artifacts(
        self,
        crawler_output: CrawlerOutput,
    ) -> DownloadArtifactManifest | None:
        if self._artifact_store is None:
            logger.debug("Artifact persistence skipped", extra={"event": "artifact_persist_skipped"})
            return None
        manifest = self._artifact_store.persist(crawler_output)
        logger.debug("Artifact persistence completed", extra={"event": "artifact_persist_done", "analysis_id": crawler_output.analysis_id, "file_count": len(manifest.files), "image_count": len(manifest.images)})
        return manifest

    def _run_analysis(
        self,
        crawler_output: CrawlerOutput,
        progress_callback: Callable[[str], None] | None = None,
        status_message_callback: Callable[[str], None] | None = None,
    ) -> AnalysisOutput:
        criterion_results = self._run_analyzers(
            crawler_output,
            progress_callback=progress_callback,
            status_message_callback=status_message_callback,
        )
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
            overall_summary=self._resolve_overall_summary(crawler_output, criteria),
        )

    def _run_analyzers(
        self,
        crawler_output: CrawlerOutput,
        progress_callback: Callable[[str], None] | None = None,
        status_message_callback: Callable[[str], None] | None = None,
    ) -> dict[str, AnalysisCriterionResult]:
        self._set_status_message_callback(status_message_callback)
        results: dict[str, AnalysisCriterionResult] = {}
        announced_ai_stage = False
        for analyzer in self._analyzers:
            if progress_callback is not None:
                if analyzer.name == "source_reliability":
                    progress_callback(STAGE_SOURCE_CHECK)
                elif not announced_ai_stage:
                    progress_callback(STAGE_AI_ANALYSIS)
                    announced_ai_stage = True
            result = analyzer.analyze(crawler_output)
            results[analyzer.name] = result
        logger.debug("Analyzer pass completed", extra={"event": "analyzer_pass_done", "analysis_id": crawler_output.analysis_id, "analyzers": list(results.keys())})
        return results

    def _set_status_message_callback(
        self,
        status_message_callback: Callable[[str], None] | None,
    ) -> None:
        if status_message_callback is None:
            return

        seen: set[int] = set()

        def _set_on(target: object | None) -> None:
            if target is None:
                return
            target_id = id(target)
            if target_id in seen:
                return
            seen.add(target_id)
            set_callback = getattr(target, "set_status_message_callback", None)
            if callable(set_callback):
                _ = set_callback(status_message_callback)

        _set_on(self._evidence_agent)
        for analyzer in self._analyzers:
            _set_on(getattr(analyzer, "_agent", None))

    def _ensure_complete_criteria(
        self,
        results: dict[str, AnalysisCriterionResult],
        crawler_output: CrawlerOutput,
    ) -> dict[str, AnalysisCriterionResult]:
        if "evidence_quality" not in results:
            logger.debug("Evidence quality missing from analyzers; using evidence agent fallback", extra={"event": "criteria_fallback", "analysis_id": crawler_output.analysis_id, "criterion": "evidence_quality"})
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
            logger.error("Analysis criteria missing after pipeline", extra={"event": "criteria_missing", "analysis_id": crawler_output.analysis_id, "missing": missing})
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

    def _resolve_overall_summary(
        self,
        crawler_output: CrawlerOutput,
        criteria: Mapping[str, AnalysisCriterionResult],
    ) -> str:
        summary_getter = getattr(self._evidence_agent, "get_overall_summary", None)
        if callable(summary_getter):
            summary = summary_getter(crawler_output)
            if isinstance(summary, str) and summary.strip():
                logger.debug("Using agent-provided overall summary", extra={"event": "overall_summary_agent", "analysis_id": crawler_output.analysis_id})
                return summary.strip()
        logger.debug("Using deterministic overall summary", extra={"event": "overall_summary_deterministic", "analysis_id": crawler_output.analysis_id})
        return self._compose_overall_summary(criteria)


__all__ = ["AnalysisService", "DeterministicAnalysisService"]

