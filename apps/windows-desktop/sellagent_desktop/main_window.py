"""Main window: sidebar navigation, stacked screens, persistent EMERGENCY STOP, status bar, live WebSocket routing."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QStatusBar, QVBoxLayout, QWidget

from sellagent_desktop import APP_NAME, APP_VERSION
from sellagent_desktop.api_client import call_async
from sellagent_desktop.context import AppContext
from sellagent_desktop.screens import SCREEN_SPECS, load_screen_class
from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.theme import logo_pixmap
from sellagent_desktop.widgets import DangerBanner, badge, button

log = logging.getLogger("sellagent.desktop")
NAV_SECTIONS = {"setup": "Start", "dashboard": "Work", "diagnostics": "AI & knowledge", "devices": "Devices & safety", "settings": "System"}
TOAST_COLORS = {"info": "#B8B2A0", "success": "#4CAF50", "warning": "#E6A23C", "error": "#E05252"}


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        ctx.navigate = self.navigate
        ctx.notify = self.notify
        self.setWindowTitle(f"{APP_NAME} — FITRON sales calling")
        self.setMinimumSize(1180, 720)
        self.resize(1400, 860)
        self.screens: dict[str, BaseScreen] = {}
        self.nav_buttons: dict[str, QPushButton] = {}
        self._build()
        self._wire_ws()
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(10_000)
        self.status_timer.timeout.connect(self.poll_status)
        self.status_timer.start()
        self.poll_status()
        self.navigate("dashboard")

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(240)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(12, 16, 12, 12)
        sl.setSpacing(6)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(72))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setAccessibleName("FITRON logo")
        sl.addWidget(logo)
        title = QLabel("SELL AGENT")
        title.setObjectName("AppTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(title)
        sub = QLabel("FITRON gym accounting")
        sub.setProperty("role", "caption")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(sub)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        navw = QWidget()
        navw.setStyleSheet("background: transparent;")
        nl = QVBoxLayout(navw)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(2)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for i, (key, label, _m, _c) in enumerate(SCREEN_SPECS):
            if key in NAV_SECTIONS:
                sec = QLabel(NAV_SECTIONS[key].upper())
                sec.setProperty("role", "caption")
                sec.setStyleSheet("margin-top: 8px; letter-spacing: 1px;")
                nl.addWidget(sec)
            b = QPushButton(label)
            b.setProperty("role", "nav")
            b.setCheckable(True)
            b.setAccessibleName(f"Go to {label}")
            b.setObjectName(f"nav_{key}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.navigate(k))
            if i < 9:
                b.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
                b.setToolTip(f"Ctrl+{i + 1}")
            self.nav_group.addButton(b)
            self.nav_buttons[key] = b
            nl.addWidget(b)
        nl.addStretch(1)
        scroll.setWidget(navw)
        sl.addWidget(scroll, 1)
        ver = QLabel(f"v{APP_VERSION}")
        ver.setProperty("role", "caption")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(ver)
        outer.addWidget(sidebar)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        top = QFrame()
        top.setStyleSheet("background-color: #141414; border-bottom: 1px solid #2A2A2A;")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(20, 8, 20, 8)
        self.crumb = QLabel("")
        self.crumb.setProperty("role", "caption")
        tl.addWidget(self.crumb)
        tl.addStretch(1)
        self.toast_lbl = QLabel("")
        self.toast_lbl.setWordWrap(False)
        self.toast_lbl.setAccessibleName("Notification")
        self.toast_lbl.setStyleSheet("background: transparent;")
        tl.addWidget(self.toast_lbl, 2)
        self.ws_badge = badge("live link: connecting", "pill")
        self.ws_badge.setToolTip("Desktop WebSocket to the local backend (call events, device heartbeats, emergency stop fan-out)")
        tl.addWidget(self.ws_badge)
        self.stop_btn = button("EMERGENCY STOP", "danger", self.emergency_stop, tooltip="Cancels every pending/active call job and tells paired phones to stop (Ctrl+Shift+X)")
        self.stop_btn.setObjectName("emergency_stop_btn")
        self.stop_btn.setMinimumHeight(36)
        tl.addWidget(self.stop_btn)
        rl.addWidget(top)
        self.stop_banner = DangerBanner("EMERGENCY STOP IS ACTIVE — no calls can be queued or dispatched. Clear it under Settings & privacy.")
        self.stop_banner.setObjectName("emergency_banner")
        rl.addWidget(self.stop_banner)
        self.stack = QStackedWidget()
        for key, label, module, cls in SCREEN_SPECS:
            screen_cls = load_screen_class(module, cls)
            screen = screen_cls(self.ctx)
            screen.key, screen.title = key, label
            screen.title_lbl.setText(label)
            self.screens[key] = screen
            self.stack.addWidget(screen)
        rl.addWidget(self.stack, 1)
        outer.addWidget(right, 1)
        self.setCentralWidget(central)

        sb = QStatusBar()
        self.setStatusBar(sb)
        self.backend_lbl = QLabel("backend: …")
        self.backend_lbl.setAccessibleName("Backend status")
        self.devices_lbl = QLabel("devices: …")
        self.devices_lbl.setAccessibleName("Connected device count")
        self.stop_lbl = QLabel("emergency stop: …")
        self.stop_lbl.setObjectName("status_emergency")
        self.stop_lbl.setAccessibleName("Emergency stop state")
        for w in (self.backend_lbl, self.devices_lbl, self.stop_lbl):
            w.setStyleSheet("padding: 0 10px;")
            sb.addPermanentWidget(w)
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(lambda: self.toast_lbl.setText(""))
        QShortcut(QKeySequence("Ctrl+Shift+X"), self, activated=self.emergency_stop)
        QShortcut(QKeySequence("F5"), self, activated=self.refresh_current)

    # ------------------------------------------------------------------ navigation
    def navigate(self, key: str, **context: Any) -> None:
        screen = self.screens.get(key)
        if screen is None:
            log.warning("unknown screen %s", key)
            return
        if context:
            screen.set_context(**context)
        self.stack.setCurrentWidget(screen)
        self.nav_buttons[key].setChecked(True)
        self.crumb.setText(f"{NAV_SECTIONS.get(self._section_of(key), '')} › {screen.title}")
        screen.refresh()

    def _section_of(self, key: str) -> str:
        current = "setup"
        for k, *_ in SCREEN_SPECS:
            if k in NAV_SECTIONS:
                current = k
            if k == key:
                return current
        return current

    def current_screen(self) -> BaseScreen:
        return self.stack.currentWidget()  # type: ignore[return-value]

    def refresh_current(self) -> None:
        self.current_screen().refresh()

    # ------------------------------------------------------------------ notifications & status
    def notify(self, text: str, level: str = "info") -> None:
        color = TOAST_COLORS.get(level, TOAST_COLORS["info"])
        self.toast_lbl.setStyleSheet(f"color: {color}; background: transparent; font-weight: {'600' if level in ('error', 'warning') else '400'};")
        self.toast_lbl.setText(text[:220])
        self.toast_lbl.setToolTip(text)
        self.statusBar().showMessage(text, 8000)
        self.toast_timer.start(9000 if level in ("error", "warning") else 5000)
        (log.error if level == "error" else log.info)("%s", text)

    def poll_status(self) -> None:
        def fetch() -> tuple:
            return self.ctx.api.get("/health/ping"), self.ctx.api.get("/settings"), self.ctx.api.get("/devices/connected")

        def done(res: tuple) -> None:
            ping, settings, conn = res
            vals = settings.get("values", {})
            self.ctx.settings_cache.update(vals)
            self.backend_lbl.setText(f"backend: {ping.get('app')} {ping.get('version')} ok")
            self.backend_lbl.setStyleSheet("padding: 0 10px; color: #4CAF50;")
            self.devices_lbl.setText(f"devices connected: {len(conn.get('connected', []))}")
            self.set_emergency_state(bool(vals.get("calling.emergency_stop_active")))

        def failed(exc: Exception) -> None:
            self.backend_lbl.setText(f"backend: UNREACHABLE ({exc})")
            self.backend_lbl.setStyleSheet("padding: 0 10px; color: #E05252;")

        call_async(fetch, done, failed)

    def set_emergency_state(self, active: bool) -> None:
        self.ctx.emergency_stop_active = active
        self.stop_banner.setVisible(active)
        self.stop_lbl.setText("emergency stop: ACTIVE" if active else "emergency stop: clear")
        self.stop_lbl.setStyleSheet("padding: 0 10px; color: #E05252; font-weight: 700;" if active else "padding: 0 10px; color: #B8B2A0;")
        self.stop_btn.setText("EMERGENCY STOP (active)" if active else "EMERGENCY STOP")

    # ------------------------------------------------------------------ emergency stop
    def emergency_stop(self, reason: str = "operator_emergency_stop") -> None:
        """No confirmation dialog on purpose: the stop must be immediate. Clearing it requires confirmation."""
        if not isinstance(reason, str) or not reason:
            reason = "operator_emergency_stop"
        self.set_emergency_state(True)
        if self.ctx.ws is not None:
            self.ctx.ws.send_emergency_stop(reason)  # lowest latency path; the REST call below is authoritative

        def done(res: dict) -> None:
            n = len(res.get("cancelled_jobs", []))
            self.notify(f"EMERGENCY STOP active — {n} job(s) cancelled", "warning")
            self.refresh_current()

        call_async(lambda: self.ctx.api.post("/call-jobs/emergency-stop", {"reason": reason, "activate": True}), done, lambda e: self.notify(f"Emergency stop request failed: {e}", "error"))

    # ------------------------------------------------------------------ websocket
    def _wire_ws(self) -> None:
        ws = self.ctx.ws
        if ws is None:
            self.ws_badge.setText("live link: off")
            return
        ws.event.connect(self.on_ws_event)
        ws.connected_changed.connect(self._ws_state)
        ws.status_text.connect(lambda t: self.ws_badge.setToolTip(f"WebSocket: {t}"))
        self._ws_state(ws.is_connected)

    def _ws_state(self, ok: bool) -> None:
        self.ws_badge.setText("live link: connected" if ok else "live link: reconnecting")
        self.ws_badge.setProperty("role", "pill-gold" if ok else "pill")
        self.ws_badge.style().unpolish(self.ws_badge)
        self.ws_badge.style().polish(self.ws_badge)

    def on_ws_event(self, env: dict) -> None:
        t = env.get("type")
        if t == "safety.emergency_stop":
            self.set_emergency_state(True)
            self.notify(f"Emergency stop broadcast received ({(env.get('payload') or {}).get('issued_by')})", "warning")
        elif t == "ack" and (env.get("payload") or {}).get("message_id") == "emergency_stop_cleared":
            self.set_emergency_state(False)
            self.notify("Emergency stop cleared", "success")
        elif t == "error":
            p = env.get("payload") or {}
            self.notify(f"Device event: {p.get('code')} — {p.get('message')}", "warning")
        elif t in ("session.heartbeat", "session.capabilities"):
            call_async(lambda: self.ctx.api.get("/devices/connected"), lambda c: self.devices_lbl.setText(f"devices connected: {len(c.get('connected', []))}"))
        for s in self.screens.values():
            try:
                s.on_ws_event(env)
            except Exception:  # noqa: BLE001
                log.exception("screen %s failed on ws event", s.key)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.status_timer.stop()
        super().closeEvent(event)
