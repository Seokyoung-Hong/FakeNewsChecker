"""Analysis submission routes for form POST flow and result rendering."""

import logging
from threading import Thread
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.dependencies import (
    get_active_analysis_repository,
    get_active_analysis_service,
    get_active_local_analysis_service,
    get_crawl_artifact_store,
    get_templates,
)
from app.artifact_store import CrawlArtifactStore
from app.progress_store import progress_store
from app.repositories import AnalysisResultRepository
from app.schemas import URLSubmission
from app.services.analysis_service import AnalysisService

router = APIRouter()
logger = logging.getLogger(__name__)


def _retry_path_for_analysis_id(analysis_id: str) -> str:
    if analysis_id.startswith("local-"):
        return "/local-search"
    return "/"


def _run_analysis_job(
    *,
    job_id: str,
    submission: URLSubmission,
    analysis_service: AnalysisService,
    repository: AnalysisResultRepository,
) -> None:
    try:
        result = analysis_service.run(
            submission,
            progress_callback=lambda stage: progress_store.update_stage(job_id, stage),
            status_message_callback=lambda message: progress_store.update_status_message(job_id, message),
        )
        analysis_id = repository.create(result)
    except Exception as exc:
        logger.exception("Background analysis job failed", extra={"event": "analysis_job_failed", "job_id": job_id, "exception_class": type(exc).__name__})
        progress_store.fail(job_id, "분석 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")
        return

    progress_store.complete(job_id, analysis_id)


def _handle_analysis_submission(
    *,
    request: Request,
    submitted_url: str,
    templates: Jinja2Templates,
    analysis_service: AnalysisService,
    repository: AnalysisResultRepository,
    retry_path: str,
) -> Response:
    logger.debug(
        "Handling analysis submission",
        extra={
            "event": "analysis_submission_start",
            "retry_path": retry_path,
            "submitted_url_length": len(submitted_url),
        },
    )
    try:
        submission = URLSubmission.model_validate({"url": submitted_url})
    except ValidationError:
        error_code = "missing_url" if not submitted_url else "invalid_url"
        logger.debug("Submission validation failed", extra={"event": "analysis_submission_invalid", "retry_path": retry_path, "error_code": error_code})
        return RedirectResponse(
            url=retry_path + "?" + urlencode({"url": submitted_url, "error": error_code}),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        result = analysis_service.run(submission)
        analysis_id = repository.create(result)
    except Exception as exc:
        logger.exception(
            "Analysis submission failed",
            extra={"event": "analysis_submission_failed", "retry_path": retry_path, "exception_class": type(exc).__name__},
        )
        return templates.TemplateResponse(
            request=request,
            name="analysis_error.html",
            context={
                "request": request,
                "submitted_url": submitted_url,
                "retry_path": retry_path,
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    logger.debug("Analysis submission completed", extra={"event": "analysis_submission_done", "analysis_id": analysis_id, "retry_path": retry_path})
    return RedirectResponse(
        url=f"/analysis/{analysis_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _start_analysis_submission(
    *,
    submitted_url: str,
    analysis_service: AnalysisService,
    repository: AnalysisResultRepository,
    flow: str,
) -> JSONResponse:
    try:
        submission = URLSubmission.model_validate({"url": submitted_url})
    except ValidationError:
        error_code = "missing_url" if not submitted_url else "invalid_url"
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error_code": error_code,
                "error_message": "검증할 URL을 입력해 주세요." if error_code == "missing_url" else "올바른 URL 형식으로 입력해 주세요.",
            },
        )

    job = progress_store.create(flow)
    Thread(
        target=_run_analysis_job,
        kwargs={
            "job_id": job.job_id,
            "submission": submission,
            "analysis_service": analysis_service,
            "repository": repository,
        },
        daemon=True,
    ).start()
    payload = progress_store.serialize(job.job_id)
    assert payload is not None
    payload["status_url"] = f"/analysis/jobs/{job.job_id}/status"
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=payload)


@router.post("/analysis", response_class=HTMLResponse)
def create_analysis(
    request: Request,
    url: Annotated[str, Form()],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    analysis_service: Annotated[AnalysisService, Depends(get_active_analysis_service)],
    repository: Annotated[AnalysisResultRepository, Depends(get_active_analysis_repository)],
) -> Response:
    """Handle browser form submission and redirect to the stored analysis."""

    logger.debug("Received online analysis request", extra={"event": "analysis_route", "path": "/analysis"})

    return _handle_analysis_submission(
        request=request,
        submitted_url=url.strip(),
        templates=templates,
        analysis_service=analysis_service,
        repository=repository,
        retry_path="/",
    )


