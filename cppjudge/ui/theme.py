"""Colours and stylesheets for the dark/light themes."""

from __future__ import annotations

from dataclasses import dataclass, field
from string import Template

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    panel: str
    surface: str
    border: str
    text: str
    muted: str
    accent: str
    accent_soft: str
    editor_bg: str
    gutter_bg: str
    gutter_text: str
    current_line: str
    selection: str
    syntax: dict[str, str] = field(default_factory=dict)

    def color(self, key: str) -> QColor:
        return QColor(getattr(self, key))


DARK = Theme(
    name="dark",
    bg="#0d1117",
    panel="#161b22",
    surface="#0d1117",
    border="#30363d",
    text="#e6edf3",
    muted="#8b949e",
    accent="#2f81f7",
    accent_soft="#1f6feb33",
    editor_bg="#0d1117",
    gutter_bg="#0d1117",
    gutter_text="#484f58",
    current_line="#161b22",
    selection="#264f78",
    syntax={
        "keyword": "#ff7b72",
        "type": "#79c0ff",
        "string": "#a5d6ff",
        "char": "#a5d6ff",
        "number": "#79c0ff",
        "comment": "#8b949e",
        "preprocessor": "#d2a8ff",
        "function": "#ffa657",
        "plain": "#e6edf3",
    },
)

LIGHT = Theme(
    name="light",
    bg="#ffffff",
    panel="#f6f8fa",
    surface="#ffffff",
    border="#d0d7de",
    text="#1f2328",
    muted="#656d76",
    accent="#0969da",
    accent_soft="#0969da1a",
    editor_bg="#ffffff",
    gutter_bg="#f6f8fa",
    gutter_text="#8c959f",
    current_line="#f0f3f6",
    selection="#b6d7ff",
    syntax={
        "keyword": "#cf222e",
        "type": "#0550ae",
        "string": "#0a3069",
        "char": "#0a3069",
        "number": "#0550ae",
        "comment": "#6e7781",
        "preprocessor": "#8250df",
        "function": "#953800",
        "plain": "#1f2328",
    },
)

VERDICT_DARK = {
    "AC": "#3fb950",
    "PE": "#d29922",
    "WA": "#f85149",
    "TLE": "#a371f7",
    "RE": "#f0883e",
    "CE": "#f85149",
    "RAN": "#58a6ff",
    "SKIPPED": "#8b949e",
}

VERDICT_LIGHT = {
    "AC": "#1a7f37",
    "PE": "#9a6700",
    "WA": "#cf222e",
    "TLE": "#8250df",
    "RE": "#bc4c00",
    "CE": "#cf222e",
    "RAN": "#0969da",
    "SKIPPED": "#656d76",
}


def theme(name: str) -> Theme:
    return LIGHT if name == "light" else DARK


def verdict_colors(name: str) -> dict[str, str]:
    return VERDICT_LIGHT if name == "light" else VERDICT_DARK


def mono_font(size: int = 11) -> QFont:
    font = QFont()
    for family in (
        "JetBrains Mono",
        "Cascadia Code",
        "Fira Code",
        "Consolas",
        "DejaVu Sans Mono",
        "Liberation Mono",
        "Menlo",
        "Noto Sans Mono",
    ):
        font.setFamily(family)
        if font.exactMatch():
            break
    else:
        font = QFont()
        font.setStyleHint(QFont.Monospace)
        font.setFamily("monospace")
    font.setStyleHint(QFont.Monospace)
    font.setFixedPitch(True)
    font.setPointSize(size)
    return font


