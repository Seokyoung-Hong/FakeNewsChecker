from __future__ import annotations

import unittest
from unittest.mock import patch

from app.agents.jiwon_agent import JiwonAnalysisAgent
from app.schemas import CrawlerOutput, URLSubmission


class JiwonAnalysisAgentTests(unittest.TestCase):
    payload: CrawlerOutput | None = None

    def setUp(self) -> None:
        self.payload = CrawlerOutput(
            analysis_id="analysis-1",
            url=URLSubmission.model_validate({"url": "https://example.com/article"}).url,
            title="기사 제목",
            content="기사 본문",
            images=["https://cdn.example.com/image.jpg"],
            metadata={},
        )

    def test_maps_text_and_image_results_into_current_criteria(self) -> None:
        text_result = {
            "overall_summary": {"verdict": "주의 필요", "reasons": ["근거 부족", "검증 제한"]},
            "source_reliability": {"score": 90, "summary": "출처가 분명합니다.", "risk": "low"},
            "expression_risk": {"score": 70, "summary": "표현이 과하지 않습니다.", "risk": "medium"},
            "context_consistency": {"score": 80, "summary": "제목과 본문이 맞습니다.", "risk": "low"},
            "claim_clarity": {"score": 60, "summary": "주장은 비교적 명확합니다.", "risk": "medium"},
            "evidence_match": {"score": 88, "summary": "근거가 본문과 맞습니다.", "risk": "low"},
            "cross_verification": {"score": 52, "summary": "교차 검증은 제한적입니다.", "risk": "medium"},
        }
        image_result = {"score": 77, "summary": "이미지 조작 가능성은 낮습니다.", "risk": "low"}

        with patch(
            "app.agents.jiwon_agent.analyze_text",
            return_value=text_result,
        ) as analyze_text_mock, patch(
            "app.agents.jiwon_agent.analyze_images",
            return_value=image_result,
        ) as analyze_images_mock:
            agent = JiwonAnalysisAgent()
            payload = self.payload
            assert payload is not None

            source = agent.analyze(payload, "source_reliability")
            claim = agent.analyze(payload, "claim_consistency")
            evidence = agent.analyze(payload, "evidence_quality")
            expression = agent.analyze(payload, "expression_risk")
            multimodal = agent.analyze(payload, "multimodal_risk")

        self.assertEqual(source.score, 90)
        self.assertEqual(expression.score, 70)
        self.assertEqual(claim.score, 70)
        self.assertIn("제목과 본문", claim.summary)
        self.assertEqual(evidence.score, 70)
        self.assertIn("근거가 본문", evidence.summary)
        self.assertEqual(multimodal.score, 77)
        analyze_text_mock.assert_called_once()
        analyze_images_mock.assert_called_once()

    def test_prefers_new_fake_news_criterion_keys_and_summary(self) -> None:
        text_result = {
            "overall_summary": {"verdict": "의심 필요", "reasons": ["검증 근거 부족"]},
            "source_reliability": {"score": 92, "summary": "도메인 신뢰성이 높습니다.", "risk": "low"},
            "claim_consistency": {"score": 44, "summary": "주장 구조가 흔들립니다.", "risk": "high"},
            "evidence_quality": {"score": 38, "summary": "근거가 부족합니다.", "risk": "high"},
            "expression_risk": {"score": 80, "summary": "선동적 표현이 낮습니다.", "risk": "low"},
        }

        with patch("app.agents.jiwon_agent.analyze_text", return_value=text_result):
            agent = JiwonAnalysisAgent()
            payload = self.payload
            assert payload is not None
            claim = agent.analyze(payload, "claim_consistency")
            evidence = agent.analyze(payload, "evidence_quality")
            summary = agent.get_overall_summary(payload)

        self.assertEqual(claim.score, 44)
        self.assertEqual(evidence.score, 38)
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertIn("검증 근거 부족", summary)

    def test_falls_back_when_partial_text_response_omits_criterion(self) -> None:
        text_result = {
            "overall_summary": {"verdict": "주의 필요", "reasons": ["근거 부족"]},
            "source_reliability": {"score": 92, "summary": "도메인 신뢰성이 높습니다.", "risk": "low"},
            "claim_consistency": {"score": 44, "summary": "주장 구조가 흔들립니다.", "risk": "high"},
            "expression_risk": {"score": 80, "summary": "선동적 표현이 낮습니다.", "risk": "low"},
        }

        with patch("app.agents.jiwon_agent.analyze_text", return_value=text_result):
            agent = JiwonAnalysisAgent()
            payload = self.payload
            assert payload is not None
            result = agent.analyze(payload, "evidence_quality")

        self.assertNotEqual(result.summary, "API 키가 없어 분석을 건너뜁니다.")

    def test_falls_back_when_hive_analysis_fails(self) -> None:
        with patch(
            "app.agents.jiwon_agent.analyze_images",
            return_value={
                "score": 50,
                "summary": "이미지 분석에 실패했습니다. (429: rate limit)",
                "risk": "unknown",
            },
        ):
            agent = JiwonAnalysisAgent()
            payload = self.payload
            assert payload is not None
            result = agent.analyze(payload, "multimodal_risk")

        self.assertNotIn("이미지 분석에 실패했습니다.", result.summary)

    def test_uses_new_fake_news_criterion_keys(self) -> None:
        text_result = {
            "source_reliability": {"score": 92, "summary": "도메인 신뢰성이 높습니다.", "risk": "low"},
            "claim_consistency": {"score": 88, "summary": "주장 정합성이 높습니다.", "risk": "low"},
            "evidence_quality": {"score": 77, "summary": "근거 제시가 비교적 충분합니다.", "risk": "medium"},
            "expression_risk": {"score": 80, "summary": "선동적 표현이 낮습니다.", "risk": "low"},
        }

        with patch("app.agents.jiwon_agent.analyze_text", return_value=text_result):
            agent = JiwonAnalysisAgent()
            payload = self.payload
            assert payload is not None

            claim = agent.analyze(payload, "claim_consistency")
            evidence = agent.analyze(payload, "evidence_quality")

        self.assertEqual(claim.score, 88)
        self.assertIn("주장 정합성", claim.summary)
        self.assertEqual(evidence.score, 77)
        self.assertIn("근거", evidence.summary)

    def test_falls_back_when_text_result_is_invalid(self) -> None:
        with patch("app.agents.jiwon_agent.analyze_text", return_value="broken"):
            agent = JiwonAnalysisAgent()
            payload = self.payload
            assert payload is not None
            result = agent.analyze(payload, "source_reliability")

        self.assertIsInstance(result.score, int)
        self.assertTrue(result.summary)

    def test_falls_back_when_text_api_key_is_unavailable(self) -> None:
        unavailable = {
            "source_reliability": {"score": 50, "summary": "API 키가 없어 분석을 건너뜁니다."},
            "claim_consistency": {"score": 50, "summary": "API 키가 없어 분석을 건너뜁니다."},
            "evidence_quality": {"score": 50, "summary": "API 키가 없어 분석을 건너뜁니다."},
            "expression_risk": {"score": 50, "summary": "API 키가 없어 분석을 건너뜁니다."},
            "multimodal_risk": {"score": 50, "summary": "API 키가 없어 분석을 건너뜁니다."},
        }

        with patch("app.agents.jiwon_agent.analyze_text", return_value=unavailable):
            agent = JiwonAnalysisAgent()
            payload = self.payload
            assert payload is not None
            result = agent.analyze(payload, "source_reliability")

        self.assertNotEqual(result.summary, "API 키가 없어 분석을 건너뜁니다.")

    def test_falls_back_when_image_api_key_is_unavailable(self) -> None:
        with patch(
            "app.agents.jiwon_agent.analyze_images",
            return_value={
                "score": 50,
                "summary": "Hive API 키가 없어 이미지 분석을 건너뜁니다.",
                "risk": "unknown",
            },
        ):
            agent = JiwonAnalysisAgent()
            payload = self.payload
            assert payload is not None
            result = agent.analyze(payload, "multimodal_risk")

        self.assertNotEqual(result.summary, "Hive API 키가 없어 이미지 분석을 건너뜁니다.")

    def test_prefers_normalized_crawler_images_over_raw_structured_urls(self) -> None:
        payload = CrawlerOutput(
            analysis_id="analysis-1",
            url=URLSubmission.model_validate({"url": "https://example.com/article"}).url,
            title="기사 제목",
            content="기사 본문",
            images=["https://cdn.example.com/absolute-image.jpg"],
            metadata={
                "source_url": "https://example.com/article",
                "structured_data": {"image_urls": ["thumb.jpg"]},
            },
        )

        with patch(
            "app.agents.jiwon_agent.analyze_images",
            return_value={"score": 77, "summary": "이미지 조작 가능성은 낮습니다.", "risk": "low"},
        ) as analyze_images_mock:
            agent = JiwonAnalysisAgent()
            _ = agent.analyze(payload, "multimodal_risk")

        analyze_images_mock.assert_called_once_with(["https://cdn.example.com/absolute-image.jpg"])


if __name__ == "__main__":
    unittest.main()
