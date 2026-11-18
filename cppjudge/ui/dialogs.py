"""Settings dialog and the no-compiler help banner."""

from __future__ import annotations

import os
import shutil

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.compiler import CompilerInfo
from ..core.paths import clean_path_text
from ..core.settings import Settings, settings_path


class PathDialog(QDialog):
    """Type or paste a path instead of navigating a file dialog."""

    def __init__(self, prefill: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Open by path")
        self.setModal(True)
        self.setMinimumWidth(620)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(12)

        heading = QLabel("Open by path")
        heading.setObjectName("title")
        outer.addWidget(heading)

        hint = QLabel(
            "Paste the full path to a C++ source file. Relative paths and ~ work too."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        self.path_edit = QLineEdit(prefill)
        self.path_edit.setPlaceholderText("/home/me/coding-stuff/solution.cpp")
        self.path_edit.setClearButtonEnabled(True)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row_layout.addWidget(self.path_edit, 1)
        row_layout.addWidget(browse)
        outer.addWidget(row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        self.path_edit.textChanged.connect(self._sync_ok)
        self._sync_ok()
        self.path_edit.setFocus()
        self.path_edit.selectAll()

    def _sync_ok(self) -> None:
        button = self.buttons.button(QDialogButtonBox.Ok)
        if button is not None:
            button.setEnabled(bool(self.path_edit.text().strip()))

    def _browse(self) -> None:
        current = clean_path_text(self.path_edit.text())
        start = ""
        if current:
            parent = os.path.dirname(os.path.expanduser(current))
            start = parent if os.path.isdir(parent) else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open C++ source",
            start,
            "C++ sources (*.cpp *.cc *.cxx *.c++ *.cp *.c);;All files (*)",
        )
        if path:
            self.path_edit.setText(path)

    def text(self) -> str:
        return self.path_edit.text()



class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: Settings,
        compilers: list[CompilerInfo],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(460)
        self._compilers = list(compilers)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(14)

        heading = QLabel("Settings")
        heading.setObjectName("title")
        outer.addWidget(heading)

        note = QLabel(
            "Only these four values survive a restart. Cases, results and file "
            "paths are never written to disk."
        )
        note.setWordWrap(True)
        note.setObjectName("hint")
        outer.addWidget(note)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft)

        compiler_row = QWidget()
        compiler_layout = QHBoxLayout(compiler_row)
        compiler_layout.setContentsMargins(0, 0, 0, 0)
        compiler_layout.setSpacing(6)
        self.compiler_combo = QComboBox()
        self.compiler_combo.setMinimumWidth(240)
        for info in self._compilers:
            self.compiler_combo.addItem(info.label, info.path)
        current = settings.compiler_path
        if current and self.compiler_combo.findData(current) < 0:
            self.compiler_combo.addItem(current, current)
        if current:
            index = self.compiler_combo.findData(current)
            if index >= 0:
                self.compiler_combo.setCurrentIndex(index)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        compiler_layout.addWidget(self.compiler_combo, 1)
        compiler_layout.addWidget(browse)
        form.addRow("Compiler", compiler_row)

        self.flags_edit = QLineEdit(settings.flags)
        self.flags_edit.setPlaceholderText("-std=c++20 -O2")
        form.addRow("Flags", self.flags_edit)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(100, 60000)
        self.timeout_spin.setSingleStep(250)
        self.timeout_spin.setSuffix(" ms")
        self.timeout_spin.setValue(settings.timeout_ms)
        form.addRow("Default timeout", self.timeout_spin)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        index = self.theme_combo.findData(settings.theme)
        self.theme_combo.setCurrentIndex(max(0, index))
        form.addRow("Theme", self.theme_combo)

        outer.addLayout(form)

        path_label = QLabel(f"Stored in <code>{settings_path()}</code>")
        path_label.setObjectName("hint")
        path_label.setTextFormat(Qt.RichText)
        path_label.setWordWrap(True)
        outer.addWidget(path_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _browse(self) -> None:
        start = shutil.which("g++") or shutil.which("clang++") or ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a C++ compiler",
            os.path.dirname(start) if start else "",
            "Executables (*)" if os.name != "nt" else "Executables (*.exe);;All files (*)",
        )
        if not path:
            return
        index = self.compiler_combo.findData(path)
        if index < 0:
            self.compiler_combo.addItem(path, path)
            index = self.compiler_combo.count() - 1
        self.compiler_combo.setCurrentIndex(index)

    def values(self) -> Settings:
        return Settings(
            compiler_path=str(self.compiler_combo.currentData() or ""),
            flags=self.flags_edit.text().strip() or "-std=c++20 -O2",
            timeout_ms=int(self.timeout_spin.value()),
            theme=str(self.theme_combo.currentData() or "dark"),
        ).normalized()


class CompilerHelpBanner(QFrame):
    browse_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("banner")
        self.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 12, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        title = QLabel("No C++ compiler found")
        title.setObjectName("bannerTitle")
        top.addWidget(title)
        top.addStretch(1)

        browse = QPushButton("Browse for compiler…")
        browse.clicked.connect(self.browse_requested)
        settings_button = QPushButton("Settings")
        settings_button.clicked.connect(self.settings_requested)
        top.addWidget(browse)
        top.addWidget(settings_button)
        layout.addLayout(top)

        body = QLabel(
            "Run is disabled until a compiler is available.<br><br>"
            "<b>Linux</b><br>"
            "<tt>sudo apt install build-essential</tt><br>"
            "<tt>sudo pacman -S base-devel</tt><br><br>"
            "<b>Windows</b> &nbsp; install "
            '<a href="https://winlibs.com/">WinLibs</a> or '
            '<a href="https://github.com/skeeto/w64devkit/releases">w64devkit</a>, '
            "then reopen the app."
        )
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText)
        body.setOpenExternalLinks(True)
        body.setObjectName("hint")
        layout.addWidget(body)

        self.setVisible(False)
