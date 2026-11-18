"""The case list with verdict badges."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Case, Result, Verdict
from .theme import Theme, verdict_colors

ROLE_ID = Qt.UserRole
ROLE_VERDICT = Qt.UserRole + 1
ROLE_DETAIL = Qt.UserRole + 2


class CaseDelegate(QStyledItemDelegate):
    ROW_HEIGHT = 36

    def __init__(self, theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._verdicts = verdict_colors(theme.name)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._verdicts = verdict_colors(theme.name)

    def sizeHint(self, option, index) -> QSize:
        return QSize(0, self.ROW_HEIGHT)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = option.rect
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        if selected:
            painter.fillRect(rect, QColor(self._theme.accent_soft))
            painter.fillRect(QRect(rect.left(), rect.top(), 3, rect.height()), QColor(self._theme.accent))
        elif hovered:
            painter.fillRect(rect, QColor(self._theme.surface))

        name = str(index.data(Qt.DisplayRole) or "")
        verdict = index.data(ROLE_VERDICT)
        detail = str(index.data(ROLE_DETAIL) or "")

        badge_text = ""
        badge_color = QColor(self._theme.muted)
        if verdict:
            verdict = str(verdict)
            badge_text = verdict
            if detail:
                badge_text += f"  {detail}"
            raw = self._verdicts.get(verdict, self._theme.muted)
            badge_color = QColor(raw)

        metrics = option.fontMetrics
        badge_width = 0
        if badge_text:
            badge_width = metrics.horizontalAdvance(badge_text) + 18

        text_rect = rect.adjusted(14, 0, -(badge_width + 18), 0)
        painter.setPen(QColor(self._theme.text))
        font = QFont(option.font)
        font.setWeight(QFont.DemiBold if selected else QFont.Normal)
        painter.setFont(font)
        elided = metrics.elidedText(name, Qt.ElideRight, max(10, text_rect.width()))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)

        if badge_text:
            badge_rect = QRect(
                rect.right() - badge_width - 10,
                rect.center().y() - 9,
                badge_width,
                18,
            )
            fill = QColor(badge_color)
            fill.setAlpha(36)
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(badge_rect, 9, 9)
            painter.setPen(QPen(badge_color))
            badge_font = QFont(option.font)
            badge_font.setPointSizeF(max(8.0, option.font.pointSizeF() - 1))
            badge_font.setWeight(QFont.DemiBold)
            painter.setFont(badge_font)
            painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

        painter.setPen(QPen(QColor(self._theme.border), 1))
        painter.drawLine(rect.left() + 10, rect.bottom(), rect.right() - 10, rect.bottom())
        painter.restore()


class CasesPanel(QWidget):
    case_selected = Signal(str)
    add_requested = Signal()
    duplicate_requested = Signal(str)
    delete_requested = Signal(str)
    rename_requested = Signal(str, str)

    def __init__(self, theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self._loading = False
        self._theme = theme

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 12, 10, 8)
        title = QLabel("CASES")
        title.setObjectName("hint")
        font = title.font()
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        font.setPointSizeF(max(8.0, font.pointSizeF() - 1))
        font.setWeight(QFont.DemiBold)
        title.setFont(font)
        self.count_label = QLabel("0")
        self.count_label.setObjectName("hint")
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        header_layout.addWidget(self.count_label)
        layout.addWidget(header)

        self.list = QListWidget()
        self.list.setItemDelegate(CaseDelegate(theme, self.list))
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setMouseTracking(True)
        self.list.setUniformItemSizes(True)
        self.list.currentItemChanged.connect(self._on_current_changed)
        self.list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.list, 1)

        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 6, 8, 8)
        footer_layout.setSpacing(4)
        self.btn_add = self._button("+", "Add a case")
        self.btn_duplicate = self._button("\u29c9", "Duplicate the selected case")
        self.btn_delete = self._button("\u2715", "Delete the selected case")
        self.btn_add.clicked.connect(self.add_requested)
        self.btn_duplicate.clicked.connect(self._duplicate)
        self.btn_delete.clicked.connect(self._delete)
        footer_layout.addWidget(self.btn_add)
        footer_layout.addWidget(self.btn_duplicate)
        footer_layout.addWidget(self.btn_delete)
        footer_layout.addStretch(1)
        layout.addWidget(footer)

    def _button(self, text: str, tip: str) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tip)
        button.setAutoRaise(False)
        button.setFixedSize(30, 28)
        return button

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        delegate = self.list.itemDelegate()
        if isinstance(delegate, CaseDelegate):
            delegate.set_theme(theme)
        self.list.viewport().update()

    # -- model ---------------------------------------------------------
    def set_cases(self, cases: list[Case], current_id: str) -> None:
        self._loading = True
        self.list.clear()
        for case in cases:
            item = QListWidgetItem(case.name)
            item.setData(ROLE_ID, case.id)
            self.list.addItem(item)
            if case.id == current_id:
                self.list.setCurrentItem(item)
        self._loading = False
        self.count_label.setText(str(len(cases)))
        self._update_buttons()

    def set_results(self, results: dict[str, Result]) -> None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            case_id = item.data(ROLE_ID)
            result = results.get(case_id)
            if result is None:
                item.setData(ROLE_VERDICT, None)
                item.setData(ROLE_DETAIL, "")
            else:
                item.setData(ROLE_VERDICT, result.verdict.value)
                item.setData(ROLE_DETAIL, self._detail(result))
        self.list.viewport().update()

    def update_result(self, case_id: str, result: Result) -> None:
        item = self._item(case_id)
        if item is None:
            return
        item.setData(ROLE_VERDICT, result.verdict.value)
        item.setData(ROLE_DETAIL, self._detail(result))
        self.list.viewport().update()

    def set_running(self, case_id: str) -> None:
        item = self._item(case_id)
        if item is None:
            return
        item.setData(ROLE_VERDICT, "")
        item.setData(ROLE_DETAIL, "")
        self.list.viewport().update()

    def clear_results(self) -> None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setData(ROLE_VERDICT, None)
            item.setData(ROLE_DETAIL, "")
        self.list.viewport().update()

    @staticmethod
    def _detail(result: Result) -> str:
        if result.verdict in (Verdict.SKIPPED, Verdict.CE):
            return ""
        return f"{result.wall_ms} ms"

    def _item(self, case_id: str) -> QListWidgetItem | None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(ROLE_ID) == case_id:
                return item
        return None

    def select_case(self, case_id: str) -> None:
        item = self._item(case_id)
        if item is not None and item is not self.list.currentItem():
            self._loading = True
            self.list.setCurrentItem(item)
            self._loading = False

    def current_case_id(self) -> str:
        item = self.list.currentItem()
        return str(item.data(ROLE_ID)) if item else ""

    # -- events --------------------------------------------------------
    def _on_current_changed(self, current, previous) -> None:
        self._update_buttons()
        if self._loading or current is None:
            return
        self.case_selected.emit(str(current.data(ROLE_ID)))

    def _on_double_click(self, item) -> None:
        case_id = str(item.data(ROLE_ID))
        name, ok = QInputDialog.getText(self, "Rename case", "Case name:", text=item.text())
        if ok and name.strip():
            self.rename_requested.emit(case_id, name.strip())

    def _duplicate(self) -> None:
        case_id = self.current_case_id()
        if case_id:
            self.duplicate_requested.emit(case_id)

    def _delete(self) -> None:
        case_id = self.current_case_id()
        if case_id:
            self.delete_requested.emit(case_id)

    def _update_buttons(self) -> None:
        has_selection = self.list.currentItem() is not None
        self.btn_duplicate.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection and self.list.count() > 1)
