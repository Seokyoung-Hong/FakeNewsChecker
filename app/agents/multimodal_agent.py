"""Helper agent that prepares multimodal risk payloads for text analyzers."""

from __future__ import annotations

from collections.abc import Callable
import logging
from pathlib import Path
from urllib.parse import urljoin

from app.agents.base import AnalysisAgent
from app.agents.local_agent import LocalAgent
from app.hive_analyzer import analyze_images
from app.schemas import AnalysisCriterionResult, CrawlerOutput


logger = logging.getLogger(__name__)

MultimodalProvider = Callable[[CrawlerOutput, dict[str, object], list[str]], dict[str, object] | None]


class MultimodalAnalysisAgent(AnalysisAgent):
    """Compute multimodal context first, then hand it to text analyzers."""

    name: str = "multimodal-analysis-agent"

    def __init__(
        self,
        *,
        multimodal_provider: MultimodalProvider,
        fallback_agent: AnalysisAgent | None = None,
    ) -> None:
        self._multimodal_provider = multimodal_provider
        self._fallback_agent = fallback_agent or LocalAgent()
        self._multimodal_cache: dict[str, dict[str, object]] = {}

    def analyze(self, crawler_output: CrawlerOutput, criterion: str) -> AnalysisCriterionResult:
        if criterion != "multimodal_risk":
            return self._fallback_agent.analyze(crawler_output, criterion)
        payload = self.analyze_payload(crawler_output)
        result = self._single_result(payload, treat_unknown_as_unavailable=False)
        if result is not None:
            return result
        return self._fallback_agent.analyze(crawler_output, criterion)

    def reset_cache(self) -> None:
        self._multimodal_cache.clear()

    def analyze_payload(self, crawler_output: CrawlerOutput) -> dict[str, object] | None:
        cached = self._multimodal_cache.get(crawler_output.analysis_id)
        if cached is not None:
            logger.debug(
                "Multimodal helper cache hit",
                extra={"event": "multimodal_helper_cache_hit", "analysis_id": crawler_output.analysis_id},
            )
            return cached

        image_urls = self._preferred_image_urls(crawler_output)
        image_paths = self._persisted_image_paths(crawler_output)
        if not image_urls and not image_paths:
            logger.debug(
                "Multimodal helper skipped: no image inputs",
                extra={"event": "multimodal_helper_no_images", "analysis_id": crawler_output.analysis_id},
            )
            return None

        hive_payload: dict[str, object] | None = None
        llm_payload: dict[str, object] | None = None

        try:
            hive_payload = analyze_images(image_urls)
        except Exception:  # noqa: BLE001
            logger.debug(
                "Multimodal helper Hive raised exception",
                extra={"event": "multimodal_helper_hive_exception", "analysis_id": crawler_output.analysis_id},
            )

        try:
            llm_payload = self._multimodal_provider(crawler_output, hive_payload or {}, image_paths)
        except Exception:  # noqa: BLE001
            logger.debug(
                "Multimodal helper provider raised exception",
                extra={"event": "multimodal_helper_provider_exception", "analysis_id": crawler_output.analysis_id},
            )

        hive_result = self._single_result(hive_payload, treat_unknown_as_unavailable=True)
        llm_result = self._single_result(llm_payload, treat_unknown_as_unavailable=True)

        if hive_result is None and llm_result is None:
            logger.debug(
                "Multimodal helper unavailable from both providers",
                extra={"event": "multimodal_helper_both_unavailable", "analysis_id": crawler_output.analysis_id},
            )
            return None

        if hive_result is None:
            assert llm_result is not None
            payload = llm_result.model_dump()
        elif llm_result is None:
            payload = hive_result.model_dump()
        else:
            payload = self._merge_results(hive_result, llm_result).model_dump()

        self._multimodal_cache[crawler_output.analysis_id] = payload
        logger.debug(
            "Multimodal helper cache save",
            extra={"event": "multimodal_helper_cache_save", "analysis_id": crawler_output.analysis_id},
        )
        return payload

    @staticmethod
    def _preferred_image_urls(crawler_output: CrawlerOutput) -> list[str]:
        normalized_images = [
            item.strip()
            for item in crawler_output.images
            if isinstance(item, str) and item.strip()
        ]
        if normalized_images:
            return normalized_images

        structured = crawler_output.metadata.get("structured_data")
        image_urls: object = None
        if isinstance(structured, dict):
            image_urls = structured.get("image_urls")
        elif hasattr(structured, "image_urls"):
            image_urls = getattr(structured, "image_urls", None)

        if not isinstance(image_urls, list):
            return []

        source_url = str(crawler_output.metadata.get("source_url") or crawler_output.url)
        return [
            urljoin(source_url, item.strip())
            for item in image_urls
            if isinstance(item, str) and item.strip()
        ]

    @staticmethod
    def _persisted_image_paths(crawler_output: CrawlerOutput) -> list[str]:
        persisted = crawler_output.metadata.get("persisted_image_paths")
        if not isinstance(persisted, list):
            return []

        normalized: list[str] = []
        seen: set[str] = set()
        for raw_path in persisted:
            if not isinstance(raw_path, str):
                continue
            candidate = raw_path.strip()
            if not candidate or candidate in seen:
                continue
            path = Path(candidate)
            if not path.is_file():
                continue
            seen.add(candidate)
            normalized.append(candidate)
            if len(normalized) == 3:
                break
        return normalized

    @staticmethod
    def _single_result(
        payload: dict[str, object] | None,
        *,
        treat_unknown_as_unavailable: bool,
    ) -> AnalysisCriterionResult | None:
        if not isinstance(payload, dict):
            return None
        score = payload.get("score")
        summary = payload.get("summary")
        risk = payload.get("risk")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            return None
        if not isinstance(summary, str) or not summary.strip():
            return None
        if treat_unknown_as_unavailable and risk == "unknown":
            return None
        normalized_risk = risk.strip() if isinstance(risk, str) and risk.strip() else None
        return AnalysisCriterionResult(
            score=max(0, min(100, int(round(score)))),
            summary=summary.strip(),
            risk=normalized_risk,
        )

    @staticmethod
    def _merge_results(
        hive_result: AnalysisCriterionResult,
        llm_result: AnalysisCriterionResult,
    ) -> AnalysisCriterionResult:
        score = min(hive_result.score, llm_result.score)
        risk = MultimodalAnalysisAgent._worst_risk(hive_result.risk, llm_result.risk)
        summary = f"{llm_result.summary} Hive 위험도 분석: {hive_result.summary}".strip()
        return AnalysisCriterionResult(score=score, summary=summary, risk=risk)

    @staticmethod
    def _worst_risk(*risks: str | None) -> str | None:
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


__all__ = ["MultimodalAnalysisAgent", "MultimodalProvider"]
