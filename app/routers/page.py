"""Page routes for the server-rendered UI shell."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..dependencies import get_templates

router = APIRouter()

_FORM_ERRORS = {
    "missing_url": "검증할 URL을 입력해 주세요.",
    "invalid_url": "올바른 URL 형식으로 입력해 주세요.",
}


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    url: str = "",
    error: str = "",
) -> HTMLResponse:
    """Render the submission homepage."""

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "submitted_url": url,
            "form_error": _FORM_ERRORS.get(error, ""),
        },
    )
