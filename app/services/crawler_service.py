"""Crawler stage for deterministic URL collection stub."""

# pyright: reportImplicitOverride=false

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from uuid import NAMESPACE_URL, uuid5
from urllib.parse import urlparse

from app.schemas import CrawlerOutput, URLSubmission


def _normalize_url(url: str) -> str:
    return url.strip().lower().rstrip("/")


class CrawlerService(ABC):
    """Service contract for retrieving source material from URL input."""

    @abstractmethod
    def collect(self, submission: URLSubmission) -> CrawlerOutput:
        """Collect crawl artifacts for the given submission."""


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


__all__ = ["CrawlerService", "DeterministicCrawlerService"]

