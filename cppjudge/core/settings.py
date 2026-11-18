"""The one exception to statelessness: a tiny settings file.

Persists compiler path, flags, timeout and theme. Never cases, results or
source paths.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from ..branding import load_branding

DEFAULT_FLAGS = "-std=c++20 -O2"
DEFAULT_TIMEOUT_MS = 2000


def config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
        root = Path(base) if base else Path.home() / ".config"
    return root / load_branding().config_dir


def settings_path() -> Path:
    return config_dir() / "settings.json"


@dataclass
class Settings:
    compiler_path: str = ""
    flags: str = DEFAULT_FLAGS
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    theme: str = "dark"

    def normalized(self) -> "Settings":
        flags = self.flags.strip() or DEFAULT_FLAGS
        timeout = max(100, min(60000, int(self.timeout_ms or DEFAULT_TIMEOUT_MS)))
        theme = self.theme if self.theme in ("dark", "light") else "dark"
        return Settings(self.compiler_path or "", flags, timeout, theme)


def load_settings(path: Path | None = None) -> Settings:
    p = path or settings_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    return Settings(
        compiler_path=str(data.get("compiler_path") or ""),
        flags=str(data.get("flags") or DEFAULT_FLAGS),
        timeout_ms=int(data.get("timeout_ms") or DEFAULT_TIMEOUT_MS),
        theme=str(data.get("theme") or "dark"),
    ).normalized()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    p = path or settings_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(settings.normalized()), indent=2) + "\n"
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".settings-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, p)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        # Settings are a convenience; never let a read-only home break the app.
        pass
