from __future__ import annotations

import unittest
from collections.abc import Callable

from app.agents.base import AnalysisAgent
from app.analyzers.base import BaseAnalyzer
from app.artifact_store import CrawlArtifactStore
from app.schemas import (
    AnalysisCriterionResult,
    AnalysisOutput,
    AnalysisResult,
    CrawlerOutput,
    ArtifactFile,
    DownloadArtifactManifest,
    DownloadedImage,
    ReportDetail,
    ReportOutput,
    ScoringOutput,
    URLSubmission,
)
from app.services.crawler_service import CrawlerService
from app.services.analysis_service import DeterministicAnalysisService
from app.services.report_service import ReportService
from app.services.scoring_service import ScoringService


class _FakeAgent(AnalysisAgent):
    def analyze(self, crawler_output: CrawlerOutput, criterion: str) -> AnalysisCriterionResult:
        del crawler_output
        return AnalysisCriterionResult(score=80, summary=f"{criterion} summary", risk="low")


class _FakeCrawlerService(CrawlerService):
    def collect(self, submission: URLSubmission) -> CrawlerOutput:
        return CrawlerOutput(
            analysis_id="analysis-1",
            url=submission.url,
            title="기사 제목",
            content="기사 본문",
            images=["https://cdn.example.com/image.jpg"],
            metadata={"source_url": str(submission.url)},
        )


class _FakeAnalyzer(BaseAnalyzer):
    def __init__(self, name: str) -> None:
        super().__init__(_FakeAgent())
        self.name = name

    def analyze(self, payload: CrawlerOutput) -> AnalysisCriterionResult:
        del payload
        return AnalysisCriterionResult(score=80, summary=f"{self.name} summary", risk="low")


class _FakeScoringService(ScoringService):
    def score(self, analysis_output: AnalysisOutput) -> ScoringOutput:
        return ScoringOutput(
            analysis_id=analysis_output.analysis_id,
            score=82,
            score_band="trustworthy",
            criteria_breakdown={"source_reliability": 80},
            rationale=["ok"],
        )


class _FakeReportService(ReportService):
    def build_report(self, analysis_output: AnalysisOutput, scoring_output: ScoringOutput) -> ReportOutput:
        del analysis_output, scoring_output
        return ReportOutput(
            analysis_id="analysis-1",
            summary="요약입니다.",
            details=[
                ReportDetail(
                    key="source_reliability",
                    label="출처 신뢰도",
                    score=80,
                    summary="괜찮습니다.",
                    risk="low",
                )
            ],
        )


class _FakeArtifactStore(CrawlArtifactStore):
    def __init__(self) -> None:
        self.persisted: CrawlerOutput | None = None

    def persist(self, crawler_output: CrawlerOutput) -> DownloadArtifactManifest:
        self.persisted = crawler_output
        return DownloadArtifactManifest(storage_directory="downloaded_news/analysis-1")

    def resolve(self, analysis_id: str, relative_path: str) -> None:
        del analysis_id, relative_path
        return None


class _ResettableAgent(_FakeAgent):
    def __init__(self) -> None:
        self.reset_count = 0

    def reset_cache(self) -> None:
        self.reset_count += 1

    def get_overall_summary(self, crawler_output: CrawlerOutput) -> str:
        del crawler_output
        return "LLM 핵심 근거: 근거 부족"


class _StatusMessageAwareAgent(_FakeAgent):
    status_message_callback: Callable[[str], None] | None
    set_status_message_callback_calls: int

    def __init__(self) -> None:
        super().__init__()
        self.status_message_callback = None
        self.set_status_message_callback_calls = 0

    def set_status_message_callback(self, status_message_callback: Callable[[str], None] | None) -> None:
        self.status_message_callback = status_message_callback
        self.set_status_message_callback_calls += 1


