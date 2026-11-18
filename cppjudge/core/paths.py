"""Turning user-typed path text into a real file path.

Kept free of Qt so it can be tested directly. Handles the messy shapes that
arrive with a paste: quotes from a shell, ``file://`` URLs from a file manager,
``~``, environment variables, trailing whitespace and relative paths.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote


def clean_path_text(text: str) -> str:
    value = (text or "").strip()
    if value.lower().startswith("file://"):
        value = unquote(value[len("file://") :])
        # file:///home/x -> /home/x ; file:///C:/x -> C:/x on Windows
        if os.name == "nt" and len(value) > 2 and value[0] == "/" and value[2] == ":":
            value = value[1:]
    value = value.strip()
    while len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()
    return value


def resolve_source_path(
    text: str, base: Path | None = None
) -> tuple[Path | None, str]:
    """Return ``(path, "")`` or ``(None, human-readable reason)``."""
    value = clean_path_text(text)
    if not value:
        return None, "Paste a path to a C++ source file first."
    if "\n" in value or "\r" in value:
        return None, "That looks like several lines of text, not a single path."

    expanded = os.path.expandvars(os.path.expanduser(value))
    path = Path(expanded)
    if not path.is_absolute():
        path = (base or Path.cwd()) / path
    try:
        path = path.resolve()
    except OSError:
        pass

    if path.is_dir():
        return None, f"{path}\nis a folder, not a file."
    if not path.exists():
        return None, f"No such file:\n{path}"
    if not path.is_file():
        return None, f"{path}\nis not a regular file."
    return path, ""
