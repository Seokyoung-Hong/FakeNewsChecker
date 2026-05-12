from __future__ import annotations

import unittest

from app.config import CrawlerSettings, OllamaSettings


class CrawlerSettingsTests(unittest.TestCase):
    def test_from_env_uses_explicit_empty_mapping(self) -> None:
        settings = CrawlerSettings.from_env({})

        self.assertEqual(settings.provider, "deterministic")
        self.assertIsNone(settings.hyperbrowser_api_key)
        self.assertEqual(settings.hyperbrowser_wait_until, "load")
        self.assertEqual(settings.hyperbrowser_wait_for_ms, 1500)
        self.assertEqual(settings.hyperbrowser_timeout_ms, 30000)


class OllamaSettingsTests(unittest.TestCase):
    def test_from_env_uses_defaults(self) -> None:
        settings = OllamaSettings.from_env({})

        self.assertEqual(settings.host, "http://localhost:11434")
        self.assertEqual(settings.model, "qwen3.5")
        self.assertEqual(settings.timeout_ms, 240000)

    def test_from_env_rejects_empty_model(self) -> None:
        with self.assertRaises(ValueError):
            OllamaSettings.from_env({"OLLAMA_MODEL": "   "})


if __name__ == "__main__":
    unittest.main()
