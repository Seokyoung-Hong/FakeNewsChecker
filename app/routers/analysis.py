"""Analysis submission routes for form POST flow and result rendering."""

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.dependencies import (
    get_active_analysis_repository,
    get_active_analysis_service,
    get_crawl_artifact_store,
    get_templates,
)
from app.artifact_store import CrawlArtifactStore
from app.repositories import AnalysisResultRepository
from app.schemas import URLSubmission
from app.services.analysis_service import AnalysisService

router = APIRouter()


@router.post("/analysis", response_class=HTMLResponse)
def create_analysis(
    request: Request,
    url: Annotated[str, Form()],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    analysis_service: Annotated[AnalysisService, Depends(get_active_analysis_service)],
    repository: Annotated[AnalysisResultRepository, Depends(get_active_analysis_repository)],
) -> Response:
    """Handle browser form submission and redirect to the stored analysis."""

    submitted_url = url.strip()

    try:
        submission = URLSubmission.model_validate({"url": submitted_url})
    except ValidationError:
        error_code = "missing_url" if not submitted_url else "invalid_url"
        return RedirectResponse(
            url="/?" + urlencode({"url": submitted_url, "error": error_code}),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        result = analysis_service.run(submission)
        analysis_id = repository.create(result)
    except Exception:
        return templates.TemplateResponse(
            request=request,
            name="analysis_error.html",
            context={
                "request": request,
                "submitted_url": submitted_url,
                "retry_path": "/",
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return RedirectResponse(
        url=f"/analysis/{analysis_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/analysis/{analysis_id}/artifacts/{artifact_path:path}")
def analysis_artifact_file(
    analysis_id: str,
    artifact_path: str,
    repository: Annotated[AnalysisResultRepository, Depends(get_active_analysis_repository)],
    artifact_store: Annotated[CrawlArtifactStore, Depends(get_crawl_artifact_store)],
) -> FileResponse:
    """Serve a previously saved crawl artifact file."""

    if repository.get(analysis_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    file_path = artifact_store.resolve(analysis_id, artifact_path)
    if file_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    return FileResponse(path=file_path)


@router.get("/analysis/{analysis_id}", response_class=HTMLResponse)
def analysis_result_page(
    request: Request,
    analysis_id: str,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    repository: Annotated[AnalysisResultRepository, Depends(get_active_analysis_repository)],
) -> HTMLResponse:
    """Render a stored analysis result page or a not-found state."""

    result = repository.get(analysis_id)

    if result is None:
        return templates.TemplateResponse(
            request=request,
            name="analysis_error.html",
            context={
                "request": request,
                "submitted_url": "",
                "retry_path": "/",
                "error_title": "분석 결과를 찾을 수 없습니다.",
                "error_message": "요청한 분석 ID가 없거나 저장소가 초기화되었습니다. 홈으로 돌아가 다시 URL을 제출해 주세요.",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context={
            "request": request,
            "result": result,
            "retry_path": "/",
        },
    )
