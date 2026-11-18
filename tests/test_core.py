"""Core tests. No Qt required: run with ``python -m unittest discover -s tests``."""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from cppjudge.core import judge, source_scan
from cppjudge.core.compiler import compile_source, parse_diagnostics, probe
from cppjudge.core.models import Case, Verdict
from cppjudge.core.runner import CaseRun, remove_tree, run_case
from cppjudge.core.session import Session
from cppjudge.core.settings import Settings, load_settings, save_settings

GXX = "/usr/bin/g++"
HAVE_GXX = Path(GXX).exists() or bool(__import__("shutil").which("g++"))


class SourceScanTests(unittest.TestCase):
    def test_directions(self):
        src = """
        freopen("in.txt", "r", stdin);
        freopen("out.txt", "w", stdout);
        std::ifstream fin("data.txt");
        ofstream fout; fout.open("res.txt");
        FILE *f = fopen("raw.bin", "wb");
        """
        result = source_scan.scan(src)
        self.assertIn("in.txt", result.inputs)
        self.assertIn("data.txt", result.inputs)
        self.assertIn("out.txt", result.outputs)
        self.assertIn("res.txt", result.outputs)
        self.assertIn("raw.bin", result.outputs)

    def test_include_headers(self):
        src = '#include <vector>\n#include "local.h"\n#include "dir/other.hpp"\n'
        self.assertEqual(
            source_scan.included_headers(src), ["local.h", "dir/other.hpp"]
        )

    def test_safe_relative_rejects_escape(self):
        self.assertIsNone(source_scan.safe_relative("../etc/passwd"))
        self.assertIsNone(source_scan.safe_relative("/etc/passwd"))
        self.assertIsNone(source_scan.safe_relative(""))
        self.assertEqual(
            source_scan.safe_relative("data/in.txt").as_posix(), "data/in.txt"
        )


class JudgeTests(unittest.TestCase):
    def _run(self, stdout: bytes, code: int = 0, **kwargs) -> CaseRun:
        return CaseRun(stdout=stdout, exit_code=code, wall_ms=5, **kwargs)

    def test_ac_is_byte_exact(self):
        case = Case(expected_text="42\n")
        result = judge.build_result(case, self._run(b"42\n"))
        self.assertEqual(result.verdict, Verdict.AC)

    def test_pe_for_crlf_and_trailing_space(self):
        case = Case(expected_text="42\n")
        result = judge.build_result(case, self._run(b"42  \r\n"))
        self.assertEqual(result.verdict, Verdict.PE)
        self.assertTrue(result.diff)

    def test_wa(self):
        case = Case(expected_text="42\n")
        result = judge.build_result(case, self._run(b"41\n"))
        self.assertEqual(result.verdict, Verdict.WA)
        self.assertIn("First difference at line 1", result.diff)

    def test_ran_when_no_expected(self):
        case = Case(expected_text="")
        result = judge.build_result(case, self._run(b"whatever\n"))
        self.assertEqual(result.verdict, Verdict.RAN)

    def test_re_beats_output(self):
        case = Case(expected_text="42\n")
        result = judge.build_result(case, self._run(b"42\n", code=3))
        self.assertEqual(result.verdict, Verdict.RE)

    def test_tle(self):
        case = Case(expected_text="42\n", timeout_ms=100)
        result = judge.build_result(case, self._run(b"", timed_out=True))
        self.assertEqual(result.verdict, Verdict.TLE)

    def test_normalize(self):
        self.assertEqual(judge.normalize("a  \r\nb\t\r\n\r\n"), "a\nb")
        self.assertEqual(judge.normalize("a\n\n\n"), "a")


class SettingsTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            original = Settings("/usr/bin/g++", "-std=c++20 -O2", 1500, "light")
            save_settings(original, path)
            loaded = load_settings(path)
            self.assertEqual(loaded, original.normalized())

    def test_corrupt_file_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text("{not json", encoding="utf-8")
            loaded = load_settings(path)
            self.assertEqual(loaded.theme, "dark")
            self.assertEqual(loaded.timeout_ms, 2000)


class SessionTests(unittest.TestCase):
    def test_add_duplicate_delete(self):
        session = Session(Settings())
        self.assertEqual(len(session.cases), 1)
        second = session.add_case()
        self.assertEqual(second.name, "Case 2")
        clone = session.duplicate_case(second.id)
        self.assertEqual(len(session.cases), 3)
        self.assertEqual(clone.name, "Case 2 copy")
        session.remove_case(clone.id)
        session.remove_case(second.id)
        self.assertEqual(len(session.cases), 1)
        session.remove_case(session.cases[0].id)
        self.assertEqual(len(session.cases), 1, "never leaves the list empty")