@router.post("/local-model", response_class=HTMLResponse)
@router.post("/local-search", response_class=HTMLResponse)
def create_local_model_analysis(
    request: Request,
    url: Annotated[str, Form()],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    analysis_service: Annotated[AnalysisService, Depends(get_active_local_analysis_service)],
    repository: Annotated[AnalysisResultRepository, Depends(get_active_analysis_repository)],
) -> Response:
    """Handle browser form submission for the local crawling analysis flow."""

    logger.debug("Received local analysis request", extra={"event": "analysis_route", "path": request.url.path})

    return _handle_analysis_submission(
        request=request,
        submitted_url=url.strip(),
        templates=templates,
        analysis_service=analysis_service,
        repository=repository,
        retry_path=request.url.path,
    )


@router.post("/analysis/start", response_class=JSONResponse)
def start_analysis(
    url: Annotated[str, Form()],
    analysis_service: Annotated[AnalysisService, Depends(get_active_analysis_service)],
    repository: Annotated[AnalysisResultRepository, Depends(get_active_analysis_repository)],
) -> JSONResponse:
    logger.debug("Received async online analysis start request", extra={"event": "analysis_start_route", "path": "/analysis/start"})
    return _start_analysis_submission(
        submitted_url=url.strip(),
        analysis_service=analysis_service,
        repository=repository,
        flow="online",
    )


@router.post("/local-model/start", response_class=JSONResponse)
@router.post("/local-search/start", response_class=JSONResponse)
def start_local_model_analysis(
    request: Request,
    url: Annotated[str, Form()],
    analysis_service: Annotated[AnalysisService, Depends(get_active_local_analysis_service)],
    repository: Annotated[AnalysisResultRepository, Depends(get_active_analysis_repository)],
) -> JSONResponse:
    logger.debug("Received async local analysis start request", extra={"event": "analysis_start_route", "path": request.url.path})
    return _start_analysis_submission(
        submitted_url=url.strip(),
        analysis_service=analysis_service,
        repository=repository,
        flow=request.url.path.lstrip("/").removesuffix("/start"),
    )


@router.get("/analysis/jobs/{job_id}/status", response_class=JSONResponse)
def analysis_job_status(job_id: str) -> JSONResponse:
    payload = progress_store.serialize(job_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis job not found")
    return JSONResponse(content=payload)


@router.get("/analysis/{analysis_id}/artifacts/{artifact_path:path}")
def analysis_artifact_file(
    analysis_id: str,
    artifact_path: str,
    repository: Annotated[AnalysisResultRepository, Depends(get_active_analysis_repository)],
    artifact_store: Annotated[CrawlArtifactStore, Depends(get_crawl_artifact_store)],
) -> FileResponse:
    """Serve a previously saved crawl artifact file."""

    if repository.get(analysis_id) is None:
        logger.debug("Artifact request failed: analysis missing", extra={"event": "artifact_404", "analysis_id": analysis_id, "artifact_path": artifact_path, "reason": "analysis_missing"})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    file_path = artifact_store.resolve(analysis_id, artifact_path)
    if file_path is None:
        logger.debug("Artifact request failed: file missing", extra={"event": "artifact_404", "analysis_id": analysis_id, "artifact_path": artifact_path, "reason": "artifact_missing"})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    logger.debug("Serving artifact file", extra={"event": "artifact_served", "analysis_id": analysis_id, "artifact_path": artifact_path})
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
        retry_path = _retry_path_for_analysis_id(analysis_id)
        logger.debug("Analysis result page miss", extra={"event": "analysis_result_miss", "analysis_id": analysis_id, "retry_path": retry_path})
        return templates.TemplateResponse(
            request=request,
            name="analysis_error.html",
            context={
                "request": request,
                "submitted_url": "",
                "retry_path": retry_path,
                "error_title": "분석 결과를 찾을 수 없습니다.",
                "error_message": "요청한 분석 ID가 없거나 저장소가 초기화되었습니다. 홈으로 돌아가 다시 URL을 제출해 주세요.",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    retry_path = _retry_path_for_analysis_id(result.analysis_id)
    logger.debug("Rendering analysis result page", extra={"event": "analysis_result_render", "analysis_id": result.analysis_id, "retry_path": retry_path})
    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context={
            "request": request,
            "result": result,
            "retry_path": retry_path,
        },
    )
