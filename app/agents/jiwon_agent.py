"""Jiwon-backed analysis agent integrating Gemini and Hive results."""

from __future__ import annotations

from collections.abc import Sequence

from app.agents.base import AnalysisAgent
from app.agents.local_agent import LocalAgent
from app.claude_analyzer import analyze_text
from app.hive_analyzer import analyze_images
from app.schemas import AnalysisCriterionResult, CrawlerOutput


class JiwonAnalysisAgent(AnalysisAgent):
    """Map Gemini/Hive analysis outputs into the app's criterion contract."""

    name: str = "jiwon-analysis-agent"

    _TEXT_CRITERIA = (
        "source_reliability",
        "claim_consistency",
        "evidence_quality",
        "expression_risk",
    )
    _TEXT_UNAVAILABLE_MESSAGE = "API 키가 없어 분석을 건너뜁니다."

    def __init__(self, fallback_agent: AnalysisAgent | None = None) -> None:
        self._fallback_agent = fallback_agent or LocalAgent()
        self._text_cache: dict[str, dict[str, object]] = {}
        self._image_cache: dict[str, dict[str, object]] = {}

    def reset_cache(self) -> None:
        self._text_cache.clear()
        self._image_cache.clear()

    def get_overall_summary(self, crawler_output: CrawlerOutput) -> str | None:
        text_result = self._text_result(crawler_output)
        if text_result is None:
            return None

        overall = text_result.get("overall_summary")
        if not isinstance(overall, dict):
            return None

        verdict = overall.get("verdict")
        reasons = overall.get("reasons")
        if not isinstance(verdict, str) or not verdict.strip():
            return None

        if isinstance(reasons, list):
            normalized = [str(reason).strip() for reason in reasons if str(reason).strip()]
            if normalized:
                return "LLM 핵심 근거: " + " / ".join(normalized)
        return f"LLM 요약 의견: {verdict.strip()}"

    def analyze(
        self,
        crawler_output: CrawlerOutput,
        criterion: str,
    ) -> AnalysisCriterionResult:
        if criterion == "multimodal_risk":
            return self._multimodal_result(crawler_output)

        text_result = self._text_result(crawler_output)
        if text_result is None:
            return self._fallback_agent.analyze(crawler_output, criterion)

        if criterion == "source_reliability":
            criterion_result = self._single_result(text_result.get("source_reliability"))
        elif criterion == "expression_risk":
            criterion_result = self._single_result(text_result.get("expression_risk"))
        elif criterion == "claim_consistency":
            criterion_result = self._single_or_combined_result(
                text_result,
                primary_key="claim_consistency",
                legacy_keys=("context_consistency", "claim_clarity"),
                fallback_summary="제목·본문·주장 정합성을 종합해 평가했습니다.",
            )
        elif criterion == "evidence_quality":
            criterion_result = self._single_or_combined_result(
                text_result,
                primary_key="evidence_quality",
                legacy_keys=("evidence_match", "cross_verification"),
                fallback_summary="근거와 교차 검증 가능성을 종합해 평가했습니다.",
            )
        else:
            return self._fallback_agent.analyze(crawler_output, criterion)

        if criterion_result is None:
            return self._fallback_agent.analyze(crawler_output, criterion)
        return criterion_result

    def _text_result(self, crawler_output: CrawlerOutput) -> dict[str, object] | None:
        analysis_id = crawler_output.analysis_id
        cached = self._text_cache.get(analysis_id)
        if cached is not None:
            return cached

        try:
            result = analyze_text(
                title=crawler_output.title,
                url=str(crawler_output.url),
                text=crawler_output.content,
            )
        except Exception:  # noqa: BLE001
            return None

        if not isinstance(result, dict):
            return None
        if self._is_text_unavailable_result(result):
            return None

        self._text_cache[analysis_id] = result
        return result

    def _multimodal_result(self, crawler_output: CrawlerOutput) -> AnalysisCriterionResult:
        analysis_id = crawler_output.analysis_id
        cached = self._image_cache.get(analysis_id)
        if cached is None:
            try:
                result = analyze_images(self._preferred_image_urls(crawler_output))
            except Exception:  # noqa: BLE001
                return self._fallback_agent.analyze(crawler_output, "multimodal_risk")

            if not isinstance(result, dict):
                return self._fallback_agent.analyze(crawler_output, "multimodal_risk")
            if self._is_image_unavailable_result(result):
                return self._fallback_agent.analyze(crawler_output, "multimodal_risk")
            self._image_cache[analysis_id] = result
            cached = result

        criterion_result = self._single_result(cached)
        if criterion_result is None:
            return self._fallback_agent.analyze(crawler_output, "multimodal_risk")
        return criterion_result

    def _single_result(self, payload: object) -> AnalysisCriterionResult | None:
        if not isinstance(payload, dict):
            return None

        score = payload.get("score")
        summary = payload.get("summary")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            return None
        if not isinstance(summary, str) or not summary.strip():
            return None

        risk = payload.get("risk")
        normalized_risk = risk.strip() if isinstance(risk, str) and risk.strip() else None
        bounded_score = max(0, min(100, int(round(score))))
        return AnalysisCriterionResult(
            score=bounded_score,
            summary=summary.strip(),
            risk=normalized_risk,
        )

    def _single_or_combined_result(
        self,
        result: dict[str, object],
        *,
        primary_key: str,
        legacy_keys: tuple[str, str],
        fallback_summary: str,
    ) -> AnalysisCriterionResult | None:
        primary = self._single_result(result.get(primary_key))
        if primary is not None:
            return primary

        legacy_first = self._single_result(result.get(legacy_keys[0]))
        legacy_second = self._single_result(result.get(legacy_keys[1]))
        return self._combine_results(
            legacy_first,
            legacy_second,
            fallback_summary=fallback_summary,
        )

    def _combine_results(
        self,
        first: AnalysisCriterionResult | None,
        second: AnalysisCriterionResult | None,
        *,
        fallback_summary: str,
    ) -> AnalysisCriterionResult | None:
        results = [result for result in (first, second) if result is not None]
        if not results:
            return None

        score = round(sum(result.score for result in results) / len(results))
        summaries = [result.summary for result in results if result.summary]
        summary = " ".join(summaries) if summaries else fallback_summary
        risks = [result.risk for result in results if result.risk]
        risk = self._worst_risk(risks)
        return AnalysisCriterionResult(score=score, summary=summary, risk=risk)

    @staticmethod
    def _worst_risk(risks: Sequence[str | None]) -> str | None:
        severity = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
        selected: str | None = None
        selected_score = -1
        for risk in risks:
            if risk is None:
                continue
            score = severity.get(risk, 0)
            if score > selected_score:
                selected = risk
                selected_score = score
        return selected

    @classmethod
    def _is_text_unavailable_result(cls, result: dict[str, object]) -> bool:
        for key in cls._TEXT_CRITERIA:
            payload = result.get(key)
            if not isinstance(payload, dict):
                return False
            if payload.get("summary") != cls._TEXT_UNAVAILABLE_MESSAGE:
                return False
        return True

    @staticmethod
    def _is_image_unavailable_result(result: dict[str, object]) -> bool:
        summary = result.get("summary")
        if not isinstance(summary, str):
            return False
        if "Hive API 키가 없어 이미지 분석을 건너뜁니다." in summary:
            return True
        if "이미지 분석에 실패했습니다." in summary:
            return True
        risk = result.get("risk")
        return risk == "unknown"

    @staticmethod
    def _preferred_image_urls(crawler_output: CrawlerOutput) -> list[str]:
        structured = crawler_output.metadata.get("structured_data")
        image_urls: object = None
        if isinstance(structured, dict):
            image_urls = structured.get("image_urls")
        else:
            image_urls = getattr(structured, "image_urls", None)

        if isinstance(image_urls, list):
            normalized = [item.strip() for item in image_urls if isinstance(item, str) and item.strip()]
            if normalized:
                return normalized
        return list(crawler_output.images)


__all__ = ["JiwonAnalysisAgent"]
