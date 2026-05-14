"""Gemini multimodal image analyzer combining prompt text and saved image bytes."""

from __future__ import annotations

import json
import logging
from datetime import date
from importlib import import_module
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.prompt_loader import load_prompt
from app.schemas import CrawlerOutput


LOGGER = logging.getLogger(__name__)

_UNAVAILABLE_SUMMARY = "Gemini 멀티모달 분석을 사용할 수 없어 건너뜁니다."


def _analysis_date() -> str:
    return date.today().isoformat()


class _GeminiMultimodalPayload(BaseModel):
    score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1)
    risk: str | None = None
    signals: list[str] = Field(default_factory=list)


def _import_genai() -> Any | None:
    try:
        return import_module("google.genai")
    except ModuleNotFoundError:
        LOGGER.debug("google.genai module is not available", extra={"event": "gemini_multimodal_module_missing"})
        return None


def _fallback_result() -> dict[str, object]:
    return {"score": 50, "summary": _UNAVAILABLE_SUMMARY, "risk": "unknown"}


def analyze_multimodal(
    crawler_output: CrawlerOutput,
    hive_result: dict[str, object],
    image_paths: list[str],
) -> dict[str, object]:
    genai_module = _import_genai()
    if not GEMINI_API_KEY or genai_module is None or not image_paths:
        LOGGER.debug(
            "Gemini multimodal fallback used",
            extra={
                "event": "gemini_multimodal_fallback",
                "has_api_key": bool(GEMINI_API_KEY),
                "has_module": genai_module is not None,
                "image_count": len(image_paths),
            },
        )
        return _fallback_result()

    client = genai_module.Client(api_key=GEMINI_API_KEY)
    types_module = getattr(genai_module, "types")
    part_factory = getattr(types_module, "Part")

    prompt = load_prompt(
        "gemini_multimodal",
        title=crawler_output.title,
        url=str(crawler_output.url),
        text=crawler_output.content[:1500],
        analysis_date=_analysis_date(),
        hive_summary=str(hive_result.get("summary", "")),
        hive_score=str(hive_result.get("score", "")),
        hive_risk=str(hive_result.get("risk", "")),
    )

    contents: list[object] = [part_factory.from_text(prompt)]
    for image_path in image_paths:
        path = Path(image_path)
        image_bytes = path.read_bytes()
        mime_type = _guess_mime_type(path)
        contents.append(part_factory.from_bytes(data=image_bytes, mime_type=mime_type))

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config={"temperature": 0.1},
    )

    raw = response.text.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = json.loads(raw.replace("```json", "").replace("```", "").strip())
    validated = _GeminiMultimodalPayload.model_validate(payload)
    return validated.model_dump()


def _guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "application/octet-stream")


__all__ = ["analyze_multimodal"]