_QSS = Template(
    """
QWidget {
    background: $bg;
    color: $text;
    font-size: 13px;
}
QLabel { background: transparent; }
QMainWindow, QDialog { background: $bg; }

QToolBar {
    background: $panel;
    border: none;
    border-bottom: 1px solid $border;
    spacing: 6px;
    padding: 6px 8px;
}
QToolBar::separator {
    background: $border;
    width: 1px;
    margin: 3px 6px;
}
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 10px;
    color: $text;
}
QToolButton:hover { background: $surface; border-color: $border; }
QToolButton:pressed { background: $border; }
QToolButton:disabled { color: $muted; }
QToolButton#primary {
    background: $accent;
    color: #ffffff;
    border: 1px solid $accent;
    font-weight: 600;
}
QToolButton#primary:hover { background: $accent_hover; }
QToolButton#primary:disabled { background: $border; border-color: $border; color: $muted; }
QToolButton#danger { color: $wa; border-color: $border; }
QToolButton#danger:hover { background: $wa_soft; }
QToolButton#danger:disabled { color: $muted; border-color: $border; background: transparent; }

QPushButton {
    background: $panel;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 6px 14px;
}
QPushButton:hover { border-color: $accent; }
QPushButton:disabled { color: $muted; }

QLineEdit, QSpinBox, QComboBox {
    background: $surface;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: $selection;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: $accent; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: $panel;
    border: 1px solid $border;
    selection-background-color: $accent_soft;
    color: $text;
    outline: none;
}

QSplitter::handle { background: $border; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }

QListWidget {
    background: $panel;
    border: none;
    border-right: 1px solid $border;
    outline: none;
}
QListWidget::item { border: none; }

QTabWidget::pane { border: none; border-top: 1px solid $border; background: $surface; }
QTabBar { background: $bg; }
QTabBar::tab {
    background: transparent;
    color: $muted;
    padding: 7px 14px;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: $text; border-bottom-color: $accent; }
QTabBar::tab:hover { color: $text; }

QPlainTextEdit, QTextEdit {
    background: $editor_bg;
    border: none;
    selection-background-color: $selection;
}

QStatusBar {
    background: $panel;
    border-top: 1px solid $border;
    color: $muted;
}
QStatusBar::item { border: none; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: $border; border-radius: 6px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: $muted; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
QScrollBar::handle:horizontal { background: $border; border-radius: 6px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

QTreeWidget {
    background: $surface;
    border: none;
    outline: none;
}
QTreeWidget::item { padding: 4px 2px; }
QTreeWidget::item:selected { background: $accent_soft; color: $text; }
QHeaderView::section {
    background: $panel;
    color: $muted;
    border: none;
    border-bottom: 1px solid $border;
    padding: 5px 6px;
}

QFrame#banner {
    background: $panel;
    border: 1px solid $border;
    border-radius: 8px;
}
QLabel#bannerTitle { font-weight: 600; font-size: 14px; }
QLabel#statusItem { color: $muted; padding-left: 16px; }
QLabel#hint { color: $muted; }
QLabel#title { font-size: 22px; font-weight: 600; }
QLabel#subtitle { color: $muted; font-size: 13px; }
QLabel#emptyButton { }
QFrame#emptyCard {
    background: $panel;
    border: 1px dashed $border;
    border-radius: 12px;
}
QMenu { background: $panel; border: 1px solid $border; padding: 4px; }
QMenu::item { padding: 6px 18px; border-radius: 4px; }
QMenu::item:selected { background: $accent_soft; }
QCheckBox { spacing: 8px; }
"""
)


def stylesheet(name: str) -> str:
    t = theme(name)
    colors = {
        "bg": t.bg,
        "panel": t.panel,
        "surface": t.surface,
        "border": t.border,
        "text": t.text,
        "muted": t.muted,
        "accent": t.accent,
        "accent_hover": t.accent,
        "accent_soft": t.accent_soft,
        "editor_bg": t.editor_bg,
        "selection": t.selection,
        "wa": verdict_colors(name)["WA"],
        "wa_soft": "#f8514922" if name == "dark" else "#cf222e14",
    }
    return _QSS.substitute(colors)


def apply_theme(app: QApplication, name: str) -> None:
    t = theme(name)
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(t.bg))
    palette.setColor(QPalette.WindowText, QColor(t.text))
    palette.setColor(QPalette.Base, QColor(t.editor_bg))
    palette.setColor(QPalette.AlternateBase, QColor(t.panel))
    palette.setColor(QPalette.Text, QColor(t.text))
    palette.setColor(QPalette.Button, QColor(t.panel))
    palette.setColor(QPalette.ButtonText, QColor(t.text))
    palette.setColor(QPalette.Highlight, QColor(t.selection))
    palette.setColor(QPalette.HighlightedText, QColor(t.text))
    palette.setColor(QPalette.ToolTipBase, QColor(t.panel))
    palette.setColor(QPalette.ToolTipText, QColor(t.text))
    palette.setColor(QPalette.PlaceholderText, QColor(t.muted))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(t.muted))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(t.muted))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(name))
