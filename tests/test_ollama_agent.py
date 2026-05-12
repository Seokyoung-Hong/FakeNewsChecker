from __future__ import annotations

import unittest
from unittest.mock import patch

from app.agents.ollama_agent import OllamaAnalysisAgent
from app.config import OllamaSettings
from app.schemas import CrawlerOutput, URLSubmission


class OllamaAnalysisAgentTests(unittest.TestCase):
    settings: OllamaSettings | None = None
    payload: CrawlerOutput | None = None

    def setUp(self) -> None:
        self.settings = OllamaSettings()
        self.payload = CrawlerOutput(
            analysis_id="analysis-1",
            url=URLSubmission.model_validate({"url": "https://example.com/article"}).url,
            title="기사 제목",
            content="기사 본문",
            images=["https://cdn.example.com/image.jpg"],
            metadata={},
        )

    def test_maps_text_results_into_current_criteria(self) -> None:
        text_result = {
            "overall_summary": {"verdict": "주의 필요", "reasons": ["근거 부족", "검증 제한"]},
            "source_reliability": {"score": 90, "summary": "출처가 분명합니다.", "risk": "low"},
            "claim_consistency": {"score": 70, "summary": "주장 구조가 일부 흔들립니다.", "risk": "medium"},
            "evidence_quality": {"score": 64, "summary": "근거 제시가 부족합니다.", "risk": "medium"},
            "expression_risk": {"score": 80, "summary": "표현이 과하지 않습니다.", "risk": "low"},
        }

        with patch("app.agents.ollama_agent.analyze_text", return_value=text_result) as analyze_text_mock:
            assert self.settings is not None
            assert self.payload is not None
            agent = OllamaAnalysisAgent(settings=self.settings)
            source = agent.analyze(self.payload, "source_reliability")
            claim = agent.analyze(self.payload, "claim_consistency")
            evidence = agent.analyze(self.payload, "evidence_quality")
            expression = agent.analyze(self.payload, "expression_risk")
            multimodal = agent.analyze(self.payload, "multimodal_risk")

        self.assertEqual(source.score, 90)
        self.assertEqual(claim.score, 70)
        self.assertEqual(evidence.score, 64)
        self.assertEqual(expression.score, 80)
        self.assertTrue(multimodal.summary)
        analyze_text_mock.assert_called_once()

    def test_falls_back_when_local_model_is_unavailable(self) -> None:
        unavailable = {
            "overall_summary": {"verdict": "주의 필요", "reasons": ["로컬 모델을 사용할 수 없어 분석을 건너뜁니다."]},
            "source_reliability": {"score": 50, "summary": "로컬 모델을 사용할 수 없어 분석을 건너뜁니다."},
            "claim_consistency": {"score": 50, "summary": "로컬 모델을 사용할 수 없어 분석을 건너뜁니다."},
            "evidence_quality": {"score": 50, "summary": "로컬 모델을 사용할 수 없어 분석을 건너뜁니다."},
            "expression_risk": {"score": 50, "summary": "로컬 모델을 사용할 수 없어 분석을 건너뜁니다."},
        }

        with patch("app.agents.ollama_agent.analyze_text", return_value=unavailable):
            assert self.settings is not None
            assert self.payload is not None
            agent = OllamaAnalysisAgent(settings=self.settings)
            result = agent.analyze(self.payload, "source_reliability")

        self.assertNotEqual(result.summary, "로컬 모델을 사용할 수 없어 분석을 건너뜁니다.")

    def test_returns_explicit_summary_when_local_model_falls_back(self) -> None:
        unavailable = {
            "overall_summary": {"verdict": "주의 필요", "reasons": ["로컬 모델을 사용할 수 없어 분석을 건너뜁니다."]},
            "source_reliability": {"score": 50, "summary": "로컬 모델을 사용할 수 없어 분석을 건너뜁니다."},
            "claim_consistency": {"score": 50, "summary": "로컬 모델을 사용할 수 없어 분석을 건너뜁니다."},
            "evidence_quality": {"score": 50, "summary": "로컬 모델을 사용할 수 없어 분석을 건너뜁니다."},
            "expression_risk": {"score": 50, "summary": "로컬 모델을 사용할 수 없어 분석을 건너뜁니다."},
        }

        with patch("app.agents.ollama_agent.analyze_text", return_value=unavailable):
            assert self.settings is not None
            assert self.payload is not None
            agent = OllamaAnalysisAgent(settings=self.settings)
            summary = agent.get_overall_summary(self.payload)

        self.assertEqual(summary, "로컬 모델 연결에 실패해 기본 분석 결과로 대체했습니다.")

    def test_does_not_retry_ollama_after_unavailable_result_within_same_request(self) -> None:
        unavailable = {
            "overall_summary": {"verdict": "주의 필요", "reasons": ["로컬 모델을 사용할 수 없어 분석을 건너뜁니다."]},
            "source_reliability": {"score": 50, "summary": "로컬 모델을 사용할 수 없어 분석을 건너뜁니다."},
            "claim_consistency": {"score": 50, "summary": "로컬 모델을 사용할 수 없어 분석을 건너뜁니다."},
            "evidence_quality": {"score": 50, "summary": "로컬 모델을 사용할 수 없어 분석을 건너뜁니다."},
            "expression_risk": {"score": 50, "summary": "로컬 모델을 사용할 수 없어 분석을 건너뜁니다."},
        }

        with patch("app.agents.ollama_agent.analyze_text", return_value=unavailable) as analyze_text_mock:
            assert self.settings is not None
            assert self.payload is not None
            agent = OllamaAnalysisAgent(settings=self.settings)
            _ = agent.analyze(self.payload, "source_reliability")
            _ = agent.analyze(self.payload, "claim_consistency")
            _ = agent.get_overall_summary(self.payload)

        analyze_text_mock.assert_called_once()
