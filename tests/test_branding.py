"""Branding lives in one JSON file so a fork can rename the app."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cppjudge import branding
from cppjudge.core.settings import config_dir


class BrandingTests(unittest.TestCase):
    def tearDown(self) -> None:
        branding.load_branding.cache_clear()

    def test_shipped_branding_is_used(self) -> None:
        branding.load_branding.cache_clear()
        current = branding.load_branding()
        shipped = json.loads(
            branding.resource_path("branding.json").read_text(encoding="utf-8")
        )
        self.assertEqual(current.app_name, shipped["app_name"])
        self.assertEqual(current.app_name, "C++ Helper")
        self.assertEqual(current.config_dir, "cpp-helper")

    def test_reads_a_replacement_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "branding.json"
            path.write_text(
                json.dumps({"app_name": "Something Else", "config_dir": "something"})
            )
            with patch.object(branding, "resource_path", return_value=path):
                branding.load_branding.cache_clear()
                current = branding.load_branding()
        self.assertEqual(current.app_name, "Something Else")
        self.assertEqual(current.config_dir, "something")
        self.assertEqual(current.exe_name, "cpp-helper", "missing keys keep defaults")

    def test_broken_file_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "branding.json"
            path.write_text("{not json")
            with patch.object(branding, "resource_path", return_value=path):
                branding.load_branding.cache_clear()
                current = branding.load_branding()
        self.assertEqual(current, branding.DEFAULTS)

    def test_config_dir_follows_branding(self) -> None:
        branding.load_branding.cache_clear()
        self.assertEqual(config_dir().name, "cpp-helper")


if __name__ == "__main__":
    unittest.main()
