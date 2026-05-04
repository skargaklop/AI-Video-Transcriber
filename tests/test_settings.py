"""Tests for the shared settings module."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import settings as settings_module
from settings import (
    DEFAULT_SETTINGS,
    get_credential,
    get_masked_settings,
    load_settings,
    mask_credential,
    save_settings,
)


class TestLoadSettings(unittest.TestCase):
    def test_returns_defaults_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(settings_module, "SETTINGS_FILE", Path(tmpdir) / "settings.json"):
                result = load_settings()
                self.assertEqual(result, DEFAULT_SETTINGS)

    def test_reads_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = Path(tmpdir) / "settings.json"
            sf.write_text(json.dumps({"groq_api_key": "gsk_test123"}))
            with patch.object(settings_module, "SETTINGS_FILE", sf):
                result = load_settings()
                self.assertEqual(result["groq_api_key"], "gsk_test123")
                # Missing keys get defaults
                self.assertEqual(result["openai_api_key"], "")

    def test_handles_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = Path(tmpdir) / "settings.json"
            sf.write_text("not valid json{{{")
            with patch.object(settings_module, "SETTINGS_FILE", sf):
                result = load_settings()
                self.assertEqual(result, DEFAULT_SETTINGS)


class TestSaveSettings(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = Path(tmpdir) / "settings.json"
            with patch.object(settings_module, "SETTINGS_FILE", sf):
                save_settings({"groq_api_key": "gsk_abc"})
                result = load_settings()
                self.assertEqual(result["groq_api_key"], "gsk_abc")

    def test_merges_with_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = Path(tmpdir) / "settings.json"
            with patch.object(settings_module, "SETTINGS_FILE", sf):
                save_settings({"groq_api_key": "gsk_first"})
                save_settings({"openai_api_key": "sk_second"})
                result = load_settings()
                self.assertEqual(result["groq_api_key"], "gsk_first")
                self.assertEqual(result["openai_api_key"], "sk_second")

    def test_atomic_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = Path(tmpdir) / "settings.json"
            with patch.object(settings_module, "SETTINGS_FILE", sf):
                save_settings({"groq_api_key": "gsk_atomic"})
                # No leftover .tmp file
                self.assertFalse(sf.with_suffix(".tmp").exists())
                # settings.json exists and is valid
                self.assertTrue(sf.exists())
                data = json.loads(sf.read_text(encoding="utf-8"))
                self.assertEqual(data["groq_api_key"], "gsk_atomic")


class TestGetCredential(unittest.TestCase):
    def test_env_var_takes_precedence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = Path(tmpdir) / "settings.json"
            sf.write_text(json.dumps({"groq_api_key": "from_settings"}))
            with patch.object(settings_module, "SETTINGS_FILE", sf):
                os.environ["TEST_GROQ_KEY"] = "from_env"
                try:
                    result = get_credential("TEST_GROQ_KEY", "groq_api_key")
                    self.assertEqual(result, "from_env")
                finally:
                    del os.environ["TEST_GROQ_KEY"]

    def test_falls_back_to_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = Path(tmpdir) / "settings.json"
            sf.write_text(json.dumps({"groq_api_key": "from_settings"}))
            with patch.object(settings_module, "SETTINGS_FILE", sf):
                result = get_credential("NONEXISTENT_VAR_12345", "groq_api_key")
                self.assertEqual(result, "from_settings")

    def test_returns_empty_when_both_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = Path(tmpdir) / "settings.json"
            with patch.object(settings_module, "SETTINGS_FILE", sf):
                result = get_credential("NONEXISTENT_VAR_12345", "groq_api_key")
                self.assertEqual(result, "")


class TestMaskCredential(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(mask_credential(""), "")

    def test_short_value(self):
        self.assertEqual(mask_credential("abc"), "****")

    def test_exact_8_chars(self):
        self.assertEqual(mask_credential("12345678"), "****")

    def test_long_value(self):
        self.assertEqual(mask_credential("gsk_abcdefgXYZ1234"), "gsk_...1234")


class TestGetMaskedSettings(unittest.TestCase):
    def test_credentials_are_masked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = Path(tmpdir) / "settings.json"
            sf.write_text(json.dumps({
                "groq_api_key": "gsk_longkey123456",
                "openai_api_key": "sk-longkey789012",
            }))
            with patch.object(settings_module, "SETTINGS_FILE", sf):
                result = get_masked_settings()
                self.assertNotEqual(result["groq_api_key"], "gsk_longkey123456")
                self.assertNotEqual(result["openai_api_key"], "sk-longkey789012")
                self.assertIn("...", result["groq_api_key"])
                self.assertIn("...", result["openai_api_key"])


if __name__ == "__main__":
    unittest.main()
