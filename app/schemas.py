"""Shared typed contracts for the analysis pipeline and persistence seam.

These schemas are intentionally transport-agnostic so stages can pass rich,
validated domain objects instead of ad-hoc dictionaries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field, HttpUrl


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class URLSubmission(BaseModel):
    """Contract for user input submitted to the analysis flow."""

    url: HttpUrl = Field(description="User-provided URL to analyze")


class CrawlerOutput(BaseModel):
    """Contract for collected source material."""

    analysis_id: str = Field(description="Analysis identifier for this pipeline run")
    url: HttpUrl
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    images: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    collected_at: datetime = Field(default_factory=_utcnow)


class AnalysisCriterionResult(BaseModel):
    """Single criterion result used by analysis and score/report stages."""

    score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1)
    risk: str | None = Field(default=None)


class AnalysisOutput(BaseModel):
    """Internal contract returned by the analysis stage."""

    analysis_id: str
    url: HttpUrl
    source_reliability: AnalysisCriterionResult
    claim_consistency: AnalysisCriterionResult
    evidence_quality: AnalysisCriterionResult
    expression_risk: AnalysisCriterionResult
    multimodal_risk: AnalysisCriterionResult
    overall_summary: str = Field(min_length=1)


class ScoringOutput(BaseModel):
    """Internal contract returned by the scoring stage."""

    analysis_id: str
    score: int = Field(ge=0, le=100)
    score_band: str = Field(description="One of: trustworthy, caution, suspicious, likely_fake")
    criteria_breakdown: dict[str, int]
    rationale: list[str] = Field(default_factory=list)


class ReportDetail(BaseModel):
    """Detail item rendered in the result page and report payload."""

    key: str
    label: str
    score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1)
    risk: str | None = None


class ReportOutput(BaseModel):
    """Final report-ready payload before rendering."""

    analysis_id: str
    summary: str = Field(min_length=1)
    details: list[ReportDetail]
    recommendation: str | None = None


class ArtifactFile(BaseModel):
    """Single saved file on local disk."""

    label: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    media_type: str | None = None


class DownloadedImage(BaseModel):
    """Result of trying to save one image locally."""

    source_url: str = Field(min_length=1)
    status: str = Field(min_length=1)
    local_file: ArtifactFile | None = None
    error: str | None = None


class DownloadArtifactManifest(BaseModel):
    """Saved crawl artifact summary shown on the result page."""

    storage_directory: str = Field(min_length=1)
    files: list[ArtifactFile] = Field(default_factory=list)
    images: list[DownloadedImage] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Persisted/final rendered result payload consumed by result page."""

    analysis_id: str = Field(default="", description="Unique result identifier")
    url: HttpUrl
    title: str
    original_content: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)
    label: str = Field(description="Human-facing score band label")
    summary: str = Field(min_length=1)
    details: list[ReportDetail]
    artifacts: DownloadArtifactManifest | None = None
    created_at: datetime = Field(default_factory=_utcnow)


def derive_score_band(score: int) -> str:
    """Map a score to the user-facing score band label."""

    if score >= 80:
        return "신뢰 가능"
    if score >= 60:
        return "주의 필요"
    if score >= 40:
        return "의심 필요"
    return "가짜뉴스 가능성 높음"


__all__ = [
    "URLSubmission",
    "CrawlerOutput",
    "AnalysisCriterionResult",
    "AnalysisOutput",
    "ScoringOutput",
    "ReportDetail",
    "ReportOutput",
    "ArtifactFile",
    "DownloadedImage",
    "DownloadArtifactManifest",
    "AnalysisResult",
    "derive_score_band",
]
