"""Local browser-backed page downloader using Playwright."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import import_module
from ipaddress import ip_address
import logging
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import OllamaSettings
from app.prompt_loader import load_prompt


logger = logging.getLogger(__name__)

_DEFAULT_MAX_AGENTIC_STEPS = 4
_DEFAULT_MAX_CANDIDATES = 8
_MIN_ARTICLE_TEXT_LENGTH = 600
_MIN_CONTENT_PARAGRAPHS = 3
_LANDING_PAGE_MARKERS = (
    "advertisement",
    "live",
    "latest",
    "top stories",
    "breaking news",
    "most read",
)


class LocalBrowserClientError(RuntimeError):
    """Raised when the local browser crawler cannot download page content."""


@dataclass(frozen=True)
class LocalBrowserDownloadResult:
    """Normalized page payload returned by the local browser client."""

    requested_url: str
    final_url: str
    title: str
    content: str
    images: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


class _NavigationActionPayload(BaseModel):
    action: str = Field(min_length=1)
    target_index: int | None = None
    rationale: str = Field(min_length=1)


class _NavigationCandidate(BaseModel):
    index: int
    text: str = Field(min_length=1)
    href: str = Field(min_length=1)
    score_hint: int


class _PageSnapshotPayload(BaseModel):
    title: str = ""
    final_url: str = ""
    article_text: str = ""
    image_urls: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    selected_root_selector: str = "body"
    candidate_targets: list[_NavigationCandidate] = Field(default_factory=list)
    visible_text_length: int = 0
    paragraph_count: int = 0


@dataclass(frozen=True)
class _ExtractionQuality:
    is_sufficient: bool
    score: int
    reason: str


@dataclass(frozen=True)
class LocalBrowserClient:
    """Thin wrapper around a local Playwright browser session."""

    backend: str = "playwright"
    headless: bool = True
    wait_until: str = "networkidle"
    wait_for_ms: int = 1000
    timeout_ms: int = 45000
    block_media: bool = True
    user_agent: str = "FakeNewsChecker/1.0"
    navigation_settings: OllamaSettings | None = None
    max_agentic_steps: int = _DEFAULT_MAX_AGENTIC_STEPS
    max_candidates: int = _DEFAULT_MAX_CANDIDATES

    def download(self, url: str) -> LocalBrowserDownloadResult:
        if self.backend != "playwright":
            raise LocalBrowserClientError(
                f"Unsupported local crawler backend: {self.backend}."
            )
        if not _is_safe_public_target(url):
            raise LocalBrowserClientError(
                "Local browser crawling is limited to safe public http/https targets."
            )

        logger.debug(
            "Starting local browser download",
            extra={
                "event": "local_browser_download_start",
                "url": url,
                "backend": self.backend,
                "headless": self.headless,
                "wait_until": self.wait_until,
                "timeout_ms": self.timeout_ms,
            },
        )
        sync_api = _import_playwright_sync_api()
        best_snapshot: _PageSnapshotPayload | None = None
        navigation_trace: list[dict[str, object]] = []
        html = ""
        try:
            with sync_api.sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.headless)
                context = browser.new_context(user_agent=self.user_agent)
                page = context.new_page()

                if self.block_media:
                    page.route("**/*", _route_handler)

                response = None
                for step_index in range(1, max(1, self.max_agentic_steps) + 1):
                    response = self._goto_with_fallback(
                        page=page,
                        url=url if step_index == 1 else page.url,
                    ) if step_index == 1 else response
                    if self.wait_for_ms > 0:
                        page.wait_for_timeout(self.wait_for_ms)

                    html = page.content()
                    title = _normalize_multiline(page.title())
                    extracted = page.evaluate(_EXTRACTION_SCRIPT)
                    snapshot = _PageSnapshotPayload.model_validate(extracted)
                    best_snapshot = _prefer_snapshot(best_snapshot, snapshot)

                    quality = _assess_extraction_quality(snapshot)
                    navigation_trace.append(
                        {
                            "step": step_index,
                            "url": snapshot.final_url or page.url,
                            "quality_score": quality.score,
                            "quality_reason": quality.reason,
                            "candidate_count": len(snapshot.candidate_targets),
                        }
                    )
                    if quality.is_sufficient:
                        break

                    action = self._choose_navigation_action(snapshot=snapshot)
                    if action is None or action.action == "finish":
                        break
                    if action.action == "open_target" and action.target_index is not None:
                        target = _find_candidate(snapshot.candidate_targets, action.target_index)
                        if target is None:
                            break
                        if not _is_allowed_navigation_target(
                            target_url=target.href,
                            current_url=page.url,
                            origin_url=url,
                        ):
                            navigation_trace.append(
                                {
                                    "step": step_index,
                                    "action": "skip_target",
                                    "target_index": action.target_index,
                                    "target_href": target.href,
                                    "rationale": "Navigation target was rejected by same-site guard.",
                                }
                            )
                            break
                        response = page.goto(
                            target.href,
                            wait_until="domcontentloaded",
                            timeout=self.timeout_ms,
                        )
                        if self.wait_for_ms > 0:
                            page.wait_for_timeout(self.wait_for_ms)
                        navigation_trace.append(
                            {
                                "step": step_index,
                                "action": "open_target",
                                "target_index": action.target_index,
                                "target_href": target.href,
                                "rationale": action.rationale,
                            }
                        )
                        continue
                    if action.action == "scroll":
                        page.evaluate("window.scrollBy(0, window.innerHeight * 0.9)")
                        if self.wait_for_ms > 0:
                            page.wait_for_timeout(self.wait_for_ms)
                        navigation_trace.append(
                            {
                                "step": step_index,
                                "action": "scroll",
                                "rationale": action.rationale,
                            }
                        )
                        continue
                    break

                if best_snapshot is None:
                    raise LocalBrowserClientError("Local browser extraction returned an invalid payload.")
                context.close()
                browser.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Local browser download failed",
                extra={
                    "event": "local_browser_download_failed",
                    "url": url,
                    "backend": self.backend,
                    "exception_class": type(exc).__name__,
                },
            )
            raise LocalBrowserClientError(f"Local browser download failed: {exc}") from exc

        final_url = _normalize_string(best_snapshot.final_url) or url
        article_text = _normalize_multiline(best_snapshot.article_text)
        if not article_text:
            raise LocalBrowserClientError("Local browser crawler could not extract article content.")

        image_urls = _normalize_string_list(best_snapshot.image_urls)
        links = _normalize_string_list(best_snapshot.links)
        selected_root_selector = _normalize_string(best_snapshot.selected_root_selector)
        status_code = getattr(response, "status", None)

        result = LocalBrowserDownloadResult(
            requested_url=url,
            final_url=final_url,
            title=_normalize_multiline(best_snapshot.title) or final_url,
            content=article_text,
            images=image_urls,
            metadata={
                "provider": "playwright-local",
                "browser_backend": self.backend,
                "status": "completed",
                "fetch_error": None,
                "source_url": final_url,
                "http_status": status_code,
                "visible_text_length": len(article_text),
                "image_count": len(image_urls),
                "link_count": len(links),
                "selected_root_selector": selected_root_selector,
                "navigation_trace": navigation_trace,
                "candidate_count": len(best_snapshot.candidate_targets),
                "markdown": article_text,
                "html": html,
                "links": links,
                "structured_data": {
                    "title": best_snapshot.title,
                    "article_text": article_text,
                    "image_urls": image_urls,
                },
            },
        )
        logger.debug(
            "Completed local browser download",
            extra={
                "event": "local_browser_download_done",
                "requested_url": url,
                "final_url": final_url,
                "image_count": len(image_urls),
                "content_length": len(article_text),
            },
        )
        return result

    def _goto_with_fallback(self, *, page: Any, url: str) -> Any:
        wait_strategies = [self.wait_until, "domcontentloaded", "load"]
        seen: set[str] = set()
        last_error: Exception | None = None
        for strategy in wait_strategies:
            normalized = strategy.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            try:
                return page.goto(
                    url,
                    wait_until=normalized,
                    timeout=self.timeout_ms,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.debug(
                    "Local browser goto strategy failed",
                    extra={
                        "event": "local_browser_goto_retry",
                        "url": url,
                        "wait_until": normalized,
                        "exception_class": type(exc).__name__,
                    },
                )
                continue
        if last_error is not None:
            raise last_error
        raise LocalBrowserClientError("No valid navigation strategy was available.")

    def _choose_navigation_action(
        self,
        *,
        snapshot: _PageSnapshotPayload,
    ) -> _NavigationActionPayload | None:
        candidates = snapshot.candidate_targets[: self.max_candidates]
        if not candidates:
            return None

        heuristic_candidate = max(candidates, key=lambda item: item.score_hint)
        second_best_score = max((item.score_hint for item in candidates if item.index != heuristic_candidate.index), default=-999)
        if (
            heuristic_candidate.score_hint >= 18
            and (heuristic_candidate.score_hint - second_best_score) >= 6
            and not _looks_like_live_or_index_link(heuristic_candidate.href, heuristic_candidate.text)
        ):
            return _NavigationActionPayload(
                action="open_target",
                target_index=heuristic_candidate.index,
                rationale="Heuristic selected a clearly article-like candidate before consulting the model.",
            )

        llm_action = self._request_navigation_action(snapshot=snapshot, candidates=candidates)
        if llm_action is not None and llm_action.action in {"open_target", "scroll"}:
            return llm_action
        if llm_action is not None and llm_action.action == "finish" and heuristic_candidate.score_hint < 12:
            return llm_action

        return _NavigationActionPayload(
            action="open_target",
            target_index=heuristic_candidate.index,
            rationale="Heuristic fallback selected the highest-ranked candidate link.",
        )

    def _request_navigation_action(
        self,
        *,
        snapshot: _PageSnapshotPayload,
        candidates: list[_NavigationCandidate],
    ) -> _NavigationActionPayload | None:
        settings = self.navigation_settings
        if settings is None:
            return None

        prompt = _build_navigation_prompt(snapshot=snapshot, candidates=candidates)
        host_model_pairs = settings.host_model_pairs
        for host, model in host_model_pairs:
            try:
                return _request_structured_navigation_action(
                    host=host,
                    model=model,
                    prompt=prompt,
                    settings=settings,
                )
            except (httpx.HTTPError, ValueError, ValidationError, json.JSONDecodeError, TypeError):
                continue
        return None


def _import_playwright_sync_api() -> Any:
    try:
        return import_module("playwright.sync_api")
    except ModuleNotFoundError as exc:
        logger.error(
            "Playwright is not installed",
            extra={"event": "playwright_sdk_missing"},
        )
        raise LocalBrowserClientError(
            "Playwright is not installed. Run 'pip install playwright' and 'playwright install chromium'."
        ) from exc


def _route_handler(route: Any) -> None:
    request = getattr(route, "request", None)
    resource_type = getattr(request, "resource_type", "")
    if resource_type in {"image", "media", "font"}:
        route.abort()
        return
    route.continue_()


def _normalize_string(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _normalize_multiline(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return "\n".join(line.strip() for line in value.splitlines() if line.strip())


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


def _prefer_snapshot(
    current: _PageSnapshotPayload | None,
    candidate: _PageSnapshotPayload,
) -> _PageSnapshotPayload:
    if current is None:
        return candidate
    current_score = _assess_extraction_quality(current).score
    candidate_score = _assess_extraction_quality(candidate).score
    if candidate_score >= current_score:
        return candidate
    return current


def _assess_extraction_quality(snapshot: _PageSnapshotPayload) -> _ExtractionQuality:
    body = _normalize_multiline(snapshot.article_text)
    lowered = body.lower()
    score = 0
    reasons: list[str] = []

    if len(body) >= _MIN_ARTICLE_TEXT_LENGTH:
        score += 50
        reasons.append("body_length")
    else:
        score += min(len(body) // 20, 25)

    if snapshot.paragraph_count >= _MIN_CONTENT_PARAGRAPHS:
        score += 20
        reasons.append("paragraph_count")

    if snapshot.selected_root_selector != "body":
        score += 15
        reasons.append("focused_root")

    marker_hits = sum(1 for marker in _LANDING_PAGE_MARKERS if marker in lowered)
    if marker_hits:
        score -= marker_hits * 12
        reasons.append("landing_markers")

    if len(snapshot.candidate_targets) >= 8 and snapshot.selected_root_selector == "body":
        score -= 15
        reasons.append("too_many_candidates")

    is_sufficient = score >= 55 and len(body) >= 250
    reason = ",".join(reasons) if reasons else "weak_body"
    return _ExtractionQuality(
        is_sufficient=is_sufficient,
        score=score,
        reason=reason,
    )


def _find_candidate(
    candidates: list[_NavigationCandidate],
    target_index: int,
) -> _NavigationCandidate | None:
    for candidate in candidates:
        if candidate.index == target_index:
            return candidate
    return None


def _looks_like_live_or_index_link(href: str, text: str) -> bool:
    lowered_href = href.strip().lower()
    lowered_text = text.strip().lower()
    return any(
        token in lowered_href or token in lowered_text
        for token in (
            "/live/",
            "live blog",
            "latest",
            "top stories",
            "breaking news",
            "news home",
        )
    )


def _is_allowed_navigation_target(
    *,
    target_url: str,
    current_url: str,
    origin_url: str,
) -> bool:
    parsed_target = urlparse(target_url)
    parsed_current = urlparse(current_url)
    parsed_origin = urlparse(origin_url)
    if parsed_target.scheme not in {"http", "https"}:
        return False
    target_host = (parsed_target.hostname or "").lower()
    current_host = (parsed_current.hostname or "").lower()
    origin_host = (parsed_origin.hostname or "").lower()
    if not target_host or not current_host or not origin_host:
        return False
    return any(
        _same_site(target_host, allowed_host)
        for allowed_host in {current_host, origin_host}
    )


def _same_site(target_host: str, allowed_host: str) -> bool:
    return (
        target_host == allowed_host
        or target_host.endswith("." + allowed_host)
        or allowed_host.endswith("." + target_host)
    )


def _build_navigation_prompt(
    *,
    snapshot: _PageSnapshotPayload,
    candidates: list[_NavigationCandidate],
) -> str:
    candidate_lines = [
        f"- index={candidate.index} score_hint={candidate.score_hint} text={candidate.text} href={candidate.href}"
        for candidate in candidates
    ]
    excerpt = _normalize_multiline(snapshot.article_text)[:1200]
    return load_prompt(
        "local_browser_navigation",
        current_url=snapshot.final_url,
        current_title=snapshot.title,
        excerpt=excerpt,
        candidate_lines="\n".join(candidate_lines),
    )


def _request_structured_navigation_action(
    *,
    host: str,
    model: str,
    prompt: str,
    settings: OllamaSettings,
) -> _NavigationActionPayload:
    endpoint = host.rstrip("/") + "/api/chat"
    body = {
        "model": model,
        "stream": True,
        "format": _NavigationActionPayload.model_json_schema(),
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": load_prompt("structured_json_system")},
            {"role": "user", "content": prompt},
        ],
    }
    with httpx.stream("POST", endpoint, json=body, timeout=settings.timeout_ms / 1000) as response:
        _ = response.raise_for_status()
        content = _extract_streamed_content(response)
    normalized = _clean_json_payload(content)
    return _NavigationActionPayload.model_validate_json(normalized)


def _clean_json_payload(raw: str) -> str:
    return raw.replace("```json", "").replace("```", "").strip()


def _extract_streamed_content(response: httpx.Response) -> str:
    parts: list[str] = []
    for line in response.iter_lines():
        if not line:
            continue
        payload_obj = json.loads(line)
        if not isinstance(payload_obj, dict):
            continue
        message = payload_obj.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str) and content:
            parts.append(content)
    return "".join(parts).strip()


_EXTRACTION_SCRIPT = r"""
() => {
  const selectors = [
    "article",
    "main",
    "[role='main']",
    ".article",
    ".article-content",
    ".post-content",
    ".entry-content",
    ".story-body",
    ".news-content",
    ".content"
  ];

  const normalizeText = (value) => (typeof value === "string" ? value.replace(/\s+\n/g, "\n").replace(/\n\s+/g, "\n").trim() : "");
  const normalizeList = (values) => {
    const seen = new Set();
    const items = [];
    for (const value of values) {
      if (typeof value !== "string") continue;
      const candidate = value.trim();
      if (!candidate || seen.has(candidate)) continue;
      seen.add(candidate);
      items.push(candidate);
    }
    return items;
  };

    const scoreCandidate = (text, href) => {
    const loweredText = (text || "").toLowerCase();
    const loweredHref = (href || "").toLowerCase();
    let score = 0;
    if (!href) return -100;
    if (loweredHref.startsWith('javascript:') || loweredHref.startsWith('mailto:')) return -100;
    if (loweredHref === window.location.href.toLowerCase()) score -= 50;
    if (loweredText.includes('read more') || loweredText.includes('full story') || loweredText.includes('full article')) score += 20;
    if (loweredHref.includes('/news/') || loweredHref.includes('/article') || loweredHref.includes('/story')) score += 18;
    if (/\/news\/articles?\//.test(loweredHref) || /\/news\/[a-z0-9-]+-\d+/.test(loweredHref)) score += 24;
    if (/\b20\d{2}\b/.test(loweredHref)) score += 10;
    if (loweredText.includes('live')) score -= 20;
    if (loweredHref.includes('/news/live/')) score -= 30;
    if (loweredText.includes('sign in') || loweredText.includes('login') || loweredText.includes('newsletter')) score -= 35;
    if (loweredText.includes('video') || loweredText.includes('audio') || loweredText.includes('podcast')) score -= 12;
    if (loweredText.includes('home') || loweredText.includes('news home')) score -= 25;
    if ((text || '').trim().length >= 25) score += 10;
    if ((text || '').trim().length >= 45) score += 6;
    return score;
  };

  const candidates = selectors
    .map((selector) => ({ selector, node: document.querySelector(selector) }))
    .filter((item) => item.node);

  let bestNode = null;
  let bestSelector = "body";
  let bestText = "";

  for (const candidate of candidates) {
    const text = normalizeText(candidate.node.innerText || "");
    if (text.length > bestText.length) {
      bestNode = candidate.node;
      bestSelector = candidate.selector;
      bestText = text;
    }
  }

  if (!bestNode) {
    bestNode = document.body;
    bestSelector = "body";
    bestText = normalizeText(document.body?.innerText || "");
  }

  const imageUrls = normalizeList([
    ...Array.from(bestNode.querySelectorAll("img")).map((image) => image.currentSrc || image.src || image.getAttribute("data-src") || ""),
    ...Array.from(document.querySelectorAll("meta[property='og:image'], meta[name='twitter:image']")).map((meta) => meta.getAttribute("content") || ""),
  ]);

  const links = normalizeList(Array.from(document.links).map((link) => link.href || "")).slice(0, 200);
  const candidateTargets = Array.from(document.querySelectorAll('a[href]'))
    .map((link, index) => ({
      index,
      text: normalizeText(link.innerText || link.textContent || ''),
      href: link.href || '',
    }))
    .filter((item) => item.text && item.href)
    .map((item) => ({ ...item, score_hint: scoreCandidate(item.text, item.href) }))
    .filter((item) => item.score_hint > -25)
    .sort((a, b) => b.score_hint - a.score_hint)
    .slice(0, 20);
  const paragraphCount = bestText ? bestText.split(/\n+/).filter((item) => item.trim().length >= 40).length : 0;

  return {
    title: normalizeText(document.title || ""),
    final_url: window.location.href,
    article_text: bestText,
    image_urls: imageUrls,
    links,
    selected_root_selector: bestSelector,
    candidate_targets: candidateTargets,
    visible_text_length: bestText.length,
    paragraph_count: paragraphCount,
  };
}
"""


__all__ = [
    "LocalBrowserClient",
    "LocalBrowserClientError",
    "LocalBrowserDownloadResult",
]


def _is_safe_public_target(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False
    if hostname.lower() in {"localhost"}:
        return False

    try:
        resolved = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except socket.gaierror:
        return False

    for candidate in resolved:
        try:
            address = ip_address(candidate)
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
