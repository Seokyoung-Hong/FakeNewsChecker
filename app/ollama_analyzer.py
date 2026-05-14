import json
import logging
from datetime import date
from collections.abc import Mapping
from collections.abc import Callable
from typing import cast

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import OllamaSettings
from app.prompt_loader import load_prompt


logger = logging.getLogger(__name__)


def _analysis_date() -> str:
    return date.today().isoformat()


_UNAVAILABLE_TEXT_SUMMARY = "로컬 모델을 사용할 수 없어 분석을 건너뜁니다."


class _OllamaCriterionPayload(BaseModel):
    score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1)
    risk: str | None = None


class _OllamaOverallSummary(BaseModel):
    verdict: str = Field(min_length=1)
    reasons: list[str] = Field(default_factory=list)


class _OllamaAnalysisPayload(BaseModel):
    overall_summary: _OllamaOverallSummary
    source_reliability: _OllamaCriterionPayload
    claim_consistency: _OllamaCriterionPayload
    evidence_quality: _OllamaCriterionPayload
    expression_risk: _OllamaCriterionPayload
    multimodal_risk: _OllamaCriterionPayload | None = None


def _fallback_text_result() -> dict[str, object]:
    result: dict[str, object] = {
        criterion: {"score": 50, "summary": _UNAVAILABLE_TEXT_SUMMARY}
        for criterion in (
            "source_reliability",
            "claim_consistency",
            "evidence_quality",
            "expression_risk",
            "multimodal_risk",
        )
    }
    result["overall_summary"] = {
        "verdict": "주의 필요",
        "reasons": [_UNAVAILABLE_TEXT_SUMMARY],
    }
    return result


def _clean_json_payload(raw: str) -> str:
    return raw.replace("```json", "").replace("```", "").strip()


def _extract_streamed_content(response: httpx.Response) -> str:
    parts: list[str] = []

    for line in response.iter_lines():
        if not line:
            continue

        payload_obj = cast(object, json.loads(line))
        if not isinstance(payload_obj, Mapping):
            continue

        payload_mapping = cast(Mapping[str, object], payload_obj)
        message = payload_mapping.get("message")
        if isinstance(message, Mapping):
            message_mapping = cast(Mapping[str, object], message)
            content = message_mapping.get("content")
            if isinstance(content, str) and content:
                parts.append(content)

    return "".join(parts).strip()


def _request_text_analysis(
    *,
    host: str,
    model: str,
    title: str,
    url: str,
    text: str,
    multimodal_result: dict[str, object] | None,
    settings: OllamaSettings,
) -> dict[str, object]:
    endpoint = host.rstrip("/") + "/api/chat"
    body = {
        "model": model,
        "stream": True,
        "format": _OllamaAnalysisPayload.model_json_schema(),
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": load_prompt("structured_json_system")},
            {"role": "user", "content": _build_prompt(title=title, url=url, text=text, multimodal_result=multimodal_result)},
        ],
    }

    with httpx.stream("POST", endpoint, json=body, timeout=settings.timeout_ms / 1000) as response:
        _ = response.raise_for_status()
        content = _extract_streamed_content(response)
    if not content.strip():
        raise ValueError("content_missing")
    normalized = _clean_json_payload(content)
    validated = _OllamaAnalysisPayload.model_validate_json(normalized)
    return validated.model_dump()


def _build_prompt(*, title: str, url: str, text: str, multimodal_result: dict[str, object] | None) -> str:
    return load_prompt(
        "ollama_text",
        title=title,
        url=url,
        text=text[:3000],
        analysis_date=_analysis_date(),
        multimodal_summary=_multimodal_summary(multimodal_result),
        multimodal_score=_multimodal_score(multimodal_result),
        multimodal_risk=_multimodal_risk(multimodal_result),
    )


