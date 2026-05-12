from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.prompt_loader import load_prompt


class PromptLoaderTests(unittest.TestCase):
    def test_reads_prompt_from_prompt_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_file = Path(temp_dir) / "custom.txt"
            prompt_file.write_text("제목: $title", encoding="utf-8")

            with patch.dict(os.environ, {"PROMPT_DIR": temp_dir}):
                rendered = load_prompt("custom", title="테스트 제목")

            self.assertEqual(rendered, "제목: 테스트 제목")

    def test_uses_fallback_prompt_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"PROMPT_DIR": temp_dir}):
                rendered = load_prompt("ollama_text", title="제목", url="url", text="본문")

        self.assertIn("제목", rendered)
        self.assertIn("url", rendered)

    def test_raises_for_missing_unknown_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"PROMPT_DIR": temp_dir}):
                with self.assertRaises(FileNotFoundError):
                    load_prompt("missing_prompt")

    def test_reloads_prompt_file_after_it_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_file = Path(temp_dir) / "custom.txt"
            prompt_file.write_text("첫번째 $title", encoding="utf-8")

            with patch.dict(os.environ, {"PROMPT_DIR": temp_dir}):
                first = load_prompt("custom", title="프롬프트")
                prompt_file.write_text("두번째 $title", encoding="utf-8")
                second = load_prompt("custom", title="프롬프트")

        self.assertEqual(first, "첫번째 프롬프트")
        self.assertEqual(second, "두번째 프롬프트")

    def test_raises_clear_error_for_missing_template_variable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_file = Path(temp_dir) / "custom.txt"
            prompt_file.write_text("제목: $title\nURL: $url", encoding="utf-8")

            with patch.dict(os.environ, {"PROMPT_DIR": temp_dir}):
                with self.assertRaisesRegex(ValueError, "Prompt 'custom' is missing template variable 'url'"):
                    load_prompt("custom", title="테스트")


if __name__ == "__main__":
    unittest.main()
