"""Optional MCP server surface for local browser crawling."""

# pyright: reportMissingImports=false

from __future__ import annotations

import logging
from typing import Any

from app.config import CrawlerSettings
from app.dependencies import get_local_crawler_service
from app.schemas import URLSubmission


logger = logging.getLogger(__name__)


def create_crawl_mcp_server() -> Any | None:
    """Create an MCP server exposing local crawl tools when enabled."""

    settings = CrawlerSettings.from_env()
    if not settings.local_crawler_mcp_enabled:
        return None

    try:
        from mcp.server.mcpserver import MCPServer
    except ModuleNotFoundError:
        logger.warning(
            "MCP SDK is unavailable; crawl MCP server disabled",
            extra={"event": "mcp_sdk_missing"},
        )
        return None

    mcp = MCPServer("FakeNewsChecker Local Crawl")

    @mcp.tool(description="Crawl a URL locally with Playwright and return extracted text, links, images, and metadata.")
    def crawl_url(url: str) -> dict[str, object]:
        submission = URLSubmission.model_validate({"url": url})
        result = get_local_crawler_service().collect(submission)
        return {
            "analysis_id": result.analysis_id,
            "url": str(result.url),
            "title": result.title,
            "content": result.content,
            "images": result.images,
            "metadata": result.metadata,
        }

    @mcp.tool(description="Return the configured local crawling backend and runtime defaults.")
    def crawl_capabilities() -> dict[str, object]:
        return {
            "backend": settings.local_crawler_backend,
            "headless": settings.local_crawler_headless,
            "wait_until": settings.local_crawler_wait_until,
            "wait_for_ms": settings.local_crawler_wait_for_ms,
            "timeout_ms": settings.local_crawler_timeout_ms,
            "block_media": settings.local_crawler_block_media,
        }

    logger.debug(
        "Created crawl MCP server",
        extra={
            "event": "mcp_server_created",
            "backend": settings.local_crawler_backend,
        },
    )
    return mcp


__all__ = ["create_crawl_mcp_server"]
