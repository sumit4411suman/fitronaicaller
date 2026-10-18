"""Base class for all screens: background requests with busy state, error reporting, refresh contract."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from sellagent_desktop.api_client import ApiError, call_async
from sellagent_desktop.context import AppContext
from sellagent_desktop.widgets import caption, page_title


# Buttons whose text starts with one of these only read or navigate; they stay enabled for read-only roles.
READ_SAFE = re.compile(r"^(Reload|Refresh|Search|Open|Check|Retrieve|Filter|Export|Close|Go to|Call queue|All campaigns|Manage devices|◀|▶|Previous|Next|Today|Show|View|Download|Save as)", re.IGNORECASE)


class _Lock(QObject):
    """Keeps a button disabled even when screen logic re-enables it (selection changes etc.)."""

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:  # noqa: N802
        if ev.type() == QEvent.Type.EnabledChange and isinstance(obj, QAbstractButton) and obj.property("perm_locked") and obj.isEnabled():
            obj.setEnabled(False)
        return False


_LOCK = _Lock()


class BaseScreen(QWidget):
    key = ""
    title = ""
    subtitle = ""
    area = ""  # backend permission area; GET needs '<area>:read', writes need '<area>:write' 
    scrollable = False  # long dashboards put their content in a scroll area so cards never get squeezed

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.api = ctx.api
        self.last_error: Exception | None = None
        self._busy = 0
        if self.scrollable:
            from PySide6.QtWidgets import QFrame, QScrollArea

            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            inner = QWidget()
            inner.setObjectName("Content")
            area.setWidget(inner)
            outer.addWidget(area)
            self.root = QVBoxLayout(inner)
        else:
            self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 16, 20, 16)
        self.root.setSpacing(10)
        head = QHBoxLayout()
        self.title_lbl = page_title(self.title)
        head.addWidget(self.title_lbl)
        head.addStretch(1)
        self.busy_lbl = QLabel("")
        self.busy_lbl.setProperty("role", "caption")
        self.busy_lbl.setAccessibleName("Loading indicator")
        head.addWidget(self.busy_lbl)
        self.root.addLayout(head)
        self.denied_lbl = QLabel("")
        self.denied_lbl.setProperty("role", "chip-danger")
        self.denied_lbl.setWordWrap(True)
        self.denied_lbl.setVisible(False)
        self.root.addWidget(self.denied_lbl)
        if self.subtitle:
            self.root.addWidget(caption(self.subtitle))
        self.build()

    # ------------------------------------------------------------------ to override
    def build(self) -> None:
        """Create widgets. Called once from __init__."""

    def refresh(self) -> None:
        """Reload data from the backend. Must never raise; errors are reported through ``report_error``."""

    def set_context(self, **kwargs: Any) -> None:
        """Receive navigation context (e.g. ``contact_id``)."""

    def on_ws_event(self, env: dict) -> None:
        """Live event from the desktop WebSocket (already on the UI thread)."""

    # ------------------------------------------------------------------ permissions
    def can_read(self) -> bool:
        return not self.area or self.ctx.can(f"{self.area}:read")

    def apply_permissions(self) -> None:
        """Disable write actions the current role lacks. A button may name its own permission with the dynamic
        property ``perm`` (e.g. 'calls:write') or opt out with ``readonly_ok``."""
        role = self.ctx.role
        readable = self.can_read()
        self.denied_lbl.setVisible(not readable)
        self.denied_lbl.setText(f"Your role ({role}) can't view this screen ({self.area}:read)." if not readable else "")
        default_write = f"{self.area}:write" if self.area else None
        for b in self.findChildren(QPushButton):
            if b.property("readonly_ok") or b.objectName() == "emergency_stop_btn":
                continue
            perm = b.property("perm") or (None if READ_SAFE.match(b.text().replace("&&", "&").lstrip("+ ")) else default_write)
            locked = bool(perm) and not self.ctx.can(str(perm))
            if not readable and not b.property("perm"):
                locked = True
            was = bool(b.property("perm_locked"))
            b.setProperty("perm_locked", locked)
            if locked:
                if not was:
                    b.setProperty("perm_tooltip_backup", b.toolTip())
                    b.setProperty("perm_prev_enabled", b.isEnabled())
                    b.installEventFilter(_LOCK)
                b.setEnabled(False)
                b.setToolTip(f"Your role ({role}) can't do this (needs {perm or self.area + ':read'})")
            elif was:
                b.removeEventFilter(_LOCK)
                b.setToolTip(b.property("perm_tooltip_backup") or "")
                b.setEnabled(bool(b.property("perm_prev_enabled")))

    # ------------------------------------------------------------------ helpers
    def run(self, fn: Callable[[], Any], on_done: Callable[[Any], None] | None = None, on_error: Callable[[Exception], None] | None = None, busy_text: str = "Loading…") -> None:
        self._set_busy(True, busy_text)

        def _done(res: Any) -> None:
            self._set_busy(False)
            self.last_error = None
            if on_done:
                try:
                    on_done(res)
                except Exception as exc:  # noqa: BLE001 - UI handler bug must not kill the app
                    self.report_error(exc)

        def _err(exc: Exception) -> None:
            self._set_busy(False)
            if on_error:
                on_error(exc)
            else:
                self.report_error(exc)

        call_async(fn, _done, _err)

    def _set_busy(self, on: bool, text: str = "") -> None:
        self._busy += 1 if on else -1
        if self._busy < 0:
            self._busy = 0
        if self._busy and on:
            self.busy_lbl.setText(text)
            QGuiApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        elif not self._busy:
            self.busy_lbl.setText("")
            while QGuiApplication.overrideCursor() is not None:
                QGuiApplication.restoreOverrideCursor()

    def report_error(self, exc: Exception) -> None:
        self.last_error = exc
        if isinstance(exc, ApiError):
            self.ctx.notify(f"{self.title}: {exc}", "error")
        else:
            tb = getattr(exc, "ui_traceback", "")
            self.ctx.notify(f"{self.title}: {exc.__class__.__name__}: {exc}", "error")
            if tb:
                import logging

                logging.getLogger("sellagent.desktop").error("%s", tb)

    def toast(self, text: str, level: str = "info") -> None:
        self.ctx.notify(text, level)

    @property
    def is_busy(self) -> bool:
        return self._busy > 0
