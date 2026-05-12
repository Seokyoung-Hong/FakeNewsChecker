"""Crawler stage for deterministic and HyperBrowser-backed URL collection."""

# pyright: reportImplicitOverride=false

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5
from urllib.parse import urlparse, urlsplit, urlunsplit

from app.cache_store import (
    load_hyperbrowser_cache,
    load_local_browser_cache,
    save_hyperbrowser_cache,
    save_local_browser_cache,
)
from app.services.hyperbrowser_client import (
    HyperbrowserClientError,
    HyperbrowserDownloadResult,
)
from app.services.local_browser_client import (
    LocalBrowserClientError,
    LocalBrowserDownloadResult,
    _is_safe_public_target,
)
from app.schemas import CrawlerOutput, URLSubmission


logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    raw = url.strip()
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()

    userinfo = ""
    if parts.username:
        userinfo = parts.username
        if parts.password:
            userinfo += f":{parts.password}"
        userinfo += "@"

    port = parts.port
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None

    netloc = userinfo + hostname
    if port is not None:
        netloc += f":{port}"

    path = parts.path or "/"
    query = parts.query
    normalized = urlunsplit((scheme, netloc, path, query, ""))
    if normalized != raw:
        logger.debug("Canonicalized URL", extra={"event": "url_canonicalized", "original_url": raw, "canonical_url": normalized})
    return normalized


class CrawlerService(ABC):
    """Service contract for retrieving source material from URL input."""

    @abstractmethod
    def collect(self, submission: URLSubmission) -> CrawlerOutput:
        """Collect crawl artifacts for the given submission."""


class HyperbrowserCrawlerError(RuntimeError):
    """Raised when the HyperBrowser-backed crawler cannot produce valid output."""


class _HyperbrowserClientProtocol(Protocol):
    def download(self, url: str) -> HyperbrowserDownloadResult: ...


class _LocalBrowserClientProtocol(Protocol):
    def download(self, url: str) -> LocalBrowserDownloadResult: ...


class DeterministicCrawlerService(CrawlerService):
    """Offline deterministic crawler.

    It intentionally never performs any network activity and builds a stable
    synthetic payload from normalized URL structure.
    """

    def collect(self, submission: URLSubmission) -> CrawlerOutput:
        normalized_url = _normalize_url(str(submission.url))
        parsed = urlparse(normalized_url)

        analysis_id = str(uuid5(NAMESPACE_URL, normalized_url))
        host = parsed.hostname or "unknown-host"
        slug = (parsed.path.strip("/") or "stub-article").replace("/", "_")
        title = f"[stub] {host} · {slug}"

        signature = hashlib.sha1(normalized_url.encode("utf-8")).hexdigest()[:12]
        metadata_key = signature[:8]
        content = (
            "이 페이지는 실제 네트워크 요청 없이 생성된 오프라인 스텁 텍스트입니다. "
            f"요청 URL: {normalized_url}. "
            f"요약 신호: host={host}, path_depth={parsed.path.count('/')} "
            "등 안정적인 입력 신호를 기반으로 추출됩니다."
        )

        images = [
            f"stub://media/{metadata_key}/{index}.png" for index in range(2)
            if (index == 0 or "news" in normalized_url)
        ]

        output = CrawlerOutput(
            analysis_id=analysis_id,
            url=submission.url,
            title=title,
            content=content,
            images=images,
            metadata={
                "seed": signature,
                "host": host,
                "path": parsed.path,
                "query": parsed.query,
                "scheme": parsed.scheme,
            },
        )
        logger.debug("Deterministic crawler collected output", extra={"event": "crawler_collect_deterministic", "analysis_id": analysis_id, "host": host, "image_count": len(output.images)})
        return output


class HyperbrowserCrawlerService(CrawlerService):
    """Real crawler implementation backed by HyperBrowser Web Fetch."""

    _client: _HyperbrowserClientProtocol

    def __init__(self, client: _HyperbrowserClientProtocol) -> None:
        self._client = client

    def collect(self, submission: URLSubmission) -> CrawlerOutput:
        original_url = str(submission.url)
        if not _is_safe_public_target(original_url):
            raise LocalBrowserCrawlerError(
                "Local browser crawling is limited to safe public http/https targets."
            )
        normalized_url = _normalize_url(original_url)
        analysis_id = str(uuid5(NAMESPACE_URL, normalized_url))

        cached = load_hyperbrowser_cache(normalized_url, analysis_id)
        if cached is not None:
            logger.debug("Hyperbrowser crawler cache hit", extra={"event": "hyperbrowser_cache_hit", "analysis_id": analysis_id, "canonical_url": normalized_url})
            return cached.model_copy(update={"url": submission.url})
        logger.debug("Hyperbrowser crawler cache miss", extra={"event": "hyperbrowser_cache_miss", "analysis_id": analysis_id, "canonical_url": normalized_url})

        try:
            downloaded = self._client.download(original_url)
        except HyperbrowserClientError as exc:
            logger.warning("Hyperbrowser download failed", extra={"event": "hyperbrowser_collect_failed", "canonical_url": normalized_url, "exception_class": type(exc).__name__})
            raise HyperbrowserCrawlerError(str(exc)) from exc

        parsed = urlparse(downloaded.final_url or original_url)

        title = self._first_non_empty(downloaded.title, self._slug_title(parsed))
        content = self._as_string(downloaded.content)

        if not content:
            logger.warning("Hyperbrowser returned empty content", extra={"event": "hyperbrowser_collect_empty", "canonical_url": normalized_url, "analysis_id": analysis_id})
            raise HyperbrowserCrawlerError(
                "HyperBrowser crawler could not extract article content."
            )

        metadata = downloaded.metadata.copy()
        metadata.update(
            {
                "provider": str(metadata.get("provider") or "hyperbrowser"),
                "normalized_url": normalized_url,
                "requested_url": original_url,
                "final_url": downloaded.final_url,
                "host": parsed.hostname or "unknown-host",
                "path": parsed.path,
                "query": parsed.query,
                "scheme": parsed.scheme,
                "images_found": len(downloaded.images),
            }
        )

        crawler_output = CrawlerOutput(
            analysis_id=analysis_id,
            url=submission.url,
            title=title,
            content=content,
            images=downloaded.images,
            metadata=metadata,
        )
        save_hyperbrowser_cache(normalized_url, crawler_output)
        logger.debug("Hyperbrowser crawler collected output", extra={"event": "crawler_collect_hyperbrowser", "analysis_id": analysis_id, "final_url": downloaded.final_url, "image_count": len(downloaded.images), "content_length": len(crawler_output.content)})
        return crawler_output

    @staticmethod
    def _slug_title(parsed: object) -> str:
        path = getattr(parsed, "path", "") or ""
        host = getattr(parsed, "hostname", None) or "unknown-host"
        slug = (str(path).strip("/") or "article").replace("/", " ")
        return f"{host} · {slug}"

    @staticmethod
    def _as_string(value: object) -> str:
        if isinstance(value, str):
            return value.strip()
        return ""

    @classmethod
    def _first_non_empty(cls, *values: object) -> str:
        for value in values:
            text = cls._as_string(value)
            if text:
                return text
        return ""


