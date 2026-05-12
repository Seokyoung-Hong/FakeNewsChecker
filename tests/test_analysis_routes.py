from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.artifact_store import FilesystemCrawlArtifactStore
from app.dependencies import (
    get_active_analysis_repository,
    get_active_analysis_service,
    get_active_local_analysis_service,
    get_crawl_artifact_store,
)
from app.main import app
from app.progress_store import progress_store
from app.repositories import InMemoryAnalysisResultRepository
from app.schemas import AnalysisResult, ReportDetail, URLSubmission


class _FakeAnalysisService:
    _analysis_id: str

    def __init__(self, analysis_id: str) -> None:
        self._analysis_id = analysis_id

    def run(self, submission: URLSubmission) -> AnalysisResult:
        return AnalysisResult(
            analysis_id=self._analysis_id,
            url=submission.url,
            title="기사 제목",
            original_content="본문",
            score=80,
            label="신뢰 가능",
            summary="요약",
            details=[
                ReportDetail(
                    key="source_reliability",
                    label="출처 신뢰도",
                    score=80,
                    summary="ok",
                    risk="low",
                )
            ],
        )


class _ProgressAwareFakeAnalysisService(_FakeAnalysisService):
    def run(self, submission: URLSubmission, progress_callback=None) -> AnalysisResult:
        if callable(progress_callback):
            progress_callback("body_collection")
            progress_callback("source_check")
            progress_callback("ai_analysis")
            progress_callback("report_build")
        return super().run(submission)


class _ImmediateThread:
    def __init__(self, target, kwargs=None, daemon=None):
        self._target = target
        self._kwargs = kwargs or {}
        self._daemon = daemon

    def start(self) -> None:
        self._target(**self._kwargs)


class AnalysisSubmissionRouteTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        progress_store.clear()

    def test_homepage_renders_verification_sections(self) -> None:
        client = TestClient(app)

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("검증하고 싶은 뉴스", response.text)
        self.assertIn("Start verification", response.text)
        self.assertIn("What happens next", response.text)
        self.assertIn('id="form-error-summary"', response.text)
        self.assertIn('id="loading-error-message"', response.text)

    def test_post_analysis_redirects_to_result_page(self) -> None:
        repository = InMemoryAnalysisResultRepository()
        app.dependency_overrides[get_active_analysis_service] = lambda: _FakeAnalysisService("online-1")
        app.dependency_overrides[get_active_analysis_repository] = lambda: repository
        try:
            client = TestClient(app)
            response = client.post("/analysis", data={"url": "https://example.com/article"}, follow_redirects=False)
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/analysis/online-1")
        self.assertIsNotNone(repository.get("online-1"))

    def test_post_local_model_redirects_to_result_page(self) -> None:
        repository = InMemoryAnalysisResultRepository()
        app.dependency_overrides[get_active_local_analysis_service] = lambda: _FakeAnalysisService("local-1")
        app.dependency_overrides[get_active_analysis_repository] = lambda: repository
        try:
            client = TestClient(app)
            response = client.post("/local-model", data={"url": "https://example.com/article"}, follow_redirects=False)
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/analysis/local-1")
        self.assertIsNotNone(repository.get("local-1"))

    def test_local_model_page_uses_local_form_action(self) -> None:
        client = TestClient(app)
        response = client.get("/local-model")

        self.assertEqual(response.status_code, 200)
        self.assertIn('action="/local-model"', response.text)
        self.assertIn("링크를 입력하고 확인하세요", response.text)
        self.assertIn("local model", response.text.lower())

    def test_local_result_page_uses_local_retry_path(self) -> None:
        repository = InMemoryAnalysisResultRepository()
        repository.create(
            AnalysisResult(
                analysis_id="local-1",
                url=URLSubmission.model_validate({"url": "https://example.com/article"}).url,
                title="기사 제목",
                original_content="본문",
                score=80,
                label="신뢰 가능",
                summary="요약",
                details=[
                    ReportDetail(
                        key="source_reliability",
                        label="출처 신뢰도",
                        score=80,
                        summary="ok",
                        risk="low",
                    )
                ],
            )
        )
        app.dependency_overrides[get_active_analysis_repository] = lambda: repository
        try:
            client = TestClient(app)
            response = client.get("/analysis/local-1")
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/local-model"', response.text)
        self.assertIn("무엇을 확인했는지 먼저 보여드립니다.", response.text)
        self.assertIn("세부 검증 항목", response.text)
        self.assertIn("원문과 저장 자료", response.text)

    def test_start_analysis_returns_progress_payload_and_status(self) -> None:
        repository = InMemoryAnalysisResultRepository()
        app.dependency_overrides[get_active_analysis_service] = lambda: _ProgressAwareFakeAnalysisService("online-1")
        app.dependency_overrides[get_active_analysis_repository] = lambda: repository
        with patch("app.routers.analysis.Thread", _ImmediateThread):
            client = TestClient(app)
            response = client.post("/analysis/start", data={"url": "https://example.com/article"})

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["redirect_url"], "/analysis/online-1")
        self.assertEqual(payload["stage"], "report_build")

        status_response = client.get(payload["status_url"])
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["status"], "completed")

    def test_start_local_model_returns_progress_payload(self) -> None:
        repository = InMemoryAnalysisResultRepository()
        app.dependency_overrides[get_active_local_analysis_service] = lambda: _ProgressAwareFakeAnalysisService("local-1")
        app.dependency_overrides[get_active_analysis_repository] = lambda: repository
        with patch("app.routers.analysis.Thread", _ImmediateThread):
            client = TestClient(app)
            response = client.post("/local-model/start", data={"url": "https://example.com/article"})

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["flow"], "local-model")
        self.assertEqual(payload["redirect_url"], "/analysis/local-1")

    def test_missing_analysis_id_renders_recovery_error_page(self) -> None:
        client = TestClient(app)

        response = client.get("/analysis/missing-id")

        self.assertEqual(response.status_code, 404)
        self.assertIn("분석 결과를 찾을 수 없습니다.", response.text)
        self.assertIn("이전 화면으로 돌아가 다시 시도하기", response.text)


