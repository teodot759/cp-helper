"""Run a compiled binary with a case's input, safely and with a wall clock."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from . import source_scan
from .models import Case

IS_WINDOWS = os.name == "nt"

OUTPUT_CAP = 8 * 1024 * 1024
ARTIFACT_MAX = 1024 * 1024
TERM_GRACE = 0.2

# Files the runner creates itself; never reported as program artifacts.
RESERVED = {"input.txt", "main.cpp", "main", "main.exe"}


@dataclass
class CaseRun:
    stdout: bytes = b""
    stderr: bytes = b""
    exit_code: int | None = None
    wall_ms: int = 0
    timed_out: bool = False
    cancelled: bool = False
    truncated: bool = False
    artifacts: dict[str, str] = field(default_factory=dict)
    artifact_note: str = ""


class _Drain(threading.Thread):
    """Read one pipe into a capped buffer without blocking the caller."""

    def __init__(self, stream, cap: int, on_cap):
        super().__init__(daemon=True)
        self.stream = stream
        self.cap = cap
        self.on_cap = on_cap
        self.buffer = bytearray()
        self.truncated = False
        self.error: str = ""

    def run(self) -> None:
        try:
            while True:
                chunk = self.stream.read(65536)
                if not chunk:
                    break
                room = self.cap - len(self.buffer)
                if room > 0:
                    self.buffer += chunk[:room]
                if len(chunk) > max(room, 0) and not self.truncated:
                    self.truncated = True
                    self.on_cap()
        except (OSError, ValueError) as exc:
            self.error = str(exc)


def kill_tree(proc: subprocess.Popen) -> None:
    """Terminate the process and every descendant, then reap it."""
    try:
        parent = psutil.Process(proc.pid)
    except psutil.Error:
        parent = None

    children: list[psutil.Process] = []
    if parent is not None:
        try:
            children = parent.children(recursive=True)
        except psutil.Error:
            children = []

    for child in children:
        try:
            child.terminate()
        except psutil.Error:
            pass
    if parent is not None:
        try:
            parent.terminate()
        except psutil.Error:
            pass

    _dead, alive = psutil.wait_procs(
        ([parent] if parent else []) + children, timeout=TERM_GRACE
    )
    for child in alive:
        try:
            child.kill()
        except psutil.Error:
            pass
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def _snapshot(rundir: Path) -> dict[str, tuple[int, int]]:
    state: dict[str, tuple[int, int]] = {}
    for root, _dirs, files in os.walk(rundir):
        for name in files:
            path = Path(root) / name
            rel = path.relative_to(rundir).as_posix()
            if rel in RESERVED:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            state[rel] = (stat.st_size, stat.st_mtime_ns)
    return state


def _collect_artifacts(rundir: Path, before: dict[str, tuple[int, int]]) -> tuple[dict[str, str], str]:
    artifacts: dict[str, str] = {}
    notes: list[str] = []
    for rel, (size, mtime) in sorted(_snapshot(rundir).items()):
        if before.get(rel) == (size, mtime):
            continue
        if rel.endswith((".exe", ".o", ".obj", ".pdb")):
            continue
        path = rundir / rel
        if size > ARTIFACT_MAX:
            notes.append(f"{rel} ({size} bytes, too large to show)")
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in data:
            artifacts[rel] = f"<binary file, {len(data)} bytes>"
        else:
            artifacts[rel] = data.decode("utf-8", "replace")
    return artifacts, "\n".join(notes)


def _write_program_files(rundir: Path, source: str, input_text: str) -> None:
    source_scan.write_case_files(rundir, source, input_text)


def run_case(
    *,
    exe_path: Path,
    source_text: str,
    source_name: str,
    rundir: Path,
    case: Case,
    cancel_event: threading.Event,
    output_cap: int = OUTPUT_CAP,
) -> CaseRun:
    rundir.mkdir(parents=True, exist_ok=True)

    exe_copy = rundir / exe_path.name
    try:
        shutil.copy2(exe_path, exe_copy)
        os.chmod(exe_copy, 0o755)
    except OSError as exc:
        return CaseRun(stderr=f"Could not stage the executable: {exc}".encode(), exit_code=-1)

    # The source lives beside the binary so relative #include tricks and
    # self-inspection programs behave; it is excluded from artifacts.
    try:
        (rundir / "main.cpp").write_text(source_text, encoding="utf-8", newline="\n")
    except OSError:
        pass

    _write_program_files(rundir, source_text, case.input_text)
    before = _snapshot(rundir)

    stdin_path = rundir / "input.txt"
    stdin_handle = open(stdin_path, "rb")

    kwargs: dict = {
        "cwd": str(rundir),
        "stdin": stdin_handle,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "close_fds": True,
    }
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    cap_hit = threading.Event()
    started = time.monotonic()
    try:
        proc = subprocess.Popen([str(exe_copy)], **kwargs)
    except OSError as exc:
        stdin_handle.close()
        return CaseRun(stderr=f"Could not start the program: {exc}".encode(), exit_code=-1)

    out_drain = _Drain(proc.stdout, output_cap, cap_hit.set)
    err_drain = _Drain(proc.stderr, output_cap, cap_hit.set)
    out_drain.start()
    err_drain.start()

    timeout_s = max(case.timeout_ms, 50) / 1000.0
    deadline = started + timeout_s
    timed_out = False
    cancelled = False

    while True:
        if cancel_event.is_set():
            cancelled = True
            break
        if cap_hit.is_set():
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            break
        try:
            proc.wait(timeout=min(0.05, remaining))
            break
        except subprocess.TimeoutExpired:
            continue

    if timed_out or cancelled or cap_hit.is_set():
        kill_tree(proc)

    wall_ms = int((time.monotonic() - started) * 1000)
    out_drain.join(timeout=1.0)
    err_drain.join(timeout=1.0)

    for stream in (proc.stdout, proc.stderr):
        try:
            if stream is not None:
                stream.close()
        except OSError:
            pass
    try:
        stdin_handle.close()
    except OSError:
        pass

    truncated = out_drain.truncated or err_drain.truncated
    artifacts, artifact_note = _collect_artifacts(rundir, before)
    stderr_bytes = bytes(err_drain.buffer)
    if truncated:
        note = f"[output truncated at {output_cap // (1024 * 1024)} MB]".encode()
        stderr_bytes += b"\n" + note
    if cancelled:
        stderr_bytes += b"\n[stopped]"
    if err_drain.error and not stderr_bytes:
        stderr_bytes = err_drain.error.encode()

    return CaseRun(
        stdout=bytes(out_drain.buffer),
        stderr=stderr_bytes,
        exit_code=proc.returncode,
        wall_ms=wall_ms,
        timed_out=timed_out,
        cancelled=cancelled,
        truncated=truncated,
        artifacts=artifacts,
        artifact_note=artifact_note,
    )


def remove_tree(path: Path, attempts: int = 4) -> None:
    """Delete a scratch directory, tolerating Windows handle lag."""
    for attempt in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == attempts - 1:
                return
            time.sleep(0.1 * (attempt + 1))
            if IS_WINDOWS:
                _clear_readonly(path)


def _clear_readonly(path: Path) -> None:
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            target = os.path.join(root, name)
            try:
                os.chmod(target, 0o700)
            except OSError:
                pass


def sweep_leftovers(base: Path, min_age_s: float = 6 * 3600) -> None:
    """Remove scratch dirs orphaned by a crash on a previous launch.

    Only old directories are touched so a second instance running right now
    keeps its scratch space.
    """
    try:
        entries = list(base.glob("cppjudge-*"))
    except OSError:
        return
    now = time.time()
    for entry in entries:
        try:
            if now - entry.stat().st_mtime < min_age_s:
                continue
        except OSError:
            continue
        remove_tree(entry, attempts=1)


def scratch_root() -> Path:
    import tempfile

    return Path(tempfile.gettempdir())


def new_scratch_dir() -> Path:
    path = scratch_root() / f"cppjudge-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path
