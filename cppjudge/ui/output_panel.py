"""Bottom panel: input, expected output, stdout, stderr, diff, files, build."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Case, Diagnostic, Result, Verdict
from . import theme as theme_mod


class _CodeView(QPlainTextEdit):
    def __init__(self, placeholder: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(theme_mod.mono_font(10))
        self.setPlaceholderText(placeholder)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)


class OutputPanel(QWidget):
    TAB_INPUT = 0
    TAB_EXPECTED = 1
    TAB_STDOUT = 2
    TAB_STDERR = 3
    TAB_DIFF = 4
    TAB_FILES = 5
    TAB_BUILD = 6

    input_changed = Signal(str)
    expected_changed = Signal(str)
    diagnostic_activated = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._guard = False
        self._files: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs)

        self.input_edit = QPlainTextEdit()
        self.input_edit.setFont(theme_mod.mono_font(10))
        self.input_edit.setPlaceholderText("Type or paste the program's stdin here.")
        self.input_edit.textChanged.connect(self._on_input_changed)
        self.tabs.addTab(self.input_edit, "Input")

        self.expected_edit = QPlainTextEdit()
        self.expected_edit.setFont(theme_mod.mono_font(10))
        self.expected_edit.setPlaceholderText(
            "Leave empty to only check that the program exits cleanly."
        )
        self.expected_edit.textChanged.connect(self._on_expected_changed)
        self.tabs.addTab(self.expected_edit, "Expected")

        self.stdout_edit = _CodeView("Press Run to see the program's stdout.")
        self.tabs.addTab(self.stdout_edit, "Stdout")

        self.stderr_edit = _CodeView("Nothing on stderr.")
        self.tabs.addTab(self.stderr_edit, "Stderr")

        self.diff_edit = _CodeView("Run a case with expected output to see a diff.")
        self.tabs.addTab(self.diff_edit, "Diff")

        files_page = QWidget()
        files_layout = QVBoxLayout(files_page)
        files_layout.setContentsMargins(8, 6, 8, 6)
        files_layout.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel("Files written by the program")
        label.setObjectName("hint")
        self.files_combo = QComboBox()
        self.files_combo.setMinimumWidth(220)
        self.files_combo.currentIndexChanged.connect(self._show_file)
        row.addWidget(label)
        row.addWidget(self.files_combo, 1)
        files_layout.addLayout(row)
        self.files_view = _CodeView("The program did not write any files.")
        files_layout.addWidget(self.files_view, 1)
        self.tabs.addTab(files_page, "Files")

        self.build_tree = QTreeWidget()
        self.build_tree.setHeaderLabels(["", "Location", "Message"])
        self.build_tree.setColumnWidth(0, 70)
        self.build_tree.setColumnWidth(1, 230)
        self.build_tree.setRootIsDecorated(False)
        self.build_tree.setAlternatingRowColors(False)
        self.build_tree.itemClicked.connect(self._on_build_row)
        self.tabs.addTab(self.build_tree, "Build")

        self.tabs.setTabToolTip(
            self.TAB_INPUT, "In-memory only. Lost when the app closes."
        )
        self.tabs.setTabToolTip(
            self.TAB_EXPECTED,
            "Compared against stdout. Empty expected output means 'just run it'.",
        )

    # -- case text -----------------------------------------------------
    def set_case(self, case: Case) -> None:
        self._guard = True
        self.input_edit.setPlainText(case.input_text)
        self.expected_edit.setPlainText(case.expected_text)
        self._guard = False

    def commit_pending(self) -> None:
        # Edits are pushed live; this exists so the window can force a sync.
        pass

    def _on_input_changed(self) -> None:
        if not self._guard:
            self.input_changed.emit(self.input_edit.toPlainText())

    def _on_expected_changed(self) -> None:
        if not self._guard:
            self.expected_changed.emit(self.expected_edit.toPlainText())

    # -- results -------------------------------------------------------
    def clear_case_output(self) -> None:
        self.stdout_edit.setPlainText("")
        self.stderr_edit.setPlainText("")
        self.diff_edit.setPlainText("")
        self.files_view.setPlainText("")
        self._files = {}
        self.files_combo.clear()

    def clear_results(self) -> None:
        self.clear_case_output()
        self.build_tree.clear()
        self.tabs.setTabText(self.TAB_BUILD, "Build")

    def show_result(self, result: Result, focus: bool = True) -> None:
        self.stdout_edit.setPlainText(result.stdout)
        stderr = result.stderr
        if result.exit_code not in (None, 0):
            from ..core.judge import exit_description

            stderr = (stderr + f"\n[program {exit_description(result.exit_code)}]").strip()
        self.stderr_edit.setPlainText(stderr)

        if result.verdict == Verdict.AC:
            self.diff_edit.setPlainText("Output matches exactly.")
        elif result.verdict == Verdict.RAN:
            self.diff_edit.setPlainText(
                "This case has no expected output, so nothing was compared."
            )
        elif result.verdict == Verdict.SKIPPED:
            self.diff_edit.setPlainText("This case did not run.")
        elif result.verdict == Verdict.TLE:
            self.diff_edit.setPlainText(
                result.note or "The program exceeded the wall-clock limit."
            )
        elif result.verdict == Verdict.RE:
            self.diff_edit.setPlainText(
                "The program failed to exit cleanly"
                + (f": {result.note}" if result.note else ".")
            )
        else:
            self.diff_edit.setPlainText(result.diff or "No differences to show.")

        self._files = dict(result.produced_files)
        self.files_combo.blockSignals(True)
        self.files_combo.clear()
        self.files_combo.addItems(sorted(self._files))
        self.files_combo.blockSignals(False)
        if self._files:
            self.files_combo.setCurrentIndex(0)
            self._show_file()
        else:
            self.files_view.setPlainText("")

        if focus:
            if result.verdict in (Verdict.WA, Verdict.PE):
                self.tabs.setCurrentIndex(self.TAB_DIFF)
            elif result.verdict == Verdict.RE:
                self.tabs.setCurrentIndex(self.TAB_STDERR)
            else:
                self.tabs.setCurrentIndex(self.TAB_STDOUT)

    def _show_file(self, *_args) -> None:
        name = self.files_combo.currentText()
        if not name:
            self.files_view.setPlainText("")
            return
        self.files_view.setPlainText(self._files.get(name, ""))

    # -- build ---------------------------------------------------------
    def show_build(self, diagnostics: list[Diagnostic], messages: str = "") -> int:
        self.build_tree.clear()
        self.diff_edit.setPlainText("")
        self.stdout_edit.setPlainText("")
        self.stderr_edit.setPlainText("")
        self._files = {}
        self.files_combo.clear()

        problem_count = 0
        for diag in diagnostics:
            if diag.severity == "note" and not diag.message.strip():
                continue
            item = QTreeWidgetItem(
                [
                    diag.severity,
                    diag.location,
                    " ".join(diag.message.split()),
                ]
            )
            item.setData(0, Qt.UserRole, diag)
            color = "#f85149" if diag.is_error else "#d29922" if diag.severity == "warning" else "#8b949e"
            item.setForeground(0, QColor(color))
            item.setToolTip(2, diag.message)
            self.build_tree.addTopLevelItem(item)
            if diag.is_error or diag.severity == "warning":
                problem_count += 1

        if not diagnostics and messages.strip():
            item = QTreeWidgetItem(["error", "", messages.strip()])
            item.setForeground(0, QColor("#f85149"))
            self.build_tree.addTopLevelItem(item)
            problem_count = 1

        self.tabs.setTabText(
            self.TAB_BUILD, f"Build ({problem_count})" if problem_count else "Build"
        )
        self.tabs.setCurrentIndex(self.TAB_BUILD)
        return problem_count

    def _on_build_row(self, item: QTreeWidgetItem, _column: int) -> None:
        diag = item.data(0, Qt.UserRole)
        if isinstance(diag, Diagnostic):
            self.diagnostic_activated.emit(diag)

    def focus_build(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_BUILD)

    def set_mono_size(self, size: int) -> None:
        font = theme_mod.mono_font(size)
        for widget in (
            self.input_edit,
            self.expected_edit,
            self.stdout_edit,
            self.stderr_edit,
            self.diff_edit,
            self.files_view,
        ):
            widget.setFont(font)