class DiagnosticsTests(unittest.TestCase):
    def test_parses_locations_and_drops_carets(self):
        text = (
            "main.cpp: In function 'int main()':\n"
            "main.cpp:3:5: error: expected ';' before 'std'\n"
            "    3 |     std::cout << x\n"
            "      |     ^~~\n"
            "/usr/bin/ld: undefined reference to `foo()'\n"
        )
        diags = parse_diagnostics(text)
        located = [d for d in diags if d.line]
        self.assertEqual(len(located), 1)
        self.assertEqual(located[0].line, 3)
        self.assertTrue(any("undefined reference" in d.message for d in diags))
        self.assertFalse(any("^~~" in d.message for d in diags))


@unittest.skipUnless(HAVE_GXX, "g++ not available")
class IntegrationTests(unittest.TestCase):
    SOURCE = (
        "#include <iostream>\n"
        "#include <fstream>\n"
        "#include <string>\n"
        "int main(){\n"
        '  std::ifstream in("input.txt");\n'
        "  long long a = 0, b = 0;\n"
        "  if (!(in >> a >> b)) return 0;\n"
        '  std::ofstream out("sum.txt");\n'
        "  out << a + b << '\\n';\n"
        '  std::cout << a + b << "\\n";\n'
        "  return 0;\n"
        "}\n"
    )

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cppjudge-unittest-"))
        self.build = self.tmp / "build"
        self.build.mkdir()
        (self.build / "main.cpp").write_text(self.SOURCE)

    def tearDown(self):
        remove_tree(self.tmp)

    def test_freopen_style_io(self):
        outcome = compile_source(GXX, self.build / "main.cpp", self.build, "-O0")
        self.assertTrue(outcome.ok, outcome.messages)
        case = Case(input_text="2 40\n", expected_text="42\n", timeout_ms=5000)
        run = run_case(
            exe_path=outcome.exe_path,
            source_text=self.SOURCE,
            source_name="main.cpp",
            rundir=self.tmp / "run",
            case=case,
            cancel_event=threading.Event(),
        )
        result = judge.build_result(case, run)
        self.assertEqual(result.verdict, Verdict.AC, result.stderr)
        self.assertIn("sum.txt", result.produced_files)
        self.assertEqual(result.produced_files["sum.txt"].strip(), "42")

    def test_timeout_kills_tree(self):
        slow = "int main(){ while(true){} }\n"
        (self.build / "main.cpp").write_text(slow)
        outcome = compile_source(GXX, self.build / "main.cpp", self.build, "-O0")
        self.assertTrue(outcome.ok, outcome.messages)
        case = Case(timeout_ms=250, expected_text="")
        started = time.monotonic()
        run = run_case(
            exe_path=outcome.exe_path,
            source_text=slow,
            source_name="main.cpp",
            rundir=self.tmp / "slow",
            case=case,
            cancel_event=threading.Event(),
        )
        elapsed = time.monotonic() - started
        self.assertTrue(run.timed_out)
        self.assertLess(elapsed, 3.0)
        self.assertEqual(judge.build_result(case, run).verdict, Verdict.TLE)

    def test_cancel_event(self):
        slow = "int main(){ while(true){} }\n"
        (self.build / "main.cpp").write_text(slow)
        outcome = compile_source(GXX, self.build / "main.cpp", self.build, "-O0")
        cancel = threading.Event()
        cancel.set()
        case = Case(timeout_ms=5000, expected_text="")
        run = run_case(
            exe_path=outcome.exe_path,
            source_text=slow,
            source_name="main.cpp",
            rundir=self.tmp / "cancel",
            case=case,
            cancel_event=cancel,
        )
        self.assertTrue(run.cancelled)
        self.assertEqual(judge.build_result(case, run).verdict, Verdict.SKIPPED)


@unittest.skipUnless(HAVE_GXX, "g++ not available")
class CompilerTests(unittest.TestCase):
    def test_probe_and_verify(self):
        info = probe(GXX)
        self.assertIsNotNone(info)
        self.assertEqual(info.family, "g++")

    def test_compile_error_produces_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "main.cpp").write_text("int main(){ oops }\n")
            outcome = compile_source(GXX, base / "main.cpp", base, "-O0")
            self.assertFalse(outcome.ok)
            self.assertTrue(any(d.is_error for d in outcome.diagnostics))


if __name__ == "__main__":
    unittest.main()
