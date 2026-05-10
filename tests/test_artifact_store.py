from __future__ import annotations

import json
import socket
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.artifact_store import FilesystemCrawlArtifactStore
from app.schemas import CrawlerOutput, URLSubmission


class _FakeHeaders:
    def __init__(self, content_type: str) -> None:
        self._content_type = content_type

    def get_content_type(self) -> str:
        return self._content_type


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str) -> None:
        self._body = body
        self.headers = _FakeHeaders(content_type)

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb


class FilesystemCrawlArtifactStoreTests(unittest.TestCase):
    def test_persist_writes_files_and_downloads_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FilesystemCrawlArtifactStore(Path(tmp_dir))
            crawler_output = CrawlerOutput(
                analysis_id="analysis-1",
                url=URLSubmission.model_validate({"url": "https://example.com/article"}).url,
                title="기사 제목",
                content="기사 본문",
                images=["https://cdn.example.com/non-structured.jpg"],
                metadata={
                    "markdown": "# 기사 제목\n\n기사 본문",
                    "html": "<html><body><img src='image.jpg'></body></html>",
                    "links": ["https://example.com/other"],
                    "structured_data": {
                        "title": "기사 제목",
                        "image_urls": [
                            "https://cdn.example.com/image-1.jpg",
                            "https://cdn.example.com/image-2.jpg",
                            "https://cdn.example.com/image-3.jpg",
                        ],
                    },
                    "job_id": "job-123",
                    "status": "completed",
                    "source_url": "https://example.com/article",
                },
            )

            with patch("app.artifact_store._is_safe_public_image_host", return_value=True), patch(
                "app.artifact_store.urlopen",
                return_value=_FakeResponse(b"image-bytes", "image/jpeg"),
            ):
                manifest = store.persist(crawler_output)

            self.assertTrue(Path(manifest.storage_directory).exists())
            self.assertTrue(any(file.relative_path == "article.txt" for file in manifest.files))
            self.assertTrue(any(file.relative_path == "metadata.json" for file in manifest.files))
            self.assertTrue(any(file.relative_path == "structured_data.json" for file in manifest.files))
            self.assertEqual(manifest.images[0].status, "downloaded")
            self.assertIsNotNone(manifest.images[0].local_file)
            self.assertEqual(len(manifest.images), 2)
            first_file = manifest.images[0].local_file
            second_file = manifest.images[1].local_file
            assert first_file is not None
            assert second_file is not None
            self.assertEqual(first_file.relative_path, "images/image-001.jpg")
            self.assertEqual(second_file.relative_path, "images/image-002.jpg")

            metadata_path = Path(manifest.storage_directory) / "metadata.json"
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["title"], "기사 제목")

            structured_path = Path(manifest.storage_directory) / "structured_data.json"
            structured_payload = json.loads(structured_path.read_text(encoding="utf-8"))
            self.assertEqual(structured_payload["saved_images"][0]["relative_path"], "images/image-001.jpg")
            self.assertEqual(structured_payload["saved_images"][1]["relative_path"], "images/image-002.jpg")

    def test_persist_accepts_attribute_style_structured_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FilesystemCrawlArtifactStore(Path(tmp_dir))
            crawler_output = CrawlerOutput(
                analysis_id="analysis-1",
                url=URLSubmission.model_validate({"url": "https://example.com/article"}).url,
                title="기사 제목",
                content="기사 본문",
                images=[],
                metadata={
                    "source_url": "https://example.com/article",
                    "structured_data": SimpleNamespace(
                        title="기사 제목",
                        image_urls=["https://cdn.example.com/image-1.jpg", "https://cdn.example.com/image-2.jpg"],
                    ),
                },
            )

            with patch("app.artifact_store._is_safe_public_image_host", return_value=True), patch(
                "app.artifact_store.urlopen",
                return_value=_FakeResponse(b"image-bytes", "image/jpeg"),
            ):
                manifest = store.persist(crawler_output)

        self.assertEqual(len(manifest.images), 2)
        self.assertEqual(manifest.images[0].status, "downloaded")

    def test_persist_normalizes_relative_structured_image_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FilesystemCrawlArtifactStore(Path(tmp_dir))
            crawler_output = CrawlerOutput(
                analysis_id="analysis-1",
                url=URLSubmission.model_validate({"url": "https://example.com/news/article"}).url,
                title="기사 제목",
                content="기사 본문",
                images=[],
                metadata={
                    "source_url": "https://example.com/news/article",
                    "structured_data": {
                        "title": "기사 제목",
                        "image_urls": ["thumb.jpg", "/images/cover.png"],
                    },
                },
            )

            captured_urls: list[str] = []

            def fake_urlopen(request: object, timeout: int) -> _FakeResponse:
                del timeout
                full_url = getattr(request, "full_url")
                assert isinstance(full_url, str)
                captured_urls.append(full_url)
                return _FakeResponse(b"image-bytes", "image/png")

            with patch("app.artifact_store._is_safe_public_image_host", return_value=True), patch(
                "app.artifact_store.urlopen",
                side_effect=fake_urlopen,
            ):
                manifest = store.persist(crawler_output)

        self.assertEqual(
            captured_urls,
            [
                "https://example.com/news/thumb.jpg",
                "https://example.com/images/cover.png",
            ],
        )
        self.assertEqual(len(manifest.images), 2)

    def test_resolve_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FilesystemCrawlArtifactStore(Path(tmp_dir))
            analysis_dir = Path(tmp_dir) / "analysis-1"
            analysis_dir.mkdir(parents=True)
            (analysis_dir / "article.txt").write_text("hello", encoding="utf-8")

            self.assertIsNone(store.resolve("analysis-1", "../secrets.txt"))
            self.assertIsNotNone(store.resolve("analysis-1", "article.txt"))

    def test_resolve_rejects_analysis_id_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FilesystemCrawlArtifactStore(Path(tmp_dir))

            self.assertIsNone(store.resolve("..", "outside.txt"))

    def test_persist_skips_non_public_image_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FilesystemCrawlArtifactStore(Path(tmp_dir))
            crawler_output = CrawlerOutput(
                analysis_id="analysis-1",
                url=URLSubmission.model_validate({"url": "https://example.com/article"}).url,
                title="기사 제목",
                content="기사 본문",
                images=[],
                metadata={"structured_data": {"image_urls": ["http://127.0.0.1/private.png"]}},
            )

            manifest = store.persist(crawler_output)

        self.assertEqual(manifest.images[0].status, "skipped")
        self.assertIn("not allowed", manifest.images[0].error or "")

    def test_persist_skips_unresolvable_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FilesystemCrawlArtifactStore(Path(tmp_dir))
            crawler_output = CrawlerOutput(
                analysis_id="analysis-1",
                url=URLSubmission.model_validate({"url": "https://example.com/article"}).url,
                title="기사 제목",
                content="기사 본문",
                images=[],
                metadata={"structured_data": {"image_urls": ["https://invalid.example.test/image.png"]}},
            )

            with patch("app.artifact_store.socket.getaddrinfo", side_effect=socket.gaierror()):
                manifest = store.persist(crawler_output)

        self.assertEqual(manifest.images[0].status, "skipped")


if __name__ == "__main__":
    unittest.main()
