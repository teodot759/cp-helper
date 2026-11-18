"""The code editor: line numbers, C++ highlighting, compiler marks."""

from __future__ import annotations

import re

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from ..core.models import Diagnostic
from . import theme as theme_mod
from .theme import Theme


class LineNumberArea(QWidget):
    def __init__(self, editor: "CodeEditor") -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:  # pragma: no cover - trivial
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # pragma: no cover - paint
        self.editor.line_number_area_paint_event(event)


_KEYWORDS = """
alignas alignof and and_eq asm auto bitand bitor break case catch class compl
concept const consteval constexpr constinit const_cast continue co_await
co_return co_yield decltype default delete do dynamic_cast else enum explicit
export extern false for friend goto if inline mutable namespace new noexcept
not not_eq nullptr operator or or_eq private protected public register
reinterpret_cast requires return sizeof static static_assert static_cast struct
switch template this thread_local throw true try typedef typeid typename union
using virtual volatile while xor xor_eq override final
"""

_TYPES = """
void bool char char8_t char16_t char32_t wchar_t short int long float double
signed unsigned size_t ssize_t ptrdiff_t int8_t int16_t int32_t int64_t uint8_t
uint16_t uint32_t uint64_t intmax_t uintmax_t std string wstring vector map set
unordered_map unordered_set pair tuple queue stack deque priority_queue
array list bitset complex optional variant function shared_ptr unique_ptr
weak_ptr string_view span initializer_list istream ostream ifstream ofstream
fstream stringstream istringstream ostringstream FILE auto
"""


class CppHighlighter(QSyntaxHighlighter):
    def __init__(self, document, theme: Theme) -> None:
        super().__init__(document)
        self._theme = theme
        self._rules: list[tuple[re.Pattern, QTextCharFormat]] = []
        self._build(theme)

    @staticmethod
    def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Bold)
        if italic:
            fmt.setFontItalic(True)
        return fmt

    def _build(self, theme: Theme) -> None:
        s = theme.syntax
        keywords = "|".join(sorted(_KEYWORDS.split(), key=len, reverse=True))
        types = "|".join(sorted(_TYPES.split(), key=len, reverse=True))
        self._rules = [
            (
                re.compile(rf"\b(?:{keywords})\b"),
                self._fmt(s["keyword"], bold=True),
            ),
            (
                re.compile(rf"\b(?:{types})\b"),
                self._fmt(s["type"]),
            ),
            (
                re.compile(r"\b[A-Za-z_]\w*(?=\s*\()"),
                self._fmt(s["function"]),
            ),
            (
                re.compile(r"\b(?:0[xX][0-9a-fA-F']+|0[bB][01']+|\d[\d']*(?:\.\d+)?(?:[eE][+-]?\d+)?)[uUlLfF]*\b"),
                self._fmt(s["number"]),
            ),
            (
                re.compile(r"^\s*#\s*\w+"),
                self._fmt(s["preprocessor"]),
            ),
            (
                re.compile(r'"(?:[^"\\]|\\.)*"'),
                self._fmt(s["string"]),
            ),
            (
                re.compile(r"'(?:[^'\\]|\\.)*'"),
                self._fmt(s["char"]),
            ),
        ]
        self._comment = self._fmt(s["comment"], italic=True)
        self._line_comment_re = re.compile(r"//[^\n]*")

    def rehighlight_with(self, theme: Theme) -> None:
        self._build(theme)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        line_comment = self._line_comment_re.search(text)
        limit = line_comment.start() if line_comment else len(text)

        # Multi-line block comments first, so keywords inside them lose.
        self.setCurrentBlockState(0)
        start = 0
        if self.previousBlockState() != 1:
            start = text.find("/*")
            if start >= limit:
                start = -1
        while start >= 0:
            end = text.find("*/", start)
            if end == -1:
                self.setCurrentBlockState(1)
                self.setFormat(start, len(text) - start, self._comment)
                break
            end += 2
            self.setFormat(start, end - start, self._comment)
            start = text.find("/*", end)
            if start >= limit:
                start = -1

        if self.currentBlockState() == 1:
            return

        for pattern, fmt in self._rules:
            for match in pattern.finditer(text):
                if match.start() >= limit:
                    break
                self.setFormat(match.start(), match.end() - match.start(), fmt)

        if line_comment:
            self.setFormat(line_comment.start(), len(text) - line_comment.start(), self._comment)


