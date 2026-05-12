"""In-memory progress tracking for analysis jobs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import Lock
from uuid import uuid4


logger = logging.getLogger(__name__)

STAGE_BODY_COLLECTION = "body_collection"
STAGE_SOURCE_CHECK = "source_check"
STAGE_AI_ANALYSIS = "ai_analysis"
STAGE_REPORT_BUILD = "report_build"

_STAGE_LABELS = {
    STAGE_BODY_COLLECTION: "본문 수집중",
    STAGE_SOURCE_CHECK: "출처 확인중",
    STAGE_AI_ANALYSIS: "AI 분석중",
    STAGE_REPORT_BUILD: "리포트 생성 중",
}


@dataclass
class AnalysisProgressJob:
    job_id: str
    flow: str
    status: str = "running"
    stage: str = STAGE_BODY_COLLECTION
    analysis_id: str | None = None
    error_message: str | None = None
    completed_stages: list[str] = field(default_factory=list)


class InMemoryAnalysisProgressStore:
    _lock: Lock

    def __init__(self) -> None:
        self._jobs: dict[str, AnalysisProgressJob] = {}
        self._lock = Lock()

    def create(self, flow: str) -> AnalysisProgressJob:
        job = AnalysisProgressJob(job_id=str(uuid4()), flow=flow)
        with self._lock:
            self._jobs[job.job_id] = job
        logger.debug("Created analysis progress job", extra={"event": "progress_job_created", "job_id": job.job_id, "flow": flow})
        return job

    def update_stage(self, job_id: str, stage: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if job.stage != stage and job.stage not in job.completed_stages:
                job.completed_stages.append(job.stage)
            job.stage = stage
        logger.debug("Updated analysis progress stage", extra={"event": "progress_job_stage", "job_id": job_id, "stage": stage})

    def complete(self, job_id: str, analysis_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if job.stage not in job.completed_stages:
                job.completed_stages.append(job.stage)
            job.status = "completed"
            job.analysis_id = analysis_id
        logger.debug("Completed analysis progress job", extra={"event": "progress_job_completed", "job_id": job_id, "analysis_id": analysis_id})

    def fail(self, job_id: str, error_message: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.error_message = error_message
        logger.debug("Failed analysis progress job", extra={"event": "progress_job_failed", "job_id": job_id})

    def get(self, job_id: str) -> AnalysisProgressJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return AnalysisProgressJob(
                job_id=job.job_id,
                flow=job.flow,
                status=job.status,
                stage=job.stage,
                analysis_id=job.analysis_id,
                error_message=job.error_message,
                completed_stages=list(job.completed_stages),
            )

    def serialize(self, job_id: str) -> dict[str, object] | None:
        job = self.get(job_id)
        if job is None:
            return None
        redirect_url = f"/analysis/{job.analysis_id}" if job.analysis_id else None
        return {
            "job_id": job.job_id,
            "flow": job.flow,
            "status": job.status,
            "stage": job.stage,
            "stage_label": _STAGE_LABELS[job.stage],
            "completed_stages": list(job.completed_stages),
            "analysis_id": job.analysis_id,
            "redirect_url": redirect_url,
            "error_message": job.error_message,
        }

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()


progress_store = InMemoryAnalysisProgressStore()


__all__ = [
    "STAGE_AI_ANALYSIS",
    "STAGE_BODY_COLLECTION",
    "STAGE_REPORT_BUILD",
    "STAGE_SOURCE_CHECK",
    "AnalysisProgressJob",
    "InMemoryAnalysisProgressStore",
    "progress_store",
]
