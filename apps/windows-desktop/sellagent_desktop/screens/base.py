"""Base class for all screens: background requests with busy state, error reporting, refresh contract."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from sellagent_desktop.api_client import ApiError, call_async
from sellagent_desktop.context import AppContext
from sellagent_desktop.widgets import caption, page_title


class BaseScreen(QWidget):
    key = ""
    title = ""
    subtitle = ""
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
