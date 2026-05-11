"""Crawler stage for deterministic and HyperBrowser-backed URL collection."""

# pyright: reportImplicitOverride=false

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5
from urllib.parse import urlparse

from app.services.hyperbrowser_client import (
    HyperbrowserClientError,
    HyperbrowserDownloadResult,
)
from app.schemas import CrawlerOutput, URLSubmission


def _normalize_url(url: str) -> str:
    return url.strip().lower().rstrip("/")


class CrawlerService(ABC):
    """Service contract for retrieving source material from URL input."""

    @abstractmethod
    def collect(self, submission: URLSubmission) -> CrawlerOutput:
        """Collect crawl artifacts for the given submission."""


class HyperbrowserCrawlerError(RuntimeError):
    """Raised when the HyperBrowser-backed crawler cannot produce valid output."""


class _HyperbrowserClientProtocol(Protocol):
    def download(self, url: str) -> HyperbrowserDownloadResult: ...


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

        return CrawlerOutput(
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


class HyperbrowserCrawlerService(CrawlerService):
    """Real crawler implementation backed by HyperBrowser Web Fetch."""

    _client: _HyperbrowserClientProtocol

    def __init__(self, client: _HyperbrowserClientProtocol) -> None:
        self._client = client

    def collect(self, submission: URLSubmission) -> CrawlerOutput:
        original_url = str(submission.url)
        normalized_url = _normalize_url(original_url)
        analysis_id = str(uuid5(NAMESPACE_URL, normalized_url))

        try:
            downloaded = self._client.download(original_url)
        except HyperbrowserClientError as exc:
            raise HyperbrowserCrawlerError(str(exc)) from exc

        parsed = urlparse(downloaded.final_url or original_url)

        title = self._first_non_empty(downloaded.title, self._slug_title(parsed))
        content = self._as_string(downloaded.content)

        if not content:
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

        return CrawlerOutput(
            analysis_id=analysis_id,
            url=submission.url,
            title=title,
            content=content,
            images=downloaded.images,
            metadata=metadata,
        )

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

__all__ = [
    "CrawlerService",
    "DeterministicCrawlerService",
    "HyperbrowserCrawlerError",
    "HyperbrowserCrawlerService",
]