class LocalBrowserCrawlerError(RuntimeError):
    """Raised when the local browser crawler cannot produce valid output."""


class LocalBrowserCrawlerService(CrawlerService):
    """Real crawler implementation backed by a local browser session."""

    _client: _LocalBrowserClientProtocol

    def __init__(self, client: _LocalBrowserClientProtocol) -> None:
        self._client = client

    def collect(self, submission: URLSubmission) -> CrawlerOutput:
        original_url = str(submission.url)
        if not _is_safe_public_target(original_url):
            raise LocalBrowserCrawlerError(
                "Local browser crawling is limited to safe public http/https targets."
            )
        normalized_url = _normalize_url(original_url)
        analysis_id = str(uuid5(NAMESPACE_URL, normalized_url))

        cached = load_local_browser_cache(normalized_url, analysis_id)
        if cached is not None:
            logger.debug(
                "Local browser crawler cache hit",
                extra={
                    "event": "local_browser_cache_hit",
                    "analysis_id": analysis_id,
                    "canonical_url": normalized_url,
                },
            )
            return cached.model_copy(update={"url": submission.url})
        logger.debug(
            "Local browser crawler cache miss",
            extra={
                "event": "local_browser_cache_miss",
                "analysis_id": analysis_id,
                "canonical_url": normalized_url,
            },
        )

        try:
            downloaded = self._client.download(original_url)
        except LocalBrowserClientError as exc:
            logger.warning(
                "Local browser download failed",
                extra={
                    "event": "local_browser_collect_failed",
                    "canonical_url": normalized_url,
                    "exception_class": type(exc).__name__,
                },
            )
            raise LocalBrowserCrawlerError(str(exc)) from exc

        parsed = urlparse(downloaded.final_url or original_url)
        title = HyperbrowserCrawlerService._first_non_empty(
            downloaded.title,
            HyperbrowserCrawlerService._slug_title(parsed),
        )
        content = HyperbrowserCrawlerService._as_string(downloaded.content)
        if not content:
            raise LocalBrowserCrawlerError(
                "Local browser crawler could not extract article content."
            )

        metadata = downloaded.metadata.copy()
        metadata.update(
            {
                "provider": str(metadata.get("provider") or "playwright-local"),
                "normalized_url": normalized_url,
                "requested_url": original_url,
                "final_url": downloaded.final_url,
                "host": parsed.hostname or "unknown-host",
                "path": parsed.path,
                "query": parsed.query,
                "scheme": parsed.scheme,
                "images_found": len(downloaded.images),
            }
        )

        crawler_output = CrawlerOutput(
            analysis_id=analysis_id,
            url=submission.url,
            title=title,
            content=content,
            images=downloaded.images,
            metadata=metadata,
        )
        save_local_browser_cache(normalized_url, crawler_output)
        logger.debug(
            "Local browser crawler collected output",
            extra={
                "event": "crawler_collect_local_browser",
                "analysis_id": analysis_id,
                "final_url": downloaded.final_url,
                "image_count": len(downloaded.images),
                "content_length": len(crawler_output.content),
            },
        )
        return crawler_output


class PrefixedCrawlerService(CrawlerService):
    """Wrap another crawler and namespace the produced analysis ID."""

    _inner: CrawlerService
    _prefix: str

    def __init__(self, inner: CrawlerService, prefix: str) -> None:
        normalized_prefix = prefix.strip()
        if not normalized_prefix:
            raise ValueError("prefix must not be empty")
        self._inner = inner
        self._prefix = normalized_prefix

    def collect(self, submission: URLSubmission) -> CrawlerOutput:
        result = self._inner.collect(submission)
        expected_prefix = self._prefix
        if result.analysis_id.startswith(expected_prefix):
            return result
        prefixed = result.model_copy(update={"analysis_id": expected_prefix + result.analysis_id})
        logger.debug("Prefixed crawler analysis id", extra={"event": "crawler_id_prefixed", "original_analysis_id": result.analysis_id, "prefixed_analysis_id": prefixed.analysis_id})
        return prefixed

__all__ = [
    "CrawlerService",
    "DeterministicCrawlerService",
    "HyperbrowserCrawlerError",
    "HyperbrowserCrawlerService",
    "LocalBrowserCrawlerError",
    "LocalBrowserCrawlerService",
    "PrefixedCrawlerService",
]