class DeterministicAnalysisServiceTests(unittest.TestCase):
    def test_run_attaches_saved_artifacts_to_analysis_result(self) -> None:
        artifact_store = _FakeArtifactStore()
        service = DeterministicAnalysisService(
            crawler_service=_FakeCrawlerService(),
            analyzers=[
                _FakeAnalyzer("source_reliability"),
                _FakeAnalyzer("claim_consistency"),
                _FakeAnalyzer("expression_risk"),
                _FakeAnalyzer("multimodal_risk"),
            ],
            scoring_service=_FakeScoringService(),
            report_service=_FakeReportService(),
            artifact_store=artifact_store,
        )

        result = service.run(URLSubmission.model_validate({"url": "https://example.com/article"}))

        self.assertIsInstance(result, AnalysisResult)
        self.assertIsNotNone(result.artifacts)
        artifacts = result.artifacts
        assert artifacts is not None
        self.assertEqual(artifacts.storage_directory, "downloaded_news/analysis-1")
        self.assertIsNotNone(artifact_store.persisted)

    def test_run_attaches_persisted_image_paths_to_runtime_metadata(self) -> None:
        class _ImageArtifactStore(_FakeArtifactStore):
            def persist(self, crawler_output: CrawlerOutput) -> DownloadArtifactManifest:
                self.persisted = crawler_output
                return DownloadArtifactManifest(
                    storage_directory="downloaded_news/analysis-1",
                    images=[
                        DownloadedImage(
                            source_url="https://cdn.example.com/image.jpg",
                            status="downloaded",
                            local_file=ArtifactFile(
                                label="저장 이미지 1",
                                relative_path="images/image-001.jpg",
                                size_bytes=10,
                                media_type="image/jpeg",
                            ),
                        )
                    ],
                )

        artifact_store = _ImageArtifactStore()
        service = DeterministicAnalysisService(
            crawler_service=_FakeCrawlerService(),
            analyzers=[
                _FakeAnalyzer("source_reliability"),
                _FakeAnalyzer("claim_consistency"),
                _FakeAnalyzer("expression_risk"),
                _FakeAnalyzer("multimodal_risk"),
            ],
            scoring_service=_FakeScoringService(),
            report_service=_FakeReportService(),
            artifact_store=artifact_store,
        )

        _ = service.run(URLSubmission.model_validate({"url": "https://example.com/article"}))

        assert artifact_store.persisted is not None
        self.assertEqual(
            artifact_store.persisted.metadata["persisted_image_paths"],
            ["downloaded_news/analysis-1/images/image-001.jpg"],
        )

    def test_run_resets_cache_on_shared_agent_once(self) -> None:
        artifact_store = _FakeArtifactStore()
        resettable_agent = _ResettableAgent()
        service = DeterministicAnalysisService(
            crawler_service=_FakeCrawlerService(),
            analyzers=[
                _FakeAnalyzer("source_reliability"),
                _FakeAnalyzer("claim_consistency"),
                _FakeAnalyzer("expression_risk"),
                _FakeAnalyzer("multimodal_risk"),
            ],
            scoring_service=_FakeScoringService(),
            report_service=_FakeReportService(),
            evidence_agent=resettable_agent,
            artifact_store=artifact_store,
        )

        for analyzer in service._analyzers:
            analyzer._agent = resettable_agent

        service.run(URLSubmission.model_validate({"url": "https://example.com/article"}))

        self.assertEqual(resettable_agent.reset_count, 1)

    def test_run_prefers_llm_overall_summary_when_available(self) -> None:
        artifact_store = _FakeArtifactStore()
        resettable_agent = _ResettableAgent()
        service = DeterministicAnalysisService(
            crawler_service=_FakeCrawlerService(),
            analyzers=[
                _FakeAnalyzer("source_reliability"),
                _FakeAnalyzer("claim_consistency"),
                _FakeAnalyzer("expression_risk"),
                _FakeAnalyzer("multimodal_risk"),
            ],
            scoring_service=_FakeScoringService(),
            report_service=_FakeReportService(),
            evidence_agent=resettable_agent,
            artifact_store=artifact_store,
        )

        for analyzer in service._analyzers:
            analyzer._agent = resettable_agent

        analysis_output = service._run_analysis(
            _FakeCrawlerService().collect(URLSubmission.model_validate({"url": "https://example.com/article"}))
        )

        self.assertEqual(analysis_output.overall_summary, "LLM 핵심 근거: 근거 부족")

    def test_run_reports_progress_stages_in_order(self) -> None:
        artifact_store = _FakeArtifactStore()
        resettable_agent = _ResettableAgent()
        service = DeterministicAnalysisService(
            crawler_service=_FakeCrawlerService(),
            analyzers=[
                _FakeAnalyzer("source_reliability"),
                _FakeAnalyzer("claim_consistency"),
                _FakeAnalyzer("expression_risk"),
                _FakeAnalyzer("multimodal_risk"),
            ],
            scoring_service=_FakeScoringService(),
            report_service=_FakeReportService(),
            evidence_agent=resettable_agent,
            artifact_store=artifact_store,
        )

        for analyzer in service._analyzers:
            analyzer._agent = resettable_agent

        stages: list[str] = []

        def progress_callback(stage: str) -> None:
            stages.append(stage)

        _ = service.run(
            URLSubmission.model_validate({"url": "https://example.com/article"}),
            progress_callback=progress_callback,
        )

        self.assertEqual(
            stages,
            [
                "body_collection",
                "source_check",
                "ai_analysis",
                "report_build",
            ],
        )

    def test_run_registers_status_message_callback_for_status_updates(self) -> None:
        artifact_store = _FakeArtifactStore()
        evidence_agent = _StatusMessageAwareAgent()
        analyzer_agent = _StatusMessageAwareAgent()
        service = DeterministicAnalysisService(
            crawler_service=_FakeCrawlerService(),
            analyzers=[
                _FakeAnalyzer("source_reliability"),
                _FakeAnalyzer("claim_consistency"),
                _FakeAnalyzer("expression_risk"),
                _FakeAnalyzer("multimodal_risk"),
            ],
            scoring_service=_FakeScoringService(),
            report_service=_FakeReportService(),
            evidence_agent=evidence_agent,
            artifact_store=artifact_store,
        )

        for analyzer in service._analyzers:
            analyzer._agent = analyzer_agent

        status_messages: list[str] = []

        def status_message_callback(message: str) -> None:
            status_messages.append(message)

        _ = service.run(
            URLSubmission.model_validate({"url": "https://example.com/article"}),
            status_message_callback=status_message_callback,
        )

        self.assertEqual(status_messages, [])
        self.assertEqual(evidence_agent.set_status_message_callback_calls, 1)
        self.assertEqual(evidence_agent.status_message_callback, status_message_callback)
        self.assertEqual(analyzer_agent.set_status_message_callback_calls, 1)
        self.assertEqual(analyzer_agent.status_message_callback, status_message_callback)


if __name__ == "__main__":
    unittest.main()
