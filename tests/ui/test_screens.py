"""Every screen refreshes against the real backend without errors and exposes its key widgets."""

from __future__ import annotations

import pytest
from sellagent_desktop.api_client import wait_for_idle as wait_idle

pytestmark = pytest.mark.ui

KEY_WIDGETS = {
    "setup": ["grid"], "models": ["catalog_table", "ack", "pull_btn"], "dashboard": ["chart", "cards", "donut", "ai_rows", "recent", "device_grid"], "contacts": ["table", "search", "new_btn", "filter_chips"],
    "contact_detail": ["tabs", "empty", "avatar", "stage_combo", "msg_btn"], "import_export": ["map_table", "dup_policy", "commit_btn"], "campaigns": ["table", "detail"], "eligibility": ["contact", "banner"],
    "call_queue": ["table", "routes_box"], "live_call": ["picker", "state_lbl", "agent_line", "utterance", "mute_btn", "mode_chip"], "call_history": ["table", "outcome"], "diagnostics": ["tabs", "sim_log", "tts_text"],
    "knowledge": ["table", "query", "approve_btn"], "persona": ["editors", "save_btn", "preview_btn", "sim_log"], "scripts": ["table", "editors"], "followups": ["tree", "views", "day_list"], "analytics": ["chart", "campaign", "reports_table", "gen_btn"], "devices": ["code_lbl", "lan_toggle", "table"], "provider": ["editors", "save_btn", "test_btn", "status"],
    "audio_tests": ["table", "gate_lbl", "history"], "suppression": ["table", "check_edit"], "settings": ["editors", "save_btn"], "backup": ["table"], "logs": ["health", "log_view", "audit"], "profile": ["name_lbl", "operator"], "users": ["table", "matrix", "new_btn"], "workers": ["table", "ai_grid", "run_btn"],
}


def test_all_screens_registered_and_reachable(window):
    from sellagent_desktop.screens import NAV_GROUPS, SCREEN_SPECS

    assert len(SCREEN_SPECS) == 27  # + Telephony provider configuration
    assert [label for _, label, _ in NAV_GROUPS] == ["Dashboard", "Contacts", "Campaigns", "Call Console", "Follow-ups", "Reports", "Knowledge Base", "AI Settings", "Devices", "System Status", "Settings"]
    grouped = [k for _, _, keys in NAV_GROUPS for k in keys]
    assert sorted(grouped) == sorted(k for k, *_ in SCREEN_SPECS)
    assert set(window.screens) == {k for k, *_ in SCREEN_SPECS}
    assert set(KEY_WIDGETS) == set(window.screens)


@pytest.mark.parametrize("key", list(KEY_WIDGETS))
def test_screen_refreshes_without_error(window, key):
    window.navigate(key)
    assert wait_idle(), f"{key} did not become idle"
    screen = window.screens[key]
    assert window.nav_button_for(key).isChecked()
    assert screen.isVisibleTo(window)
    assert screen.last_error is None, f"{key}: {screen.last_error}"
    assert screen.title_lbl.text() == screen.title
    for attr in KEY_WIDGETS[key]:
        assert hasattr(screen, attr), f"{key} missing widget {attr}"


def test_theme_is_brand_qss_verbatim(qapp, window):
    from sellagent_desktop import paths

    qss = paths.theme_qss_path().read_text(encoding="utf-8")
    assert "#0B0B0B" in qss and "#D4AF37" in qss and "#F7F6F2" in qss
    assert window.findChild(type(window.search), "Search") is window.search
    assert window.search.placeholderText().startswith("Search contacts, campaigns, or enter a number")
    assert qss in qapp.styleSheet()  # loaded verbatim, supplement appended after it
    assert "Noto Sans Devanagari" in qapp.font().families() or "Noto Sans Devanagari" in qss


def test_status_bar_and_live_link(window, qapp):
    import time

    deadline = time.time() + 8
    while time.time() < deadline and not window.ctx.ws.is_connected:
        qapp.processEvents()
        time.sleep(0.05)
    assert window.ctx.ws.is_connected
    wait_idle()
    assert "backend:" in window.backend_lbl.text() and "ok" in window.backend_lbl.text()
    assert window.backend_chip.text() == "Backend: Running"
    assert window.ai_chip.text() == "Local AI: Offline"  # no LLM in tests -> must not claim Online
    assert window.device_chip.text() == "Phone: not paired"
    assert window.ai_card.property("role") == "card-dark"
    assert "devices connected" in window.devices_lbl.text()
    assert window.stop_btn.property("role") == "danger"


def test_dashboard_honest_values(window):
    window.navigate("dashboard")
    wait_idle()
    d = window.screens["dashboard"]
    assert d.greeting.text().endswith("!") and "Good" in d.greeting.text()
    assert d.ready_lbl.text() == "Local AI not available — human-assisted mode"
    assert d.ai_rows["LLM"].text() == "Not available"
    assert "Not paired" in [w.text() for w in d.device_grid.findChildren(type(d.greeting))]
    assert "vs last week" not in " ".join(w.text() for w in d.findChildren(type(d.greeting)))


def test_route_badges_show_autonomous_not_supported(window):
    window.navigate("call_queue")
    wait_idle()
    s = window.screens["call_queue"]
    texts = []
    for i in range(s.routes_box.count()):
        w = s.routes_box.itemAt(i).widget()
        if w is not None:
            texts += [c.text() for c in w.findChildren(type(s.elig_banner))]
    assert any("autonomous: NOT SUPPORTED (release gate closed)" in t for t in texts)


def test_settings_autonomous_toggle_disabled_when_gate_closed(window):
    window.navigate("settings")
    wait_idle()
    s = window.screens["settings"]
    w = s.editors["calling.autonomous_enabled"]
    assert not w.isEnabled()
    assert "release gate" in w.toolTip().lower()


def test_simulation_panel_badged(window):
    window.navigate("diagnostics")
    wait_idle()
    s = window.screens["diagnostics"]
    badges = [lbl for lbl in s.findChildren(type(s.sim_state)) if lbl.property("role") == "badge-mock"]
    assert any(b.text() == "SIMULATION" for b in badges)
    assert any("SIMULATED LOOPBACK" in b.text() for b in badges)
