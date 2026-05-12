"""Page routes for the server-rendered UI shell."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..dependencies import get_ollama_settings, get_templates
from ..config import OllamaSettings

router = APIRouter()
logger = logging.getLogger(__name__)

_FORM_ERRORS = {
    "missing_url": "검증할 URL을 입력해 주세요.",
    "invalid_url": "올바른 URL 형식으로 입력해 주세요.",
}


def _render_index(
    request: Request,
    templates: Jinja2Templates,
    *,
    submitted_url: str,
    error: str,
    analysis_action: str,
    submit_label: str,
    page_title: str,
    intro_copy: str,
    mode_badge: str,
) -> HTMLResponse:
    logger.debug(
        "Rendering index page",
        extra={
            "event": "page_render",
            "analysis_action": analysis_action,
            "has_submitted_url": bool(submitted_url),
            "has_error": bool(error),
            "mode_badge": mode_badge,
        },
    )
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "submitted_url": submitted_url,
            "form_error": _FORM_ERRORS.get(error, ""),
            "analysis_action": analysis_action,
            "submit_label": submit_label,
            "page_title": page_title,
            "intro_copy": intro_copy,
            "mode_badge": mode_badge,
        },
    )


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    url: str = "",
    error: str = "",
) -> HTMLResponse:
    """Render the submission homepage."""

    logger.debug("Serving online index page", extra={"event": "index_route", "path": "/", "error": error or None})

    return _render_index(
        request,
        templates,
        submitted_url=url,
        error=error,
        analysis_action="/analysis",
        submit_label="검증하기",
        page_title="검증하고 싶은 뉴스·게시글 URL을 입력하세요.",
        intro_copy="뉴스 기사, SNS 게시글, 블로그 링크를 붙여 넣으면 이후 단계에서 신뢰도 리포트를 확인할 수 있습니다.",
        mode_badge="Online Model",
    )


@router.get("/local-model", response_class=HTMLResponse)
@router.get("/local-search", response_class=HTMLResponse)
def local_model_index(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    ollama_settings: Annotated[OllamaSettings, Depends(get_ollama_settings)],
    url: str = "",
    error: str = "",
) -> HTMLResponse:
    """Render the local crawling + local model submission page."""

    logger.debug(
        "Serving local-model index page",
        extra={"event": "local_model_index_route", "path": "/local-model", "error": error or None, "model": ollama_settings.model},
    )

    return _render_index(
        request,
        templates,
        submitted_url=url,
        error=error,
        analysis_action=request.url.path,
        submit_label="로컬 검색으로 검증하기",
        page_title=f"로컬 검색 + 로컬 모델({ollama_settings.model})로 분석할 URL을 입력하세요.",
        intro_copy=(
            f"이 경로는 Playwright 기반 로컬 브라우저 크롤링으로 본문을 수집하고, "
            f"서버에서 실행 중인 Ollama의 {ollama_settings.model} 모델로 텍스트 분석을 수행합니다."
        ),
        mode_badge="Local Search",
    )
