import json
import logging
from datetime import date
from importlib import import_module
from typing import Any

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.prompt_loader import load_prompt


LOGGER = logging.getLogger(__name__)

_UNAVAILABLE_TEXT_SUMMARY = "API 키가 없어 분석을 건너뜁니다."
_TEXT_CRITERIA_KEYS = (
    "source_reliability",
    "claim_consistency",
    "evidence_quality",
    "expression_risk",
)


def _analysis_date() -> str:
    return date.today().isoformat()


def _import_genai() -> Any | None:
    try:
        return import_module("google.genai")
    except ModuleNotFoundError:
        LOGGER.debug("google.genai module is not available", extra={"event": "gemini_module_missing"})
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


def analyze_text(
    title: str,
    url: str,
    text: str,
    multimodal_result: dict[str, object] | None = None,
) -> dict[str, object]:
    return analyze_text_with_multimodal(
        title=title,
        url=url,
        text=text,
        multimodal_result=multimodal_result,
    )


def analyze_text_with_multimodal(
    title: str,
    url: str,
    text: str,
    multimodal_result: dict[str, object] | None,
) -> dict[str, object]:
    genai_module = _import_genai()
    if not GEMINI_API_KEY or genai_module is None:
        LOGGER.debug("Gemini text analysis fallback used", extra={"event": "gemini_fallback", "has_api_key": bool(GEMINI_API_KEY), "has_module": genai_module is not None})
        return _fallback_text_result()

    client = genai_module.Client(api_key=GEMINI_API_KEY)

    prompt = load_prompt(
        "gemini_text",
        title=title,
        url=url,
        text=text[:3000],
        analysis_date=_analysis_date(),
        multimodal_summary=_multimodal_summary(multimodal_result),
        multimodal_score=_multimodal_score(multimodal_result),
        multimodal_risk=_multimodal_risk(multimodal_result),
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "temperature": 0.1,
            "tools": [{"google_search": {}}],
        },
    )

    raw = response.text.strip()
    LOGGER.debug("Gemini response received", extra={"event": "gemini_response_received", "url": url, "response_length": len(raw)})

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        payload = json.loads(cleaned)

    if not isinstance(payload, dict):
        raise TypeError("LLM response is not a JSON object")

    _legacy_text_result_bridge(payload)
    _inject_multimodal_result(payload, multimodal_result)
    payload.setdefault(
        "overall_summary",
        {"verdict": "주의 필요", "reasons": [_UNAVAILABLE_TEXT_SUMMARY]},
    )

    LOGGER.debug("Gemini parsed payload", extra={"event": "gemini_payload_parsed", "url": url, "payload_keys": list(payload.keys())})
    return payload


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


__all__ = ["analyze_text", "analyze_text_with_multimodal"]
