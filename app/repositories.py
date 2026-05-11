"""In-memory repository abstraction for analysis result storage."""

from __future__ import annotations

import copy
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from threading import RLock
from typing import Protocol


class AnalysisResultLike(Protocol):
    """Shape contract shared by persisted result payloads."""

    analysis_id: str


def _default_id_factory() -> str:
    return str(uuid.uuid4())


class AnalysisResultRepository(ABC):
    """Repository protocol used by services and routes."""

    @abstractmethod
    def create(self, result: AnalysisResultLike) -> str:
        """Store the result and return its analysis ID."""
        del result
        raise NotImplementedError

    @abstractmethod
    def get(self, analysis_id: str) -> AnalysisResultLike | None:
        """Fetch a stored result by analysis ID."""
        del analysis_id
        raise NotImplementedError


class InMemoryAnalysisResultRepository(AnalysisResultRepository):
    """Thread-safe in-memory repository for prototype persistence."""

    def __init__(
        self,
        id_factory: Callable[[], str] = _default_id_factory,
    ) -> None:
        self._id_factory: Callable[[], str] = id_factory
        self._store: dict[str, AnalysisResultLike] = {}
        self._lock: RLock = RLock()

    def create(self, result: AnalysisResultLike) -> str:
        result_payload = copy.deepcopy(result)
        if not result_payload.analysis_id:
            result_payload.analysis_id = self._id_factory()

        with self._lock:
            self._store[result_payload.analysis_id] = result_payload

        return result_payload.analysis_id

    def get(self, analysis_id: str) -> AnalysisResultLike | None:
        with self._lock:
            result = self._store.get(analysis_id)

        if result is None:
            return None

        return copy.deepcopy(result)
