"""Runtime configuration helpers for crawler and model selection."""

# pyright: reportMissingImports=false

from __future__ import annotations

import os
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from itertools import zip_longest

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional local convenience only
    def load_dotenv() -> bool:
        return False


_ = load_dotenv()

logger = logging.getLogger(__name__)


def _as_bool(value: str, *, default: bool) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Boolean environment value is invalid: {value!r}")

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
    local_crawler_backend: str = "playwright"
    local_crawler_headless: bool = True
    local_crawler_wait_until: str = "networkidle"
    local_crawler_wait_for_ms: int = 1000
    local_crawler_timeout_ms: int = 45000
    local_crawler_block_media: bool = True
    local_crawler_user_agent: str = "FakeNewsChecker/1.0"
    local_crawler_mcp_enabled: bool = False
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
        local_crawler_backend = env.get("LOCAL_CRAWLER_BACKEND", "playwright").strip().lower() or "playwright"
        if local_crawler_backend not in {"playwright"}:
            raise ValueError("LOCAL_CRAWLER_BACKEND must be 'playwright'.")

        local_crawler_wait_until = env.get("LOCAL_CRAWLER_WAIT_UNTIL", "networkidle").strip().lower()
        if local_crawler_wait_until not in {"load", "domcontentloaded", "networkidle", "commit"}:
            raise ValueError(
                "LOCAL_CRAWLER_WAIT_UNTIL must be one of 'load', 'domcontentloaded', 'networkidle', or 'commit'."
            )

        local_crawler_headless = _as_bool(env.get("LOCAL_CRAWLER_HEADLESS", "true"), default=True)
        local_crawler_block_media = _as_bool(env.get("LOCAL_CRAWLER_BLOCK_MEDIA", "true"), default=True)
        local_crawler_mcp_enabled = _as_bool(env.get("LOCAL_CRAWLER_MCP_ENABLED", "false"), default=False)
        local_crawler_wait_for_ms = int(env.get("LOCAL_CRAWLER_WAIT_FOR_MS", "1000"))
        local_crawler_timeout_ms = int(env.get("LOCAL_CRAWLER_TIMEOUT_MS", "45000"))
        local_crawler_user_agent = env.get("LOCAL_CRAWLER_USER_AGENT", "FakeNewsChecker/1.0").strip() or "FakeNewsChecker/1.0"
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
                "local_crawler_backend": local_crawler_backend,
                "local_crawler_headless": local_crawler_headless,
                "local_crawler_wait_until": local_crawler_wait_until,
                "local_crawler_wait_for_ms": local_crawler_wait_for_ms,
                "local_crawler_timeout_ms": local_crawler_timeout_ms,
                "local_crawler_block_media": local_crawler_block_media,
                "local_crawler_mcp_enabled": local_crawler_mcp_enabled,
                "artifact_root_dir": str(Path(artifact_root_dir)),
            },
        )
        return cls(
            provider=provider,
            hyperbrowser_api_key=hyperbrowser_api_key,
            hyperbrowser_wait_until=hyperbrowser_wait_until,
            hyperbrowser_wait_for_ms=hyperbrowser_wait_for_ms,
            hyperbrowser_timeout_ms=hyperbrowser_timeout_ms,
            local_crawler_backend=local_crawler_backend,
            local_crawler_headless=local_crawler_headless,
            local_crawler_wait_until=local_crawler_wait_until,
            local_crawler_wait_for_ms=local_crawler_wait_for_ms,
            local_crawler_timeout_ms=local_crawler_timeout_ms,
            local_crawler_block_media=local_crawler_block_media,
            local_crawler_user_agent=local_crawler_user_agent,
            local_crawler_mcp_enabled=local_crawler_mcp_enabled,
            artifact_root_dir=str(Path(artifact_root_dir)),
        )


@dataclass(frozen=True)
class OllamaSettings:
    """Environment-backed local Ollama configuration."""

    host: str = "http://localhost:11434"
    fallback_hosts: tuple[str, ...] = ()
    fallback_models: tuple[str, ...] = ()
    model: str = "qwen3.5"
    timeout_ms: int = 240000

    @property
    def hosts(self) -> tuple[str, ...]:
        ordered_hosts: list[str] = []
        seen: set[str] = set()
        for candidate in (self.host, *self.fallback_hosts):
            normalized = candidate.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered_hosts.append(normalized)
        return tuple(ordered_hosts)

    @property
    def host_model_pairs(self) -> tuple[tuple[str, str], ...]:
        models = (self.model, *self.fallback_models)
        host_model_pairs: list[tuple[str, str]] = []
        for host, model in zip_longest(self.hosts, models, fillvalue=self.model):
            host_model_pairs.append((host, model))
        return tuple(host_model_pairs)

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "OllamaSettings":
        env = os.environ if environ is None else environ

        host = env.get("OLLAMA_HOST", "http://localhost:11434").strip()
        if not host:
            raise ValueError("OLLAMA_HOST must not be empty.")

        fallback_hosts_raw = env.get("OLLAMA_FALLBACK_HOSTS", "")
        fallback_hosts: list[str] = []
        if fallback_hosts_raw.strip():
            for raw_candidate in fallback_hosts_raw.split(","):
                candidate = raw_candidate.strip()
                if not candidate:
                    raise ValueError("OLLAMA_FALLBACK_HOSTS must not contain empty hosts.")
                fallback_hosts.append(candidate)

        fallback_models_raw = env.get("OLLAMA_FALLBACK_MODELS", "")
        fallback_models: list[str] = []
        if fallback_models_raw.strip():
            for raw_candidate in fallback_models_raw.split(","):
                candidate = raw_candidate.strip()
                if not candidate:
                    raise ValueError("OLLAMA_FALLBACK_MODELS must not contain empty model names.")
                fallback_models.append(candidate)

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
            "fallback_hosts": tuple(fallback_hosts),
            "fallback_models": tuple(fallback_models),
            "ordered_hosts": tuple(dict.fromkeys([host, *fallback_hosts])),
            "fallback_count": len(fallback_hosts),
            "fallback_model_count": len(fallback_models),
            "model": model,
            "timeout_ms": timeout_ms,
        },
        )
        return cls(
            host=host,
            fallback_hosts=tuple(fallback_hosts),
            fallback_models=tuple(fallback_models),
            model=model,
            timeout_ms=timeout_ms,
        )


__all__ = [
    "ANTHROPIC_API_KEY",
    "HIVE_API_KEY",
    "GEMINI_API_KEY",
    "CrawlerSettings",
    "OllamaSettings",
]