class CodeEditor(QPlainTextEdit):
    INDENT = 4

    def __init__(self, theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._line_area = LineNumberArea(self)
        self._diag_lines: dict[int, str] = {}

        self.setFont(theme_mod.mono_font(11))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFrameShape(QPlainTextEdit.NoFrame)
        self.setTabChangesFocus(False)
        self._update_tab_width()

        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._on_update_request)
        self.cursorPositionChanged.connect(self._on_cursor_moved)
        self._highlighter = CppHighlighter(self.document(), theme)

        self._update_margin()
        self._highlight_current_line()

    # -- geometry ------------------------------------------------------
    def _update_tab_width(self) -> None:
        metrics = QFontMetricsF(self.font())
        self.setTabStopDistance(metrics.horizontalAdvance(" ") * self.INDENT)

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 16 + int(QFontMetricsF(self.font()).horizontalAdvance("9") * digits)

    def _update_margin(self) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _on_update_request(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_margin()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    # -- painting ------------------------------------------------------
    def _highlight_current_line(self) -> None:
        selections: list[QTextEdit.ExtraSelection] = []
        if not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor(self._theme.current_line))
            sel.format.setProperty(QTextFormat.FullWidthSelection, True)
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            selections.append(sel)
        for line, severity in self._diag_lines.items():
            block = self.document().findBlockByNumber(max(0, line - 1))
            if not block.isValid():
                continue
            sel = QTextEdit.ExtraSelection()
            color = QColor("#f85149") if severity != "warning" else QColor("#d29922")
            tint = QColor(color)
            tint.setAlpha(38)
            sel.format.setBackground(tint)
            sel.format.setProperty(QTextFormat.FullWidthSelection, True)
            sel.cursor = QTextCursor(block)
            sel.cursor.clearSelection()
            selections.append(sel)
        self.setExtraSelections(selections)

    def _on_cursor_moved(self) -> None:
        self._highlight_current_line()

    def line_number_area_paint_event(self, event) -> None:
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QColor(self._theme.gutter_bg))

        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        height = int(QFontMetricsF(self.font()).height())
        width = self._line_area.width() - 10

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line = number + 1
                severity = self._diag_lines.get(line)
                if severity:
                    color = QColor("#f85149") if severity != "warning" else QColor("#d29922")
                    painter.setBrush(color)
                    painter.setPen(Qt.NoPen)
                    painter.drawEllipse(4, top + height // 2 - 3, 6, 6)
                    painter.setPen(QColor(self._theme.gutter_text))
                else:
                    painter.setPen(QColor(self._theme.gutter_text))
                painter.setFont(self.font())
                painter.drawText(0, top, width, height, Qt.AlignRight, str(line))
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            number += 1

    # -- diagnostics ---------------------------------------------------
    def set_diagnostics(self, diagnostics: list[Diagnostic]) -> None:
        marks: dict[int, str] = {}
        for diag in diagnostics:
            if diag.line > 0:
                current = marks.get(diag.line)
                if current != "error":
                    marks[diag.line] = "warning" if diag.severity == "warning" else "error"
        self._diag_lines = marks
        self._highlight_current_line()
        self._line_area.update()

    def clear_diagnostics(self) -> None:
        self._diag_lines = {}
        self._highlight_current_line()
        self._line_area.update()

    def goto_line(self, line: int, col: int = 0) -> None:
        block = self.document().findBlockByNumber(max(0, line - 1))
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        if col > 0:
            cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, col - 1)
        self.setTextCursor(cursor)
        self.centerCursor()
        self.setFocus()

    # -- theming -------------------------------------------------------
    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._highlighter.rehighlight_with(theme)
        self._highlight_current_line()
        self._line_area.update()

    def set_mono_size(self, size: int) -> None:
        font = theme_mod.mono_font(size)
        self.setFont(font)
        self._update_tab_width()
        self._update_margin()

    # -- editing -------------------------------------------------------
    def _leading_whitespace(self, text: str) -> str:
        return text[: len(text) - len(text.lstrip(" \t"))]

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key_Tab and not event.modifiers():
            cursor = self.textCursor()
            if cursor.hasSelection():
                self._indent_selection(cursor, unindent=False)
            else:
                cursor.insertText(" " * self.INDENT)
            return
        if key == Qt.Key_Backtab:
            self._indent_selection(self.textCursor(), unindent=True)
            return
        if key in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers():
            cursor = self.textCursor()
            text = cursor.block().text()
            indent = self._leading_whitespace(text)
            before = text[: cursor.positionInBlock()].rstrip()
            after = text[cursor.positionInBlock() :].lstrip()
            opens = before.endswith(("{", "(", "["))
            extra = " " * self.INDENT if opens else ""
            cursor.insertText("\n" + indent + extra)
            # Keep a closing brace aligned with its opener.
            if opens and after.startswith(("}", ")", "]")):
                pos = cursor.position()
                cursor.insertText("\n" + indent)
                cursor.setPosition(pos)
                self.setTextCursor(cursor)
            self.ensureCursorVisible()
            return
        super().keyPressEvent(event)

    def _indent_selection(self, cursor: QTextCursor, unindent: bool) -> None:
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.beginEditBlock()
        first = self.document().findBlock(start).blockNumber()
        last = self.document().findBlock(end).blockNumber()
        for number in range(first, last + 1):
            block = self.document().findBlockByNumber(number)
            if not block.isValid():
                break
            block_cursor = QTextCursor(block)
            block_cursor.movePosition(QTextCursor.StartOfBlock)
            if unindent:
                text = block.text()
                remove = len(text) - len(text.lstrip(" "))
                remove = min(remove, self.INDENT)
                for _ in range(remove):
                    block_cursor.deleteChar()
            else:
                block_cursor.insertText(" " * self.INDENT)
        cursor.endEditBlock()
