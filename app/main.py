"""Application bootstrap for the FastAPI app."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routers.analysis import router as analysis_router
from .routers.page import router as page_router


def create_app() -> FastAPI:
    """Create the top-level FastAPI application.

    This function intentionally keeps startup wiring thin and delegates
    all feature behavior to future routers and services.
    """

    app = FastAPI(title="Fake News Verification API")
    static_dir = Path(__file__).resolve().parent / "static"

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.include_router(page_router)
    app.include_router(analysis_router)
    return app


app = create_app()
