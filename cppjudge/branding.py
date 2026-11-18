"""Product identity, read from ``resources/branding.json``.

Keeping the display name, config directory and executable name in one place
lets a fork rename the app without touching code.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Branding:
    app_name: str = "C++ Helper"
    config_dir: str = "cpp-helper"
    exe_name: str = "cpp-helper"


DEFAULTS = Branding()


def resource_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "cppjudge" / "resources" / name
    return Path(__file__).with_name("resources") / name


@lru_cache(maxsize=1)
def load_branding() -> Branding:
    try:
        data = json.loads(resource_path("branding.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULTS
    if not isinstance(data, dict):
        return DEFAULTS
    return Branding(
        app_name=str(data.get("app_name") or DEFAULTS.app_name),
        config_dir=str(data.get("config_dir") or DEFAULTS.config_dir),
        exe_name=str(data.get("exe_name") or DEFAULTS.exe_name),
    )
