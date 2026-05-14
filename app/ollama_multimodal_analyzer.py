"""Ollama multimodal image analyzer using /api/chat with base64 images."""

from __future__ import annotations

import base64
import json
import logging
from datetime import date
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import OllamaSettings
from app.prompt_loader import load_prompt
from app.schemas import CrawlerOutput


logger = logging.getLogger(__name__)


def _analysis_date() -> str:
    return date.today().isoformat()

_UNAVAILABLE_SUMMARY = "로컬 멀티모달 모델을 사용할 수 없어 분석을 건너뜁니다."


class _OllamaMultimodalPayload(BaseModel):
    score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1)
    risk: str | None = None
    signals: list[str] = Field(default_factory=list)


def _fallback_result() -> dict[str, object]:
    return {"score": 50, "summary": _UNAVAILABLE_SUMMARY, "risk": "unknown"}


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
            content = message.get("content")
            if isinstance(content, str) and content:
                parts.append(content)
    return "".join(parts).strip()


def _request_multimodal_analysis(
    *,
    host: str,
    model: str,
    crawler_output: CrawlerOutput,
    hive_result: dict[str, object],
    image_paths: list[str],
    settings: OllamaSettings,
) -> dict[str, object]:
    endpoint = host.rstrip("/") + "/api/chat"
    prompt = load_prompt(
        "ollama_multimodal",
        title=crawler_output.title,
        url=str(crawler_output.url),
        text=crawler_output.content[:1500],
        analysis_date=_analysis_date(),
        hive_summary=str(hive_result.get("summary", "")),
        hive_score=str(hive_result.get("score", "")),
        hive_risk=str(hive_result.get("risk", "")),
    )
    images = [base64.b64encode(Path(path).read_bytes()).decode("utf-8") for path in image_paths]
    body = {
        "model": model,
        "stream": True,
        "format": _OllamaMultimodalPayload.model_json_schema(),
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": load_prompt("structured_json_system")},
            {"role": "user", "content": prompt, "images": images},
        ],
    }
    with httpx.stream("POST", endpoint, json=body, timeout=settings.timeout_ms / 1000) as response:
        _ = response.raise_for_status()
        content = _extract_streamed_content(response)
    if not content.strip():
        raise ValueError("content_missing")
    validated = _OllamaMultimodalPayload.model_validate_json(_clean_json_payload(content))
    return validated.model_dump()


def analyze_multimodal(
    crawler_output: CrawlerOutput,
    hive_result: dict[str, object],
    image_paths: list[str],
    settings: OllamaSettings,
    *,
    on_failover: Callable[[str, str, str], None] | None = None,
) -> dict[str, object]:
    if not image_paths:
        return _fallback_result()

    host_model_pairs = settings.host_model_pairs
    for index, (host, model) in enumerate(host_model_pairs, start=1):
        try:
            return _request_multimodal_analysis(
                host=host,
                model=model,
                crawler_output=crawler_output,
                hive_result=hive_result,
                image_paths=image_paths,
                settings=settings,
            )
        except httpx.HTTPError:
            if index < len(host_model_pairs):
                next_host, next_model = host_model_pairs[index]
                if on_failover is not None:
                    on_failover(host, next_host, next_model)
                continue
        except (ValueError, ValidationError, json.JSONDecodeError, TypeError):
            if index < len(host_model_pairs):
                next_host, next_model = host_model_pairs[index]
                if on_failover is not None:
                    on_failover(host, next_host, next_model)
                continue
            return _fallback_result()

    return _fallback_result()


__all__ = ["analyze_multimodal"]
