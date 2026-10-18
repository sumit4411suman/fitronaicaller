"""Main window per the approved mockup: dark gold sidebar, white header (search, status chips, operator, EMERGENCY STOP),
light content area with the eleven navigation groups. Every one of the registered screens stays reachable via
``navigate(screen_key)``; groups with several screens show them as tabs."""

from __future__ import annotations

import logging
import time
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton, QScrollArea, QStackedWidget, QStatusBar, QTabWidget, QVBoxLayout, QWidget

from sellagent_desktop import APP_NAME, APP_VERSION
from sellagent_desktop.api_client import call_async
from sellagent_desktop.context import AppContext
from sellagent_desktop.screens import NAV_GROUPS, SCREEN_SPECS, group_for, load_screen_class
from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.theme import logo_pixmap
from sellagent_desktop.widgets import DangerBanner, avatar, button, caption, chip, set_chip, set_role

log = logging.getLogger("sellagent.desktop")
TOAST_COLORS = {"info": "#6B665A", "success": "#2E7D32", "warning": "#B8720A", "error": "#C62828"}


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        ctx.navigate = self.navigate
        ctx.notify = self.notify
        self.setWindowTitle(f"{APP_NAME} — FITRON sales calling")
        self.setMinimumSize(1180, 720)
        self.resize(1440, 880)
        self.screens: dict[str, BaseScreen] = {}
        self.nav_buttons: dict[str, QPushButton] = {}  # keyed by NAV group
        self.group_pages: dict[str, QWidget] = {}
        self.group_tabs: dict[str, QTabWidget] = {}
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
        outer.addWidget(self._build_sidebar())
        right = QWidget()
        right.setObjectName("Content")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self._build_header())
        self.stop_banner = DangerBanner("EMERGENCY STOP IS ACTIVE — no calls can be queued or dispatched. Clear it under Settings › Privacy & calling settings.")
        self.stop_banner.setObjectName("emergency_banner")
        rl.addWidget(self.stop_banner)
        self.stack = QStackedWidget()
        self.stack.setObjectName("Content")
        for key, label, module, cls in SCREEN_SPECS:
            screen = load_screen_class(module, cls)(self.ctx)
            screen.key, screen.title = key, label
            screen.title_lbl.setText(label)
            self.screens[key] = screen
        for nav_key, _label, keys in NAV_GROUPS:
            if len(keys) == 1:
                page: QWidget = self.screens[keys[0]]
            else:
                page = QWidget()
                page.setObjectName("Content")
                pl = QVBoxLayout(page)
                pl.setContentsMargins(12, 10, 12, 8)
                tabs = QTabWidget()
                tabs.setDocumentMode(True)
                for k in keys:
                    tabs.addTab(self.screens[k], self.screens[k].title)
                tabs.currentChanged.connect(lambda idx, t=tabs: self._tab_changed(t, idx))
                pl.addWidget(tabs)
                self.group_tabs[nav_key] = tabs
            self.group_pages[nav_key] = page
            self.stack.addWidget(page)
        rl.addWidget(self.stack, 1)
        outer.addWidget(right, 1)
        self.setCentralWidget(central)

        sb = QStatusBar()
        self.setStatusBar(sb)
        self.backend_lbl = QLabel("backend: …")
        self.backend_lbl.setAccessibleName("Backend status")
        self.devices_lbl = QLabel("devices connected: …")
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
        QShortcut(QKeySequence("Ctrl+K"), self, activated=lambda: (self.search.setFocus(), self.search.selectAll()))

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(248)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(14, 18, 14, 14)
        sl.setSpacing(6)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(logo_pixmap(44))
        logo.setAccessibleName("FITRON logo")
        brand.addWidget(logo)
        words = QHBoxLayout()
        words.setSpacing(6)
        t1 = QLabel("SELL")
        t1.setObjectName("AppTitle")
        t2 = QLabel("AGENT")
        t2.setObjectName("AppTitleAccent")
        words.addWidget(t1)
        words.addWidget(t2)
        words.addStretch(1)
        brand.addLayout(words, 1)
        sl.addLayout(brand)
        sub = caption("FITRON gym accounting · local AI sales calls")
        sl.addWidget(sub)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        navw = QWidget()
        nl = QVBoxLayout(navw)
        nl.setContentsMargins(0, 8, 0, 0)
        nl.setSpacing(3)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for i, (nav_key, label, keys) in enumerate(NAV_GROUPS):
            b = QPushButton(label)
            b.setProperty("role", "nav")
            b.setCheckable(True)
            b.setAccessibleName(f"Go to {label}")
            b.setObjectName(f"nav_{nav_key}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=keys[0]: self.navigate(k))
            if i < 9:
                b.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
            b.setToolTip(", ".join(self.screens[k].title for k in keys) if hasattr(self, "screens") and self.screens else label)
            self.nav_group.addButton(b)
            self.nav_buttons[nav_key] = b
            nl.addWidget(b)
        nl.addStretch(1)
        scroll.setWidget(navw)
        sl.addWidget(scroll, 1)
        # AI Engine status box (dark card)
        self.ai_card = QFrame()
        self.ai_card.setProperty("role", "card-dark")
        al = QVBoxLayout(self.ai_card)
        al.setContentsMargins(12, 10, 12, 10)
        al.setSpacing(3)
        t = QLabel("AI Engine")
        t.setProperty("role", "gold")
        al.addWidget(t)
        self.ai_provider_lbl = QLabel("checking…")
        self.ai_provider_lbl.setProperty("role", "caption")
        self.ai_provider_lbl.setAccessibleName("AI provider status")
        self.ai_cpu_lbl = caption("CPU: …")
        self.ai_ram_lbl = caption("RAM: …")
        self.ai_gpu_lbl = caption("No GPU (CPU mode)")
        for w in (self.ai_provider_lbl, self.ai_cpu_lbl, self.ai_ram_lbl, self.ai_gpu_lbl):
            al.addWidget(w)
        sl.addWidget(self.ai_card)
        ver = caption(f"v{APP_VERSION}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(ver)
        return sidebar

    def _build_header(self) -> QFrame:
        top = QFrame()
        top.setObjectName("Header")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(20, 10, 20, 10)
        tl.setSpacing(12)
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Search contacts, campaigns, or enter a number...   Ctrl+K")
        self.search.setAccessibleName("Global search")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(320)
        self.search.returnPressed.connect(self.global_search)
        tl.addWidget(self.search, 3)
        self.toast_lbl = QLabel("")
        self.toast_lbl.setAccessibleName("Notification")
        tl.addWidget(self.toast_lbl, 2)
        self.ai_chip = chip("Local AI: checking", "neutral")
        self.ai_chip.setObjectName("chip_ai")
        self.backend_chip = chip("Backend: starting", "neutral")
        self.backend_chip.setObjectName("chip_backend")
        self.device_chip = chip("Phone: not paired", "neutral")
        self.device_chip.setObjectName("chip_device")
        for c in (self.ai_chip, self.backend_chip, self.device_chip):
            tl.addWidget(c)
        self.op_avatar = avatar("Operator", small=True)
        self.op_name = QLabel("Operator")
        self.op_name.setObjectName("operator_name")
        self.op_name.setAccessibleName("Operator name")
        self.op_name.setStyleSheet("font-weight: 600;")
        tl.addWidget(self.op_avatar)
        tl.addWidget(self.op_name)
        self.stop_btn = button("EMERGENCY STOP", "danger", self.emergency_stop, tooltip="Cancels every pending/active call job and tells paired phones to stop (Ctrl+Shift+X)")
        self.stop_btn.setObjectName("emergency_stop_btn")
        tl.addWidget(self.stop_btn)
        return top

    # ------------------------------------------------------------------ navigation
    def navigate(self, key: str, **context: Any) -> None:
        screen = self.screens.get(key)
        if screen is None:
            log.warning("unknown screen %s", key)
            return
        if context:
            screen.set_context(**context)
        nav_key = group_for(key)
        self.stack.setCurrentWidget(self.group_pages[nav_key])
        self.nav_buttons[nav_key].setChecked(True)
        tabs = self.group_tabs.get(nav_key)
        if tabs is not None:
            tabs.blockSignals(True)
            tabs.setCurrentWidget(screen)
            tabs.blockSignals(False)
        screen.refresh()

    def _tab_changed(self, tabs: QTabWidget, idx: int) -> None:
        w = tabs.widget(idx)
        if isinstance(w, BaseScreen):
            w.refresh()

    def nav_button_for(self, screen_key: str) -> QPushButton:
        return self.nav_buttons[group_for(screen_key)]

    def current_screen(self) -> BaseScreen:
        page = self.stack.currentWidget()
        if isinstance(page, BaseScreen):
            return page
        for tabs in self.group_tabs.values():
            if tabs.isAncestorOf(page) or tabs.parentWidget() is page:
                return tabs.currentWidget()  # type: ignore[return-value]
        return self.screens["dashboard"]

    def refresh_current(self) -> None:
        self.current_screen().refresh()

    def global_search(self) -> None:
        q = self.search.text().strip()
        if not q:
            return
        self.navigate("contacts", query=q)

    # ------------------------------------------------------------------ notifications & status
    def notify(self, text: str, level: str = "info") -> None:
        color = TOAST_COLORS.get(level, TOAST_COLORS["info"])
        self.toast_lbl.setStyleSheet(f"color: {color}; background: transparent; font-weight: {'600' if level in ('error', 'warning') else '400'};")
        self.toast_lbl.setText(text[:160])
        self.toast_lbl.setToolTip(text)
        self.statusBar().showMessage(text, 8000)
        self.toast_timer.start(9000 if level in ("error", "warning") else 5000)
        (log.error if level == "error" else log.info)("%s", text)

    def poll_status(self) -> None:
        api = self.ctx.api

        def fetch() -> dict:
            out: dict[str, Any] = {"ping": api.get("/health/ping"), "settings": api.get("/settings"), "connected": api.get("/devices/connected"), "devices": api.get("/devices")}
            try:
                out["ai"] = api.get("/ai/status")
            except Exception as exc:  # noqa: BLE001 - AI status must never break the status poll
                out["ai"] = {"available": False, "message": str(exc), "provider": "?"}
            out["sys"] = _system_stats()
            return out

        call_async(fetch, self._status_done, self._status_failed)

    def _status_done(self, res: dict) -> None:
        ping, settings, conn, devices, ai, sysinfo = res["ping"], res["settings"], res["connected"], res["devices"], res["ai"], res["sys"]
        vals = settings.get("values", {})
        self.ctx.settings_cache.update(vals)
        self.ctx.ai_status = ai
        self.ctx.devices = devices
        self.ctx.connected_devices = conn.get("connected", [])
        self.backend_lbl.setText(f"backend: {ping.get('app')} {ping.get('version')} ok")
        self.backend_lbl.setStyleSheet("padding: 0 10px; color: #2E7D32;")
        set_chip(self.backend_chip, "Backend: Running", "success")
        set_chip(self.ai_chip, "Local AI: Online" if ai.get("available") else "Local AI: Offline", "success" if ai.get("available") else "danger")
        self.ai_chip.setToolTip(f"{ai.get('provider')} — {ai.get('message') or 'ok'} · model {ai.get('configured_model')} ({'installed' if ai.get('configured_model_installed') else 'not installed'})")
        self._device_chip()
        self.devices_lbl.setText(f"devices connected: {len(self.ctx.connected_devices)}")
        name = str(vals.get("general.operator_name") or "Operator")
        self.op_name.setText(name)
        self.op_avatar.setText(name[:2].upper())
        disp = str(vals.get("general.app_display_name") or APP_NAME)
        self.setWindowTitle(f"{disp} — FITRON sales calling")
        self.set_emergency_state(bool(vals.get("calling.emergency_stop_active")))
        self.ai_provider_lbl.setText(f"{ai.get('provider', '?')}: {'Online' if ai.get('available') else 'Offline'} · {ai.get('configured_model') or ''}")
        set_role(self.ai_provider_lbl, "success" if ai.get("available") else "danger")
        self.ai_cpu_lbl.setText(sysinfo.get("cpu", "CPU: n/a"))
        self.ai_ram_lbl.setText(sysinfo.get("ram", "RAM: n/a"))
        self.ai_gpu_lbl.setText("No GPU (CPU mode)")

    def _device_chip(self) -> None:
        approved = [d for d in self.ctx.devices if d.get("status") == "approved"]
        if not approved:
            set_chip(self.device_chip, "Phone: not paired", "neutral")
            self.device_chip.setToolTip("Pair the Android companion under Devices")
            return
        approved.sort(key=lambda d: d.get("last_seen_at") or "", reverse=True)
        dev = approved[0]
        online = dev["id"] in self.ctx.connected_devices
        set_chip(self.device_chip, f"{dev.get('model') or dev.get('name')}: {'Connected' if online else 'Not connected'}", "success" if online else "warning")
        self.device_chip.setToolTip(f"{dev.get('name')} · Android {dev.get('android_version')} · app {dev.get('app_version')}")

    def _status_failed(self, exc: Exception) -> None:
        self.backend_lbl.setText(f"backend: UNREACHABLE ({exc})")
        self.backend_lbl.setStyleSheet("padding: 0 10px; color: #C62828;")
        set_chip(self.backend_chip, "Backend: Unreachable", "danger")

    def set_emergency_state(self, active: bool) -> None:
        self.ctx.emergency_stop_active = active
        self.stop_banner.setVisible(active)
        self.stop_lbl.setText("emergency stop: ACTIVE" if active else "emergency stop: clear")
        self.stop_lbl.setStyleSheet("padding: 0 10px; color: #C62828; font-weight: 700;" if active else "padding: 0 10px; color: #6B665A;")
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
            self.notify(f"EMERGENCY STOP active — {len(res.get('cancelled_jobs', []))} job(s) cancelled", "warning")
            self.refresh_current()

        call_async(lambda: self.ctx.api.post("/call-jobs/emergency-stop", {"reason": reason, "activate": True}), done, lambda e: self.notify(f"Emergency stop request failed: {e}", "error"))

    # ------------------------------------------------------------------ websocket
    def _wire_ws(self) -> None:
        ws = self.ctx.ws
        if ws is None:
            return
        ws.event.connect(self.on_ws_event)
        ws.connected_changed.connect(self._ws_state)
        self._ws_state(ws.is_connected)

    def _ws_state(self, ok: bool) -> None:
        self.backend_chip.setToolTip("Live WebSocket link: " + ("connected" if ok else "reconnecting"))

    def on_ws_event(self, env: dict) -> None:
        t = env.get("type")
        p = env.get("payload") or {}
        if t == "safety.emergency_stop":
            self.set_emergency_state(True)
            self.notify(f"Emergency stop broadcast received ({p.get('issued_by')})", "warning")
        elif t == "ack" and p.get("message_id") == "emergency_stop_cleared":
            self.set_emergency_state(False)
            self.notify("Emergency stop cleared", "success")
        elif t == "error":
            self.notify(f"Device event: {p.get('code')} — {p.get('message')}", "warning")
            if p.get("code") == "device_disconnected":
                self.poll_status()
        elif t == "session.heartbeat":
            self.ctx.last_heartbeat = {**p, "received_at": time.time()}
            self.poll_status()
        elif t == "session.capabilities":
            self.poll_status()
        for s in self.screens.values():
            try:
                s.on_ws_event(env)
            except Exception:  # noqa: BLE001
                log.exception("screen %s failed on ws event", s.key)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.status_timer.stop()
        super().closeEvent(event)


def _system_stats() -> dict[str, str]:
    try:
        import psutil

        vm = psutil.virtual_memory()
        return {"cpu": f"CPU: {psutil.cpu_percent(interval=None):.0f}%", "ram": f"RAM: {vm.used / 1024**3:.1f} / {vm.total / 1024**3:.1f} GB"}
    except ImportError:
        return {"cpu": "CPU: n/a (psutil not installed)", "ram": "RAM: n/a (psutil not installed)"}
    except Exception as exc:  # noqa: BLE001
        return {"cpu": f"CPU: n/a ({exc.__class__.__name__})", "ram": "RAM: n/a"}
