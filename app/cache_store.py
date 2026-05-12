"""Small filesystem-backed TTL cache helpers for prototype integrations."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from app.schemas import CrawlerOutput


logger = logging.getLogger(__name__)


_DEFAULT_CACHE_TTL = timedelta(days=10)


def _artifact_root_dir() -> Path:
    configured = os.environ.get("ANALYSIS_ARTIFACT_ROOT", "downloaded_news").strip() or "downloaded_news"
    project_root = Path(__file__).resolve().parent.parent
    return project_root / Path(configured)


def _cache_root() -> Path:
    return _artifact_root_dir() / ".cache"


def _cache_file(namespace: str, cache_key: str) -> Path:
    digest = sha256(cache_key.encode("utf-8")).hexdigest()
    directory = _cache_root() / namespace
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{digest}.json"


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _load_ttl_payload(namespace: str, cache_key: str, ttl: timedelta) -> object | None:
    path = _cache_file(namespace, cache_key)
    if not path.is_file():
        logger.debug("TTL cache miss: file missing", extra={"event": "ttl_cache_miss", "namespace": namespace, "reason": "missing_file", "cache_file": str(path)})
        return None

    try:
        payload_obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.debug("TTL cache miss: unreadable payload", extra={"event": "ttl_cache_miss", "namespace": namespace, "reason": "invalid_payload", "cache_file": str(path)})
        return None

    if not isinstance(payload_obj, dict):
        logger.debug("TTL cache miss: payload not dict", extra={"event": "ttl_cache_miss", "namespace": namespace, "reason": "payload_not_dict", "cache_file": str(path)})
        return None
    payload: dict[str, object] = payload_obj

    cached_at_raw = payload.get("cached_at")
    value = payload.get("value")
    if not isinstance(cached_at_raw, str):
        logger.debug("TTL cache miss: cached_at missing", extra={"event": "ttl_cache_miss", "namespace": namespace, "reason": "missing_cached_at", "cache_file": str(path)})
        return None

    try:
        cached_at = datetime.fromisoformat(cached_at_raw)
    except ValueError:
        logger.debug("TTL cache miss: cached_at invalid", extra={"event": "ttl_cache_miss", "namespace": namespace, "reason": "invalid_cached_at", "cache_file": str(path)})
        return None

    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=UTC)

    if _utcnow() - cached_at > ttl:
        logger.debug("TTL cache miss: expired", extra={"event": "ttl_cache_miss", "namespace": namespace, "reason": "expired", "cache_file": str(path)})
        return None
    logger.debug("TTL cache hit", extra={"event": "ttl_cache_hit", "namespace": namespace, "cache_file": str(path)})
    return value


def _save_ttl_payload(namespace: str, cache_key: str, value: object) -> None:
    path = _cache_file(namespace, cache_key)
    payload = {
        "cached_at": _utcnow().isoformat(),
        "value": value,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.debug("TTL cache saved", extra={"event": "ttl_cache_saved", "namespace": namespace, "cache_file": str(path)})


def load_hyperbrowser_cache(normalized_url: str, analysis_id: str) -> CrawlerOutput | None:
    payload = _load_ttl_payload("hyperbrowser", normalized_url, _DEFAULT_CACHE_TTL)
    if not isinstance(payload, dict):
        return None

    try:
        cached = CrawlerOutput.model_validate(payload)
    except Exception:
        return None
    return cached.model_copy(update={"analysis_id": analysis_id})


def save_hyperbrowser_cache(normalized_url: str, crawler_output: CrawlerOutput) -> None:
    _save_ttl_payload(
        "hyperbrowser",
        normalized_url,
        crawler_output.model_dump(mode="json"),
    )


def load_local_browser_cache(normalized_url: str, analysis_id: str) -> CrawlerOutput | None:
    payload = _load_ttl_payload("local-browser", normalized_url, _DEFAULT_CACHE_TTL)
    if not isinstance(payload, dict):
        return None

    try:
        cached = CrawlerOutput.model_validate(payload)
    except Exception:
        return None
    return cached.model_copy(update={"analysis_id": analysis_id})


def save_local_browser_cache(normalized_url: str, crawler_output: CrawlerOutput) -> None:
    _save_ttl_payload(
        "local-browser",
        normalized_url,
        crawler_output.model_dump(mode="json"),
    )


def load_hive_cache(image_urls: tuple[str, ...]) -> dict[str, object] | None:
    cache_key = "\n".join(image_urls)
    payload = _load_ttl_payload("hive", cache_key, _DEFAULT_CACHE_TTL)
    if not isinstance(payload, dict):
        return None
    return dict(payload)


def save_hive_cache(image_urls: tuple[str, ...], result: dict[str, object]) -> None:
    cache_key = "\n".join(image_urls)
    _save_ttl_payload("hive", cache_key, result)


__all__ = [
    "load_hive_cache",
    "load_hyperbrowser_cache",
    "load_local_browser_cache",
    "save_hive_cache",
    "save_hyperbrowser_cache",
    "save_local_browser_cache",
]
