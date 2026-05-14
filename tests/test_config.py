from __future__ import annotations

import unittest

from app.config import CrawlerSettings, OllamaSettings, is_production_mode


class CrawlerSettingsTests(unittest.TestCase):
    def test_from_env_uses_explicit_empty_mapping(self) -> None:
        settings = CrawlerSettings.from_env({})

        self.assertEqual(settings.provider, "deterministic")
        self.assertIsNone(settings.hyperbrowser_api_key)
        self.assertEqual(settings.hyperbrowser_wait_until, "load")
        self.assertEqual(settings.hyperbrowser_wait_for_ms, 1500)
        self.assertEqual(settings.hyperbrowser_timeout_ms, 30000)
        self.assertEqual(settings.local_crawler_backend, "playwright")
        self.assertTrue(settings.local_crawler_headless)
        self.assertEqual(settings.local_crawler_wait_until, "networkidle")
        self.assertEqual(settings.local_crawler_wait_for_ms, 1000)
        self.assertEqual(settings.local_crawler_timeout_ms, 45000)
        self.assertTrue(settings.local_crawler_block_media)
        self.assertFalse(settings.local_crawler_mcp_enabled)

    def test_from_env_parses_local_crawler_settings(self) -> None:
        settings = CrawlerSettings.from_env(
            {
                "LOCAL_CRAWLER_BACKEND": "playwright",
                "LOCAL_CRAWLER_HEADLESS": "false",
                "LOCAL_CRAWLER_WAIT_UNTIL": "load",
                "LOCAL_CRAWLER_WAIT_FOR_MS": "2500",
                "LOCAL_CRAWLER_TIMEOUT_MS": "90000",
                "LOCAL_CRAWLER_BLOCK_MEDIA": "no",
                "LOCAL_CRAWLER_MCP_ENABLED": "yes",
                "LOCAL_CRAWLER_USER_AGENT": "CustomAgent/2.0",
            }
        )

        self.assertEqual(settings.local_crawler_backend, "playwright")
        self.assertFalse(settings.local_crawler_headless)
        self.assertEqual(settings.local_crawler_wait_until, "load")
        self.assertEqual(settings.local_crawler_wait_for_ms, 2500)
        self.assertEqual(settings.local_crawler_timeout_ms, 90000)
        self.assertFalse(settings.local_crawler_block_media)
        self.assertTrue(settings.local_crawler_mcp_enabled)
        self.assertEqual(settings.local_crawler_user_agent, "CustomAgent/2.0")


class OllamaSettingsTests(unittest.TestCase):
    def test_from_env_uses_defaults(self) -> None:
        settings = OllamaSettings.from_env({})

        self.assertEqual(settings.host, "http://localhost:11434")
        self.assertEqual(settings.fallback_hosts, ())
        self.assertEqual(settings.hosts, ("http://localhost:11434",))
        self.assertEqual(settings.model, "qwen3.5")
        self.assertEqual(settings.timeout_ms, 240000)

    def test_from_env_parses_ordered_fallback_hosts(self) -> None:
        settings = OllamaSettings.from_env(
            {
                "OLLAMA_HOST": "http://desktop:11434",
                "OLLAMA_FALLBACK_HOSTS": " http://server:11434 , http://localhost:11434 ",
            }
        )

        self.assertEqual(settings.host, "http://desktop:11434")
        self.assertEqual(
            settings.fallback_hosts,
            ("http://server:11434", "http://localhost:11434"),
        )
        self.assertEqual(
            settings.hosts,
            (
                "http://desktop:11434",
                "http://server:11434",
                "http://localhost:11434",
            ),
        )

    def test_hosts_deduplicates_primary_and_fallback_entries(self) -> None:
        settings = OllamaSettings(
            host="http://desktop:11434",
            fallback_hosts=("http://desktop:11434", "http://server:11434"),
        )

        self.assertEqual(
            settings.hosts,
            ("http://desktop:11434", "http://server:11434"),
        )

    def test_from_env_rejects_empty_fallback_host_entry(self) -> None:
        with self.assertRaises(ValueError):
            _ = OllamaSettings.from_env({"OLLAMA_FALLBACK_HOSTS": "http://desktop:11434,  ,http://server:11434"})

    def test_from_env_rejects_empty_model(self) -> None:
        with self.assertRaises(ValueError):
            _ = OllamaSettings.from_env({"OLLAMA_MODEL": "   "})

    def test_from_env_parses_fallback_models(self) -> None:
        settings = OllamaSettings.from_env(
            {
                "OLLAMA_HOST": "http://primary:11434",
                "OLLAMA_FALLBACK_HOSTS": "http://backup:11434 , http://third:11434",
                "OLLAMA_MODEL": "llama-main",
                "OLLAMA_FALLBACK_MODELS": "llama-fail1, llama-fail2",
            }
        )

        self.assertEqual(
            settings.host_model_pairs,
            (
                ("http://primary:11434", "llama-main"),
                ("http://backup:11434", "llama-fail1"),
                ("http://third:11434", "llama-fail2"),
            ),
        )

    def test_host_model_pairs_falls_back_to_primary_model_for_extra_hosts(self) -> None:
        settings = OllamaSettings(
            host="http://primary:11434",
            fallback_hosts=("http://backup:11434",),
            model="llama-main",
            fallback_models=(),
        )

        self.assertEqual(
            settings.host_model_pairs,
            (
                ("http://primary:11434", "llama-main"),
                ("http://backup:11434", "llama-main"),
            ),
        )

    def test_from_env_rejects_empty_fallback_model_entry(self) -> None:
        with self.assertRaises(ValueError):
            _ = OllamaSettings.from_env(
                {
                    "OLLAMA_HOST": "http://primary:11434",
                    "OLLAMA_FALLBACK_MODELS": "llama-main, , llama-two",
                }
            )


class ProductionModeTests(unittest.TestCase):
    def test_is_production_mode_defaults_to_true(self) -> None:
        self.assertTrue(is_production_mode({}))

    def test_is_production_mode_reads_lowercase_env_flag(self) -> None:
        self.assertFalse(is_production_mode({"production_mode": "false"}))

    def test_is_production_mode_reads_uppercase_env_flag(self) -> None:
        self.assertFalse(is_production_mode({"PRODUCTION_MODE": "false"}))


if __name__ == "__main__":
    _ = unittest.main()
