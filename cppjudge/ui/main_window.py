"""The main window: toolbar, case list, editor, output and wiring."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.jobs import (
    DiscoverJob,
    DiscoverSignals,
    ProbeJob,
    ProbeSignals,
    RunJob,
    RunSignals,
)
from ..core.judge import exit_description
from ..core.models import Result, Verdict
from ..core.paths import clean_path_text, resolve_source_path
from ..core.runner import sweep_leftovers
from ..core.session import Session
from ..core.settings import Settings, save_settings
from ..branding import load_branding
from .cases_panel import CasesPanel
from .dialogs import CompilerHelpBanner, PathDialog, SettingsDialog
from .editor import CodeEditor
from .output_panel import OutputPanel
from .theme import apply_theme, theme

CPP_SUFFIXES = {".cpp", ".cc", ".cxx", ".c++", ".cp", ".c"}
APP_NAME = load_branding().app_name


def _decode_source(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(encoding), "utf-8"
        except UnicodeDecodeError:
            continue
    try:
        return raw.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        return raw.decode("utf-8", "replace"), "utf-8"


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.session = Session(settings)
        self._theme = theme(settings.theme)
        self._compilers: list = []
        self._compiler_map: dict[str, object] = {}
        self._running = False
        self._closing = False
        self._compile_ms: int | None = None
        self._compile_failed = False
        self._cancel = threading.Event()
        self._run_job: RunJob | None = None
        self._run_signals: RunSignals | None = None
        self._discover_signals: DiscoverSignals | None = None
        self._discover_job: DiscoverJob | None = None
        self._probe_signals: ProbeSignals | None = None
        self._probe_job: ProbeJob | None = None
        self._loading_editor = False

        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        self.setMinimumSize(880, 600)
        self.resize(1200, 800)

        self._create_actions()
        self._create_toolbars()
        self._create_central()
        self._create_statusbar()
        self._connect()

        self._refresh_cases()
        self._update_title()
        self._update_run_state()
        self._apply_theme(self.session.settings.theme, initial=True)

        QTimer.singleShot(0, self._startup)

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _create_actions(self) -> None:
        self.act_open = QAction("Open", self)
        self.act_open.setShortcut(QKeySequence("Ctrl+O"))
        self.act_open.setToolTip("Open a .cpp file (Ctrl+O)")

        self.act_open_path = QAction("Open path…", self)
        self.act_open_path.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.act_open_path.setToolTip(
            "Paste the full path to a file and open it (Ctrl+Shift+O)"
        )

        self.act_save = QAction("Save", self)
        self.act_save.setShortcut(QKeySequence("Ctrl+S"))
        self.act_save.setToolTip("Write the buffer to disk (Ctrl+S)")

        self.act_run = QAction("\u25b6  Run", self)
        self.act_run.setShortcuts([QKeySequence("F5"), QKeySequence("Ctrl+Return")])
        self.act_run.setToolTip("Run the selected case (F5 or Ctrl+Enter)")

        self.act_run_all = QAction("\u25b6\u25b6  Run all", self)
        self.act_run_all.setShortcut(QKeySequence("Ctrl+F5"))
        self.act_run_all.setToolTip("Run every case in order (Ctrl+F5)")

        self.act_stop = QAction("\u25a0  Stop", self)
        self.act_stop.setShortcut(QKeySequence("Shift+F5"))
        self.act_stop.setToolTip("Kill the running program (Shift+F5)")
        self.act_stop.setEnabled(False)

        self.act_settings = QAction("Settings", self)
        self.act_settings.setToolTip("Compiler, flags, timeout and theme")

    def _create_toolbars(self) -> None:
        file_bar = QToolBar("File")
        file_bar.setMovable(False)
        file_bar.setFloatable(False)
        file_bar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(Qt.TopToolBarArea, file_bar)

        file_bar.addAction(self.act_open)
        file_bar.addAction(self.act_open_path)
        file_bar.addAction(self.act_save)
        file_bar.addSeparator()

        compiler_label = QLabel("Compiler")
        compiler_label.setObjectName("hint")
        file_bar.addWidget(compiler_label)

        self.compiler_combo = QComboBox()
        self.compiler_combo.setMinimumWidth(210)
        self.compiler_combo.setToolTip("Compiler used for every run")
        self.compiler_combo.addItem("Detecting…")
        self.compiler_combo.setEnabled(False)
        file_bar.addWidget(self.compiler_combo)

        self.act_browse = QAction("Browse…", self)
        self.act_browse.setToolTip("Pick a compiler executable")
        file_bar.addAction(self.act_browse)

        flags_label = QLabel("Flags")
        flags_label.setObjectName("hint")
        file_bar.addWidget(flags_label)
        self.flags_edit = QLineEdit(self.session.settings.flags)
        self.flags_edit.setMinimumWidth(230)
        self.flags_edit.setMaximumWidth(340)
        self.flags_edit.setToolTip("Passed to the compiler before -o")
        file_bar.addWidget(self.flags_edit)

        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        file_bar.addWidget(spacer)

        file_bar.addAction(self.act_settings)

        run_bar = QToolBar("Run")
        run_bar.setMovable(False)
        run_bar.setFloatable(False)
        run_bar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBarBreak()
        self.addToolBar(Qt.TopToolBarArea, run_bar)

        run_bar.addAction(self.act_run)
        run_bar.addAction(self.act_run_all)
        run_bar.addAction(self.act_stop)
        run_bar.addSeparator()

        timeout_label = QLabel("Timeout")
        timeout_label.setObjectName("hint")
        run_bar.addWidget(timeout_label)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(100, 60000)
        self.timeout_spin.setSingleStep(250)
        self.timeout_spin.setSuffix(" ms")
        self.timeout_spin.setValue(self.session.settings.timeout_ms)
        self.timeout_spin.setToolTip("Wall-clock limit for the selected case")
        run_bar.addWidget(self.timeout_spin)

        run_bar.addSeparator()
        self.shortcut_hint = QLabel("F5 run  ·  Ctrl+F5 run all  ·  Shift+F5 stop")
        self.shortcut_hint.setObjectName("hint")
        run_bar.addWidget(self.shortcut_hint)

        for action, name in ((self.act_run, "primary"), (self.act_stop, "danger")):
            widget = run_bar.widgetForAction(action)
            if isinstance(widget, QToolButton):
                widget.setObjectName(name)

    def _create_central(self) -> None:
        self.stack = QStackedWidget()

        self.welcome = self._build_welcome()
        self.workspace = self._build_workspace()

        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.workspace)
        self.stack.setCurrentIndex(0)
        self.setCentralWidget(self.stack)

    def _build_welcome(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.addStretch(1)

        card = QFrame()
        card.setObjectName("emptyCard")
        card.setFixedWidth(620)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(36, 32, 36, 32)
        inner.setSpacing(10)

        title = QLabel("Open a .cpp file")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel(
            "One file, one process, no setup.\n"
            "Drop a file on this window, paste its path below, or press Ctrl+O.\n\n"
            "Programs that read input.txt with freopen work exactly like\n"
            "programs that use cin — you never create or delete the files yourself."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(False)
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setFixedWidth(540)

        open_button = QPushButton("Open file…")
        open_button.setFixedWidth(160)
        open_button.clicked.connect(self._open_dialog)
        self.welcome_button = open_button

        or_label = QLabel("or paste a full path")
        or_label.setObjectName("hint")
        or_label.setAlignment(Qt.AlignCenter)

        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)
        self.welcome_path = QLineEdit()
        self.welcome_path.setPlaceholderText("/home/me/coding-stuff/solution.cpp")
        self.welcome_path.setClearButtonEnabled(True)
        self.welcome_path.returnPressed.connect(self._open_welcome_path)
        open_path_button = QPushButton("Open")
        open_path_button.setFixedWidth(84)
        open_path_button.clicked.connect(self._open_welcome_path)
        path_layout.addWidget(self.welcome_path, 1)
        path_layout.addWidget(open_path_button)

        inner.addWidget(title)
        inner.addWidget(subtitle)
        inner.addSpacing(8)
        inner.addWidget(open_button, 0, Qt.AlignCenter)
        inner.addSpacing(4)
        inner.addWidget(or_label)
        inner.addWidget(path_row)

        outer.addWidget(card, 0, Qt.AlignCenter)
        outer.addStretch(1)
        return page

    def _build_workspace(self) -> QWidget:
        workspace = QSplitter(Qt.Vertical)
        workspace.setChildrenCollapsible(False)

        top = QSplitter(Qt.Horizontal)
        top.setChildrenCollapsible(False)

        self.cases_panel = CasesPanel(self._theme)
        self.cases_panel.setMinimumWidth(170)
        self.cases_panel.setMaximumWidth(360)

        editor_area = QWidget()
        editor_layout = QVBoxLayout(editor_area)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        self.banner = CompilerHelpBanner()
        editor_layout.addWidget(self.banner)

        self.editor = CodeEditor(self._theme)
        self.editor.setPlaceholderText("Open a .cpp file to start writing.")
        editor_layout.addWidget(self.editor, 1)

        top.addWidget(self.cases_panel)
        top.addWidget(editor_area)
        top.setStretchFactor(0, 0)
        top.setStretchFactor(1, 1)
        top.setSizes([230, 970])

        self.output = OutputPanel()
        self.output.setMinimumHeight(150)

        workspace.addWidget(top)
        workspace.addWidget(self.output)
        workspace.setStretchFactor(0, 3)
        workspace.setStretchFactor(1, 2)
        workspace.setSizes([520, 300])
        return workspace

    def _create_statusbar(self) -> None:
        bar = self.statusBar()
        self.status_compiler = QLabel("Detecting compiler…")
        self.status_run = QLabel("")
        self.status_run.setObjectName("statusItem")
        self.status_timing = QLabel("")
        self.status_timing.setObjectName("statusItem")
        bar.addWidget(self.status_compiler, 1)
        bar.addPermanentWidget(self.status_run)
        bar.addPermanentWidget(self.status_timing)

    def _connect(self) -> None:
        self.act_open.triggered.connect(self._open_dialog)
        self.act_open_path.triggered.connect(self._open_path_dialog)
        self.act_save.triggered.connect(self._save_buffer)
        self.act_run.triggered.connect(lambda: self._run(False))
        self.act_run_all.triggered.connect(lambda: self._run(True))
        self.act_stop.triggered.connect(self.stop)
        self.act_browse.triggered.connect(self._browse_compiler)
        self.act_settings.triggered.connect(self._open_settings)

        self.compiler_combo.currentIndexChanged.connect(self._on_compiler_changed)
        self.flags_edit.editingFinished.connect(self._on_flags_changed)
        self.timeout_spin.valueChanged.connect(self._on_timeout_changed)

        self.cases_panel.case_selected.connect(self._on_case_selected)
        self.cases_panel.add_requested.connect(self._add_case)
        self.cases_panel.duplicate_requested.connect(self._duplicate_case)
        self.cases_panel.delete_requested.connect(self._delete_case)
        self.cases_panel.rename_requested.connect(self._rename_case)

        self.output.input_changed.connect(self._on_input_changed)
        self.output.expected_changed.connect(self._on_expected_changed)
        self.output.diagnostic_activated.connect(self._on_diagnostic)

        self.editor.textChanged.connect(self._on_editor_changed)
        self.banner.browse_requested.connect(self._browse_compiler)
        self.banner.settings_requested.connect(self._open_settings)

    def _startup(self) -> None:
        for widget in (self.compiler_combo, self.flags_edit, self.timeout_spin):
            widget.clearFocus()
        if self.session.source_path is None:
            self.welcome_button.setFocus()
        else:
            self.editor.setFocus()
        sweep_leftovers_async()
        self._start_discovery()

    # ------------------------------------------------------------------
    # files
    # ------------------------------------------------------------------
    def _open_dialog(self) -> None:
        if not self._confirm_discard():
            return
        start = str(self.session.source_path.parent) if self.session.source_path else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open C++ source",
            start,
            "C++ sources (*.cpp *.cc *.cxx *.c++ *.cp *.c);;All files (*)",
        )
        if path:
            self.open_path(Path(path))

    def _open_path_dialog(self) -> None:
        if not self._confirm_discard():
            return
        prefill = self._clipboard_path_hint()
        while True:
            dialog = PathDialog(prefill, self)
            if dialog.exec() != QDialog.Accepted:
                return
            path, error = resolve_source_path(dialog.text())
            if path is not None:
                self.open_path(path)
                return
            QMessageBox.warning(self, "Cannot open that path", error)
            prefill = dialog.text()

    def _open_welcome_path(self) -> None:
        path, error = resolve_source_path(self.welcome_path.text())
        if path is None:
            QMessageBox.warning(self, "Cannot open that path", error)
            self.welcome_path.setFocus()
            self.welcome_path.selectAll()
            return
        if not self._confirm_discard():
            return
        self.welcome_path.clear()
        self.open_path(path)

    def _clipboard_path_hint(self) -> str:
        """Prefill the dialog when the clipboard already holds a path."""
        text = QGuiApplication.clipboard().text().strip()
        if not text or "\n" in text or "\r" in text:
            return ""
        cleaned = clean_path_text(text)
        if not cleaned:
            return ""
        if Path(cleaned).suffix.lower() in CPP_SUFFIXES or "/" in cleaned or "\\" in cleaned:
            return cleaned
        return ""

    def open_path(self, path: Path) -> None:
        path = Path(path)
        try:
            raw = path.read_bytes()
        except OSError as exc:
            QMessageBox.critical(self, "Cannot open file", f"{path}\n\n{exc}")
            return

        text, encoding = _decode_source(raw)
        newline = "\r\n" if b"\r\n" in raw else "\n"
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        self.session.source_path = path
        self.session.source_encoding = encoding
        self.session.newline = newline

        self._loading_editor = True
        self.editor.setPlainText(text)
        self._loading_editor = False
        self.editor.document().clearUndoRedoStacks()
        self.editor.clear_diagnostics()

        self.session.set_dirty(False)
        self.session.clear_results()
        self._refresh_cases()
        self.cases_panel.clear_results()
        self.output.clear_results()
        self.output.set_case(self.session.current_case)

        self.stack.setCurrentIndex(1)
        self._update_title()
        self._update_run_state()
        self._update_case_timeout()
        self.editor.setFocus()
        self.status_compiler.setText(self._compiler_status_text())

    def _save_buffer(self) -> bool:
        path = self.session.source_path
        if path is None:
            return False
        text = self.editor.toPlainText()
        if self.session.newline != "\n":
            text = text.replace("\n", self.session.newline)
        try:
            data = text.encode(self.session.source_encoding, errors="replace")
        except LookupError:
            data = text.encode("utf-8", errors="replace")
        try:
            path.write_bytes(data)
        except OSError as exc:
            QMessageBox.critical(self, "Cannot save file", f"{path}\n\n{exc}")
            return False
        self.session.set_dirty(False)
        self._update_title()
        self.status_run.setText(f"Saved {path.name}")
        return True

    def _confirm_discard(self) -> bool:
        if not self.session.dirty or self.session.source_path is None:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved changes")
        box.setIcon(QMessageBox.Warning)
        box.setText(f"Save changes to {self.session.display_name}?")
        box.setInformativeText("The buffer is not written anywhere automatically.")
        box.setStandardButtons(
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
        )
        box.setDefaultButton(QMessageBox.Save)
        result = box.exec()
        if result == QMessageBox.Save:
            return self._save_buffer()
        return result != QMessageBox.Cancel

    def _on_editor_changed(self) -> None:
        if self._loading_editor:
            return
        if not self.session.dirty:
            self.session.set_dirty(True)
            self._update_title()

    def _update_title(self) -> None:
        if self.session.source_path is None:
            self.setWindowTitle(APP_NAME)
            return
        marker = "\u2022 " if self.session.dirty else ""
        self.setWindowTitle(f"{marker}{self.session.source_path.name} — {APP_NAME}")

    # ------------------------------------------------------------------
    # cases
    # ------------------------------------------------------------------
    def _refresh_cases(self) -> None:
        self.cases_panel.set_cases(self.session.cases, self.session.current_case_id)
        self.cases_panel.set_results(self.session.results)

    def _on_case_selected(self, case_id: str) -> None:
        case = self.session.case(case_id)
        if case is None:
            return
        self.session.current_case_id = case_id
        self.output.set_case(case)
        result = self.session.results.get(case_id)
        self.output.clear_case_output()
        if result is not None:
            self.output.show_result(result, focus=True)
        self._update_case_timeout()

    def _add_case(self) -> None:
        case = self.session.add_case()
        self.session.current_case_id = case.id
        self._refresh_cases()
        self.cases_panel.select_case(case.id)
        self.output.set_case(case)
        self.output.clear_case_output()
        self._update_case_timeout()
        self.output.input_edit.setFocus()

    def _duplicate_case(self, case_id: str) -> None:
        clone = self.session.duplicate_case(case_id)
        if clone is None:
            return
        self.session.current_case_id = clone.id
        self._refresh_cases()
        self.cases_panel.select_case(clone.id)
        self.output.set_case(clone)
        self.output.clear_case_output()
        self._update_case_timeout()

    def _delete_case(self, case_id: str) -> None:
        self.session.remove_case(case_id)
        self._refresh_cases()
        self.cases_panel.select_case(self.session.current_case_id)
        self._on_case_selected(self.session.current_case_id)

    def _rename_case(self, case_id: str, name: str) -> None:
        case = self.session.case(case_id)
        if case is None:
            return
        case.name = name
        self._refresh_cases()
        self.cases_panel.select_case(case_id)

    def _on_input_changed(self, text: str) -> None:
        self.session.current_case.input_text = text

    def _on_expected_changed(self, text: str) -> None:
        self.session.current_case.expected_text = text

    def _on_timeout_changed(self, value: int) -> None:
        self.session.current_case.timeout_ms = int(value)
        self.session.settings.timeout_ms = int(value)
        save_settings(self.session.settings)

    def _update_case_timeout(self) -> None:
        value = self.session.current_case.timeout_ms
        if self.timeout_spin.value() != value:
            self.timeout_spin.blockSignals(True)
            self.timeout_spin.setValue(value)
            self.timeout_spin.blockSignals(False)

    def _on_diagnostic(self, diagnostic) -> None:
        if diagnostic.line > 0:
            self.editor.goto_line(diagnostic.line, diagnostic.col)

    # ------------------------------------------------------------------
    # compiler
    # ------------------------------------------------------------------
    def _start_discovery(self) -> None:
        signals = DiscoverSignals()
        job = DiscoverJob(
            signals,
            self.session.settings.compiler_path,
            self.session.settings.flags,
        )
        signals.done.connect(self._on_discovered)
        self._discover_signals = signals
        self._discover_job = job
        QThreadPool.globalInstance().start(job)

    def _on_discovered(self, result) -> None:
        self._compilers = list(result.compilers)
        self._compiler_map = {info.path: info for info in self._compilers}
        self.compiler_combo.setEnabled(True)
        self.compiler_combo.blockSignals(True)
        self.compiler_combo.clear()
        for info in self._compilers:
            self.compiler_combo.addItem(info.label, info.path)
            index = self.compiler_combo.count() - 1
            tooltip = info.path
            if info.warning:
                tooltip += f"\n{info.warning}"
            self.compiler_combo.setItemData(index, tooltip, Qt.ToolTipRole)

        preferred = self.session.settings.compiler_path
        index = self.compiler_combo.findData(preferred) if preferred else -1
        index = max(index, 0)
        if not self._compilers:
            self.compiler_combo.addItem("No compiler found", "")
        self.compiler_combo.setCurrentIndex(index)
        self.compiler_combo.blockSignals(False)

        if not self._compilers:
            self.banner.setVisible(True)
            if result.note:
                self.banner.setToolTip(result.note)
            self.status_compiler.setText("No C++ compiler found")
        else:
            self.banner.setVisible(False)
            self.status_compiler.setText(self._compiler_status_text())
            if result.note:
                self.status_run.setText(result.note)
            self._on_compiler_changed(self.compiler_combo.currentIndex())
        self._update_run_state()

    def _compiler_status_text(self) -> str:
        info = self._current_compiler()
        if info is None:
            return "No compiler found — install one or use Browse"
        text = f"{info.label}  ·  {info.path}"
        if getattr(info, "warning", ""):
            text += "  (flags warning)"
        return text

    def _current_compiler(self):
        path = self.compiler_combo.currentData()
        if not path:
            return None
        return self._compiler_map.get(str(path))

    def _on_compiler_changed(self, _index: int) -> None:
        info = self._current_compiler()
        self.session.settings.compiler_path = info.path if info else ""
        save_settings(self.session.settings)
        self.status_compiler.setText(self._compiler_status_text())
        self._update_run_state()

    def _browse_compiler(self) -> None:
        start = str(Path(self._current_compiler().path).parent) if self._current_compiler() else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a C++ compiler",
            start,
            "All files (*)",
        )
        if path:
            self._probe_and_add(Path(path))

    def _probe_and_add(self, path: Path) -> None:
        if str(path) in self._compiler_map:
            index = self.compiler_combo.findData(str(path))
            if index >= 0:
                self.compiler_combo.setCurrentIndex(index)
            return
        self.compiler_combo.setEnabled(False)
        self.status_compiler.setText(f"Checking {path.name}…")
        signals = ProbeSignals()
        job = ProbeJob(signals, str(path), self.session.settings.flags)
        signals.done.connect(self._on_probe_done)
        self._probe_signals = signals
        self._probe_job = job
        QThreadPool.globalInstance().start(job)

    def _on_probe_done(self, info) -> None:
        self.compiler_combo.setEnabled(True)
        if info is None:
            self.status_compiler.setText("No compiler selected")
            QMessageBox.warning(
                self,
                "Compiler not usable",
                "That file did not respond to --version or failed a test compile.\n"
                "Pick g++, clang++ or a MinGW g++.exe.",
            )
            return
        self._compilers.append(info)
        self._compiler_map[info.path] = info
        self.compiler_combo.addItem(info.label, info.path)
        index = self.compiler_combo.count() - 1
        self.compiler_combo.setItemData(index, info.path, Qt.ToolTipRole)
        self.compiler_combo.setCurrentIndex(index)
        self.banner.setVisible(False)
        self._on_compiler_changed(index)

    def _on_flags_changed(self) -> None:
        flags = self.flags_edit.text().strip() or "-std=c++20 -O2"
        self.flags_edit.setText(flags)
        if flags != self.session.settings.flags:
            self.session.settings.flags = flags
            save_settings(self.session.settings)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            self.session.settings, list(self._compilers), self
        )
        if dialog.exec() != SettingsDialog.Accepted:
            return
        new = dialog.values()
        old_theme = self.session.settings.theme
        self.session.settings = new
        save_settings(new)

        self.flags_edit.setText(new.flags)
        self.timeout_spin.blockSignals(True)
        self.timeout_spin.setValue(new.timeout_ms)
        self.timeout_spin.blockSignals(False)

        index = self.compiler_combo.findData(new.compiler_path)
        if index >= 0:
            self.compiler_combo.setCurrentIndex(index)
        elif new.compiler_path:
            self._probe_and_add(Path(new.compiler_path))

        if new.theme != old_theme:
            self._apply_theme(new.theme)
        self._update_run_state()

    # ------------------------------------------------------------------
    # running
    # ------------------------------------------------------------------
    def _update_run_state(self) -> None:
        has_source = self.session.source_path is not None
        has_compiler = self._current_compiler() is not None
        enabled = has_source and has_compiler and not self._running
        self.act_run.setEnabled(enabled)
        self.act_run_all.setEnabled(enabled)
        self.act_stop.setEnabled(self._running)
        self.act_save.setEnabled(has_source)
        if self._running:
            reason = ""
        elif not has_source:
            reason = "Open a .cpp file first"
        elif not has_compiler:
            reason = "Install a C++ compiler or point Browse at one"
        else:
            reason = ""
        self.act_run.setToolTip(reason or "Run the selected case (F5 or Ctrl+Enter)")
        self.act_run_all.setToolTip(reason or "Run every case in order (Ctrl+F5)")

    def _run(self, all_cases: bool) -> None:
        if self._running:
            return
        if self.session.source_path is None:
            return
        compiler = self._current_compiler()
        if compiler is None:
            return
        if not self._save_buffer():
            return

        cases = list(self.session.cases) if all_cases else [self.session.current_case]
        if not cases:
            return

        self.session.clear_results()
        self.cases_panel.clear_results()
        self.output.clear_results()
        self.editor.clear_diagnostics()
        self._compile_ms = None
        self._compile_failed = False

        self._cancel = threading.Event()
        self._running = True
        self._set_running_ui(True)
        self.status_run.setText("Compiling…")
        self.status_timing.setText("")

        signals = RunSignals()
        signals.compile_started.connect(self._on_compile_started)
        signals.compile_succeeded.connect(self._on_compile_succeeded)
        signals.compile_failed.connect(self._on_compile_failed)
        signals.case_started.connect(self._on_case_started)
        signals.case_finished.connect(self._on_case_finished)
        signals.failed.connect(self._on_run_failed)
        signals.finished.connect(self._on_run_finished)

        job = RunJob(
            signals,
            source_path=self.session.source_path,
            source_text=self.editor.toPlainText(),
            cases=cases,
            compiler=compiler.path,
            flags=self.session.settings.flags,
            cancel_event=self._cancel,
        )
        self._run_signals = signals
        self._run_job = job
        QThreadPool.globalInstance().start(job)

    def _set_running_ui(self, running: bool) -> None:
        self._running = running
        self._update_run_state()
        self.editor.setReadOnly(running)

    def stop(self) -> None:
        if not self._running:
            return
        self._cancel.set()
        self.status_run.setText("Stopping…")

    def _on_compile_started(self) -> None:
        self.status_run.setText("Compiling…")

    def _on_compile_succeeded(self, duration_ms: int) -> None:
        self._compile_ms = duration_ms
        self.status_timing.setText(f"compiled {duration_ms} ms")

    def _on_compile_failed(self, diagnostics, messages: str) -> None:
        self._compile_ms = None
        self._compile_failed = True
        self.status_run.setText("Compile failed")
        self.status_timing.setText("")
        self.editor.set_diagnostics(list(diagnostics))
        self.output.show_build(list(diagnostics), messages)

    def _on_case_started(self, case_id: str) -> None:
        case = self.session.case(case_id)
        name = case.name if case else "case"
        self.cases_panel.set_running(case_id)
        self.status_run.setText(f"Running {name}…")

    def _on_case_finished(self, case_id: str, result: Result) -> None:
        self.session.results[case_id] = result
        self.cases_panel.update_result(case_id, result)
        if case_id == self.session.current_case_id and not (
            self._compile_failed and result.verdict == Verdict.SKIPPED
        ):
            self.output.show_result(result)
        case = self.session.case(case_id)
        name = case.name if case else "case"
        pieces = [name, result.verdict.value]
        if result.verdict not in (Verdict.SKIPPED, Verdict.CE):
            pieces.append(f"{result.wall_ms} ms")
        if result.exit_code not in (None, 0):
            pieces.append(exit_description(result.exit_code))
        self.status_run.setText("  ·  ".join(pieces))

    def _on_run_failed(self, message: str) -> None:
        self.status_run.setText("Run crashed")
        QMessageBox.critical(self, "Run failed", message)

    def _on_run_finished(self, cancelled: bool) -> None:
        self._set_running_ui(False)
        if self._closing:
            return
        if cancelled:
            self.status_run.setText("Stopped")
            return
        if self._compile_failed:
            self.status_run.setText("Compile failed")
            return
        counts: dict[str, int] = {}
        for result in self.session.results.values():
            counts[result.verdict.value] = counts.get(result.verdict.value, 0) + 1
        total = sum(counts.values())
        if not total:
            self.status_run.setText("Finished")
            return
        order = ["AC", "PE", "WA", "TLE", "RE", "CE", "RAN", "SKIPPED"]
        parts = [f"{counts[key]} {key}" for key in order if counts.get(key)]
        self.status_run.setText(f"{total} case{'s' if total != 1 else ''}  ·  " + "  ".join(parts))

    # ------------------------------------------------------------------
    # theme
    # ------------------------------------------------------------------
    def _apply_theme(self, name: str, initial: bool = False) -> None:
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, name)
        self._theme = theme(name)
        if not initial:
            self.editor.apply_theme(self._theme)
            self.cases_panel.set_theme(self._theme)

    # ------------------------------------------------------------------
    # drag and drop / close
    # ------------------------------------------------------------------
    def _dropped_path(self, mime):
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.is_file() and path.suffix.lower() in CPP_SUFFIXES:
                return path
        return None

    def dragEnterEvent(self, event) -> None:
        if self._dropped_path(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        path = self._dropped_path(event.mimeData())
        if path is None:
            event.ignore()
            return
        event.acceptProposedAction()
        if self._confirm_discard():
            self.open_path(path)

    def closeEvent(self, event) -> None:
        if self._running:
            self._cancel.set()
        if not self._confirm_discard():
            event.ignore()
            return
        self._closing = True
        # Drop queued signals so a finishing worker cannot touch deleted widgets.
        for signals in (
            self._run_signals,
            self._discover_signals,
            self._probe_signals,
        ):
            if signals is not None:
                try:
                    signals.disconnect()
                except (RuntimeError, TypeError):
                    pass
        QThreadPool.globalInstance().waitForDone(3000)
        event.accept()


def sweep_leftovers_async() -> None:
    def work() -> None:
        try:
            sweep_leftovers()
        except Exception:
            pass

    threading.Thread(target=work, daemon=True).start()
