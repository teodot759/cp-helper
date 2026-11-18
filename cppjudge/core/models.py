"""Plain data structures shared by the core and the UI.

Nothing here imports Qt; the GUI wraps these types in widgets.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    AC = "AC"
    PE = "PE"
    WA = "WA"
    TLE = "TLE"
    RE = "RE"
    CE = "CE"
    RAN = "RAN"
    SKIPPED = "SKIPPED"

    @property
    def label(self) -> str:
        return self.value


@dataclass
class Case:
    """A named input/expected-output pair. In memory only."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = "Case 1"
    input_text: str = ""
    expected_text: str = ""
    timeout_ms: int = 2000

    def duplicate(self, name: str) -> "Case":
        return Case(
            name=name,
            input_text=self.input_text,
            expected_text=self.expected_text,
            timeout_ms=self.timeout_ms,
        )


@dataclass
class Diagnostic:
    """One compiler message. ``line``/``col`` are 0 when unknown."""

    severity: str = "error"
    file: str = ""
    line: int = 0
    col: int = 0
    message: str = ""
    raw: str = ""

    @property
    def is_error(self) -> bool:
        return self.severity in ("error", "fatal error")

    @property
    def location(self) -> str:
        if self.file and self.line:
            return f"{self.file}:{self.line}:{self.col}"
        return self.file or ""


@dataclass
class Result:
    case_id: str
    verdict: Verdict = Verdict.SKIPPED
    stdout: str = ""
    stdout_raw: bytes = b""
    stderr: str = ""
    exit_code: int | None = None
    wall_ms: int = 0
    produced_files: dict[str, str] = field(default_factory=dict)
    diff: str = ""
    note: str = ""
