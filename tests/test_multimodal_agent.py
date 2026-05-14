from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.agents.base import AnalysisAgent
from app.agents.multimodal_agent import MultimodalAnalysisAgent
from app.schemas import AnalysisCriterionResult, CrawlerOutput, URLSubmission


class _DelegateAgent(AnalysisAgent):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def analyze(self, crawler_output: CrawlerOutput, criterion: str) -> AnalysisCriterionResult:
        del crawler_output
        self.calls.append(criterion)
        return AnalysisCriterionResult(score=81, summary=f"{criterion} delegated", risk="low")


class _FallbackAgent(AnalysisAgent):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def analyze(self, crawler_output: CrawlerOutput, criterion: str) -> AnalysisCriterionResult:
        del crawler_output
        self.calls.append(criterion)
        return AnalysisCriterionResult(score=55, summary="fallback multimodal", risk="medium")


class MultimodalAnalysisAgentTests(unittest.TestCase):
    def test_falls_back_for_non_multimodal_criteria(self) -> None:
        fallback = _FallbackAgent()
        agent = MultimodalAnalysisAgent(
            multimodal_provider=lambda crawler_output, hive_result, image_paths: {},
            fallback_agent=fallback,
        )
        payload = CrawlerOutput(
            analysis_id="analysis-1",
            url=URLSubmission.model_validate({"url": "https://example.com/article"}).url,
            title="기사 제목",
            content="기사 본문",
            images=[],
            metadata={},
        )

        result = agent.analyze(payload, "source_reliability")

        self.assertEqual(result.summary, "fallback multimodal")
        self.assertEqual(fallback.calls, ["source_reliability"])

    def test_combines_hive_and_llm_results_for_multimodal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "image.jpg"
            image_path.write_bytes(b"fake-image")
            payload = CrawlerOutput(
                analysis_id="analysis-1",
                url=URLSubmission.model_validate({"url": "https://example.com/article"}).url,
                title="기사 제목",
                content="기사 본문",
                images=["https://cdn.example.com/image.jpg"],
                metadata={"persisted_image_paths": [str(image_path)]},
            )
            agent = MultimodalAnalysisAgent(
                multimodal_provider=lambda crawler_output, hive_result, image_paths: {
                    "score": 73,
                    "summary": f"LLM 분석 완료 ({len(image_paths)}장)",
                    "risk": "medium",
                },
                fallback_agent=_FallbackAgent(),
            )

            from unittest.mock import patch

            with patch(
                "app.agents.multimodal_agent.analyze_images",
                return_value={"score": 61, "summary": "Hive 조작 가능성 일부", "risk": "high"},
            ):
                result = agent.analyze(payload, "multimodal_risk")
                cached = agent.analyze_payload(payload)

        self.assertEqual(result.score, 61)
        self.assertEqual(result.risk, "high")
        self.assertIn("LLM 분석 완료", result.summary)
        self.assertIn("Hive 위험도 분석", result.summary)
        assert cached is not None
        self.assertEqual(cached["score"], 61)

    def test_uses_single_provider_result_when_hive_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "image.jpg"
            image_path.write_bytes(b"fake-image")
            payload = CrawlerOutput(
                analysis_id="analysis-1",
                url=URLSubmission.model_validate({"url": "https://example.com/article"}).url,
                title="기사 제목",
                content="기사 본문",
                images=["https://cdn.example.com/image.jpg"],
                metadata={"persisted_image_paths": [str(image_path)]},
            )
            agent = MultimodalAnalysisAgent(
                multimodal_provider=lambda crawler_output, hive_result, image_paths: {
                    "score": 77,
                    "summary": "LLM 단독 분석",
                    "risk": "low",
                },
                fallback_agent=_FallbackAgent(),
            )

            from unittest.mock import patch

            with patch(
                "app.agents.multimodal_agent.analyze_images",
                return_value={"score": 50, "summary": "Hive API 키가 없어 이미지 분석을 건너뜁니다.", "risk": "unknown"},
            ):
                result = agent.analyze(payload, "multimodal_risk")

        self.assertEqual(result.summary, "LLM 단독 분석")
        self.assertEqual(result.score, 77)
