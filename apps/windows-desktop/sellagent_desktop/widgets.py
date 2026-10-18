"""Reusable themed widgets. Everything uses the brand ``role`` properties from packages/brand/qt/theme.qss."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from PySide6.QtCore import QDateTime, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

GOLD, GOLD_LIGHT, GOLD_MUTED, GOLD_DARK = "#D4AF37", "#E6C85A", "#8A7124", "#B8962E"
DARK, DARK_SURFACE, DARK_BORDER, DARK_TEXT, DARK_TEXT2 = "#0B0B0B", "#141414", "#2A2A2A", "#F5F0E1", "#B8B2A0"
SURFACE, BORDER, TEXT, TEXT2, CONTENT_BG = "#FFFFFF", "#E6E2D6", "#1A1A1A", "#6B665A", "#F7F6F2"
SUCCESS, WARNING, DANGER, INFO = "#2E7D32", "#B8720A", "#C62828", "#2B5D9B"
CHIP_KINDS = ("success", "warning", "danger", "info", "neutral")


# ---------------------------------------------------------------------- formatting helpers
def fmt_dt(value: Any, with_seconds: bool = False) -> str:
    """ISO timestamp (UTC from the backend) -> local time string. Empty string for None."""
    if not value:
        return ""
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S" if with_seconds else "%Y-%m-%d %H:%M")


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def to_iso(qdt: QDateTime) -> str:
    py = qdt.toPython()
    if py.tzinfo is None:
        py = py.astimezone()
    return py.isoformat()


def fmt_bytes(n: Any) -> str:
    try:
        v = float(n)
    except (TypeError, ValueError):
        return "unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024:
            return f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} PB"


def pretty_json(data: Any) -> str:
    try:
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(data)


# ---------------------------------------------------------------------- basic labels / badges
def page_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("PageTitle")
    return lbl


def caption(text: str, wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "caption")
    lbl.setWordWrap(wrap)
    return lbl


def badge(text: str, role: str = "pill") -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", role)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return lbl


def mock_badge(text: str = "SIMULATION") -> QLabel:
    """Marks anything that is not real cellular/call evidence."""
    b = badge(text, "badge-mock")
    b.setToolTip("This is a simulation or PC-local diagnostic. It is NOT evidence of real phone-call behaviour.")
    b.setAccessibleName(f"{text} badge")
    return b


def status_label(text: str, role: str | None = None) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(True)
    return lbl


def set_role(widget: QWidget, role: str | None) -> None:
    widget.setProperty("role", role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def mark_invalid(widget: QWidget, invalid: bool, message_label: QLabel | None = None, message: str = "") -> None:
    widget.setProperty("invalid", "true" if invalid else "false")
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    if message_label is not None:
        message_label.setText(message if invalid else "")
        message_label.setVisible(invalid)


def error_label() -> QLabel:
    lbl = QLabel("")
    lbl.setProperty("role", "danger")
    lbl.setWordWrap(True)
    lbl.setVisible(False)
    return lbl


def button(text: str, role: str | None = None, on_click: Callable[[], None] | None = None, tooltip: str = "") -> QPushButton:
    b = QPushButton(text.replace("&", "&&"))  # literal ampersands, not mnemonics
    if role:
        b.setProperty("role", role)
    b.setAccessibleName(text)
    if tooltip:
        b.setToolTip(tooltip)
    if on_click:
        b.clicked.connect(lambda _checked=False: on_click())  # never leak QPushButton's `checked` bool into handlers
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def hbox(*widgets: QWidget | str, stretch_last: bool = False, spacing: int = 8) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for x in widgets:
        if x == "stretch":
            lay.addStretch(1)
        else:
            lay.addWidget(x)  # type: ignore[arg-type]
    if stretch_last:
        lay.addStretch(1)
    return w


# ---------------------------------------------------------------------- cards
class Card(QFrame):
    def __init__(self, title: str | None = None, gold: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("role", "card-gold" if gold else "card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 12)
        self.body.setSpacing(8)
        self.title_lbl: QLabel | None = None
        if title:
            t = QLabel(title)
            t.setProperty("role", "card-title")
            self.title_lbl = t
            self.body.addWidget(t)

    def add(self, w: QWidget) -> QWidget:
        self.body.addWidget(w)
        return w


class StatCard(Card):
    """A single number with a caption; the number comes from the backend only."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.setMinimumWidth(150)
        self.value_lbl = QLabel("—")
        self.value_lbl.setProperty("role", "metric")
        self.value_lbl.setAccessibleName(f"{title} value")
        self.title_lbl = caption(title)
        self.body.addWidget(self.value_lbl)
        self.body.addWidget(self.title_lbl)

    def set_value(self, v: Any) -> None:
        if isinstance(v, float):
            self.value_lbl.setText(f"{v:.0%}" if 0 <= v <= 1 else f"{v:.1f}")
        else:
            self.value_lbl.setText("—" if v is None else str(v))


