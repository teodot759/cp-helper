"""Compiler discovery, verification and invocation."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .models import Diagnostic

IS_WINDOWS = os.name == "nt"

_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\s*\.\s*(\d+))?")
_DIAG_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*"
    r"(?P<sev>fatal error|error|warning|note):\s*(?P<msg>.*)$"
)
_CONTEXT_RE = re.compile(
    r"^(?P<file>[^:\s]+\.(?:cpp|cc|cxx|c\+\+|h|hpp|hxx|hh)):\s+(?P<msg>.+)$"
)

PROBE_PROGRAM = """#include <iostream>
int main() {
    long long a = 0, b = 0;
    std::cin >> a >> b;
    std::cout << a + b << '\\n';
    return 0;
}
"""

_BASE_NAMES = ("g++", "clang++", "c++")


def _spawn_flags() -> dict:
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def split_flags(flags: str) -> list[str]:
    try:
        parts = shlex.split(flags, posix=not IS_WINDOWS)
    except ValueError:
        parts = flags.split()
    return [p.strip('"') if IS_WINDOWS else p for p in parts if p.strip()]


@dataclass
class CompilerInfo:
    path: str
    label: str
    version: tuple[int, int, int] = (0, 0, 0)
    family: str = "other"
    warning: str = ""

    @property
    def display(self) -> str:
        return self.label

    @property
    def rank(self) -> tuple[int, int, int, int]:
        family_rank = 0 if self.family == "g++" else 1 if self.family == "clang++" else 2
        major, minor, patch = self.version
        return (family_rank, -major, -minor, -patch)


@dataclass
class BuildOutcome:
    ok: bool
    exe_path: Path | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    messages: str = ""
    duration_ms: int = 0


@dataclass
class DiscoveryResult:
    compilers: list[CompilerInfo] = field(default_factory=list)
    note: str = ""


def _family(name: str, version_line: str) -> str:
    blob = f"{name} {version_line}".lower()
    if "clang" in blob:
        return "clang++"
    if "g++" in blob or "gcc" in blob or "free software foundation" in blob:
        return "g++"
    return "other"


def _parse_version(text: str) -> tuple[int, int, int]:
    match = _VERSION_RE.search(text)
    if not match:
        return (0, 0, 0)
    parts = [int(g) if g else 0 for g in match.groups()]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def _resolve(name: str) -> str | None:
    expanded = os.path.expandvars(os.path.expanduser(name.strip()))
    if not expanded:
        return None
    if os.path.isabs(expanded):
        return expanded if os.path.isfile(expanded) else None
    found = shutil.which(expanded)
    if found:
        return found
    for base in _search_dirs():
        candidate = os.path.join(base, expanded)
        if os.name == "nt" and not expanded.lower().endswith(".exe"):
            candidate += ".exe"
        if os.path.isfile(candidate):
            return candidate
    return None


def _search_dirs() -> list[str]:
    dirs: list[str] = []
    if IS_WINDOWS:
        local = os.environ.get("LOCALAPPDATA", "")
        profile = os.environ.get("USERPROFILE", "")
        candidates = [
            r"C:\msys64\mingw64\bin",
            r"C:\msys64\ucrt64\bin",
            r"C:\msys64\clang64\bin",
            r"C:\w64devkit\bin",
            r"C:\MinGW\bin",
            r"C:\ProgramData\chocolatey\bin",
            r"C:\Program Files\LLVM\bin",
        ]
        if local:
            candidates.append(os.path.join(local, "Programs", "mingw64", "bin"))
        if profile:
            candidates.append(os.path.join(profile, "scoop", "shims"))
        dirs.extend(candidates)
        dirs.extend(_registry_paths())
    else:
        dirs.extend(
            [
                "/usr/bin",
                "/usr/local/bin",
                "/snap/bin",
                "/opt/homebrew/bin",
                "/usr/local/opt/llvm/bin",
                "/nix/var/nix/profiles/default/bin",
                os.path.expanduser("~/.local/bin"),
                os.path.expanduser("~/.cargo/bin"),
            ]
        )
    dirs.extend(os.environ.get("PATH", "").split(os.pathsep))
    return [d for d in dirs if d]


def _registry_paths() -> list[str]:
    """Explorer caches its environment at login; ask the registry directly."""
    try:
        import winreg
    except ImportError:
        return []
    found: list[str] = []
    locations = [
        (winreg.HKEY_CURRENT_USER, r"Environment", "Path"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            "Path",
        ),
    ]
    for hive, key, value in locations:
        try:
            with winreg.OpenKey(hive, key) as handle:
                raw, _ = winreg.QueryValueEx(handle, value)
        except OSError:
            continue
        for entry in str(raw).split(";"):
            entry = os.path.expandvars(entry.strip())
            if entry and os.path.isdir(entry):
                found.append(entry)
    return found


def candidate_paths(preferred: str = "") -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    def add(raw: str | None) -> None:
        if not raw:
            return
        path = _resolve(raw)
        if not path:
            return
        key = os.path.normcase(os.path.realpath(path))
        if key in seen:
            return
        seen.add(key)
        ordered.append(path)

    add(preferred)
    add(os.environ.get("CXX"))
    for name in _BASE_NAMES:
        add(name)
    for major in range(22, 6, -1):
        add(f"g++-{major}")
        add(f"clang++-{major}")

    extra_names = list(_BASE_NAMES) + [f"g++-{m}" for m in range(22, 6, -1)]
    extra_names += [f"clang++-{m}" for m in range(22, 6, -1)]
    for directory in _search_dirs():
        for name in extra_names:
            add(os.path.join(directory, name))
        if IS_WINDOWS:
            for name in ("g++.exe", "clang++.exe", "c++.exe"):
                add(os.path.join(directory, name))
    return ordered


def probe(path: str) -> CompilerInfo | None:
    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True,
            timeout=3,
            stdin=subprocess.DEVNULL,
            **_spawn_flags(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stdout or b"") + (proc.stderr or b"")
    out = text.decode("utf-8", "replace").strip()
    if not out:
        return None
    first = out.splitlines()[0]
    version = _parse_version(first)
    family = _family(os.path.basename(path), first)
    label = f"{'clang++' if family == 'clang++' else 'g++' if family == 'g++' else os.path.basename(path)}"
    if version != (0, 0, 0):
        label += " " + ".".join(str(v) for v in version)
    return CompilerInfo(path=path, label=label, version=version, family=family)


def _compile_command(compiler: str, flags: list[str], exe: Path, source: Path) -> list[str]:
    return [compiler, *flags, "-pipe", "-Wall", "-o", str(exe), str(source)]


def verify(info: CompilerInfo, flags: str) -> CompilerInfo | None:
    """A real test compile. ``--version`` alone misses broken toolchains."""
    with tempfile.TemporaryDirectory(prefix="cppjudge-probe-") as tmp:
        base = Path(tmp)
        source = base / "probe.cpp"
        source.write_text(PROBE_PROGRAM, encoding="utf-8")
        exe = base / ("probe.exe" if IS_WINDOWS else "probe")
        attempts: list[tuple[list[str], str]] = []
        configured = split_flags(flags) or ["-O2"]
        attempts.append((configured, ""))
        if configured != ["-O0"]:
            attempts.append((["-O0"], "configured flags failed; compiler is usable without them"))

        first_error = ""
        for args, warning in attempts:
            try:
                proc = subprocess.run(
                    _compile_command(info.path, args, exe, source),
                    capture_output=True,
                    timeout=30,
                    stdin=subprocess.DEVNULL,
                    cwd=str(base),
                    **_spawn_flags(),
                )
            except (OSError, subprocess.SubprocessError) as exc:
                first_error = first_error or str(exc)
                continue
            if proc.returncode == 0 and exe.exists():
                if warning:
                    info.warning = warning
                return info
            stderr = (proc.stderr or b"").decode("utf-8", "replace").strip()
            if stderr and not first_error:
                first_error = stderr.splitlines()[0]
    if first_error:
        info.warning = first_error
    return None


def discover(preferred: str = "", flags: str = "", limit: int = 6) -> DiscoveryResult:
    """Cheap probe for every candidate, then a real compile for each survivor."""
    probed: list[CompilerInfo] = []
    seen: set = set()
    for path in candidate_paths(preferred):
        try:
            stat = os.stat(path)
            key: tuple = ("inode", stat.st_dev, stat.st_ino)
        except OSError:
            key = ("path", path)
        if key in seen:
            continue
        seen.add(key)
        info = probe(path)
        if info is not None:
            # Same binary under two names (hard links, cc/c++ symlinks) is noise.
            identity = ("version", info.family, info.version)
            if identity in seen:
                continue
            seen.add(identity)
            probed.append(info)
    probed.sort(key=lambda c: c.rank)

    usable: list[CompilerInfo] = []
    failures: list[CompilerInfo] = []
    for info in probed[:limit]:
        verified = verify(info, flags or "")
        if verified is not None:
            usable.append(verified)
        else:
            failures.append(info)

    note = ""
    if not usable and failures:
        note = "Found a compiler but it failed a test compile: " + ", ".join(
            f"{c.label} ({c.warning})" for c in failures[:2]
        )
    return DiscoveryResult(compilers=usable, note=note)


def parse_diagnostics(text: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for line in text.splitlines():
        # Source excerpts and caret lines from GCC/Clang are noise in a list view.
        if re.match(r"^\s*(?:\d+\s*)?\|", line):
            continue
        match = _DIAG_RE.match(line)
        if match:
            diagnostics.append(
                Diagnostic(
                    severity=match.group("sev"),
                    file=match.group("file"),
                    line=int(match.group("line")),
                    col=int(match.group("col")),
                    message=match.group("msg"),
                    raw=line,
                )
            )
            continue
        contextual = _CONTEXT_RE.match(line)
        if contextual:
            diagnostics.append(
                Diagnostic(
                    severity="note",
                    file=contextual.group("file"),
                    message=contextual.group("msg"),
                    raw=line,
                )
            )
            continue
        if line.strip() and ("error" in line or "undefined reference" in line):
            diagnostics.append(Diagnostic(severity="error", message=line.strip(), raw=line))
        elif line.strip() and "warning" in line:
            diagnostics.append(Diagnostic(severity="warning", message=line.strip(), raw=line))
        else:
            diagnostics.append(Diagnostic(severity="note", message=line, raw=line))
    return diagnostics


def compile_source(
    compiler: str,
    source: Path,
    out_dir: Path,
    flags: str,
    timeout_s: float = 15.0,
) -> BuildOutcome:
    out_dir.mkdir(parents=True, exist_ok=True)
    exe = out_dir / ("main.exe" if IS_WINDOWS else "main")
    cmd = _compile_command(compiler, split_flags(flags), exe, source)

    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_s,
            stdin=subprocess.DEVNULL,
            cwd=str(out_dir),
            **_spawn_flags(),
        )
    except subprocess.TimeoutExpired:
        elapsed = int((time.monotonic() - started) * 1000)
        message = (
            f"Compilation did not finish within {int(timeout_s)} s.\n"
            "This is almost always an antivirus scan holding the new binary.\n"
        )
        return BuildOutcome(
            ok=False,
            diagnostics=[Diagnostic(severity="error", message=message)],
            messages=message,
            duration_ms=elapsed,
        )
    except OSError as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        message = f"Could not start the compiler:\n{exc}\nCommand: {' '.join(cmd)}"
        return BuildOutcome(
            ok=False,
            diagnostics=[Diagnostic(severity="error", message=str(exc))],
            messages=message,
            duration_ms=elapsed,
        )

    elapsed = int((time.monotonic() - started) * 1000)
    stderr = (proc.stderr or b"").decode("utf-8", "replace")
    stdout = (proc.stdout or b"").decode("utf-8", "replace")
    combined = "\n".join(part for part in (stderr, stdout) if part).strip()
    ok = proc.returncode == 0 and exe.exists()
    if not ok and not combined:
        combined = f"Compilation failed with exit code {proc.returncode}."
    diagnostics = parse_diagnostics(combined)
    if not ok and not any(d.is_error for d in diagnostics):
        diagnostics.append(Diagnostic(severity="error", message=combined or "Compilation failed."))
    return BuildOutcome(
        ok=ok,
        exe_path=exe if ok else None,
        diagnostics=diagnostics,
        messages=combined,
        duration_ms=elapsed,
    )
