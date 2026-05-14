"""Application bootstrap for the FastAPI app."""

import contextlib
import os
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .mcp_server import create_crawl_mcp_server
from .routers.analysis import router as analysis_router
from .routers.page import router as page_router


logger = logging.getLogger(__name__)


_RESERVED_LOG_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__.keys())


class AppDebugFormatter(logging.Formatter):
    """Render app logs with structured extras visible in plain text."""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOG_RECORD_FIELDS and not key.startswith("_")
        }
        if not extras:
            return message

        context = " ".join(f"{key}={value!r}" for key, value in sorted(extras.items()))
        return f"{message} | {context}"


def configure_logging() -> None:
    """Configure application logger once with visible debug context."""

    log_level_name = os.environ.get("APP_LOG_LEVEL", "DEBUG").strip().upper() or "DEBUG"
    log_level = getattr(logging, log_level_name, logging.DEBUG)

    app_logger = logging.getLogger("app")
    app_logger.setLevel(log_level)
    app_logger.propagate = False

    if app_logger.handlers:
        for handler in app_logger.handlers:
            handler.setLevel(log_level)
        return

    handler = logging.StreamHandler()
    handler.setLevel(log_level)
    handler.setFormatter(
        AppDebugFormatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    app_logger.addHandler(handler)


def create_app() -> FastAPI:
    """Create the top-level FastAPI application.

    This function intentionally keeps startup wiring thin and delegates
    all feature behavior to future routers and services.
    """

    configure_logging()
    mcp_server = create_crawl_mcp_server()
    mcp_app = None
    if mcp_server is not None:
        mcp_app = mcp_server.streamable_http_app(json_response=True)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        del app
        if mcp_server is None:
            yield
            return
        async with mcp_server.session_manager.run():
            yield

    app = FastAPI(title="바로봄 API", lifespan=lifespan)
    static_dir = Path(__file__).resolve().parent / "static"

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    if mcp_app is not None:
        app.mount("/mcp/crawl", mcp_app)
    app.include_router(page_router)
    app.include_router(analysis_router)
    logger.debug(
        "create_app configured FastAPI application",
        extra={
            "event": "app_create",
            "static_dir": str(static_dir),
            "has_crawl_mcp": mcp_app is not None,
            "routers": ["page_router", "analysis_router"],
        },
    )
    return app


app = create_app()