def analyze_text(
    title: str,
    url: str,
    text: str,
    settings: OllamaSettings,
    *,
    multimodal_result: dict[str, object] | None = None,
    on_failover: Callable[[str, str, str], None] | None = None,
) -> dict[str, object]:
    host_model_pairs = settings.host_model_pairs
    for index, (host, model) in enumerate(host_model_pairs, start=1):
        logger.debug(
            "Starting Ollama text analysis",
            extra={
                "event": "ollama_request_start",
                "host": host,
                "model": model,
                "host_index": index,
                "host_count": len(host_model_pairs),
                "url": url,
                "text_length": len(text),
            },
        )
        try:
            payload = _request_text_analysis(
                host=host,
                model=model,
                title=title,
                url=url,
                text=text,
                multimodal_result=multimodal_result,
                settings=settings,
            )
        except httpx.HTTPError as exc:
            has_next = index < len(host_model_pairs)
            if has_next:
                next_host, next_model = host_model_pairs[index]
                if on_failover is not None:
                    on_failover(host, next_host, next_model)
                logger.debug(
                    "Ollama host unavailable; attempting failover",
                    extra={
                        "event": "ollama_request_host_failover",
                        "failed_host": host,
                        "failed_model": model,
                        "next_host": next_host,
                        "next_model": next_model,
                        "host_index": index,
                        "host_count": len(host_model_pairs),
                        "exception_class": type(exc).__name__,
                    },
                )
            else:
                logger.debug(
                    "Ollama host unavailable",
                    extra={
                        "event": "ollama_request_host_unavailable",
                        "host": host,
                        "model": model,
                        "host_index": index,
                        "host_count": len(host_model_pairs),
                        "exception_class": type(exc).__name__,
                    },
                )
            continue
        except (ValueError, ValidationError, json.JSONDecodeError, TypeError) as exc:
            has_next = index < len(host_model_pairs)
            if has_next:
                next_host, next_model = host_model_pairs[index]
                if on_failover is not None:
                    on_failover(host, next_host, next_model)
                logger.debug(
                    "Ollama text analysis produced invalid structured output; attempting failover",
                    extra={
                        "event": "ollama_request_payload_failover",
                        "host": host,
                        "model": model,
                        "next_host": next_host,
                        "next_model": next_model,
                        "host_index": index,
                        "host_count": len(host_model_pairs),
                        "exception_class": type(exc).__name__,
                    },
                )
                continue
            logger.debug(
                "Ollama text analysis fell back",
                extra={
                    "event": "ollama_request_fallback",
                    "host": host,
                    "host_index": index,
                    "host_count": len(host_model_pairs),
                    "model": model,
                    "exception_class": type(exc).__name__,
                },
            )
            return _fallback_text_result()

        logger.debug(
            "Ollama text analysis completed",
            extra={
                "event": "ollama_request_done",
                "host": host,
                "host_index": index,
                "host_count": len(host_model_pairs),
                "model": model,
                "payload_keys": list(payload.keys()),
            },
        )
        _inject_multimodal_result(payload, multimodal_result)
        return payload

    logger.debug(
        "All Ollama hosts unavailable",
        extra={
            "event": "ollama_request_all_hosts_unavailable",
            "host_model_pairs": host_model_pairs,
        },
    )
    return _fallback_text_result()


def _inject_multimodal_result(payload: dict[str, object], multimodal_result: dict[str, object] | None) -> None:
    if not isinstance(multimodal_result, dict):
        return
    if not isinstance(payload.get("multimodal_risk"), dict):
        payload["multimodal_risk"] = dict(multimodal_result)


def _multimodal_summary(multimodal_result: dict[str, object] | None) -> str:
    if not isinstance(multimodal_result, dict):
        return "없음"
    summary = multimodal_result.get("summary")
    return summary.strip() if isinstance(summary, str) and summary.strip() else "없음"


def _multimodal_score(multimodal_result: dict[str, object] | None) -> str:
    if not isinstance(multimodal_result, dict):
        return ""
    score = multimodal_result.get("score")
    return str(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else ""


def _multimodal_risk(multimodal_result: dict[str, object] | None) -> str:
    if not isinstance(multimodal_result, dict):
        return ""
    risk = multimodal_result.get("risk")
    return risk.strip() if isinstance(risk, str) and risk.strip() else ""


__all__ = ["analyze_text"]
