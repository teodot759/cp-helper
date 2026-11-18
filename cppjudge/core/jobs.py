"""Background jobs: compiler discovery and the run pipeline."""

from __future__ import annotations

import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from . import compiler as compiler_mod
from .compiler import DiscoveryResult
from .judge import build_result
from .models import Case, Result, Verdict
from .runner import new_scratch_dir, remove_tree, run_case
from .source_scan import included_headers, safe_relative


class RunSignals(QObject):
    compile_started = Signal()
    compile_succeeded = Signal(int)
    compile_failed = Signal(object, str)
    case_started = Signal(str)
    case_finished = Signal(str, object)
    failed = Signal(str)
    finished = Signal(bool)


class RunJob(QRunnable):
    """Compile once, then run every requested case in order."""

    HEADER_MAX = 1024 * 1024

    def __init__(
        self,
        signals: RunSignals,
        *,
        source_path: Path,
        source_text: str,
        cases: list[Case],
        compiler: str,
        flags: str,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self.signals = signals
        self.source_path = source_path
        self.source_text = source_text
        self.cases = cases
        self.compiler = compiler
        self.flags = flags
        self.cancel = cancel_event
        self.setAutoDelete(True)

    def _copy_sibling_headers(self, build_dir: Path) -> None:
        parent = self.source_path.parent
        for name in included_headers(self.source_text):
            rel = safe_relative(name)
            if rel is None:
                continue
            origin = parent.joinpath(*rel.parts)
            try:
                if not origin.is_file() or origin.stat().st_size > self.HEADER_MAX:
                    continue
                target = build_dir.joinpath(*rel.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(origin.read_bytes())
            except OSError:
                continue

    def run(self) -> None:
        cancelled = False
        work: Path | None = None
        try:
            work = new_scratch_dir()
            build_dir = work / "build"
            build_dir.mkdir(parents=True, exist_ok=True)
            source = build_dir / "main.cpp"
            source.write_text(self.source_text, encoding="utf-8", newline="\n")
            self._copy_sibling_headers(build_dir)

            self.signals.compile_started.emit()
            outcome = compiler_mod.compile_source(
                self.compiler, source, build_dir, self.flags
            )

            # Diagnostics point at the scratch copy; show the user's filename.
            original_name = self.source_path.name
            for diag in outcome.diagnostics:
                if diag.file and Path(diag.file).name == "main.cpp":
                    diag.file = original_name

            if not outcome.ok or outcome.exe_path is None:
                self.signals.compile_failed.emit(outcome.diagnostics, outcome.messages)
                note = (outcome.messages or "Compilation failed.")[:4000]
                for case in self.cases:
                    self.signals.case_finished.emit(
                        case.id,
                        Result(case_id=case.id, verdict=Verdict.SKIPPED, stderr=note),
                    )
                return

            self.signals.compile_succeeded.emit(outcome.duration_ms)

            for index, case in enumerate(self.cases):
                if self.cancel.is_set():
                    cancelled = True
                    self.signals.case_finished.emit(
                        case.id, Result(case_id=case.id, verdict=Verdict.SKIPPED)
                    )
                    continue
                if not self.cases[index:]:
                    break
                self.signals.case_started.emit(case.id)
                rundir = work / f"case-{index:02d}-{case.id[:8]}"
                run = run_case(
                    exe_path=outcome.exe_path,
                    source_text=self.source_text,
                    source_name=self.source_path.name,
                    rundir=rundir,
                    case=case,
                    cancel_event=self.cancel,
                )
                self.signals.case_finished.emit(case.id, build_result(case, run))
                if run.cancelled:
                    cancelled = True
        except Exception as exc:  # never let a worker die silently
            self.signals.failed.emit(f"{exc}\n\n{traceback.format_exc(limit=4)}")
        finally:
            if work is not None:
                remove_tree(work)
            self.signals.finished.emit(cancelled)


class DiscoverSignals(QObject):
    done = Signal(object)


class DiscoverJob(QRunnable):
    def __init__(self, signals: DiscoverSignals, preferred: str, flags: str) -> None:
        super().__init__()
        self.signals = signals
        self.preferred = preferred
        self.flags = flags
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = compiler_mod.discover(self.preferred, self.flags)
        except Exception as exc:
            result = DiscoveryResult(note=f"Compiler discovery failed: {exc}")
        self.signals.done.emit(result)


class ProbeSignals(QObject):
    done = Signal(object)


class ProbeJob(QRunnable):
    """Verify a manually browsed compiler without blocking the GUI."""

    def __init__(self, signals: ProbeSignals, path: str, flags: str) -> None:
        super().__init__()
        self.signals = signals
        self.path = path
        self.flags = flags
        self.setAutoDelete(True)

    def run(self) -> None:
        info = compiler_mod.probe(self.path)
        if info is not None:
            info = compiler_mod.verify(info, self.flags)
        self.signals.done.emit(info)
