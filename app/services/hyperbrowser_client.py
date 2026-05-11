"""HyperBrowser-based page downloader."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from importlib import import_module
from typing import Any
from urllib.parse import urljoin


class HyperbrowserClientError(RuntimeError):
    """Raised when HyperBrowser cannot download or parse page content."""


@dataclass(frozen=True)
class HyperbrowserDownloadResult:
    """Normalized page payload returned by the HyperBrowser client."""

    requested_url: str
    final_url: str
    title: str
    content: str
    images: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class HyperbrowserClient:
    """Thin wrapper around HyperBrowser Web Fetch."""

    api_key: str
    wait_until: str = "load"
    wait_for_ms: int = 1500
    timeout_ms: int = 30000

    def download(self, url: str) -> HyperbrowserDownloadResult:
        hyperbrowser_module, models_module = _import_hyperbrowser()

        try:
            client = hyperbrowser_module.Hyperbrowser(api_key=self.api_key)
            result = client.web.fetch(self._build_fetch_params(models_module, url))
        except Exception as exc:  # noqa: BLE001
            raise HyperbrowserClientError(f"HyperBrowser download failed: {exc}") from exc

        status = _as_string(_read_value(result, "status")) or "unknown"
        error = _as_string(_read_value(result, "error"))
        job_id = _as_string(_read_value(result, "jobId"))
        data = _read_mapping_like(_read_value(result, "data"))
        metadata = _read_mapping_like(_read_value(data, "metadata"))
        structured = _read_mapping_like(
            _read_value(data, "json_") or _read_value(data, "json")
        )

        title = _first_non_empty(
            _read_value(structured, "title"),
            _read_value(metadata, "title"),
        )
        content = _first_non_empty(
            _read_value(structured, "article_text"),
            _read_value(structured, "content"),
            _read_value(data, "markdown"),
        )
        html = _as_string(_read_value(data, "html"))
        links = _normalize_string_list(_read_value(data, "links"))
        final_url = _first_non_empty(
            _read_value(metadata, "sourceURL"),
            _read_value(metadata, "source_url"),
            url,
        )
        images = _collect_image_urls(
            structured=structured,
            html=html,
            links=links,
            base_url=final_url,
        )

        if status != "completed":
            if error:
                raise HyperbrowserClientError(f"HyperBrowser fetch failed: {error}")
            raise HyperbrowserClientError(f"HyperBrowser fetch failed: {error}")

        if not content:
            raise HyperbrowserClientError(
                "HyperBrowser download did not produce readable content."
            )

        return HyperbrowserDownloadResult(
            requested_url=url,
            final_url=final_url,
            title=title or final_url,
            content=content,
            images=images,
            metadata={
                "provider": "hyperbrowser",
                "job_id": job_id,
                "status": status,
                "fetch_error": error or None,
                "source_url": final_url,
                "image_count": len(images),
                "link_count": len(links),
                "visible_text_length": len(content),
                "markdown": _as_string(_read_value(data, "markdown")),
                "html": html,
                "links": links,
                "structured_data": structured,
            },
        )

    def _build_fetch_params(self, models_module: Any, url: str) -> Any:
        fetch_output_json = models_module.FetchOutputJson(
            type="json",
            prompt=(
                "Extract the page title, the main article or post text, and every meaningful "
                "image URL that belongs to the article body, post body, or card-news/carousel slides. "
                "For Instagram or similar SNS posts, include every actual post/carousel image in order. "
                "Exclude profile pictures, author avatars, commenter avatars, icons, logos, navigation images, and ad images."
            ),
            schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "article_text": {"type": "string"},
                    "image_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["article_text", "image_urls"],
                "additionalProperties": False,
            },
        )

        return models_module.FetchParams(
            url=url,
            outputs=models_module.FetchOutputOptions(
                formats=["markdown", "html", "links", fetch_output_json],
                exclude_selectors=["nav", "footer", "aside"],
            ),
            navigation=models_module.FetchNavigationOptions(
                wait_until=self.wait_until,
                wait_for=self.wait_for_ms,
                timeout_ms=self.timeout_ms,
            ),
        )


def _import_hyperbrowser() -> tuple[Any, Any]:
    try:
        hyperbrowser_module = import_module("hyperbrowser")
        models_module = import_module("hyperbrowser.models")
    except ModuleNotFoundError as exc:
        raise HyperbrowserClientError(
            "HyperBrowser SDK is not installed. Run 'pip install hyperbrowser'."
        ) from exc

    return hyperbrowser_module, models_module


def _read_value(source: object, key: str) -> object | None:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _read_mapping_like(source: object) -> object:
    if source is None:
        return {}
    return source


def _as_string(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return "\n".join(line.strip() for line in value.splitlines() if line.strip())


def _first_non_empty(*values: object) -> str:
    for value in values:
        text = _as_string(value)
        if text:
            return text
    return ""


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        items.append(candidate)
    return items


class _ImageCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []
        self._seen: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value for key, value in attrs if value}
        if tag.lower() == "img":
            self._add(attributes.get("src"))
            self._add(attributes.get("data-src"))
            self._add_srcset(attributes.get("srcset"))
            self._add_srcset(attributes.get("data-srcset"))
            return

        if tag.lower() == "meta":
            property_name = (attributes.get("property") or attributes.get("name") or "").lower()
            if property_name in {"og:image", "twitter:image"}:
                self._add(attributes.get("content"))

    def _add_srcset(self, value: str | None) -> None:
        if not value:
            return
        for part in value.split(","):
            self._add(part.strip().split(" ")[0])

    def _add(self, value: str | None) -> None:
        if not value:
            return
        candidate = value.strip()
        if not candidate or candidate in self._seen:
            return
        self._seen.add(candidate)
        self.urls.append(candidate)


def _collect_image_urls(
    *, structured: object, html: str, links: list[str], base_url: str
) -> list[str]:
    images = _normalize_string_list(_read_value(structured, "image_urls"))
    parser = _ImageCollector()
    if html:
        parser.feed(html)
    images.extend(parser.urls)
    images.extend(link for link in links if _looks_like_image_url(link))

    deduped: list[str] = []
    seen: set[str] = set()
    for image in images:
        candidate = _resolve_url(image, base_url)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def _resolve_url(value: str, base_url: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    return urljoin(base_url, candidate)


def _looks_like_image_url(value: str) -> bool:
    lowered = value.lower()
    return lowered.endswith(
        (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp", ".avif")
    )


__all__ = [
    "HyperbrowserClient",
    "HyperbrowserClientError",
    "HyperbrowserDownloadResult",
]
