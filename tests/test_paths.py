"""Path resolution for pasted/typed input."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cppjudge.core.paths import clean_path_text, resolve_source_path


class CleanTextTests(unittest.TestCase):
    def test_strips_quotes_and_space(self):
        self.assertEqual(clean_path_text('  "/tmp/a b.cpp"  '), "/tmp/a b.cpp")
        self.assertEqual(clean_path_text("'/tmp/x.cpp'"), "/tmp/x.cpp")

    def test_unquotes_file_url(self):
        self.assertEqual(clean_path_text("file:///tmp/a%20b.cpp"), "/tmp/a b.cpp")

    def test_keeps_inner_quotes(self):
        self.assertEqual(clean_path_text("/tmp/it's.cpp"), "/tmp/it's.cpp")


class ResolveTests(unittest.TestCase):
    def test_absolute_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sol.cpp"
            target.write_text("int main(){}\n")
            path, error = resolve_source_path(str(target))
            self.assertEqual(error, "")
            self.assertEqual(path, target.resolve())

    def test_tilde_and_relative(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "rel.cpp").write_text("int main(){}\n")
            path, error = resolve_source_path("rel.cpp", base=base)
            self.assertEqual(error, "")
            self.assertEqual(path, (base / "rel.cpp").resolve())

    def test_missing(self):
        path, error = resolve_source_path("/definitely/not/here.cpp")
        self.assertIsNone(path)
        self.assertIn("No such file", error)

    def test_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, error = resolve_source_path(tmp)
            self.assertIsNone(path)
            self.assertIn("folder", error)

    def test_empty(self):
        path, error = resolve_source_path("   ")
        self.assertIsNone(path)
        self.assertIn("Paste", error)

    def test_multiline_paste(self):
        path, error = resolve_source_path("a.cpp\nb.cpp")
        self.assertIsNone(path)
        self.assertIn("several lines", error)


if __name__ == "__main__":
    unittest.main()
