"""Runtime configuration helpers for crawler and model selection."""

# pyright: reportMissingImports=false

from __future__ import annotations

import os
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional local convenience only
    def load_dotenv() -> bool:
        return False


_ = load_dotenv()

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
HIVE_API_KEY = os.getenv("HIVE_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


@dataclass(frozen=True)
class CrawlerSettings:
    """Environment-backed crawler configuration."""

    provider: str = "deterministic"
    hyperbrowser_api_key: str | None = None
    hyperbrowser_wait_until: str = "load"
    hyperbrowser_wait_for_ms: int = 1500
    hyperbrowser_timeout_ms: int = 30000
    artifact_root_dir: str = "downloaded_news"

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "CrawlerSettings":
        env = os.environ if environ is None else environ

        provider = env.get("CRAWLER_PROVIDER", "deterministic").strip().lower()
        if provider not in {"deterministic", "hyperbrowser"}:
            raise ValueError(
                "CRAWLER_PROVIDER must be one of 'deterministic' or 'hyperbrowser'."
            )

        hyperbrowser_api_key_raw = env.get("HYPERBROWSER_API_KEY", "")
        hyperbrowser_api_key = hyperbrowser_api_key_raw.strip() or None
        hyperbrowser_wait_until = env.get("HYPERBROWSER_WAIT_UNTIL", "load").strip().lower()
        if hyperbrowser_wait_until not in {"load", "domcontentloaded", "networkidle"}:
            raise ValueError(
                "HYPERBROWSER_WAIT_UNTIL must be one of 'load', 'domcontentloaded', or 'networkidle'."
            )

        hyperbrowser_wait_for_ms = int(env.get("HYPERBROWSER_WAIT_FOR_MS", "1500"))
        hyperbrowser_timeout_ms = int(env.get("HYPERBROWSER_TIMEOUT_MS", "30000"))
        artifact_root_dir = (
            env.get("ANALYSIS_ARTIFACT_ROOT", "downloaded_news").strip()
            or "downloaded_news"
        )

        if provider == "hyperbrowser" and not hyperbrowser_api_key:
            raise ValueError(
                "HYPERBROWSER_API_KEY is required when CRAWLER_PROVIDER=hyperbrowser."
            )

        logger.debug(
            "Resolved crawler settings",
            extra={
                "event": "crawler_settings_resolved",
                "provider": provider,
                "hyperbrowser_has_api_key": bool(hyperbrowser_api_key),
                "wait_until": hyperbrowser_wait_until,
                "wait_for_ms": hyperbrowser_wait_for_ms,
                "timeout_ms": hyperbrowser_timeout_ms,
                "artifact_root_dir": str(Path(artifact_root_dir)),
            },
        )
        return cls(
            provider=provider,
            hyperbrowser_api_key=hyperbrowser_api_key,
            hyperbrowser_wait_until=hyperbrowser_wait_until,
            hyperbrowser_wait_for_ms=hyperbrowser_wait_for_ms,
            hyperbrowser_timeout_ms=hyperbrowser_timeout_ms,
            artifact_root_dir=str(Path(artifact_root_dir)),
        )


@dataclass(frozen=True)
class OllamaSettings:
    """Environment-backed local Ollama configuration."""

    host: str = "http://localhost:11434"
    model: str = "qwen3.5"
    timeout_ms: int = 240000

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "OllamaSettings":
        env = os.environ if environ is None else environ

        host = env.get("OLLAMA_HOST", "http://localhost:11434").strip()
        if not host:
            raise ValueError("OLLAMA_HOST must not be empty.")

        model = env.get("OLLAMA_MODEL", "qwen3.5").strip()
        if not model:
            raise ValueError("OLLAMA_MODEL must not be empty.")

        timeout_ms = int(env.get("OLLAMA_TIMEOUT_MS", "240000"))
        if timeout_ms <= 0:
            raise ValueError("OLLAMA_TIMEOUT_MS must be a positive integer.")

        logger.debug(
            "Resolved Ollama settings",
            extra={
                "event": "ollama_settings_resolved",
                "host": host,
                "model": model,
                "timeout_ms": timeout_ms,
            },
        )
        return cls(host=host, model=model, timeout_ms=timeout_ms)


__all__ = [
    "ANTHROPIC_API_KEY",
    "HIVE_API_KEY",
    "GEMINI_API_KEY",
    "CrawlerSettings",
    "OllamaSettings",
]
