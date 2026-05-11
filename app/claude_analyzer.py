import json
import logging
from importlib import import_module
from typing import Any

from app.config import GEMINI_API_KEY


LOGGER = logging.getLogger(__name__)

_UNAVAILABLE_TEXT_SUMMARY = "API 키가 없어 분석을 건너뜁니다."
_TEXT_CRITERIA_KEYS = (
    "source_reliability",
    "claim_consistency",
    "evidence_quality",
    "expression_risk",
)


def _import_genai() -> Any | None:
    try:
        return import_module("google.genai")
    except ModuleNotFoundError:
        return None


def _fallback_text_result() -> dict[str, object]:
    result: dict[str, object] = {
        criterion: {"score": 50, "summary": _UNAVAILABLE_TEXT_SUMMARY}
        for criterion in _TEXT_CRITERIA_KEYS
    }
    result["overall_summary"] = {
        "verdict": "주의 필요",
        "reasons": [_UNAVAILABLE_TEXT_SUMMARY],
    }
    return result


def _combine_payloads(*payloads: object) -> dict[str, object]:
    candidates = [payload for payload in payloads if isinstance(payload, dict)]
    if not candidates:
        return {"score": 50, "summary": _UNAVAILABLE_TEXT_SUMMARY}
    if len(candidates) == 1:
        return dict(candidates[0])

    valid_scores: list[float] = []
    for payload in candidates:
        score = payload.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            continue
        valid_scores.append(float(score))

    score = round(sum(valid_scores) / len(valid_scores)) if valid_scores else 50
    summaries = [str(payload.get("summary", "")).strip() for payload in candidates]
    summary = " ".join(summary for summary in summaries if summary) or _UNAVAILABLE_TEXT_SUMMARY

    combined: dict[str, object] = {"score": score, "summary": summary}
    for payload in candidates:
        risk = payload.get("risk")
        if isinstance(risk, str) and risk.strip():
            combined["risk"] = risk.strip()
            break
    return combined


def _legacy_text_result_bridge(payload: dict[str, object]) -> None:
    if "claim_consistency" not in payload and {"context_consistency", "claim_clarity"} <= payload.keys():
        payload["claim_consistency"] = _combine_payloads(
            payload.get("context_consistency"),
            payload.get("claim_clarity"),
        )

    if "evidence_quality" not in payload and {"evidence_match", "cross_verification"} <= payload.keys():
        payload["evidence_quality"] = _combine_payloads(
            payload.get("evidence_match"),
            payload.get("cross_verification"),
        )


def analyze_text(title: str, url: str, text: str) -> dict[str, object]:
    genai_module = _import_genai()
    if not GEMINI_API_KEY or genai_module is None:
        return _fallback_text_result()

    client = genai_module.Client(api_key=GEMINI_API_KEY)

    prompt = f"""너는 텍스트 기반 가짜뉴스 판별 도우미야. 아래 콘텐츠가 실제로 허위이거나, 과장되었거나, 오해를 유발할 가능성이 있는지 분석해줘.

제목: {title}
URL: {url}
본문:
{text[:3000]}

중요 규칙:
- 학습 데이터에 없다는 이유만으로 허위라고 단정하지 마.
- 확인 가능한 근거 부족, 주장 모순, 맥락 왜곡, 과장·선동 표현은 강한 감점 요인이다.
- 판별 대상은 "기사/게시글의 가짜뉴스 가능성"이다.
- 판별은 출처 신뢰성, 주장 일관성, 근거의 질, 표현 위험을 중심으로 해라.

각 항목 평가 기준:
- source_reliability: 출처와 작성 주체가 신뢰 가능한지, 기사 형식이 정상적인지
- claim_consistency: 제목, 본문, 핵심 주장 사이에 모순이나 맥락 왜곡이 없는지
- evidence_quality: 근거, 수치, 인용, 공식 출처, 교차 검증 가능성이 충분한지
- expression_risk: 선동/낚시성/공포 조장/단정적 표현이 많지 않은지 (적을수록 높은 점수)

아래 JSON 형식으로만 응답해. 다른 말은 절대 하지 마:
{{
  "overall_summary": {{
    "verdict": "신뢰 가능 / 주의 필요 / 의심 필요 / 가짜뉴스 가능성 높음 중 하나",
    "reasons": ["핵심 근거 1", "핵심 근거 2", "핵심 근거 3"]
  }},
  "source_reliability": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"}},
  "claim_consistency": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"}},
  "evidence_quality": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"}},
  "expression_risk": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"}}
}}

점수 기준:
- 100 = 가짜뉴스 가능성이 매우 낮음
- 0 = 가짜뉴스 가능성이 매우 높음

overall_summary의 reasons는 판정의 핵심 근거만 적어라."""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "temperature": 0.1,
            "tools": [{"google_search": {}}],
        },
    )

    raw = response.text.strip()
    LOGGER.debug("Gemini raw response: %s", raw)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        payload = json.loads(cleaned)

    if not isinstance(payload, dict):
        raise TypeError("LLM response is not a JSON object")

    _legacy_text_result_bridge(payload)
    payload.setdefault(
        "overall_summary",
        {"verdict": "주의 필요", "reasons": [_UNAVAILABLE_TEXT_SUMMARY]},
    )

    LOGGER.debug("Gemini parsed payload keys for url=%s: %s", url, list(payload.keys()))
    return payload


__all__ = ["analyze_text"]
