"""Filesystem persistence for downloaded crawl artifacts."""

from __future__ import annotations

import json
import logging
import mimetypes
import shutil
import socket
from abc import ABC, abstractmethod
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from app.schemas import ArtifactFile, DownloadArtifactManifest, DownloadedImage, CrawlerOutput


logger = logging.getLogger(__name__)


class CrawlArtifactStore(ABC):
    """Persistence contract for downloaded crawl artifacts."""

    @abstractmethod
    def persist(self, crawler_output: CrawlerOutput) -> DownloadArtifactManifest:
        """Persist crawl artifacts and return a manifest for later display."""

    @abstractmethod
    def resolve(self, analysis_id: str, relative_path: str) -> Path | None:
        """Resolve a stored artifact path safely for file serving."""


class FilesystemCrawlArtifactStore(CrawlArtifactStore):
    """Save crawl artifacts under a dedicated analysis folder on disk."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir

    def persist(self, crawler_output: CrawlerOutput) -> DownloadArtifactManifest:
        analysis_dir = self._root_dir / crawler_output.analysis_id
        images_dir = analysis_dir / "images"
        if analysis_dir.exists():
            shutil.rmtree(analysis_dir)
        analysis_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)

        files: list[ArtifactFile] = []
        images: list[DownloadedImage] = []

        files.append(
            self._write_text_file(
                analysis_dir / "article.txt",
                crawler_output.content,
                label="본문 텍스트",
                media_type="text/plain; charset=utf-8",
                analysis_id=crawler_output.analysis_id,
            )
        )

        markdown = _as_string(crawler_output.metadata.get("markdown"))
        if markdown:
            files.append(
                self._write_text_file(
                    analysis_dir / "article.md",
                    markdown,
                    label="마크다운 본문",
                    media_type="text/markdown; charset=utf-8",
                    analysis_id=crawler_output.analysis_id,
                )
            )

        html = _as_string(crawler_output.metadata.get("html"))
        if html:
            files.append(
                self._write_text_file(
                    analysis_dir / "page.html",
                    html,
                    label="원본 HTML",
                    media_type="text/html; charset=utf-8",
                    analysis_id=crawler_output.analysis_id,
                )
            )

        links = crawler_output.metadata.get("links")
        if isinstance(links, list):
            files.append(
                self._write_json_file(
                    analysis_dir / "links.json",
                    links,
                    label="페이지 링크 목록",
                    analysis_id=crawler_output.analysis_id,
                )
            )

        source_url = _as_string(crawler_output.metadata.get("source_url")) or str(crawler_output.url)
        structured_data_raw = crawler_output.metadata.get("structured_data")
        structured_data = _as_mapping(structured_data_raw)
        structured_image_urls = _normalize_string_list(structured_data.get("image_urls"))
        structured_image_urls = [
            _resolve_url(image_url, source_url) for image_url in structured_image_urls
        ]
        structured_image_urls = [image_url for image_url in structured_image_urls if image_url]
        downloaded_structured_images = self._download_structured_images(
            analysis_id=crawler_output.analysis_id,
            images_dir=images_dir,
            image_urls=structured_image_urls,
        )

        if structured_data_raw is not None:
            structured_payload = dict(structured_data)
            structured_payload["image_urls"] = structured_image_urls
            structured_payload["saved_images"] = [
                {
                    "source_url": image.source_url,
                    "status": image.status,
                    "relative_path": image.local_file.relative_path if image.local_file else None,
                    "error": image.error,
                }
                for image in downloaded_structured_images
            ]
            files.append(
                self._write_json_file(
                    analysis_dir / "structured_data.json",
                    structured_payload,
                    label="구조화 추출 결과",
                    analysis_id=crawler_output.analysis_id,
                )
            )

        response_envelope = {
            "job_id": crawler_output.metadata.get("job_id"),
            "status": crawler_output.metadata.get("status"),
            "error": crawler_output.metadata.get("fetch_error"),
            "source_url": crawler_output.metadata.get("source_url"),
        }
        files.append(
            self._write_json_file(
                analysis_dir / "fetch_response.json",
                response_envelope,
                label="HyperBrowser 응답 요약",
                analysis_id=crawler_output.analysis_id,
            )
        )

        metadata_payload = {
            "analysis_id": crawler_output.analysis_id,
            "url": str(crawler_output.url),
            "title": crawler_output.title,
            "collected_at": crawler_output.collected_at.isoformat(),
            "metadata": crawler_output.metadata,
        }
        files.append(
            self._write_json_file(
                analysis_dir / "metadata.json",
                metadata_payload,
                label="저장 메타데이터",
                analysis_id=crawler_output.analysis_id,
            )
        )

        image_urls = structured_image_urls
        files.append(
            self._write_json_file(
                analysis_dir / "image_urls.json",
                image_urls,
                label="structured 이미지 URL 목록",
                analysis_id=crawler_output.analysis_id,
            )
        )
        images.extend(downloaded_structured_images)

        manifest = DownloadArtifactManifest(
            storage_directory=str(analysis_dir),
            files=files,
            images=images,
        )
        logger.debug("Persisted crawl artifacts", extra={"event": "artifact_store_persist", "analysis_id": crawler_output.analysis_id, "file_count": len(files), "image_count": len(images), "storage_directory": str(analysis_dir)})
        return manifest

    def _download_structured_images(
        self,
        *,
        analysis_id: str,
        images_dir: Path,
        image_urls: list[str],
    ) -> list[DownloadedImage]:
        downloads: list[DownloadedImage] = []
        for index, image_url in enumerate(image_urls, start=1):
            downloads.append(
                self._download_image(
                    analysis_id=analysis_id,
                    images_dir=images_dir,
                    source_url=image_url,
                    index=index,
                )
            )
        return downloads

    def resolve(self, analysis_id: str, relative_path: str) -> Path | None:
        if not relative_path:
            logger.debug("Artifact resolve rejected: empty path", extra={"event": "artifact_resolve_rejected", "analysis_id": analysis_id, "reason": "empty_path"})
            return None

        base_root = self._root_dir.resolve()
        root = (self._root_dir / analysis_id).resolve()
        try:
            root.relative_to(base_root)
        except ValueError:
            logger.debug("Artifact resolve rejected: invalid analysis root", extra={"event": "artifact_resolve_rejected", "analysis_id": analysis_id, "reason": "invalid_root"})
            return None

        candidate = (root / relative_path).resolve()

        try:
            candidate.relative_to(root)
        except ValueError:
            logger.debug("Artifact resolve rejected: traversal", extra={"event": "artifact_resolve_rejected", "analysis_id": analysis_id, "relative_path": relative_path, "reason": "path_traversal"})
            return None

        if not candidate.is_file():
            logger.debug("Artifact resolve miss", extra={"event": "artifact_resolve_miss", "analysis_id": analysis_id, "relative_path": relative_path})
            return None
        logger.debug("Artifact resolved", extra={"event": "artifact_resolve_hit", "analysis_id": analysis_id, "relative_path": relative_path})
        return candidate

    def _write_text_file(
        self,
        path: Path,
        content: str,
        *,
        label: str,
        media_type: str,
        analysis_id: str,
    ) -> ArtifactFile:
        path.write_text(content, encoding="utf-8")
        return self._artifact_file(path, label=label, media_type=media_type, analysis_id=analysis_id)

    def _write_json_file(
        self,
        path: Path,
        payload: object,
        *,
        label: str,
        analysis_id: str,
    ) -> ArtifactFile:
        path.write_text(
            json.dumps(_to_jsonable(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self._artifact_file(
            path,
            label=label,
            media_type="application/json",
            analysis_id=analysis_id,
        )

    def _artifact_file(
        self,
        path: Path,
        *,
        label: str,
        media_type: str,
        analysis_id: str,
    ) -> ArtifactFile:
        relative_path = path.relative_to(self._root_dir / analysis_id).as_posix()
        return ArtifactFile(
            label=label,
            relative_path=relative_path,
            size_bytes=path.stat().st_size,
            media_type=media_type,
        )

    def _download_image(
        self,
        *,
        analysis_id: str,
        images_dir: Path,
        source_url: str,
        index: int,
    ) -> DownloadedImage:
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"}:
            return DownloadedImage(
                source_url=source_url,
                status="skipped",
                error="Only http/https image URLs can be downloaded.",
            )

        if not _is_safe_public_image_host(parsed.hostname):
            return DownloadedImage(
                source_url=source_url,
                status="skipped",
                error="Image host is not allowed for server-side download.",
            )

        extension = _guess_extension(source_url)
        filename = f"image-{index:03d}{extension}"
        destination = images_dir / filename

        try:
            request = Request(
                source_url,
                headers={"User-Agent": "FakeNewsChecker/1.0"},
            )
            with urlopen(request, timeout=20) as response:  # noqa: S310
                content = response.read()
                content_type = response.headers.get_content_type()

            if not extension or extension == ".bin":
                extension = _guess_extension_from_content_type(content_type)
                destination = images_dir / f"image-{index:03d}{extension}"

            destination.write_bytes(content)
            return DownloadedImage(
                source_url=source_url,
                status="downloaded",
                local_file=ArtifactFile(
                    label=f"저장 이미지 {index}",
                    relative_path=destination.relative_to(self._root_dir / analysis_id).as_posix(),
                    size_bytes=destination.stat().st_size,
                    media_type=content_type,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return DownloadedImage(
                source_url=source_url,
                status="failed",
                error=str(exc),
            )


def _as_string(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value


def _as_mapping(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    if value is None:
        return {}

    if hasattr(value, "__dict__"):
        raw = vars(value)
        return {str(key): item for key, item in raw.items() if not str(key).startswith("_")}
    return {}


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


def _resolve_url(value: str, base_url: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    return urljoin(base_url, candidate)


def _to_jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return {
            str(key): _to_jsonable(item)
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    return str(value)


def _guess_extension(source_url: str) -> str:
    path = urlparse(source_url).path
    suffix = Path(path).suffix.lower()
    if suffix:
        return suffix
    return ".bin"


def _guess_extension_from_content_type(content_type: str | None) -> str:
    if not content_type:
        return ".bin"
    return mimetypes.guess_extension(content_type) or ".bin"


def _is_safe_public_image_host(hostname: str | None) -> bool:
    if not hostname:
        return False

    lowered = hostname.strip().lower()
    if lowered in {"localhost", "localhost.localdomain"}:
        return False

    try:
        resolved = socket.getaddrinfo(lowered, None)
    except socket.gaierror:
        return False

    addresses = {entry[4][0] for entry in resolved}
    for address_text in addresses:
        try:
            address = ip_address(address_text)
        except ValueError:
            return False

        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            return False

    return True


__all__ = ["CrawlArtifactStore", "FilesystemCrawlArtifactStore"]
