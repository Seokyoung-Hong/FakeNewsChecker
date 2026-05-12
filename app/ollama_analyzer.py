import json
import logging

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import OllamaSettings


logger = logging.getLogger(__name__)


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


def _fallback_text_result() -> dict[str, object]:
    result: dict[str, object] = {
        criterion: {"score": 50, "summary": _UNAVAILABLE_TEXT_SUMMARY}
        for criterion in (
            "source_reliability",
            "claim_consistency",
            "evidence_quality",
            "expression_risk",
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

        payload_obj = json.loads(line)
        if not isinstance(payload_obj, dict):
            continue

        message = payload_obj.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content:
                parts.append(content)

    return "".join(parts).strip()


def analyze_text(
    title: str,
    url: str,
    text: str,
    settings: OllamaSettings,
) -> dict[str, object]:
    prompt = f"""너는 텍스트 기반 가짜뉴스 판별 도우미야. 아래 콘텐츠가 허위이거나, 과장되었거나, 오해를 유발할 가능성이 있는지 분석해줘.

제목: {title}
URL: {url}
본문:
{text[:3000]}

중요 규칙:
- 학습 데이터에 없다는 이유만으로 허위라고 단정하지 마.
- 확인 가능한 근거 부족, 주장 모순, 맥락 왜곡, 과장·선동 표현은 강한 감점 요인이다.
- 판별 대상은 기사/게시글의 가짜뉴스 가능성이다.
- 아래 JSON 형식으로만 응답해. 다른 말은 절대 하지 마.

응답 JSON 스키마:
{{
  "overall_summary": {{
    "verdict": "신뢰 가능 / 주의 필요 / 의심 필요 / 가짜뉴스 가능성 높음 중 하나",
    "reasons": ["핵심 근거 1", "핵심 근거 2", "핵심 근거 3"]
  }},
  "source_reliability": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명", "risk": "low|medium|high"}},
  "claim_consistency": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명", "risk": "low|medium|high"}},
  "evidence_quality": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명", "risk": "low|medium|high"}},
  "expression_risk": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명", "risk": "low|medium|high"}}
}}

점수 기준:
- 100 = 가짜뉴스 가능성이 매우 낮음
- 0 = 가짜뉴스 가능성이 매우 높음"""

    endpoint = settings.host.rstrip("/") + "/api/chat"
    logger.debug("Starting Ollama text analysis", extra={"event": "ollama_request_start", "host": settings.host, "model": settings.model, "url": url, "text_length": len(text)})
    body = {
        "model": settings.model,
        "stream": True,
        "format": _OllamaAnalysisPayload.model_json_schema(),
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": "Return only valid JSON matching the provided schema."},
            {"role": "user", "content": prompt},
        ],
    }

    try:
        with httpx.stream("POST", endpoint, json=body, timeout=settings.timeout_ms / 1000) as response:
            _ = response.raise_for_status()
            content = _extract_streamed_content(response)
        if not isinstance(content, str) or not content.strip():
            logger.debug("Ollama response missing content", extra={"event": "ollama_response_invalid", "reason": "content_missing", "host": settings.host, "model": settings.model})
            return _fallback_text_result()
        normalized = _clean_json_payload(content)
        validated = _OllamaAnalysisPayload.model_validate_json(normalized)
    except (httpx.HTTPError, ValueError, ValidationError, json.JSONDecodeError, TypeError) as exc:
        logger.debug("Ollama text analysis fell back", extra={"event": "ollama_request_fallback", "host": settings.host, "model": settings.model, "exception_class": type(exc).__name__})
        return _fallback_text_result()

    logger.debug("Ollama text analysis completed", extra={"event": "ollama_request_done", "host": settings.host, "model": settings.model, "payload_keys": list(validated.model_dump().keys())})
    return validated.model_dump()


__all__ = ["analyze_text"]
