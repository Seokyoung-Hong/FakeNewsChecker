from __future__ import annotations

import unittest

from app.config import CrawlerSettings


class CrawlerSettingsTests(unittest.TestCase):
    def test_from_env_uses_explicit_empty_mapping(self) -> None:
        settings = CrawlerSettings.from_env({})

        self.assertEqual(settings.provider, "deterministic")
        self.assertIsNone(settings.hyperbrowser_api_key)
        self.assertEqual(settings.hyperbrowser_wait_until, "load")
        self.assertEqual(settings.hyperbrowser_wait_for_ms, 1500)
        self.assertEqual(settings.hyperbrowser_timeout_ms, 30000)


if __name__ == "__main__":
    unittest.main()
