"""ORM model placeholders for future persistence integration.

These definitions intentionally avoid importing database-specific libraries so
that importing this module is always safe and side-effect free.
"""


from __future__ import annotations

from datetime import datetime


class PlaceholderModel:
    """Base placeholder class for future ORM model definitions."""

    __tablename__: str = "analysis_result"


class AnalysisResultRecord(PlaceholderModel):
    """Domain placeholder matching the planned persisted result shape."""

    def __init__(self) -> None:
        self.id: int | None = None
        self.url: str | None = None
        self.title: str | None = None
        self.content: str | None = None
        self.score: int | None = None
        self.result_label: str | None = None
        self.report_json: str | None = None
        self.created_at: datetime | None = None


__all__ = ["PlaceholderModel", "AnalysisResultRecord"]
