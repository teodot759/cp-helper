"""In-memory session state. Never serialized except for Settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .models import Case, Result
from .settings import Settings


@dataclass
class Session:
    settings: Settings
    source_path: Path | None = None
    source_encoding: str = "utf-8"
    newline: str = "\n"
    dirty: bool = False
    cases: list[Case] = field(default_factory=list)
    results: dict[str, Result] = field(default_factory=dict)
    current_case_id: str = ""

    def __post_init__(self) -> None:
        if not self.cases:
            case = Case(name="Case 1", timeout_ms=self.settings.timeout_ms)
            self.cases.append(case)
            self.current_case_id = case.id

    # -- cases ---------------------------------------------------------
    def case(self, case_id: str) -> Case | None:
        for case in self.cases:
            if case.id == case_id:
                return case
        return None

    @property
    def current_case(self) -> Case:
        found = self.case(self.current_case_id)
        if found is not None:
            return found
        self.current_case_id = self.cases[0].id
        return self.cases[0]

    def next_case_name(self) -> str:
        used = {case.name for case in self.cases}
        index = 1
        while f"Case {index}" in used:
            index += 1
        return f"Case {index}"

    def next_copy_name(self, base: Case) -> str:
        used = {case.name for case in self.cases}
        candidate = f"{base.name} copy"
        index = 2
        while candidate in used:
            candidate = f"{base.name} copy {index}"
            index += 1
        return candidate

    def add_case(self) -> Case:
        case = Case(name=self.next_case_name(), timeout_ms=self.settings.timeout_ms)
        self.cases.append(case)
        return case

    def duplicate_case(self, case_id: str) -> Case | None:
        source = self.case(case_id)
        if source is None:
            return None
        clone = source.duplicate(self.next_copy_name(source))
        index = self.cases.index(source) + 1
        self.cases.insert(index, clone)
        return clone

    def remove_case(self, case_id: str) -> None:
        case = self.case(case_id)
        if case is None:
            return
        self.cases.remove(case)
        self.results.pop(case_id, None)
        if not self.cases:
            self.cases.append(Case(name="Case 1", timeout_ms=self.settings.timeout_ms))
        if self.current_case_id == case_id:
            self.current_case_id = self.cases[0].id

    def clear_results(self) -> None:
        self.results.clear()

    # -- source --------------------------------------------------------
    def set_dirty(self, dirty: bool) -> None:
        self.dirty = dirty

    @property
    def display_name(self) -> str:
        return self.source_path.name if self.source_path else "Untitled"
