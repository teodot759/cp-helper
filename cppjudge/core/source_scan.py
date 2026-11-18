"""Find the filenames a program opens for itself.

Handles the common competitive-programming idioms:

    freopen("input.txt", "r", stdin);
    freopen("output.txt", "w", stdout);
    ifstream fin("input.txt");
    ofstream fout("output.txt");
    ifstream fin; fin.open("input.txt");
    FILE *f = fopen("in.txt", "r");

The result is used to pre-create those files inside the run directory, so the
user never has to create or delete anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from collections.abc import Iterable

_FREOPEN = re.compile(
    r'\bfreopen(?:_s)?\s*\(\s*"([^"\\\n]+)"\s*,\s*"([^"\\\n]*)"', re.MULTILINE
)
_STREAM_DIRECT = re.compile(
    r'\b(std::)?(ifstream|ofstream|fstream)\s+[A-Za-z_]\w*\s*\(\s*"([^"\\\n]+)"'
)
_STREAM_DECL = re.compile(r'\b(std::)?(ifstream|ofstream|fstream)\s+([A-Za-z_]\w*)')
_STREAM_OPEN = re.compile(r'\b([A-Za-z_]\w*)\s*(?:\.|->)\s*open\s*\(\s*"([^"\\\n]+)"')
_FOPEN = re.compile(r'\bfopen(?:_s)?\s*\(\s*"([^"\\\n]+)"\s*,\s*"([^"\\\n]*)"')
_C_OPEN = re.compile(r'\b([A-Za-z_]\w*)\s*=\s*(?:std::)?fopen\s*\(\s*"([^"\\\n]+)"')


@dataclass
class ScanResult:
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)

    def all_names(self) -> list[str]:
        seen: list[str] = []
        for name in self.inputs + self.outputs:
            if name not in seen:
                seen.append(name)
        return seen


def _direction(mode: str) -> str:
    mode = mode.lower()
    if "+" in mode:
        return "both"
    if "w" in mode or "a" in mode:
        return "output"
    return "input"


def _add(bucket: list[str], name: str) -> None:
    name = name.strip()
    if name and name not in bucket:
        bucket.append(name)


def scan(source: str) -> ScanResult:
    result = ScanResult()

    for name, mode in _FREOPEN.findall(source):
        d = _direction(mode)
        if d in ("input", "both"):
            _add(result.inputs, name)
        if d in ("output", "both"):
            _add(result.outputs, name)

    for name, mode in _FOPEN.findall(source):
        d = _direction(mode)
        if d in ("input", "both"):
            _add(result.inputs, name)
        if d in ("output", "both"):
            _add(result.outputs, name)

    for _, kind, name in _STREAM_DIRECT.findall(source):
        if kind == "ofstream":
            _add(result.outputs, name)
        else:
            _add(result.inputs, name)

    declared = {var: kind for _, kind, var in _STREAM_DECL.findall(source)}
    for var, name in _STREAM_OPEN.findall(source):
        kind = declared.get(var)
        if kind == "ofstream":
            _add(result.outputs, name)
        elif kind in ("ifstream", "fstream"):
            _add(result.inputs, name)
        else:
            # Unknown receiver: assume input, which is the common case.
            _add(result.inputs, name)

    return result


def safe_relative(name: str) -> PurePosixPath | None:
    """Reject absolute paths and anything escaping the run directory."""
    cleaned = name.replace("\\", "/").strip()
    if not cleaned:
        return None
    path = PurePosixPath(cleaned)
    if path.is_absolute():
        return None
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            return None
        parts.append(part)
    if not parts:
        return None
    return PurePosixPath(*parts)


def write_case_files(rundir, source: str, input_text: str) -> None:
    """Create input.txt plus every file the program expects to find."""
    from pathlib import Path

    root = Path(rundir)
    (root / "input.txt").write_text(input_text, encoding="utf-8", newline="\n")

    scanned = scan(source)
    for name in scanned.inputs:
        rel = safe_relative(name)
        if rel is None:
            continue
        target = root.joinpath(*rel.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(input_text, encoding="utf-8", newline="\n")

    for name in scanned.outputs:
        rel = safe_relative(name)
        if rel is None:
            continue
        target = root.joinpath(*rel.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(b"")


def included_headers(source: str) -> list[str]:
    """Local ``#include "x"`` names, used for the sibling-header copy."""
    found: list[str] = []
    for match in re.finditer(r'^\s*#\s*include\s*"([^"\\\n]+)"', source, re.MULTILINE):
        name = match.group(1).strip()
        if name and name not in found:
            found.append(name)
    return found


def iter_unique(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        if v not in out:
            out.append(v)
    return out