class AnalysisArtifactRouteTests(unittest.TestCase):
    def test_artifact_route_serves_saved_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            analysis_dir = root / "analysis-1"
            analysis_dir.mkdir(parents=True)
            (analysis_dir / "article.txt").write_text("saved article", encoding="utf-8")

            repository = InMemoryAnalysisResultRepository()
            repository.create(
                AnalysisResult(
                    analysis_id="analysis-1",
                    url=URLSubmission.model_validate({"url": "https://example.com/article"}).url,
                    title="기사 제목",
                    original_content="본문",
                    score=80,
                    label="신뢰 가능",
                    summary="요약",
                    details=[
                        ReportDetail(
                            key="source_reliability",
                            label="출처 신뢰도",
                            score=80,
                            summary="ok",
                            risk="low",
                        )
                    ],
                )
            )

            app.dependency_overrides[get_crawl_artifact_store] = lambda: FilesystemCrawlArtifactStore(root)
            app.dependency_overrides[get_active_analysis_repository] = lambda: repository
            try:
                client = TestClient(app)
                response = client.get("/analysis/analysis-1/artifacts/article.txt")
            finally:
                app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200)
        self.assertIn("saved article", response.text)

    def test_artifact_route_returns_not_found_when_analysis_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            analysis_dir = root / "analysis-1"
            analysis_dir.mkdir(parents=True)
            (analysis_dir / "article.txt").write_text("saved article", encoding="utf-8")

            app.dependency_overrides[get_crawl_artifact_store] = lambda: FilesystemCrawlArtifactStore(root)
            app.dependency_overrides[get_active_analysis_repository] = lambda: InMemoryAnalysisResultRepository()
            try:
                client = TestClient(app)
                response = client.get("/analysis/analysis-1/artifacts/article.txt")
            finally:
                app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
