from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.artifact_store import FilesystemCrawlArtifactStore
from app.dependencies import get_active_analysis_repository, get_crawl_artifact_store
from app.main import app
from app.repositories import InMemoryAnalysisResultRepository
from app.schemas import AnalysisResult, ReportDetail, URLSubmission


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
