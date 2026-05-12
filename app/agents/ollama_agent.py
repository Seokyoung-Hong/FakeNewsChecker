"""Ollama-backed analysis agent for local-model text evaluation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from app.agents.base import AnalysisAgent
from app.agents.local_agent import LocalAgent
from app.config import OllamaSettings
from app.ollama_analyzer import analyze_text
from app.schemas import AnalysisCriterionResult, CrawlerOutput


logger = logging.getLogger(__name__)


class OllamaAnalysisAgent(AnalysisAgent):
    """Map Ollama text outputs into the app's criterion contract."""

    name: str = "ollama-analysis-agent"

    _TEXT_CRITERIA = (
        "source_reliability",
        "claim_consistency",
        "evidence_quality",
        "expression_risk",
    )
    _TEXT_UNAVAILABLE_MESSAGE = "로컬 모델을 사용할 수 없어 분석을 건너뜁니다."

    def __init__(
        self,
        settings: OllamaSettings,
        fallback_agent: AnalysisAgent | None = None,
        status_message_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._settings = settings
        self._fallback_agent = fallback_agent or LocalAgent()
        self._text_cache: dict[str, dict[str, object]] = {}
        self._fallback_analysis_ids: set[str] = set()
        self._status_message_callback = status_message_callback

    def reset_cache(self) -> None:
        self._text_cache.clear()
        self._fallback_analysis_ids.clear()
        logger.debug("Reset Ollama agent cache", extra={"event": "ollama_agent_reset_cache"})

    def set_status_message_callback(
        self,
        status_message_callback: Callable[[str], None] | None,
    ) -> None:
        self._status_message_callback = status_message_callback

    def get_overall_summary(self, crawler_output: CrawlerOutput) -> str | None:
        if crawler_output.analysis_id in self._fallback_analysis_ids:
            logger.debug("Using fallback overall summary for local model", extra={"event": "ollama_agent_fallback_summary", "analysis_id": crawler_output.analysis_id})
            return "로컬 모델 연결에 실패해 기본 분석 결과로 대체했습니다."

        text_result = self._text_result(crawler_output)
        if crawler_output.analysis_id in self._fallback_analysis_ids:
            logger.debug("Using fallback overall summary for local model", extra={"event": "ollama_agent_fallback_summary", "analysis_id": crawler_output.analysis_id})
            return "로컬 모델 연결에 실패해 기본 분석 결과로 대체했습니다."
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

    def analyze(self, crawler_output: CrawlerOutput, criterion: str) -> AnalysisCriterionResult:
        if criterion == "multimodal_risk":
            logger.debug("Ollama agent delegates multimodal risk to fallback agent", extra={"event": "ollama_agent_multimodal_fallback", "analysis_id": crawler_output.analysis_id})
            return self._fallback_agent.analyze(crawler_output, criterion)

        text_result = self._text_result(crawler_output)
        if text_result is None:
            logger.debug("Ollama agent fell back to local agent", extra={"event": "ollama_agent_text_fallback", "analysis_id": crawler_output.analysis_id, "criterion": criterion})
            return self._fallback_agent.analyze(crawler_output, criterion)

        criterion_result = self._single_result(text_result.get(criterion))
        if criterion_result is None:
            return self._fallback_agent.analyze(crawler_output, criterion)
        return criterion_result

    def _text_result(self, crawler_output: CrawlerOutput) -> dict[str, object] | None:
        analysis_id = crawler_output.analysis_id
        if analysis_id in self._fallback_analysis_ids:
            logger.debug("Ollama agent skipping retry after fallback", extra={"event": "ollama_agent_skip_retry", "analysis_id": analysis_id})
            return None
        cached = self._text_cache.get(analysis_id)
        if cached is not None:
            logger.debug("Ollama agent text cache hit", extra={"event": "ollama_agent_cache_hit", "analysis_id": analysis_id})
            return cached

        result = analyze_text(
            title=crawler_output.title,
            url=str(crawler_output.url),
            text=crawler_output.content,
            settings=self._settings,
            on_failover=self._report_failover_status,
        )
        if not isinstance(result, dict):
            self._fallback_analysis_ids.add(analysis_id)
            logger.debug("Ollama agent received non-dict result", extra={"event": "ollama_agent_invalid_result", "analysis_id": analysis_id})
            return None
        if self._is_text_unavailable_result(result):
            self._fallback_analysis_ids.add(analysis_id)
            logger.debug("Ollama agent marked unavailable result", extra={"event": "ollama_agent_unavailable_result", "analysis_id": analysis_id})
            return None

        self._text_cache[analysis_id] = result
        self._fallback_analysis_ids.discard(analysis_id)
        logger.debug("Ollama agent cached text result", extra={"event": "ollama_agent_cache_save", "analysis_id": analysis_id})
        return result

    @staticmethod
    def _build_failover_message(
        failed_host: str,
        next_host: str,
        next_model: str,
    ) -> str:
        del failed_host, next_host
        return (
            "1순위 모델 서버 연결에 실패하여 다른 서버를 찾는 중입니다. "
            f"더 가벼운 모델 {next_model}로 시도합니다"
        )

    def _report_failover_status(
        self,
        failed_host: str,
        next_host: str,
        next_model: str,
    ) -> None:
        if self._status_message_callback is None:
            return
        self._status_message_callback(
            self._build_failover_message(
                failed_host=failed_host,
                next_host=next_host,
                next_model=next_model,
            ),
        )

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

    @classmethod
    def _is_text_unavailable_result(cls, result: dict[str, object]) -> bool:
        for key in cls._TEXT_CRITERIA:
            payload = result.get(key)
            if not isinstance(payload, dict):
                return False
            payload_dict: dict[str, object] = payload
            if payload_dict.get("summary") != cls._TEXT_UNAVAILABLE_MESSAGE:
                return False
        return True


__all__ = ["OllamaAnalysisAgent"]
