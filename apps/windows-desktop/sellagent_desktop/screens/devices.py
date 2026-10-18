"""Screen 17: Android device pairing (pairing window, pending request, device list, LAN toggle, connection state)."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from sellagent_desktop.screens.base import BaseScreen
from sellagent_desktop.widgets import Card, DataTable, EmptyState, KeyValueGrid, badge, button, caption, confirm, countdown_label, fmt_dt, pretty_json, status_label


class DevicesScreen(BaseScreen):
    key, title = "devices", "Android device pairing"

    def build(self) -> None:
        self.connected: list[str] = []
        self.poll = QTimer(self)
        self.poll.setInterval(2000)
        self.poll.timeout.connect(self.poll_status)
        self.countdown: QTimer | None = None
        top = QHBoxLayout()
        lan = Card("LAN pairing listener")
        self.lan_toggle = QCheckBox("Enable LAN listener (network.lan_pairing_enabled)")
        self.lan_toggle.setAccessibleName("Enable LAN pairing listener")
        self.lan_toggle.clicked.connect(self.toggle_lan)
        lan.add(self.lan_toggle)
        self.lan_grid = KeyValueGrid()
        lan.add(self.lan_grid)
        lan.add(caption("The listener serves only /devices/pair, /devices/pair/result, /devices/me and /ws/device over TLS with the self-signed certificate below. The main API never leaves 127.0.0.1."))
        top.addWidget(lan, 1)
        pair = Card("Pairing window", gold=True)
        self.code_lbl = QLabel("——————")
        self.code_lbl.setProperty("role", "pairing-code")
        self.code_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_lbl.setAccessibleName("Pairing code")
        pair.add(self.code_lbl)
        self.expiry_lbl = status_label("closed")
        self.expiry_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pair.add(self.expiry_lbl)
        pr = QHBoxLayout()
        self.open_btn = button("Open pairing window", "primary", self.open_pairing)
        self.close_btn = button("Close window", None, self.close_pairing)
        pr.addWidget(self.open_btn)
        pr.addWidget(self.close_btn)
        pw = QWidget()
        pw.setLayout(pr)
        pair.add(pw)
        self.instructions = caption("")
        pair.add(self.instructions)
        top.addWidget(pair, 1)
        self.root.addLayout(top)
        self.pending = Card("Pending pairing request")
        self.pending_grid = KeyValueGrid()
        self.pending.add(self.pending_grid)
        dr = QHBoxLayout()
        dr.addWidget(button("Approve", "primary", lambda: self.decide(True)))
        dr.addWidget(button("Reject", "danger", lambda: self.decide(False)))
        dr.addStretch(1)
        dw = QWidget()
        dw.setLayout(dr)
        self.pending.add(dw)
        self.pending.setVisible(False)
        self.root.addWidget(self.pending)
        dl = Card("Paired devices")
        hb = QHBoxLayout()
        self.conn_badge = badge("0 connected")
        hb.addWidget(self.conn_badge)
        hb.addWidget(caption("Connected = live WebSocket session with heartbeats."))
        hb.addStretch(1)
        hb.addWidget(button("Revoke", None, self.revoke))
        hb.addWidget(button("Delete (revoked only)", "danger", self.delete))
        hw = QWidget()
        hw.setLayout(hb)
        dl.add(hw)
        self.table = DataTable([("Name", "name"), ("Model", "model"), ("Android", "android_version"), ("App", "app_version"), ("Status", "status"), ("Connected", lambda r: "yes" if r["id"] in self.connected else "no"), ("Last seen", lambda r: fmt_dt(r.get("last_seen_at"))), ("Last IP", "last_ip"), ("Token expires", lambda r: fmt_dt(r.get("token_expires_at"))), ("Capabilities", lambda r: pretty_json(r.get("capabilities")))])
        dl.add(self.table)
        self.empty = EmptyState("No devices paired. Open a pairing window and enter the code in the SELL AGENT companion app on the phone.")
        dl.add(self.empty)
        self.root.addWidget(dl, 1)

    def refresh(self) -> None:
        self.run(lambda: (self.api.get("/devices"), self.api.get("/devices/connected"), self.api.get("/devices/pairing/status"), self.api.get("/health"), self.api.get("/settings")), self._show)

    def _show(self, res: tuple) -> None:
        devs, conn, pst, health, settings = res
        self.connected = conn.get("connected", [])
        self.table.set_rows(devs)
        self.empty.setVisible(not devs)
        self.conn_badge.setText(f"{len(self.connected)} connected")
        lan = health.get("lan") or {}
        self.lan_toggle.blockSignals(True)
        self.lan_toggle.setChecked(bool(settings.get("values", {}).get("network.lan_pairing_enabled")))
        self.lan_toggle.blockSignals(False)
        self.lan_grid.set_rows([("listener", "RUNNING" if lan.get("enabled") else "stopped"), ("addresses", ", ".join(lan.get("addresses") or []) or "none detected"), ("port", lan.get("port")), ("scheme", lan.get("scheme")), ("TLS fingerprint", lan.get("tls_fingerprint_sha256"))])
        self._pairing(pst)

    def _pairing(self, pst: dict) -> None:
        if pst.get("open"):
            self.expiry_lbl.setProperty("role", "warning")
            if self.countdown:
                self.countdown.stop()
            self.countdown = countdown_label(pst.get("expires_at"), self.expiry_lbl, "expired — open again")
            if not self.poll.isActive():
                self.poll.start()
            p = pst.get("pending")
            self.pending.setVisible(p is not None)
            if p:
                self.pending_grid.set_rows([("device", f"{p.get('device_name')} ({p.get('device_model')})"), ("android", p.get("android_version")), ("app", p.get("app_version")), ("public id", p.get("device_public_id")), ("requested", fmt_dt(p.get("requested_at"), True)), ("capabilities", pretty_json(p.get("capabilities"))), ("decision", "waiting" if p.get("approved") is None else ("approved" if p.get("approved") else "rejected"))])
        else:
            self.poll.stop()
            if self.countdown:
                self.countdown.stop()
            self.code_lbl.setText("——————")
            self.expiry_lbl.setText("closed")
            self.pending.setVisible(False)
        self.close_btn.setEnabled(bool(pst.get("open")))

    def poll_status(self) -> None:
        self.run(lambda: self.api.get("/devices/pairing/status"), self._pairing)

    def open_pairing(self) -> None:
        if not self.lan_toggle.isChecked() and not confirm(self, "LAN listener is off", "The phone can only reach this PC when the LAN listener is enabled. Open the window anyway (useful for testing on this PC)?", "Open anyway"):
            return
        self.run(lambda: self.api.post("/devices/pairing/open"), self._opened)

    def _opened(self, w: dict) -> None:
        self.code_lbl.setText(str(w.get("pairing_code")))
        lan = w.get("lan") or {}
        self.instructions.setText(f"{w.get('instructions')}\nAddresses: {', '.join(lan.get('addresses') or []) or 'LAN listener off'} · port {lan.get('port')} · fingerprint {w.get('tls_fingerprint_sha256')} · protocol {w.get('protocol_version')} · attempts left {w.get('attempts_left')}")
        self._pairing({"open": True, "expires_at": w.get("expires_at"), "pending": None})
        self.toast("Pairing window open", "success")

    def close_pairing(self) -> None:
        self.run(lambda: self.api.post("/devices/pairing/close"), lambda _: self.refresh())

    def decide(self, approve: bool) -> None:
        if approve and not confirm(self, "Approve device", "Approving issues a 90-day device token. Only approve a phone you physically hold.", "Approve"):
            return
        self.run(lambda: self.api.post("/devices/pairing/decide", {"approve": approve}), lambda r: (self.toast("Device approved" if r.get("approved") else "Request rejected", "success" if r.get("approved") else "warning"), self.refresh()))

    def toggle_lan(self, checked: bool) -> None:
        if checked and not confirm(self, "Expose pairing listener on Wi-Fi", "Enabling the LAN listener opens an HTTPS/WSS port on every network interface of this PC (default 8766). Only device pairing and device WebSocket endpoints are exposed, protected by TLS and pairing codes, but anyone on the same Wi-Fi can see the port. Enable only on a trusted network.", "Enable", danger=True):
            self.lan_toggle.setChecked(False)
            return
        self.run(lambda: self.api.patch("/settings", {"values": {"network.lan_pairing_enabled": checked}}), lambda _: (self.toast("LAN listener " + ("enabled (starts within 5 s)" if checked else "disabled"), "warning"), QTimer.singleShot(5500, self.refresh)))

    def _sel(self) -> dict | None:
        d = self.table.selected_row()
        if not d:
            self.toast("Select a device", "warning")
        return d

    def revoke(self) -> None:
        d = self._sel()
        if d and confirm(self, "Revoke device", f"Revoke {d['name']}? Its token stops working immediately and any live session is closed.", "Revoke", danger=True):
            self.run(lambda: self.api.post(f"/devices/{d['id']}/revoke"), lambda _: self.refresh())

    def delete(self) -> None:
        d = self._sel()
        if d and confirm(self, "Delete device", f"Delete the record of {d['name']}?", "Delete", danger=True):
            self.run(lambda: self.api.delete(f"/devices/{d['id']}"), lambda _: self.refresh())

    def on_ws_event(self, env: dict) -> None:
        if env.get("type") in ("session.heartbeat", "session.capabilities") or (env.get("type") == "error" and (env.get("payload") or {}).get("code") == "device_disconnected"):
            self.run(lambda: self.api.get("/devices/connected"), lambda c: (setattr(self, "connected", c.get("connected", [])), self.conn_badge.setText(f"{len(self.connected)} connected"), self.table.set_rows(self.table.rows)))