class KeyValueGrid(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(4)

    def set_rows(self, rows: Iterable[tuple[str, Any]]) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, (k, v) in enumerate(rows):
            kl = caption(k, wrap=False)
            vl = QLabel("" if v is None else str(v))
            vl.setWordWrap(True)
            vl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.grid.addWidget(kl, i, 0, Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(vl, i, 1)


class EmptyState(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setProperty("role", "caption")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumHeight(60)


class DangerBanner(QFrame):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("role", "danger-banner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        lay.addWidget(self.label)
        self.setVisible(False)


# ---------------------------------------------------------------------- tables
Column = tuple[str, str | Callable[[dict], Any]]


class DataTable(QTableWidget):
    """Read-only table fed with dict rows. ``columns`` are (header, key-or-callable)."""

    def __init__(self, columns: Sequence[Column], parent: QWidget | None = None, stretch_column: int | None = None):
        super().__init__(0, len(columns), parent)
        self.columns = list(columns)
        self.rows: list[dict] = []
        self.setHorizontalHeaderLabels([c[0] for c in self.columns])
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setSortingEnabled(True)
        self.setWordWrap(False)
        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(True)
        if stretch_column is not None:
            hdr.setSectionResizeMode(stretch_column, QHeaderView.ResizeMode.Stretch)
        self.setMinimumHeight(140)

    def set_rows(self, rows: list[dict]) -> None:
        self.setSortingEnabled(False)
        self.rows = list(rows)
        self.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            for c, (_, key) in enumerate(self.columns):
                val = key(row) if callable(key) else row.get(key)
                if isinstance(val, bool):
                    text = "yes" if val else "no"
                elif isinstance(val, list | dict):
                    text = ", ".join(map(str, val)) if isinstance(val, list) else pretty_json(val)
                elif val is None:
                    text = ""
                else:
                    text = str(val)
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, r)
                item.setToolTip(text if len(text) > 30 else "")
                self.setItem(r, c, item)
        self.setSortingEnabled(True)
        self.resizeColumnsToContents()
        hdr = self.horizontalHeader()
        for c in range(len(self.columns)):
            if hdr.sectionSize(c) > 320:
                hdr.resizeSection(c, 320)

    def selected_row(self) -> dict | None:
        items = self.selectedItems()
        if not items:
            return None
        idx = items[0].data(Qt.ItemDataRole.UserRole)
        return self.rows[idx] if idx is not None and idx < len(self.rows) else None

    def select_data_row(self, index: int) -> bool:
        """Select the visual row showing ``self.rows[index]`` (rows may be re-ordered by column sorting)."""
        for r in range(self.rowCount()):
            it = self.item(r, 0)
            if it is not None and it.data(Qt.ItemDataRole.UserRole) == index:
                self.selectRow(r)
                return True
        return False

    def select_first(self) -> None:
        if self.rowCount():
            self.selectRow(0)


# ---------------------------------------------------------------------- chart
class BarChart(QWidget):
    """Minimal QPainter bar chart (no fake data: it only draws what ``set_data`` receives)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._data: list[tuple[str, float]] = []
        self.setMinimumHeight(170)
        self.setAccessibleName("Calls per day bar chart")

    def set_data(self, data: list[tuple[str, float]]) -> None:
        self._data = data
        self.setAccessibleDescription("; ".join(f"{k}: {v:g}" for k, v in data) or "no data")
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(8, 8, -8, -24)
        p.fillRect(self.rect(), QColor(SURFACE))
        p.setPen(QPen(QColor(BORDER)))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if not self._data:
            p.setPen(QColor(TEXT2))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No calls recorded in the last 7 days")
            p.end()
            return
        max_v = max(v for _, v in self._data) or 1.0
        n = len(self._data)
        slot = rect.width() / n
        bar_w = max(6.0, slot * 0.55)
        font = QFont(p.font())
        font.setPointSize(8)
        p.setFont(font)
        for i, (label, v) in enumerate(self._data):
            h = (v / max_v) * (rect.height() - 18)
            x = rect.left() + i * slot + (slot - bar_w) / 2
            y = rect.bottom() - h
            p.fillRect(int(x), int(y), int(bar_w), int(h), QColor(GOLD if v else BORDER))
            p.setPen(QColor(TEXT))
            p.drawText(int(rect.left() + i * slot), int(y) - 16, int(slot), 14, Qt.AlignmentFlag.AlignCenter, f"{v:g}")
            p.setPen(QColor(TEXT2))
            p.drawText(int(rect.left() + i * slot), rect.bottom() + 4, int(slot), 16, Qt.AlignmentFlag.AlignCenter, label[-5:])


# ---------------------------------------------------------------------- dialogs
def themed_box(parent: QWidget | None, icon: QMessageBox.Icon, title: str, text: str, detail: str | None = None) -> QMessageBox:
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    if detail:
        box.setDetailedText(detail)
    return box


def info(parent: QWidget | None, title: str, text: str) -> None:
    themed_box(parent, QMessageBox.Icon.Information, title, text).exec()


def warn(parent: QWidget | None, title: str, text: str, detail: str | None = None) -> None:
    themed_box(parent, QMessageBox.Icon.Warning, title, text, detail).exec()


def confirm(parent: QWidget | None, title: str, text: str, ok_text: str = "Continue", danger: bool = False) -> bool:
    box = themed_box(parent, QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question, title, text)
    ok = box.addButton(ok_text, QMessageBox.ButtonRole.AcceptRole)
    ok.setProperty("role", "danger" if danger else "primary")
    box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is ok


class TextInputDialog(QDialog):
    """Single-field dialog with validation (red border + inline message)."""

    def __init__(self, parent: QWidget | None, title: str, label: str, *, multiline: bool = False, min_length: int = 1, placeholder: str = "", password: bool = False, required_literal: str | None = None, note: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        if note:
            lay.addWidget(caption(note))
        lay.addWidget(QLabel(label))
        self.min_length, self.required_literal = min_length, required_literal
        self.edit: QLineEdit | QPlainTextEdit
        if multiline:
            self.edit = QPlainTextEdit()
            self.edit.setPlaceholderText(placeholder)
            self.edit.setMinimumHeight(90)
        else:
            self.edit = QLineEdit()
            self.edit.setPlaceholderText(placeholder)
            if password:
                self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setAccessibleName(label)
        lay.addWidget(self.edit)
        self.err = error_label()
        lay.addWidget(self.err)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setProperty("role", "primary")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def value(self) -> str:
        return self.edit.text() if isinstance(self.edit, QLineEdit) else self.edit.toPlainText()

    def _accept(self) -> None:
        v = self.value().strip()
        if self.required_literal is not None and v != self.required_literal:
            mark_invalid(self.edit, True, self.err, f"Type {self.required_literal} exactly to continue")
            return
        if len(v) < self.min_length:
            mark_invalid(self.edit, True, self.err, f"At least {self.min_length} character(s) required")
            return
        mark_invalid(self.edit, False, self.err)
        self.accept()


class FormDialog(QDialog):
    """Generic form dialog: ``add_field(key, label, widget, required)`` + ``values()``. Subclasses override ``validate``."""

    def __init__(self, parent: QWidget | None, title: str, ok_text: str = "Save"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.outer = QVBoxLayout(self)
        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.outer.addLayout(self.form)
        self.fields: dict[str, QWidget] = {}
        self.required: set[str] = set()
        self.errors: dict[str, QLabel] = {}
        self.form_error = error_label()
        self.outer.addWidget(self.form_error)
        self.bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        okb = self.bb.button(QDialogButtonBox.StandardButton.Ok)
        okb.setText(ok_text)
        okb.setProperty("role", "primary")
        okb.setAccessibleName(ok_text)
        self.bb.accepted.connect(self._on_accept)
        self.bb.rejected.connect(self.reject)
        self.outer.addWidget(self.bb)

    def add_field(self, key: str, label: str, widget: QWidget, required: bool = False, help_text: str | None = None) -> QWidget:
        widget.setAccessibleName(label)
        self.fields[key] = widget
        if required:
            self.required.add(key)
            label = label + " *"
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(widget)
        if help_text:
            lay.addWidget(caption(help_text))
        err = error_label()
        lay.addWidget(err)
        self.errors[key] = err
        self.form.addRow(label, box)
        return widget

    def raw_value(self, key: str) -> Any:
        w = self.fields[key]
        if isinstance(w, QLineEdit):
            return w.text().strip()
        if isinstance(w, QPlainTextEdit):
            return w.toPlainText().strip()
        if isinstance(w, QComboBox):
            return w.currentData() if w.currentData() is not None else w.currentText()
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, QDateTimeEdit):
            return to_iso(w.dateTime())
        if hasattr(w, "value"):
            return w.value()
        return None

    def values(self) -> dict[str, Any]:
        return {k: self.raw_value(k) for k in self.fields}

    def set_field_error(self, key: str, message: str) -> None:
        mark_invalid(self.fields[key], True, self.errors[key], message)

    def clear_errors(self) -> None:
        for k in self.fields:
            mark_invalid(self.fields[k], False, self.errors[k])
        self.form_error.setVisible(False)

    def validate(self) -> bool:
        ok = True
        for k in self.required:
            v = self.raw_value(k)
            if v in ("", None):
                self.set_field_error(k, "This field is required")
                ok = False
        return ok

    def show_error(self, text: str) -> None:
        self.form_error.setText(text)
        self.form_error.setVisible(True)

    def _on_accept(self) -> None:
        self.clear_errors()
        if self.validate():
            self.accept()


def combo(items: Iterable[tuple[str, Any]], current: Any = None) -> QComboBox:
    cb = QComboBox()
    for text, data in items:
        cb.addItem(text, data)
    if current is not None:
        i = cb.findData(current)
        if i >= 0:
            cb.setCurrentIndex(i)
    return cb


def datetime_edit(default: QDateTime | None = None) -> QDateTimeEdit:
    de = QDateTimeEdit(default or QDateTime.currentDateTime().addDays(1))
    de.setCalendarPopup(True)
    de.setDisplayFormat("yyyy-MM-dd HH:mm")
    return de


def countdown_label(expires_iso: str, label: QLabel, done_text: str = "expired") -> QTimer:
    """Updates ``label`` every second with the remaining time until ``expires_iso``."""
    exp = parse_dt(expires_iso)
    timer = QTimer(label)

    def tick() -> None:
        if exp is None:
            label.setText("")
            timer.stop()
            return
        left = int((exp - datetime.now(UTC)).total_seconds())
        if left <= 0:
            label.setText(done_text)
            timer.stop()
        else:
            label.setText(f"expires in {left // 60}:{left % 60:02d}")

    timer.timeout.connect(tick)
    timer.start(1000)
    tick()
    return timer


# ---------------------------------------------------------------------- chips, avatars, donut
def chip(text: str, kind: str = "neutral") -> QLabel:
    """Tinted status chip; ``kind`` is one of success/warning/danger/info/neutral (brand roles)."""
    kind = kind if kind in CHIP_KINDS else "neutral"
    lbl = QLabel(text)
    lbl.setProperty("role", f"chip-{kind}")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    lbl.setAccessibleName(text)
    return lbl


def set_chip(lbl: QLabel, text: str, kind: str) -> None:
    lbl.setText(text)
    set_role(lbl, f"chip-{kind if kind in CHIP_KINDS else 'neutral'}")


STAGE_CHIP = {"new": "neutral", "contacted": "info", "interested": "success", "demo_scheduled": "success", "converted": "success", "not_interested": "warning", "do_not_call": "danger"}
STATUS_CHIP = {"draft": "neutral", "authorized": "info", "active": "success", "paused": "warning", "completed": "neutral", "archived": "neutral",
               "pending": "neutral", "blocked": "danger", "queued": "info", "dispatched": "info", "in_progress": "success", "failed": "danger", "cancelled": "neutral",
               "approved": "success", "pending_review": "warning", "rejected": "danger", "superseded": "neutral", "expired": "neutral", "open": "info", "done": "success"}


def initials(name: str | None) -> str:
    parts = [w for w in (name or "").replace("-", " ").split() if w]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()


def avatar(name: str | None, small: bool = False) -> QLabel:
    lbl = QLabel(initials(name))
    lbl.setProperty("role", "avatar-small" if small else "avatar")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setAccessibleName(f"Avatar {name or ''}")
    return lbl


class DonutChart(QWidget):
    """Donut of real counts (label, value, colour). Shows ``empty_text`` when every value is zero."""

    def __init__(self, parent: QWidget | None = None, empty_text: str = "no calls yet"):
        super().__init__(parent)
        self._data: list[tuple[str, float, str]] = []
        self._center = ""
        self.empty_text = empty_text
        self.setMinimumSize(220, 190)
        self.setAccessibleName("Connection rate donut chart")

    def set_data(self, data: list[tuple[str, float, str]], center: str = "") -> None:
        self._data, self._center = data, center
        self.setAccessibleDescription("; ".join(f"{k}: {v:g}" for k, v, _ in data) or self.empty_text)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtCore import QRectF

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        total = sum(v for _, v, _ in self._data)
        side = min(self.width() - 120, self.height() - 16)
        rect = QRectF(8, 8, max(side, 40), max(side, 40))
        if total <= 0:
            p.setPen(QPen(QColor(BORDER), 18))
            p.drawEllipse(rect.adjusted(9, 9, -9, -9))
            p.setPen(QColor(TEXT2))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.empty_text)
            p.end()
            return
        start = 90 * 16
        for _, v, col in self._data:
            span = -int(round(v / total * 360 * 16))
            p.setPen(QPen(QColor(col), 18, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawArc(rect.adjusted(9, 9, -9, -9), start, span)
            start += span
        p.setPen(QColor(TEXT))
        f = QFont(p.font())
        f.setPointSize(13)
        f.setBold(True)
        p.setFont(f)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._center)
        f.setPointSize(8)
        f.setBold(False)
        p.setFont(f)
        y = int(rect.top()) + 6
        for label, v, col in self._data:
            p.fillRect(int(rect.right()) + 14, y + 2, 10, 10, QColor(col))
            p.setPen(QColor(TEXT))
            p.drawText(int(rect.right()) + 30, y + 11, f"{label} {v:g}")
            y += 18
        p.end()
