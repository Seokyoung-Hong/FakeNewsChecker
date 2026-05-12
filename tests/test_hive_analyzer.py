from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app.hive_analyzer import analyze_images


def _cache_root_path(tmp_dir: str) -> str:
    return str(Path(tmp_dir, "artifact-cache"))


class HiveAnalyzerCacheTests(unittest.TestCase):
    def test_reuses_cached_result_within_ttl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = {"ANALYSIS_ARTIFACT_ROOT": _cache_root_path(tmp_dir)}
            response_payload = {
                "status": {"output": [{"classes": [{"class": "ai_generated", "score": 0.1}]}]}
            }
            response = httpx.Response(
                200,
                json=response_payload,
                request=httpx.Request("POST", "https://api.thehive.ai/api/v3/hive/ai-generated-and-deepfake-content-detection"),
            )
            with patch.dict("os.environ", env, clear=False), patch("app.hive_analyzer.HIVE_API_KEY", "secret"), patch(
                "app.hive_analyzer.httpx.post",
                return_value=response,
            ) as post_mock:
                first = analyze_images(["https://cdn.example.com/image-1.jpg", "https://cdn.example.com/image-1.jpg"])
                second = analyze_images(["https://cdn.example.com/image-1.jpg"])

        self.assertEqual(first, second)
        post_mock.assert_called_once()

    def test_does_not_cache_failure_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = {"ANALYSIS_ARTIFACT_ROOT": _cache_root_path(tmp_dir)}
            with patch.dict("os.environ", env, clear=False), patch("app.hive_analyzer.HIVE_API_KEY", "secret"), patch(
                "app.hive_analyzer.httpx.post",
                side_effect=httpx.ConnectError("down"),
            ) as post_mock:
                first = analyze_images(["https://cdn.example.com/image-1.jpg"])
                second = analyze_images(["https://cdn.example.com/image-1.jpg"])

        self.assertEqual(first["risk"], "unknown")
        self.assertEqual(second["risk"], "unknown")
        self.assertEqual(post_mock.call_count, 2)

    def test_does_not_cache_partial_success_when_one_image_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = {"ANALYSIS_ARTIFACT_ROOT": _cache_root_path(tmp_dir)}
            ok_response = httpx.Response(
                200,
                json={"status": {"output": [{"classes": [{"class": "ai_generated", "score": 0.1}]}]}},
                request=httpx.Request("POST", "https://api.thehive.ai/api/v3/hive/ai-generated-and-deepfake-content-detection"),
            )
            responses = [
                ok_response,
                httpx.Response(
                    500,
                    json={"message": "temporary error"},
                    request=httpx.Request("POST", "https://api.thehive.ai/api/v3/hive/ai-generated-and-deepfake-content-detection"),
                ),
                ok_response,
                httpx.Response(
                    500,
                    json={"message": "temporary error"},
                    request=httpx.Request("POST", "https://api.thehive.ai/api/v3/hive/ai-generated-and-deepfake-content-detection"),
                ),
            ]
            with patch.dict("os.environ", env, clear=False), patch("app.hive_analyzer.HIVE_API_KEY", "secret"), patch(
                "app.hive_analyzer.httpx.post",
                side_effect=responses,
            ) as post_mock:
                first = analyze_images([
                    "https://cdn.example.com/image-1.jpg",
                    "https://cdn.example.com/image-2.jpg",
                ])
                second = analyze_images([
                    "https://cdn.example.com/image-1.jpg",
                    "https://cdn.example.com/image-2.jpg",
                ])

        self.assertEqual(first, second)
        self.assertEqual(post_mock.call_count, 4)
